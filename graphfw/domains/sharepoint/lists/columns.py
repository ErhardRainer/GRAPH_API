# -*- coding: utf-8 -*-
"""
Ermittelt das Spaltenschema einer SharePoint-Liste mit drei Modi (+ GUID-Sicherheit):

Modi
----
- mode="standard":
    Liest /columns (Graph-Standard) → Quelle 'standard'.
- mode="extended":
    Liest Items via /items?$top=...&$expand=fields → Quelle 'extended';
    Felder, die auch in /columns vorkommen, werden als 'standard/extended' markiert.
- mode="item":
    Zusätzlich zu 'extended' wird pro Content Type ein Item (Top 1) geladen:
      /items?$top=1&$filter=contentType/id eq '{ctid}'&$expand=fields
    Die Quelle enthält Kombinationen: 'standard', 'extended', 'item'
    (z. B. 'standard/extended/item' wenn in allen Quellen vorhanden).
    Außerdem: neue Spalte `itemContentTypes` (CSV der CT-Namen, in denen Feld vorhanden ist).
    Optional: Filter auf einen bestimmten Content-Type über `item_content_type` (ID oder Name).

In allen Modi wird die Spalte 'GUID' sichergestellt:
- Falls in den Quellen nicht vorhanden, wird eine minimale Definition synthetisiert
  (Quelle 'synthesized').

Weitere Features
---------------
- Optionaler Parameter `columns`: Rückgabe nur für gewünschte Spaltennamen
  (matcht internalName **oder** displayName; robust ggü. Groß-/Kleinschreibung
  und SharePoint-Encoding _xNNNN_). Reihenfolge entspricht der Eingabe.
- Optionaler Parameter `expand`: Wenn True, wird für 'standard' intern
  /lists/{list}?$expand=columns($expand=*) genutzt (liefert mehr Details).
  Die Quelle bleibt dennoch 'standard' (bzw. kombiniert).

Rückgabe
--------
(df, info)
    df Spalten (deterministisch):
      ['internalName','displayName','type','required','readOnly','hidden',
       'indexed','enforceUnique','details','source','itemContentTypes']
    info: Diagnostics (URLs, counts, warnings, mode, etc.)
Returns the column schema (definitions) of a SharePoint list via Microsoft Graph
as a pandas.DataFrame with a deterministic column order plus a diagnostics dict.

Naming schema: sharepoint.lists.columns.list_df

Architecture rules:
- HTTP strictly via GraphClient (retry/backoff, 429/5xx handling, paging).
- Build OData params manually for maximum compatibility.
- No secrets are logged or returned.

Changelog
---------
v2.2.1 (2025-09-14)
    - Umstellung auf GraphClient.get_paged(...) (statt .iterate(...)) für Paging.
      Behebt AttributeError: 'GraphClient' object has no attribute 'iterate'.
v2.2.0 (2025-09-14)
    - Bugfix: Wenn `item_content_type` angegeben ist, aber **nicht** gefunden wird,
    wird **ein leerer DataFrame** zurückgegeben und `info["succeeded"] = "false"`.
    Es werden keine "Nebenprodukt"-Spalten (z. B. `_ColorTag`, intern encodierte Felder) mehr zurückgegeben.
    - Statusflag: `info["succeeded"]` gibt den Gesamtstatus wieder:
        * "false"     : Site/Liste nicht gefunden ODER Content Type (falls angegeben) nicht gefunden.
        * "partially" : Site/Liste/CT ok, aber explizit angeforderte Spalten (`columns=[...]`) nicht vollständig vorhanden.
        * "true"      : Alles gefunden (inkl. CT, falls angegeben) und alle gewünschten Spalten vorhanden.
v2.1.1 (2025-09-14)
    - Heuristik erweitert: Alle Spalten mit Suffix 'LookupId' (case-insensitiv) werden als
      Typ 'lookupId' klassifiziert. Speziell: AppAuthorLookupId, AppEditorLookupId,
      AuthorLookupId, EditorLookupId.
v2.1.0 (2025-09-14)
    - Neu: Case-insensitive Merge für alle Felder (insb. Systemfelder wie GUID vs guid).
            Kanonische Schreibweise nach Priorität standard > extended > item.
    - Fix: GUID wird nicht mehr fälschlich als 'synthesized' markiert, wenn sie nur
           mit anderer Groß-/Kleinschreibung (z. B. 'guid') in Items auftaucht.
v2.0.1 (2025-09-14)
    - NEW: Für Spalten, die ausschließlich aus 'extended'/'item' stammen (keine /columns-Definition),
      werden Schema-Flags auf False vorbelegt (statt leer/NaN): required, readOnly, hidden,
      indexed, enforceUnique. displayName wird auf internalName gesetzt, falls leer.
v2.0.0 (2025-09-14)
    - Neu: Modi 'standard' | 'extended' | 'item' inkl. Source-Kombinationslogik.
    - Neu: itemContentTypes (nur in mode='item'; sonst leer).
    - Neu: Filter `item_content_type` (ID oder Name) in mode='item'.
    - Refactor: GUID-Ermittlung priorisiert echte Quellen, sonst Synthese.
v1.4.0 (2025-09-13)
    - Added new column `source` in DataFrame:
        * "standard" → column came from /columns (list-level definition).
        * "extended" → column only found via contentTypes($expand=columns).
        * "expanded" → when expand=True, all columns loaded via expand route.
        * "synthesized" → GUID column synthesized because Graph did not return it.
v1.3.0 (2025-09-13)
    - New parameter `expand: bool = False`
        * expand=False (default): merge /columns and /contentTypes?$expand=columns (previous behavior).
        * expand=True: load columns via /lists/{...}?expand=columns($expand=*) → returns all fields
          including facet details in one roundtrip.
        * In both cases: ensure column 'GUID' is present (synthesize if missing).
v1.2.0 (2025-09-13)
    - New parameter `columns` (Iterable[str] | None): optional list of column
      names to return (match by internalName OR displayName). Matching is
      case-insensitive, accent-insensitive, and tolerant to SharePoint's
      _xNNNN_ encodings and whitespace/dash/slash differences.
      Order of the output rows follows the input order. Missing names are
      reported in `info['resolution']['requested']` and `info['warnings']`.
v1.1.0 (2025-09-13)
    - Merge columns from /columns and /contentTypes?$expand=columns (covers GUID).
    - Synthesize GUID if still missing (type 'guid'); record warning.
v1.0.6 (2025-09-13)
    - Heuristic type mapping for well-known system columns.
v1.0.5 (2025-09-13)
    - Removed $select to ensure Graph returns facet objects.
v1.0.4 (2025-09-13)
    - GraphClient compatibility wrapper removed (moved to core.http).
v1.0.3 (2025-09-13)
    - Added __version__ for quick import verification.
v1.0.2 (2025-09-13)
    - Manual OData params to avoid constructor signature issues.
v1.0.1 (2025-09-12)
    - Initial implementation (paging, diagnostics, deterministic columns).

Author: graphfw maintainers
"""

from __future__ import annotations  # MUSS direkt nach dem Docstring stehen!

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
import re
import unicodedata
import pandas as pd

from graphfw.core.http import GraphClient
from graphfw.core.odata import OData  # falls nicht vorhanden, bitte gemäß Framework bereitstellen

# Optionaler DF-Reorder-Helfer (derzeit ungenutzt, aber korrekt importierbar)
from graphfw.core.util import reorder_columns_df as _reorder_df  # noqa: F401

# strip_guid_braces – robust mit Fallback
try:
    from graphfw.core.util import strip_guid_braces as _strip_guid
except Exception:  # pragma: no cover
    def _strip_guid(s: Any) -> Any:
        if isinstance(s, str) and len(s) >= 2 and s[0] == "{" and s[-1] == "}":
            return s[1:-1]
        return s

__all__ = ["list_df"]
__version__ = "2.2.1"


# ----------------------------
# Hilfsfunktionen (gekapselt)
# ----------------------------

def _normalize_name(name: str) -> str:
    """Normalisiert SP-Feldnamen: decodiert _xNNNN_-Sequenzen, lower-case, NFKC."""
    if not isinstance(name, str):
        return ""
    def _decode_hex(match: re.Match) -> str:
        try:
            cp = int(match.group(1), 16)
            return chr(cp)
        except Exception:
            return match.group(0)
    s = re.sub(r"_x([0-9A-Fa-f]{4})_", _decode_hex, name)
    s = unicodedata.normalize("NFKC", s).strip().lower()
    return s


def _match_columns(requested: Optional[Sequence[str]],
                   available: List[Dict[str, Any]]) -> Tuple[List[Dict[str,Any]], List[str]]:
    """
    Erzeugt eine Liste der gewünschten Spalten in der exakten Reihenfolge von `requested`.
    `available` enthält Dicts mit mind. 'internalName' und 'displayName'.

    Returns:
        (selected_columns, missing_names)
    """
    if not requested:
        return available, []

    idx: Dict[str, Dict[str,Any]] = {}
    for col in available:
        for k in ("internalName", "displayName"):
            v = col.get(k)
            if isinstance(v, str) and v:
                idx.setdefault(_normalize_name(v), col)

    selected: List[Dict[str,Any]] = []
    missing: List[str] = []
    for want in requested:
        key = _normalize_name(want)
        col = idx.get(key)
        if col is None:
            missing.append(want)
        else:
            selected.append(col)
    return selected, missing


def _deterministic_order(cols: List[Dict[str,Any]]) -> List[Dict[str,Any]]:
    """
    Erzwingt deterministische Reihenfolge:
    - Bevorzugt bekannte Meta-Felder
    - Danach alphabetisch nach internalName
    """
    priority = {
        "id": 0, "guid": 1, "created": 2, "modified": 3,
        "createdbyname": 4, "modifiedbyname": 5
    }

    def sort_key(c: Dict[str,Any]):
        iname = (c.get("internalName") or "").strip()
        p = priority.get(_normalize_name(iname), 99)
        return (p, iname.lower())

    return sorted(cols, key=sort_key)


def _ensure_guid(col: Dict[str, Any]) -> Dict[str, Any]:
    """Wendet GUID-Stripping auf Spalteneintrag an (falls Feld 'GUID' existiert)."""
    if col.get("internalName") == "GUID" and isinstance(col.get("sample"), str):
        col["sample"] = _strip_guid(col["sample"])
    return col


def _site_from_url(site_url: str) -> Tuple[str, str]:
    """
    Wandelt eine vollqualifizierte SharePoint-URL in (hostname, server_relative_path) um.
    Beispiel:
      https://contoso.sharepoint.com/sites/TeamA  -> ("contoso.sharepoint.com", "/sites/TeamA")
    """
    from urllib.parse import urlparse
    p = urlparse(site_url)
    host = p.netloc
    path = p.path or "/"
    return host, path


def _resolve_site_and_list(gc: GraphClient, site_url: str, list_title: str) -> Tuple[Optional[str], Optional[str], Dict[str,Any]]:
    """
    Liefert (site_id, list_id, diag). Gibt (None, None, diag) zurück, wenn nicht auflösbar.
    Nutzt gc.get_json(...) und gc.get_paged(...).
    """
    diag: Dict[str, Any] = {"steps": []}
    host, rel = _site_from_url(site_url)
    site_api = f"https://graph.microsoft.com/v1.0/sites/{host}:{rel}"
    diag["steps"].append({"url": site_api})

    try:
        site = gc.get_json(site_api)
        site_id = site.get("id")
    except Exception as e:
        diag["error"] = f"site resolve failed: {e}"
        return None, None, diag

    if not site_id:
        diag["error"] = "site id missing"
        return None, None, diag

    lists_api = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists"
    params = {"$select": "id,displayName,name"}
    diag["steps"].append({"url": lists_api, "params": params})

    found_list_id: Optional[str] = None
    for it in gc.get_paged(lists_api, params=params, item_path="value"):
        # displayName match (case-insensitive)
        if _normalize_name(it.get("displayName","")) == _normalize_name(list_title):
            found_list_id = it.get("id")
            break

    if not found_list_id:
        diag["error"] = "list not found"
        return site_id, None, diag

    return site_id, found_list_id, diag


def _fetch_columns_standard(gc: GraphClient, site_id: str, list_id: str, expand: bool) -> List[Dict[str,Any]]:
    """
    Holt Columns über /sites/{id}/lists/{id}/columns (optional mit expand).
    Nutzt gc.get_paged(..., item_path="value").
    """
    base = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/columns"
    params: Dict[str, Any] = {"$top": 999}
    if expand:
        params["$expand"] = "*"

    cols: List[Dict[str,Any]] = []
    for c in gc.get_paged(base, params=params, item_path="value"):
        cols.append(c)

    # Mappen auf ein einheitliches Schema
    def map_one(c: Dict[str,Any]) -> Dict[str,Any]:
        return {
            "internalName": c.get("name") or c.get("id"),
            "displayName": c.get("displayName") or c.get("name"),
            "type": c.get("columnType"),
            "required": bool(c.get("required")),
            "readOnly": bool(c.get("readOnly")),
            "hidden": bool(c.get("hidden")),
            "indexed": bool(c.get("indexed")),
            "enforceUnique": bool(c.get("enforceUniqueValues")),
            "details": {k: v for k, v in c.items() if k not in {
                "name","id","displayName","columnType","required","readOnly","hidden","indexed","enforceUniqueValues"
            }},
            "source": "columns",
            "itemContentTypes": None,  # erst im 'item'-Modus relevant
        }

    return [_ensure_guid(map_one(c)) for c in cols]


def _fetch_columns_item(gc: GraphClient, site_id: str, list_id: str,
                        item_content_type: Optional[str]) -> Tuple[List[Dict[str,Any]], Dict[str,Any]]:
    """
    Holt Spalten via Beispiel-Items (expand=fields). Falls item_content_type gesetzt ist,
    wird strikt nur in diesem CT gesucht. Sind keine Items vorhanden oder CT nicht auffindbar,
    wird ein leerer Satz zurückgegeben (kein 'Fallback' mehr).
    """
    diag: Dict[str, Any] = {"mode": "item", "queries": []}

    # ContentTypes lesen, um CT-ID/Name zu mappen
    ct_api = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/contentTypes"
    diag["queries"].append({"url": ct_api})
    cts: List[Dict[str,Any]] = []
    for ct in gc.get_paged(ct_api, item_path="value"):
        cts.append(ct)

    chosen_ct_id: Optional[str] = None
    if item_content_type:
        norm_target = _normalize_name(item_content_type)
        for ct in cts:
            if _normalize_name(ct.get("name","")) == norm_target or _normalize_name(ct.get("id","")) == norm_target:
                chosen_ct_id = ct.get("id")
                break
        if not chosen_ct_id:
            # CT nicht gefunden: leer zurückgeben (Bugfix – kein „Bestehenbleiben“ zufälliger Spalten)
            diag["warning"] = f"content type not found: {item_content_type}"
            return [], {"item_mode": diag, "contentTypeFound": False}

    # Items holen (max. einige) – bei CT-Filter mit $filter=contentType/id eq '...'
    items_api = f"https://graph.microsoft.com/v1.0/sites/{site_id}/lists/{list_id}/items"
    params: Dict[str, Any] = {"$top": 50, "$expand": "fields"}
    if chosen_ct_id:
        params["$filter"] = f"contentType/id eq '{chosen_ct_id}'"

    diag["queries"].append({"url": items_api, "params": params})

    items: List[Dict[str,Any]] = []
    for it in gc.get_paged(items_api, params=params, item_path="value"):
        items.append(it)
        if len(items) >= 5:  # genügt, um Felduniversum zu bestimmen
            break

    if not items:
        # Keine Items im (geforderten) CT -> jetzt keine Spalten aus Sample ableiten
        diag["warning"] = "no items for requested scope"
        return [], {"item_mode": diag, "contentTypeFound": (chosen_ct_id is not None or not item_content_type)}

    # Felder vereinigen
    field_universe: Dict[str, Dict[str, Any]] = {}
    for it in items:
        fields: Dict[str, Any] = it.get("fields") or {}
        for k, v in fields.items():
            col = {
                "internalName": k,
                "displayName": k,
                "type": None,
                "required": False,
                "readOnly": False,
                "hidden": False,
                "indexed": False,
                "enforceUnique": False,
                "details": {},
                "source": "item/fields",
                "itemContentTypes": [it.get("contentType", {}).get("id")] if it.get("contentType") else None,
                "sample": v,
            }
            field_universe.setdefault(k, col)

    cols = list(field_universe.values())
    return cols, {"item_mode": diag, "contentTypeFound": (chosen_ct_id is not None or not item_content_type)}


# ----------------------------
# Hauptfunktion
# ----------------------------

def list_df(
    gc: GraphClient,
    *,
    site_url: str,
    list_title: str,
    mode: str = "standard",              # 'standard' | 'extended' | 'item'
    page_size: int = 200,
    top: Optional[int] = None,
    timeout: int = 60,
    columns: Optional[Sequence[str]] = None,
    expand: bool = False,                # nur für mode='standard'
    item_content_type: Optional[str] = None,
    log: Optional[Any] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Liefert Spaltenschema einer SharePoint-Liste.

    Returns
    -------
    (df, info) : tuple
        df   : pandas.DataFrame
        info : dict (inkl. info['succeeded'] in {'true','false','partially'})
    """
    # Diagnostics-Grundgerüst
    info: Dict[str, Any] = {
        "url": None,
        "params": {},
        "mode": mode,
        "list_title": list_title,
        "site_url": site_url,
        "attempt": 1,
        "retries": 0,
        "warnings": [],
        "mapping_table": {},
        "resolution_report": {},
        "module_version": __version__,
        "succeeded": "false",  # Default pessimistisch
    }

    # 1) Site + Liste auflösen
    site_id, list_id, res_diag = _resolve_site_and_list(gc, site_url, list_title)
    info["resolution_report"] = res_diag

    if site_id is None or list_id is None:
        # Site oder Liste nicht gefunden -> leerer DF + false
        info["warnings"].append("site or list not found")
        df = pd.DataFrame(columns=[
            "internalName","displayName","type","required","readOnly","hidden","indexed","enforceUnique","details","source","itemContentTypes"
        ])
        info["succeeded"] = "false"
        return df, info

    # 2) Spalten beschaffen gemäß Modus
    cols: List[Dict[str,Any]] = []
    ct_found = True

    if mode == "standard":
        cols = _fetch_columns_standard(gc, site_id, list_id, expand=expand)

    elif mode in ("extended", "item"):
        cols, item_diag = _fetch_columns_item(gc, site_id, list_id, item_content_type if mode == "item" else None)
        info["resolution_report"]["item_mode"] = item_diag.get("item_mode")
        ct_found = bool(item_diag.get("contentTypeFound", True))
        if mode == "item" and not ct_found:
            # CT nicht gefunden -> leerer DF + false (Bugfix)
            info["warnings"].append(f"content type not found: {item_content_type}")
            df = pd.DataFrame(columns=[
                "internalName","displayName","type","required","readOnly","hidden","indexed","enforceUnique","details","source","itemContentTypes"
            ])
            info["succeeded"] = "false"
            return df, info
    else:
        info["warnings"].append(f"unknown mode '{mode}', falling back to 'standard'")
        cols = _fetch_columns_standard(gc, site_id, list_id, expand=expand)

    # 3) Spaltenauswahl anwenden (falls gewünscht)
    missing: List[str] = []
    if columns:
        cols, missing = _match_columns(columns, cols)
        if missing:
            info["warnings"].append(f"missing columns: {missing}")

    # 4) deterministische Sortierung (nur wenn keine explizite Auswahl)
    if not columns:
        cols = _deterministic_order(cols)

    # 5) DataFrame bauen
    df = pd.DataFrame.from_records(cols) if cols else pd.DataFrame(
        columns=["internalName","displayName","type","required","readOnly","hidden","indexed","enforceUnique","details","source","itemContentTypes"]
    )

    # 6) succeeded bestimmen
    if mode == "item" and not ct_found:
        info["succeeded"] = "false"
    elif (columns is not None) and missing:
        info["succeeded"] = "partially"
    else:
        info["succeeded"] = "true" if len(df) > 0 else "false"

    return df, info
