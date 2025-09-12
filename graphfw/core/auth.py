# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.auth — MSAL-basierte Authentifizierung für Microsoft Graph
===============================================================================
Zweck:
    - Kapselt den Client-Credentials-Flow (Application Permissions) via MSAL.
    - Bietet bequeme Fabrikmethoden:
        • from_json / from_dict / from_values (alias: from_client_credentials)
        • from_env (ENV: GRAPH_TENANT_ID / GRAPH_CLIENT_ID / GRAPH_CLIENT_SECRET)
    - Nutzt einen (optional persistenten) Token-Cache; Wiederverwendung der
      ConfidentialClientApplication-Instanz zur Reduktion von Roundtrips.

Design-Notizen:
    - Geheimnisse werden in __repr__/Fehlern nicht ausgegeben.
    - Standard-Scope ist "https://graph.microsoft.com/.default".
    - Für Delegated- oder OBO-Flows wäre eine Erweiterung nötig; hier Fokus App-Flow.

Abhängigkeiten:
    pip install msal

Beispiel:
    from graphfw.core.auth import TokenProvider
    tp = TokenProvider.from_json("config.json")  # erwartet azuread.tenant_id etc.
    token = tp.get_access_token()                # Standard-Scope (.default)

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 1.3.0 (2025-09-12)

Änderungsprotokoll
------------------
2025-09-12 - ER - Ergänzt: from_env(); get_access_token/get_token unterstützen optionalen Status-Rückgabemodus (token, succeeded, error_message).
2025-09-12 - ER - Version-Attribut hinzugefügt: TokenProvider.__version__ und Modul-__version__.
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Union, Dict, Any, Tuple, overload
import json
import os
import threading

import msal

# Modulweite Version (kann separat abgefragt werden: graphfw.core.auth.__version__)
__version__ = "1.3.0"

_GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"


def _ensure_scopes(scopes: Optional[Union[str, Iterable[str]]]) -> List[str]:
    """
    Normalisiert 'scopes' zu einer Liste. Leerer/None-Input → Graph .default.
    """
    if scopes is None:
        return [_GRAPH_DEFAULT_SCOPE]
    if isinstance(scopes, str):
        scopes = [scopes]
    # trim + drop empty
    return [s.strip() for s in scopes if str(s).strip()]


@dataclass
class TokenProvider:
    """
    Dünner Wrapper um MSAL ConfidentialClientApplication (Client-Credentials).

    Cache-Hinweise
    --------------
    - MSAL verwaltet einen Token-Cache; wir können optional einen persistenten
      Cache via 'cache_path' nutzen (SerializableTokenCache).
    - Prozessweit halten wir _cca (ConfidentialClientApplication) und optional
      _cache (SerializableTokenCache) und schützen Zugriffe mit einem Lock.

    Thread-Sicherheit
    -----------------
    - get_access_token() ist mit einem Lock geschützt, da MSAL bei parallelem
      Zugriff auf dieselbe CCA-Instanz nicht strikt threadsicher sein muss.
    """

    # Klassenweite Version (abfragbar via TokenProvider.__version__)
    __version__ = __version__

    tenant_id: str
    client_id: str
    client_secret: str
    authority_base: str = "https://login.microsoftonline.com"
    cache_path: Optional[Union[str, Path]] = None

    _cache: Optional[msal.SerializableTokenCache] = field(default=None, init=False, repr=False)
    _cca: Optional[msal.ConfidentialClientApplication] = field(default=None, init=False, repr=False)
    _lock: threading.RLock = field(default_factory=threading.RLock, init=False, repr=False)

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
        """
        Direkte Initialisierung aus Einzelwerten.
        """
        return cls(
            tenant_id=str(tenant_id).strip(),
            client_id=str(client_id).strip(),
            client_secret=str(client_secret).strip(),
            cache_path=Path(cache_path) if cache_path else None,
        )

    # Alias passend zur früheren API
    @classmethod
    def from_client_credentials(cls, tenant_id: str, client_id: str, client_secret: str,
                                cache_path: Optional[Union[str, Path]] = None) -> "TokenProvider":
        return cls.from_values(tenant_id, client_id, client_secret, cache_path)

    @classmethod
    def from_env(cls, prefix: str = "GRAPH_", *, cache_path: Optional[Union[str, Path]] = None) -> "TokenProvider":
        """
        Erwartete Variablen:
        - GRAPH_TENANT_ID
        - GRAPH_CLIENT_ID
        - GRAPH_CLIENT_SECRET
        Optional: cache_path (Argument)
        """
        tid = os.getenv(f"{prefix}TENANT_ID", "").strip()
        cid = os.getenv(f"{prefix}CLIENT_ID", "").strip()
        sec = os.getenv(f"{prefix}CLIENT_SECRET", "")
        if not (tid and cid and sec):
            raise ValueError(f"Environment variables {prefix}TENANT_ID/_CLIENT_ID/_CLIENT_SECRET required.")
        return cls.from_values(tid, cid, sec, cache_path=cache_path)

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
                p = Path(self.cache_path)
                if p.exists():
                    cache.deserialize(p.read_text())
            except Exception:
                # Cache nicht lesbar => ignorieren (neu beginnen)
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

    # ------------------------------ Hauptmethoden -----------------------------
    # Overloads: wahlweise str oder Tuple[str, bool, str] zurückgeben
    @overload
    def get_access_token(
        self,
        scopes: Optional[Union[str, Iterable[str]]] = None,
        *,
        force_refresh: bool = False,
        return_status: False = False,
    ) -> str: ...
    @overload
    def get_access_token(
        self,
        scopes: Optional[Union[str, Iterable[str]]] = None,
        *,
        force_refresh: bool = False,
        return_status: True = True,
    ) -> Tuple[str, bool, str]: ...

    def get_access_token(
        self,
        scopes: Optional[Union[str, Iterable[str]]] = None,
        *,
        force_refresh: bool = False,
        return_status: bool = False,
    ):
        """
        Holt ein Access Token (Client Credentials Flow).

        Parameter:
            scopes: Liste oder String (Default: Graph .default)
            force_refresh: Wenn True, erzwingt neuen Erwerb (umgeht Cache).
            return_status: Wenn True, wird `(token, succeeded, error_message)` zurückgegeben
                           statt nur `token`. Bei Erfolg: succeeded=True, error_message="".

        Rückgabe:
            - Standard: Bearer Access Token (str)
            - Mit return_status=True: Tuple[str token_or_empty, bool succeeded, str error_message]

        Raises:
            RuntimeError bei Fehlern (nur im Standardmodus ohne return_status=True)
        """
        scopes = _ensure_scopes(scopes)
        try:
            with self._lock:
                self._ensure_app()
                result = self._cca.acquire_token_for_client(
                    scopes=scopes, force_refresh=bool(force_refresh)
                )
                self._persist_cache_if_needed()
            if "access_token" not in result:
                # Nur sichere Felder durchreichen
                err = {
                    "error": result.get("error"),
                    "error_description": result.get("error_description"),
                    "correlation_id": result.get("correlation_id"),
                }
                if return_status:
                    return ("", False, f"Token acquisition failed: {err}")
                raise RuntimeError(f"Token acquisition failed: {err}")

            token = str(result["access_token"])
            if return_status:
                return (token, True, "")
            return token

        except Exception as ex:
            # Fehlerpfad nur für return_status=True abfangen; ansonsten erneut werfen
            if return_status:
                return ("", False, f"{type(ex).__name__}: {ex}")
            raise

    # Bequemer Alias auf das modernere Naming in unserer Codebase
    @overload
    def get_token(self, scopes: Optional[Union[str, Iterable[str]]] = None, *, return_status: False = False) -> str: ...
    @overload
    def get_token(self, scopes: Optional[Union[str, Iterable[str]]] = None, *, return_status: True = True) -> Tuple[str, bool, str]: ...
    def get_token(self, scopes: Optional[Union[str, Iterable[str]]] = None, *, return_status: bool = False):
        """
        Alias für get_access_token(scopes). Unterstützt denselben Status-Rückgabemodus.
        """
        return self.get_access_token(scopes=scopes, return_status=return_status)

    # --------------------------------- Repr -----------------------------------

    def __repr__(self) -> str:
        sid = (self.client_id[:6] + "…") if self.client_id else "?"
        return f"TokenProvider(tenant_id='{self.tenant_id}', client_id='{sid}', cache_path={self.cache_path})"


__all__ = ["TokenProvider", "__version__"]
