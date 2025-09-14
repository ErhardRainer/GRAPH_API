"""
graphfw.domains.sharepoint.sites.lists
======================================

Liste alle SharePoint-Listen eines Sites über Microsoft Graph.

Funktion(en)
------------
- `list_df(gc, site, *, top=None)`:
  Liefert `(df, info)` mit den Spalten `['id', 'name', 'description', 'url']`.

Versionierung
-------------
- 0.2.0 (2025-09-14)
  * Modul neu unter `domains/sharepoint/sites/lists.py`, um bestehendes `__init__.py` nicht zu überschreiben.
  * Unveränderte Funktionalität gegenüber Erstversion: Selektiert Felder `id,name,description,webUrl`.
  * Verbesserte Site-Segment-Logik; robust gegen URL/ID/Segment.
  * Diagnostics in `info` erweitert (`count`, `warnings`).

- 0.1.0 (2025-09-14)
  * Erstveröffentlichung: Ermittelt alle Listen eines Sites (id, name, description, url).
  * Paginierung via `@odata.nextLink`, deterministische Spaltenreihenfolge, OData `$select`.

Hinweise
--------
- **HTTP** ausschließlich über `GraphClient` (autom. Retry/Backoff/Paging).
- **OData** via `OData(select=...)`.
- Rückgabe stets `(df, info)`:
  * `df`: `pandas.DataFrame` mit deterministischer Spaltenreihenfolge.
  * `info`: `dict` mit `url`, `params`, `attempt`, `retries`, `warnings`, `count`.
- Keine Ausgabe von Secrets.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import pandas as pd

from graphfw.core.http import GraphClient
from graphfw.core.odata import OData  # vorhanden im Framework

__all__ = ["list_df", "__version__"]
__version__ = "0.2.0"


def list_df(
    gc: GraphClient,
    site: str,
    *,
    top: Optional[int] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Liste alle SharePoint-Listen eines Sites.

    Es werden die Felder `id`, `name`, `description`, `url` (aus `webUrl`) zurückgegeben.
    Die Zeilen werden in der vom Graph gelieferten Reihenfolge übernommen; die Spalten sind
    deterministisch angeordnet. Paginierung über `@odata.nextLink` wird automatisch
    abgearbeitet. Optional kann clientseitig über `top` begrenzt werden.

    Parameters
    ----------
    gc : GraphClient
        Authentifizierter Graph-HTTP-Client (Retry/Backoff/Paging via Framework).
    site : str
        Site-Identifikation (eine der folgenden Formen):
          - Vollständige Web-URL: ``https://<tenant>.sharepoint.com/sites/<pfad>``
          - Site-ID (GUID oder zusammengesetzte ID)
          - Bereits fertiges Graph-Segment, das mit ``sites/`` beginnt.
    top : int, optional (keyword-only)
        Clientseitiges Limit der maximal zurückzugebenden Einträge.

    Returns
    -------
    (df, info) : Tuple[pandas.DataFrame, dict]
        df
            DataFrame mit Spalten: ``['id', 'name', 'description', 'url']``.
        info
            Diagnostik-Informationen:
              - ``url``: aufgerufene Basis-URL (ohne Query).
              - ``params``: verwendete OData-Parameter (z. B. ``{"$select": "id,name,..."}``).
              - ``attempt``: Anzahl der Versuche (falls vom Client bereitgestellt).
              - ``retries``: Anzahl/Schätzung von Retries (falls verfügbar).
              - ``warnings``: Liste von Warnhinweisen (Strings).
              - ``count``: Anzahl der gelieferten Zeilen.

    Raises
    ------
    RuntimeError
        Bei nicht auflösbarem `site` oder unerwarteter Antwortstruktur.

    Examples
    --------
    >>> df, info = list_df(gc, site="https://contoso.sharepoint.com/sites/HR")
    >>> df.columns.tolist()
    ['id', 'name', 'description', 'url']
    """
    # --- lokale Hilfsfunktionen ----------------------------------------------------------
    def _normalize_site_to_segment(s: str) -> str:
        """
        Erzeugt ein `sites/...`-Segment für Microsoft Graph aus der Eingabe `site`.

        Unterstützt:
          - Voll-URL: https://<host>/sites/<path>  ->  sites/<host>:/sites/<path>:
          - Bereits fertiges Segment beginnend mit 'sites/'
          - Sonst: Annahme Site-ID -> 'sites/{s}'
        """
        s = s.strip()
        if not s:
            raise RuntimeError("Parameter 'site' darf nicht leer sein.")

        if s.startswith("sites/"):
            return s  # bereits korrektes Segment

        if s.startswith("http://") or s.startswith("https://"):
            parts = urlparse(s)
            host = parts.netloc
            path = parts.path or ""
            if not host:
                raise RuntimeError(f"Ungültige Site-URL: {s!r} (kein Host ermittelbar)")
            if path and not path.startswith("/"):
                path = "/" + path
            # root-site -> sites/{host}:  |  sonst: sites/{host}:{/sites/<path>}:
            return f"sites/{host}:" + (f"{path}:" if path else "")

        # Annahme: Site-ID
        return f"sites/{s}"

    def _iter_pages(start_url: str, params: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Holt alle Seiten und sammelt die 'value'-Elemente in einer Liste.
        Bricht ab, wenn `top` erreicht ist.
        """
        collected: List[Dict[str, Any]] = []
        url = start_url
        first = True
        while url:
            payload = gc.get(url, params=params if first else None)
            first = False
            if not isinstance(payload, dict):
                raise RuntimeError("Unerwartete Antwortstruktur vom GraphClient (erwarte dict/JSON).")
            page_items = payload.get("value", [])
            if not isinstance(page_items, list):
                raise RuntimeError("Unerwartete Antwortstruktur: Feld 'value' fehlt oder ist kein Array.")
            collected.extend(page_items)
            if top is not None and len(collected) >= top:
                return collected[:top]
            url = payload.get("@odata.nextLink") or None
        return collected

    def _to_df(items: List[Dict[str, Any]]) -> pd.DataFrame:
        """
        Extrahiert die Zielspalten und baut einen DataFrame in deterministischer Reihenfolge.
        """
        rows = [
            {
                "id": it.get("id"),
                "name": it.get("name"),
                "description": it.get("description"),
                "url": it.get("webUrl"),
            }
            for it in items
        ]
        return pd.DataFrame.from_records(rows, columns=["id", "name", "description", "url"])

    # --- Hauptlogik ----------------------------------------------------------------------
    warnings: List[str] = []

    # 1) Site-Segment auflösen
    try:
        site_segment = _normalize_site_to_segment(site)
    except Exception as ex:
        raise RuntimeError(f"Site konnte nicht aufgelöst werden: {ex}") from ex

    # 2) URL + OData-Select
    base_url = f"/v1.0/{site_segment}/lists"
    odata = OData(select=["id", "name", "description", "webUrl"])
    params: Dict[str, Any] = odata.as_params()

    # 3) Paginierung/Abholung
    items = _iter_pages(base_url, params)

    # 4) DataFrame bauen
    df = _to_df(items)

    # 5) Diagnostics (abhängig von GraphClient-Implementation)
    attempt = getattr(gc, "last_attempt_count", None)
    retries = getattr(gc, "last_retry_count", None)
    info: Dict[str, Any] = {
        "url": base_url,
        "params": params,
        "attempt": attempt,
        "retries": retries,
        "warnings": warnings,
        "count": int(len(df)),
        "module_version": __version__,
    }

    return df, info
