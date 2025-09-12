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
    - Optional persistenter Token-Cache; Wiederverwendung der MSAL-CCA-Instanz.

Design-Notizen:
    - Geheimnisse werden in __repr__/Fehlern nicht ausgegeben.
    - Standard-Scope ist "https://graph.microsoft.com/.default".
    - Fokus: App-Only (Client Credentials). Delegated/OBO wäre Erweiterung.

Abhängigkeiten:
    pip install msal

Beispiel:
    from graphfw.core.auth import TokenProvider
    tp = TokenProvider.from_json("config.json")
    token = tp.get_access_token()  # Standard-Scope (.default)

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 1.4.1 (2025-09-12)

Änderungsprotokoll
------------------
2025-09-12 - ER - Ergänzt: from_env(); Status-Rückgaben für Fabriken & Token (return_status=True).
2025-09-12 - ER - Version-Attribut hinzugefügt: TokenProvider.__version__ und Modul-__version__.
2025-09-12 - ER - Fix: force_refresh wird nicht mehr an MSAL übergeben. Echte Erneuerung
                       via kurzlebiger cacheloser MSAL-App (kein ValueError mehr).
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

# Modulweite Version
__version__ = "1.4.1"

_GRAPH_DEFAULT_SCOPE = "https://graph.microsoft.com/.default"


def _ensure_scopes(scopes: Optional[Union[str, Iterable[str]]]) -> List[str]:
    if scopes is None:
        return [_GRAPH_DEFAULT_SCOPE]
    if isinstance(scopes, str):
        scopes = [scopes]
    return [s.strip() for s in scopes if str(s).strip()]


@dataclass
class TokenProvider:
    """
    Wrapper um MSAL ConfidentialClientApplication (Client-Credentials).
    """

    # Klassenweite Version
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
    @overload
    @classmethod
    def from_json(cls, config_path: Union[str, Path], section: str = "azuread") -> "TokenProvider": ...
    @overload
    @classmethod
    def from_json(cls, config_path: Union[str, Path], section: str = "azuread",
                  *, return_status: True) -> Tuple[Optional["TokenProvider"], bool, str]: ...

    @classmethod
    def from_json(cls, config_path: Union[str, Path], section: str = "azuread",
                  *, return_status: bool = False):
        try:
            path = Path(config_path)
            if not path.exists():
                raise FileNotFoundError(f"Config file not found: {path}")
            cfg = json.loads(path.read_text(encoding="utf-8"))
            if section not in cfg:
                raise KeyError(f"Section '{section}' not found in {path}")
            a = cfg[section]
            prov = cls.from_dict(a)
            if return_status:
                return (prov, True, "")
            return prov
        except Exception as ex:
            if return_status:
                return (None, False, f"{type(ex).__name__}: {ex}")
            raise

    @overload
    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "TokenProvider": ...
    @overload
    @classmethod
    def from_dict(cls, d: Dict[str, Any], *, return_status: True) -> Tuple[Optional["TokenProvider"], bool, str]: ...

    @classmethod
    def from_dict(cls, d: Dict[str, Any], *, return_status: bool = False):
        try:
            prov = cls.from_values(
                tenant_id=d["tenant_id"],
                client_id=d["client_id"],
                client_secret=d["client_secret"],
                cache_path=d.get("cache_path"),
            )
            if return_status:
                return (prov, True, "")
            return prov
        except Exception as ex:
            if return_status:
                return (None, False, f"{type(ex).__name__}: {ex}")
            raise

    @overload
    @classmethod
    def from_values(cls, tenant_id: str, client_id: str, client_secret: str,
                    cache_path: Optional[Union[str, Path]] = None) -> "TokenProvider": ...
    @overload
    @classmethod
    def from_values(cls, tenant_id: str, client_id: str, client_secret: str,
                    cache_path: Optional[Union[str, Path]] = None, *,
                    return_status: True) -> Tuple[Optional["TokenProvider"], bool, str]: ...

    @classmethod
    def from_values(
        cls,
        tenant_id: str,
        client_id: str,
        client_secret: str,
        cache_path: Optional[Union[str, Path]] = None,
        *,
        return_status: bool = False,
    ):
        try:
            prov = cls(
                tenant_id=str(tenant_id).strip(),
                client_id=str(client_id).strip(),
                client_secret=str(client_secret).strip(),
                cache_path=Path(cache_path) if cache_path else None,
            )
            if return_status:
                return (prov, True, "")
            return prov
        except Exception as ex:
            if return_status:
                return (None, False, f"{type(ex).__name__}: {ex}")
            raise

    @overload
    @classmethod
    def from_client_credentials(cls, tenant_id: str, client_id: str, client_secret: str,
                                cache_path: Optional[Union[str, Path]] = None) -> "TokenProvider": ...
    @overload
    @classmethod
    def from_client_credentials(cls, tenant_id: str, client_id: str, client_secret: str,
                                cache_path: Optional[Union[str, Path]] = None, *,
                                return_status: True) -> Tuple[Optional["TokenProvider"], bool, str]: ...

    @classmethod
    def from_client_credentials(cls, tenant_id: str, client_id: str, client_secret: str,
                                cache_path: Optional[Union[str, Path]] = None, *,
                                return_status: bool = False):
        return cls.from_values(tenant_id, client_id, client_secret, cache_path, return_status=return_status)

    @overload
    @classmethod
    def from_env(cls, prefix: str = "GRAPH_", *, cache_path: Optional[Union[str, Path]] = None) -> "TokenProvider": ...
    @overload
    @classmethod
    def from_env(cls, prefix: str = "GRAPH_", *, cache_path: Optional[Union[str, Path]] = None,
                 return_status: True) -> Tuple[Optional["TokenProvider"], bool, str]: ...

    @classmethod
    def from_env(cls, prefix: str = "GRAPH_", *, cache_path: Optional[Union[str, Path]] = None,
                 return_status: bool = False):
        try:
            tid = os.getenv(f"{prefix}TENANT_ID", "").strip()
            cid = os.getenv(f"{prefix}CLIENT_ID", "").strip()
            sec = os.getenv(f"{prefix}CLIENT_SECRET", "")
            if not (tid and cid and sec):
                raise ValueError(f"Environment variables {prefix}TENANT_ID/_CLIENT_ID/_CLIENT_SECRET required.")
            prov = cls.from_values(tid, cid, sec, cache_path=cache_path)
            if return_status:
                return (prov, True, "")
            return prov
        except Exception as ex:
            if return_status:
                return (None, False, f"{type(ex).__name__}: {ex}")
            raise

    # --------------------------------- Utils ----------------------------------
    @property
    def authority(self) -> str:
        return f"{self.authority_base.rstrip('/')}/{self.tenant_id}"

    def _ensure_app(self) -> None:
        if self._cca is not None:
            return
        cache = None
        if self.cache_path:
            cache = msal.SerializableTokenCache()
            try:
                p = Path(self.cache_path)
                if p.exists():
                    cache.deserialize(p.read_text())
            except Exception:
                cache = msal.SerializableTokenCache()
        self._cache = cache
        self._cca = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=self._cache,
        )

    def _persist_cache_if_needed(self) -> None:
        if self._cache is None or not self.cache_path:
            return
        try:
            if self._cache.has_state_changed:
                p = Path(self.cache_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(self._cache.serialize())
        except Exception:
            pass

    # ------------------------------ Token-Methoden -----------------------------
    def _acquire_token_cacheless(self, scopes: List[str]) -> Dict[str, Any]:
        """Erzwingt einen neuen Token, indem eine MSAL-CCA ohne Cache verwendet wird."""
        tmp_app = msal.ConfidentialClientApplication(
            client_id=self.client_id,
            authority=self.authority,
            client_credential=self.client_secret,
            token_cache=None,  # kritisch: kein Cache -> kein force_refresh nötig
        )
        return tmp_app.acquire_token_for_client(scopes=scopes)

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

        - force_refresh=True: Cache wird umgangen (cachelose CCA).
        - return_status=True: gibt (token|"" , succeeded: bool, error_message: str) zurück.
        """
        scopes = _ensure_scopes(scopes)
        try:
            if force_refresh:
                result = self._acquire_token_cacheless(scopes)
            else:
                with self._lock:
                    self._ensure_app()
                    # ACHTUNG: kein force_refresh-Parameter hier!
                    result = self._cca.acquire_token_for_client(scopes=scopes)
                    self._persist_cache_if_needed()

            if "access_token" not in result:
                err = {
                    "error": result.get("error"),
                    "error_description": result.get("error_description"),
                    "correlation_id": result.get("correlation_id"),
                }
                if return_status:
                    return ("", False, f"Token acquisition failed: {err}")
                raise RuntimeError(f"Token acquisition failed: {err}")

            token = str(result["access_token"])
            return (token, True, "") if return_status else token

        except Exception as ex:
            if return_status:
                return ("", False, f"{type(ex).__name__}: {ex}")
            raise

    @overload
    def get_token(self, scopes: Optional[Union[str, Iterable[str]]] = None, *, return_status: False = False) -> str: ...
    @overload
    def get_token(self, scopes: Optional[Union[str, Iterable[str]]] = None, *, return_status: True = True) -> Tuple[str, bool, str]: ...
    def get_token(self, scopes: Optional[Union[str, Iterable[str]]] = None, *, return_status: bool = False):
        return self.get_access_token(scopes=scopes, return_status=return_status)

    # --------------------------------- Repr -----------------------------------
    def __repr__(self) -> str:
        sid = (self.client_id[:6] + "…") if self.client_id else "?"
        return f"TokenProvider(tenant_id='{self.tenant_id}', client_id='{sid}', cache_path={self.cache_path})"


__all__ = ["TokenProvider", "__version__"]
