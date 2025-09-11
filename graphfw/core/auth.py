# auth.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.auth — MSAL-basierte Authentifizierung für Microsoft Graph
===============================================================================
Zweck:
    - Kapselt den Client-Credentials-Flow (Application Permissions) via MSAL.
    - Bietet bequeme Fabrikmethoden (from_json / from_dict / from_values).
    - Nutzt einen (optional persistenten) Token-Cache; Wiederverwendung der
      ConfidentialClientApplication-Instanz zur Reduktion von Roundtrips.

Abhängigkeiten:
    pip install msal

Beispiel:
    from graphfw.core.auth import TokenProvider
    tp = TokenProvider.from_json("config.json")  # erwartet azuread.tenant_id etc.
    token = tp.get_access_token()                # 'https://graph.microsoft.com/.default'

Wichtig:
    - Secrets werden in __repr__ / Logs maskiert.
    - Standard-Scope ist "https://graph.microsoft.com/.default" (Graph v1.0).
    - Für Delegated- oder OBO-Flows wäre eine Erweiterung nötig; hier Fokus App-Flow.

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Union, Dict, Any
import json
import threading

import msal


_GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"


def _ensure_scopes(scopes: Optional[Union[str, Iterable[str]]]) -> List[str]:
    """Normalisiert 'scopes' zu einer Liste."""
    if scopes is None:
        return [_GRAPH_DEFAULT_SCOPE]
    if isinstance(scopes, str):
        scopes = [scopes]
    return list(scopes)


@dataclass
class TokenProvider:
    """
    Dünner Wrapper um MSAL ConfidentialClientApplication.

    Hinweise zum Cache:
        - MSAL verwaltet Caches intern; bei Client-Credentials prüft MSAL vor
          dem Token-Endpunkt die Cache-Hits (abhängig von Scope/Authority).
        - Für Prozess-weite Wiederverwendung halten wir _cca und _cache.
        - Optional: persistenter Cache über 'cache_path'.

    Thread-Sicherheit:
        - get_access_token() schützt den Aufruf mit einem Lock, da MSAL intern
          nicht zwingend threadsicher ist, wenn dieselbe App parallel benutzt wird.
    """
    tenant_id: str
    client_id: str
    client_secret: str
    authority_base: str = "https://login.microsoftonline.com"
    cache_path: Optional[Union[str, Path]] = None

    _cache: Optional[msal.SerializableTokenCache] = field(default=None, init=False, repr=False)
    _cca: Optional[msal.ConfidentialClientApplication] = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    # ------------------------------- Fabriken ---------------------------------

    @classmethod
    def from_json(cls, config_path: Union[str, Path], section: str = "azuread") -> "TokenProvider":
        """
        Lädt azuread-Credentials aus JSON:
        {
          "azuread": {
             "tenant_id": "...",
             "client_id": "...",
             "client_secret": "...",
             "cache_path": "optional/path/to/cache.bin"
          }
        }
        """
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {path}")

        cfg = json.loads(path.read_text(encoding="utf-8"))
        if section not in cfg:
            raise KeyError(f"Section '{section}' not found in {path}")
        a = cfg[section]
        return cls.from_dict(a)

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TokenProvider":
        return cls.from_values(
            tenant_id=d["tenant_id"],
            client_id=d["client_id"],
            client_secret=d["client_secret"],
            cache_path=d.get("cache_path"),
        )

    @classmethod
    def from_values(
        cls,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        cache_path: Optional[Union[str, Path]] = None,
    ) -> "TokenProvider":
        tp = cls(
            tenant_id=tenant_id.strip(),
            client_id=client_id.strip(),
            client_secret=client_secret.strip(),
            cache_path=Path(cache_path) if cache_path else None,
        )
        return tp

    # --------------------------------- Utils ----------------------------------

    @property
    def authority(self) -> str:
        """Komplette Authority-URL inkl. Tenant-ID."""
        return f"{self.authority_base.rstrip('/')}/{self.tenant_id}"

    def _ensure_app(self) -> None:
        """Initialisiert Cache und ConfidentialClientApplication (einmalig)."""
        if self._cca is not None:
            return

        # Optional: persistenten Cache laden
        cache = None
        if self.cache_path:
            cache = msal.SerializableTokenCache()
            try:
                if Path(self.cache_path).exists():
                    cache.deserialize(Path(self.cache_path).read_text())
            except Exception:
                # Cache nicht lesbar => ignorieren (wird neu aufgebaut)
                cache = msal.SerializableTokenCache()
        self._cache = cache

        self._cca = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=self._cache,
        )

    def _persist_cache_if_needed(self) -> None:
        """Schreibt den Cache zurück, falls geändert und cache_path gesetzt."""
        if self._cache is None or not self.cache_path:
            return
        try:
            if self._cache.has_state_changed:
                p = Path(self.cache_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(self._cache.serialize())
        except Exception:
            # Cache-Fehler sind nicht kritisch für die Laufzeit.
            pass

    # ------------------------------ Hauptmethode ------------------------------

    def get_access_token(
        self,
        scopes: Optional[Union[str, Iterable[str]]] = None,
        *,
        force_refresh: bool = False,
    ) -> str:
        """
        Holt ein Access Token (Client Credentials Flow).

        Parameter:
            scopes: Liste oder String (Default: Graph .default)
            force_refresh: Wenn True, erzwingt einen neuen Token-Erwerb.

        Rückgabe:
            Bearer Access Token (str)

        Raises:
            RuntimeError bei Fehlern (inkl. MSAL-Fehler-Response)
        """
        scopes = _ensure_scopes(scopes)
        with self._lock:
            self._ensure_app()

            # Für Client-Credentials macht acquire_token_for_client
            # intern eine Cache-Prüfung. force_refresh umgeht ggf. die Cache-Nutzung.
            result = self._cca.acquire_token_for_client(
                scopes=scopes,
                force_refresh=bool(force_refresh),
            )
            # Persistiere ggf. den Cache auf Platte
            self._persist_cache_if_needed()

        if "access_token" not in result:
            raise RuntimeError(f"Token acquisition failed: {result}")
        return result["access_token"]

    # --------------------------------- Repr -----------------------------------

    def __repr__(self) -> str:
        sid = self.client_id[:6] + "…"
        return f"TokenProvider(tenant_id='{self.tenant_id}', client_id='{sid}', cache_path={self.cache_path})"


__all__ = ["TokenProvider"]

