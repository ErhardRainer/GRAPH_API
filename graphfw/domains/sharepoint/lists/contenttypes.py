# -*- coding: utf-8 -*-
"""
SharePoint: lists.contenttypes.list_df

Listet die Content Types einer SharePoint-Liste via Microsoft Graph.

Naming schema: sharepoint.lists.contenttypes.list_df

Rückgabeformat:
    (df, info) – df hat deterministische Spaltenreihenfolge.

Changelog
---------
v1.0.0 (2025-09-14)
    - Erste Version: Paging, Diagnostics, deterministische Spalten.

Author: graphfw maintainers
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit, urlparse, quote

import pandas as pd

from graphfw.core.http import GraphClient
from graphfw.core.logbuffer import LogBuffer  # optional


__version__ = "1.0.0"


def list_df(
    gc: GraphClient,
    *,
    site_url: str,
    list_title: str,
    page_size: int = 200,
    timeout: Optional[int] = 60,
    log: Optional[LogBuffer] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Listet Content Types einer Liste.

    Parameters
    ----------
    gc : GraphClient
    site_url : str
        https://tenant.sharepoint.com/sites/YourSite
    list_title : str
        Anzeigename der Liste.
    page_size : int, default 200
        $top-Hinweis für die erste Seite.
    timeout : int, optional
    log : LogBuffer, optional

    Returns
    -------
    (df, info)
        df Spalten: ['id','name','description','group','hidden','readOnly','sealed']
    """
    def _normalize_site(site: str) -> Tuple[str, str, str]:
        u = urlsplit(site.rstrip("/"))
        base_url = f"{u.scheme}://{u.netloc}"
        site_path_graph = u.path.lstrip("/")
        return base_url, u.path, site_path_graph

    def _url(hostname: str, site_path_graph: str, list_title_: str) -> str:
        base = f"sites/{hostname}:/{site_path_graph}:/lists/{quote(list_title_)}"
        return f"https://graph.microsoft.com/v1.0/{base}/contentTypes"

    warnings: List[str] = []

    base_url, _, site_path_graph = _normalize_site(site_url)
    hostname = urlparse(base_url).netloc
    url = _url(hostname, site_path_graph, list_title)

    items: List[Dict[str, Any]] = []
    next_url: Optional[str] = url
    params = {"$top": int(page_size)}
    while next_url:
        j = gc.get_json(next_url, params=params if next_url == url else None, timeout=timeout)
        items.extend(j.get("value", []))
        next_url = j.get("@odata.nextLink")
        params = None

    rows: List[Dict[str, Any]] = []
    for ct in items:
        rows.append({
            "id": ct.get("id"),
            "name": ct.get("name"),
            "description": ct.get("description"),
            "group": ct.get("group"),
            "hidden": ct.get("hidden"),
            "readOnly": ct.get("readOnly"),
            "sealed": ct.get("sealed"),
        })

    df = pd.DataFrame(rows, columns=["id","name","description","group","hidden","readOnly","sealed"])

    if log is not None:
        try:
            log.to_df("sharepoint.lists.contenttypes", df.head(20))
        except Exception:
            pass

    info: Dict[str, Any] = {
        "url": url,
        "params": {"$top": page_size},
        "count": len(rows),
        "warnings": warnings,
        "resolution": {
            "hostname": hostname,
            "site_path_graph": site_path_graph,
            "list_title": list_title,
        },
        "module_version": __version__,
    }
    return df, info
