# http.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.http — HTTP-Client für Microsoft Graph (Retry, Paging, OData)
===============================================================================
Zweck:
    - Einheitlicher Zugriff auf Graph-Endpoints mit:
        * Bearer-Auth via TokenProvider
        * Exponentiellem Backoff (429/5xx), Retry-After-Respekt
        * Auto-Paging über @odata.nextLink
        * Optionale ConsistencyLevel-Header (bei $search/$count)
        * Schlanke JSON-Deserialisierung (odata.metadata=none)

    - Methoden:
        * request()    – generisch (GET/POST/…)
        * get_json()   – GET + JSON
        * get_paged()  – Generator über Items (value) oder Seiten

Abhängigkeiten:
    pip install requests

Beispiel:
    from graphfw.core.auth import TokenProvider
    from graphfw.core.http import GraphClient

    tp = TokenProvider.from_json("config.json")
    gc = GraphClient(tp)
    data = gc.get_json("/me")

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

import time
import random
from typing import Any, Dict, Generator, Iterable, Mapping, Optional, Tuple, Union
from urllib.parse import urljoin

import requests


_KNOWN_ODATA_PARAMS = {"$select", "$expand", "$filter", "$orderby", "$top", "$skip", "$count", "$search"}
_JSON_ACCEPT = "application/json;odata.metadata=none"


def _needs_consistency_level(params: Optional[Mapping[str, Any]]) -> bool:
    """Graph verlangt bei $count/$search oft 'ConsistencyLevel: eventual'."""
    if not params:
        return False
    keys = set(params.keys())
    # Falls ohne $ übergeben (z. B. 'search' statt '$search'), berücksichtigen
    if "$count" in keys or "$search" in keys or "count" in keys or "search" in keys:
        return True
    return False


def _normalize_params(params: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    """
    Erlaubt sowohl '$select' als auch 'select' etc.; normalisiert auf '$…'.
    """
    if not params:
        return {}
    out: Dict[str, Any] = {}
    for k, v in params.items():
        if k in _KNOWN_ODATA_PARAMS:
            out[k] = v
        else:
            # 'select' -> '$select' usw., falls bekannt; ansonsten unverändert
            k_norm = f"${k}" if f"${k}" in _KNOWN_ODATA_PARAMS else k
            out[k_norm] = v
    return out


class GraphClient:
    """
    Schlanker Graph-HTTP-Client mit Retry-, Paging- und OData-Unterstützung.

    Hinweis:
        - Basispfad default 'https://graph.microsoft.com/v1.0'.
        - 'path' kann absolut (https://...) oder relativ (/me/messages) sein.
        - Session wird wiederverwendet (Keep-Alive).
    """

    def __init__(
        self,
        token_provider,
        *,
        base: str = "https://graph.microsoft.com/v1.0",
        timeout: int = 60,
        max_retries: int = 5,
        backoff_factor: float = 0.5,
        user_agent: Optional[str] = None,
        session: Optional[requests.Session] = None,
        log: Optional[Any] = None,  # kompatibel zu LogBuffer, aber optional
    ) -> None:
        self.token_provider = token_provider
        self.base = base.rstrip("/") + "/"
        self.timeout = int(timeout)
        self.max_retries = int(max_retries)
        self.backoff_factor = float(backoff_factor)
        self.user_agent = user_agent or "graphfw/1.0 (+https://graph.microsoft.com)"
        self.session = session or requests.Session()
        self.log = log  # sollte .log(level,msg,**ctx) oder .info(...) unterstützen (wenn vorhanden)

    # ------------------------------- Kernaufruf --------------------------------

    def request(
        self,
        method: str,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        json: Optional[Any] = None,
        data: Optional[Any] = None,
        expected: Iterable[int] = (200,),
        timeout: Optional[int] = None,
        consistency_level: Optional[str] = None,
        retry: Optional[int] = None,
    ) -> requests.Response:
        """
        Führt einen HTTP-Request mit Retry-Logik aus.

        - expected: Liste erlaubter Statuscodes (default: 200)
        - consistency_level: z. B. "eventual" (überschreibt Auto-Erkennung)
        - retry: Anzahl Versuche (default: self.max_retries)

        Raises:
            requests.HTTPError (nach Ausschöpfen der Retries)
        """
        url = path_or_url if path_or_url.startswith("http") else urljoin(self.base, path_or_url.lstrip("/"))
        params_norm = _normalize_params(params)
        hdrs = {
            "Authorization": f"Bearer {self.token_provider.get_access_token()}",
            "Accept": _JSON_ACCEPT,
            "User-Agent": self.user_agent,
        }
        if headers:
            hdrs.update(headers)

        # ConsistencyLevel setzen, falls nötig oder explizit gewünscht
        if consistency_level:
            hdrs["ConsistencyLevel"] = consistency_level
        elif _needs_consistency_level(params_norm):
            hdrs["ConsistencyLevel"] = "eventual"

        # Retry-Schleife
        retries_left = self.max_retries if retry is None else int(retry)
        attempt = 0
        last_exc: Optional[Exception] = None

        while True:
            attempt += 1
            try:
                resp = self.session.request(
                    method=method.upper(),
                    url=url,
                    params=params_norm if params_norm else None,
                    headers=hdrs,
                    json=json,
                    data=data,
                    timeout=timeout or self.timeout,
                )
            except Exception as ex:
                last_exc = ex
                if attempt > retries_left:
                    if self.log:
                        try:
                            self.log.error("HTTP request failed (no response)", url=url, method=method, attempt=attempt)
                        except Exception:
                            pass
                    raise
                self._sleep_backoff(attempt, None)
                continue

            if resp.status_code in expected:
                return resp

            # Retry-Kandidat? (429 oder 5xx)
            if resp.status_code in (429, 500, 502, 503, 504) and attempt <= retries_left:
                retry_after = self._parse_retry_after(resp)
                if self.log:
                    try:
                        self.log.warning(
                            "HTTP retry",
                            url=url,
                            method=method,
                            status=resp.status_code,
                            attempt=attempt,
                            retry_after=retry_after,
                        )
                    except Exception:
                        pass
                self._sleep_backoff(attempt, retry_after)
                continue

            # Nicht erfolgreich und kein Retry mehr
            try:
                resp.raise_for_status()
            except Exception as ex:
                if self.log:
                    try:
                        self.log.error("HTTP error", url=url, method=method, status=resp.status_code, text=self._safe_text(resp))
                    except Exception:
                        pass
                raise
            return resp  # falls expected andere Codes enthält (z. B. 204)

    # ------------------------------- Hilfen ------------------------------------

    def get_json(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        headers: Optional[Mapping[str, str]] = None,
        expected: Iterable[int] = (200,),
        timeout: Optional[int] = None,
        consistency_level: Optional[str] = None,
    ) -> Dict[str, Any]:
        """GET + JSON-Decoding (dict)."""
        resp = self.request(
            "GET",
            path_or_url,
            params=params,
            headers=headers,
            expected=expected,
            timeout=timeout,
            consistency_level=consistency_level,
        )
        return resp.json()

    def get_paged(
        self,
        path_or_url: str,
        *,
        params: Optional[Mapping[str, Any]] = None,
        item_path: Optional[str] = "value",
        page_size_hint: Optional[int] = None,
        timeout: Optional[int] = None,
        consistency_level: Optional[str] = None,
    ) -> Generator[Dict[str, Any], None, None]:
        """
        Generator über Items (Standard: 'value') über @odata.nextLink hinweg.

        - item_path: Key im JSON, der eine Liste enthält (None → ganze Seiten yielden)
        - page_size_hint: optionaler $top-Wert für die erste Seite

        Beispiel:
            for item in gc.get_paged("/me/messages", params={"$select":"id,subject"}):
                ...
        """
        params = dict(params or {})
        if page_size_hint and "$top" not in params and "top" not in params:
            params["$top"] = int(page_size_hint)

        url = path_or_url if path_or_url.startswith("http") else urljoin(self.base, path_or_url.lstrip("/"))

        while True:
            j = self.get_json(
                url,
                params=params,
                timeout=timeout,
                consistency_level=consistency_level,
            )
            if item_path is None:
                yield j
            else:
                items = j.get(item_path, [])
                for it in items:
                    yield it

            next_url = j.get("@odata.nextLink")
            if not next_url:
                break
            # nächste Runde: absolute URL, keine params mehr anhängen
            url, params = next_url, {}

    # ------------------------------ interne Utils -----------------------------

    def _parse_retry_after(self, resp: requests.Response) -> Optional[float]:
        """Parst Retry-After (sek.) aus Header; fallback: None."""
        ra = resp.headers.get("Retry-After")
        if not ra:
            return None
        try:
            return float(ra)
        except Exception:
            return None

    def _sleep_backoff(self, attempt: int, retry_after: Optional[float]) -> None:
        """Wartet unter Berücksichtigung von Retry-After und Exponential Backoff."""
        if retry_after is not None:
            time.sleep(max(0.0, retry_after))
            return
        # Exponentielles Backoff + jitter
        delay = self.backoff_factor * (2 ** (attempt - 1))
        delay += random.uniform(0.0, 0.25)  # jitter
        time.sleep(delay)

    @staticmethod
    def _safe_text(resp: requests.Response, limit: int = 500) -> str:
        """Kürzt Response-Text für Logs."""
        try:
            t = resp.text or ""
        except Exception:
            return ""
        return t if len(t) <= limit else t[:limit] + " …"


__all__ = ["GraphClient"]
