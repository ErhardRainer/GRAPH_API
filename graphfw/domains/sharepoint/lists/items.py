# graphfw/domains/sharepoint/lists/items.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.domains.sharepoint.lists.items — SharePoint List Items → DataFrame
===============================================================================
Funktion:
    list_df(gc, *, site_url, list_title, columns="*", aliases=None, mapping=None, ...)

Merkmale (Auszug):
    - Spaltenauswahl:
        * columns="*" → alle Felder (fields.*) + Meta-Namen (CreatedByName/ModifiedByName)
        * columns=[...] → präzise Auswahl (intern. Namen); GUID wird automatisch ergänzt
        * mapping=[{"source": "...", "alias": "..."}] mit Heuristik & Resolution-Report
    - CreatedBy/ModifiedBy:
        * Ohne Expand über Top-Level-Metadaten (createdBy/lastModifiedBy.user.displayName)
        * Pseudotokens 'createdBy' / 'lastModifiedBy' in columns erkennen
    - GUID-Strip: '{...}' → '...'
    - Deterministische Spaltenreihenfolge:
        * explizite columns/mapping: exakt wie angefordert (id/CreatedByName/ModifiedByName respektieren)
        * "*" : ['id','GUID','Created','Modified','CreatedByName','ModifiedByName'] + Reihenfolge lt. Columns-Metadaten
    - Filter/OrderBy/Search/Expand (OData)
    - Unknown fields passthrough (bei "*"): keep|drop (Default keep)
    - Type-Coercion (datetime/int/float/bool/str) + tz_policy ('utc+2' Default)
    - Retry/Throttling/Paging via GraphClient
    - Diagnostics/Info: URL/Params, Mapping- & Resolution-Report, Warnungen, Counts
    - Schema-Dump & Beispiel-Item bei fehlenden Spalten (optional)
    - Optionaler Pause-Mechanismus bei fehlenden Spalten (interaktiv)

Rückgabe:
    (df, info)  – df: pandas.DataFrame, info: Dict mit Diagnosedaten

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlsplit, urlparse, quote

import pandas as pd

from graphfw.core.http import GraphClient
from graphfw.core.odata import OData, Expand
from graphfw.core.util import (
    strip_guid_braces,
    sp_encode_internal_name,
    deep_get,
    reorder_columns_df,
    coerce_types_df,
    apply_tz_policy,
)


def list_df(
    gc: GraphClient,
    *,
    site_url: str,
    list_title: str,
    # Selektion & Mapping
    columns: Union[str, Sequence[str], None] = "*",
    aliases: Optional[Sequence[str]] = None,
    mapping: Optional[Sequence[Dict[str, str]]] = None,  # [{"source": "...", "alias": "..."}]
    # OData
    filter: Optional[str] = None,
    orderby: Optional[str] = None,
    search: Optional[str] = None,
    expand: Optional[Union[str, Sequence[str], Sequence[Expand]]] = None,  # zusätzliche expands neben 'fields'
    top: Optional[int] = None,          # clientseitiges Limit (optional)
    page_size_hint: Optional[int] = None,  # $top für die erste Seite (autom. ermittelt, wenn None)
    # Verhalten
    tz_policy: str = "utc+2",
    type_map: Optional[Dict[str, str]] = None,       # {"Modified": "datetime", "Amount":"float", ...}
    unknown_fields: str = "keep",                    # "keep" | "drop" (nur für "*" relevant)
    add_meta: bool = True,                           # id/webUrl/sharepointIds/createdDateTime/lastModifiedDateTime
    add_created_modified_names: Optional[bool] = None,  # None=auto: bei "*" True; sonst anhand Pseudotokens
    include_weburl: bool = False,                    # webUrl (Top-Level) als Spalte hinzufügen
    include_content_type: bool = False,              # contentType (Top-Level) als Spalte hinzufügen
    # Diagnose/Debug
    debug_schema_dump: bool = False,
    pause_on_missing: bool = False,
    log: Any = None,  # kompatibel zu LogBuffer, optional
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    SharePoint: List Items → DataFrame.

    Parameters
    ----------
    gc : GraphClient
        Authentifizierter Graph-Client (Retry/Backoff/Paging integriert).
    site_url : str
        "https://tenant.sharepoint.com/sites/TeamA".
    list_title : str
        Anzeigename der Liste.
    columns : list[str] | "*" | None
        Interne Feldnamen oder "*" für alle Felder. Bei "*" werden Meta-Felder
        (CreatedByName/ModifiedByName) automatisch ergänzt (falls add_created_modified_names=None).
    aliases : list[str] | None
        Aliasnamen parallel zu 'columns' (gleiche Länge). Nur relevant, wenn mapping=None.
    mapping : list[{"source","alias"}] | None
        Ausdrückliche Quelldefinitionen inkl. Top-Level (z. B. "webUrl") oder fields.*
        – überschreibt 'columns'/'aliases'.
    filter, orderby, search, expand : OData-Parameter
        'filter' wird, falls es nicht mit 'fields/' beginnt, automatisch zu 'fields/<expr>' erweitert.
        'expand' sind zusätzliche Expands neben 'fields' (strings oder Expand-Objekte).
    top : int | None
        Optional clientseitiges Limit für die Gesamtanzahl Items.
    page_size_hint : int | None
        Optionaler $top-Hinweis für die erste Seite (Performance/Throttling).
    tz_policy : str
        Zeitzonen-Policy (z. B. 'utc', 'utc+2', 'local'); DateTimes werden naiv zurückgegeben.
    type_map : dict[str,str] | None
        Optionale Typumwandlung: 'datetime'|'int'|'float'|'bool'|'str'
    unknown_fields : "keep" | "drop"
        Verhalten für unbekannte Felder bei columns="*".
    add_meta : bool
        id/webUrl/sharepointIds/createdDateTime/lastModifiedDateTime als zusätzliche Spalten?
    add_created_modified_names : bool | None
        Wenn None: bei columns="*" automatisch True; sonst nur, wenn Pseudotokens in columns/mapping verlangt.
    include_weburl, include_content_type : bool
        Top-Level-Spalten zusätzlich ausgeben.
    debug_schema_dump, pause_on_missing : bool
        Bei fehlenden Spalten: Schema & Beispiel-Item dumpen, optional interaktiv pausieren.
    log : LogBuffer | None
        Optionaler Logpuffer (print + to_df()).

    Returns
    -------
    (df, info) : tuple[pandas.DataFrame, dict]
        DataFrame mit deterministischer Spaltenordnung + Diagnose-Info.
    """
    # =========================================================================
    # Unterfunktionen (gekapselt innerhalb list_df)
    # =========================================================================
    def _columns_from_value(val: Union[str, Sequence[str], None]) -> Optional[List[str]]:
        if val is None:
            return None
        if isinstance(val, str):
            s = val.strip()
            if s == "" or s == "*":
                return None
            return [c.strip() for c in s.split(",") if c and c.strip()]
        # Sequenz
        cols = [str(c).strip() for c in val if str(c).strip()]
        return cols or None

    def _ensure_guid_in_columns(cols: Optional[List[str]]) -> Optional[List[str]]:
        if cols is None:
            return None
        lc = {c.lower() for c in cols}
        return cols if "guid" in lc else cols + ["GUID"]

    def _detect_meta_flags(
        cols: Optional[List[str]],
        mapping: Optional[Sequence[Dict[str, str]]],
        add_created_modified_names: Optional[bool],
    ) -> Tuple[bool, bool, Optional[List[str]]]:
        """
        Liefert:
            want_created_name, want_modified_name, filtered_columns_for_select
        columns: entfernt Pseudotokens createdBy/lastModifiedBy
        mapping: ignoriert (meta-Felder via Top-Level)
        """
        if mapping:
            # mapping bestimmt explizit Aliase; meta-Spalten werden durch alias gesetzt
            want_created = any((m.get("source","").strip().lower() == "createdby") for m in mapping)
            want_modified = any((m.get("source","").strip().lower() == "lastmodifiedby") for m in mapping)
            return want_created, want_modified, cols

        if cols is None:
            # "*" → auto
            if add_created_modified_names is None:
                return True, True, None
            return bool(add_created_modified_names), bool(add_created_modified_names), None

        tokens = {"createdby", "lastmodifiedby"}
        want_created = any(c.lower() == "createdby" for c in cols)
        want_modified = any(c.lower() == "lastmodifiedby" for c in cols)
        filtered = [c for c in cols if c.lower() not in tokens]
        # Wenn add_created_modified_names explizit gesetzt → override
        if add_created_modified_names is not None:
            want_created = bool(add_created_modified_names)
            want_modified = bool(add_created_modified_names)
        return want_created, want_modified, (filtered or None)

    def _fetch_columns_meta(gc: GraphClient, hostname: str, site_path_graph: str, list_title: str) -> List[Dict[str, Any]]:
        url = (
            f"/sites/{hostname}:/{site_path_graph}:/lists/{quote(list_title)}/columns"
            "?$select=name,displayName,hidden,readOnly,required"
        )
        meta: List[Dict[str, Any]] = []
        for it in gc.get_paged(url, item_path="value", page_size_hint=200):
            meta.append(it)
        return meta

    def _build_name_maps(columns_meta: List[Dict[str, Any]]) -> Tuple[Dict[str, str], List[str]]:
        """
        Returns:
            by_name_ci: {lower(name) -> name}  (für case-insensitive Treffer)
            order_list: [name1, name2, ...]    (Graph-Reihenfolge)
        """
        by_name_ci = {}
        order_list: List[str] = []
        for c in columns_meta:
            nm = str(c.get("name",""))
            if not nm:
                continue
            order_list.append(nm)
            by_name_ci[nm.lower()] = nm
        return by_name_ci, order_list

    def _resolve_to_internal_field(
        raw: str,
        by_name_ci: Dict[str, str],
    ) -> Tuple[Optional[str], str]:
        """
        Versucht, einen Spaltennamen auf fields.<InternalName> zu mappen.
        - exakter/case-insensitiver Treffer
        - Heuristik: SharePoint-Encoding _x0020_/_x002d_/_x002f_
        Rückgabe: (internalPath or None, resolutionNote)
        """
        s_raw = raw.strip()
        s_lc = s_raw.lower()
        # exakter/case-insensitiver
        if s_lc in by_name_ci:
            return f"fields.{by_name_ci[s_lc]}", "fields (exact/case-insens)"
        # heuristischer Encode
        guess = sp_encode_internal_name(s_raw)
        if guess.lower() in by_name_ci:
            return f"fields.{by_name_ci[guess.lower()]}", "fields (encoded-guess)"
        return None, "missing"

    def _normalize_mapping(
        columns: Optional[List[str]],
        aliases: Optional[Sequence[str]],
        mapping: Optional[Sequence[Dict[str, str]]],
        by_name_ci: Dict[str, str],
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, Any]], List[str]]:
        """
        Erzeugt die effektive Mappingliste [{"source","alias"},...] und
        liefert zusätzlich:
            - mapping_table (Resolution je Eintrag)
            - missing_columns (Aliase ohne Auflösung)
        Spezialsymbole:
            - "id" (Top-Level -> 'id')
            - "guid" -> bevorzugt fields.GUID, fallback sharepointIds.listItemUniqueId
            - "createdBy"/"lastModifiedBy": Top-Level Meta (Name)
            - "webUrl": top-level
        """
        result: List[Dict[str, str]] = []
        mapping_table: List[Dict[str, Any]] = []
        missing_aliases: List[str] = []

        if mapping:
            pairs = [(m.get("source","").strip(), (m.get("alias") or m.get("source")).strip()) for m in mapping]
        else:
            cols = columns or []
            als: List[str]
            if aliases and len(aliases) == len(cols):
                als = [a.strip() for a in aliases]
            else:
                als = [c.strip() for c in cols]
            pairs = list(zip(cols, als))

        for src_raw, alias in pairs:
            s_lc = src_raw.lower()
            internal = None
            resolution = None

            # Sonderfälle
            if s_lc == "id":
                internal, resolution = "id", "top-level:id"
            elif s_lc == "guid":
                if "guid" in by_name_ci:
                    internal, resolution = "fields.GUID", "fields.GUID"
                else:
                    internal, resolution = "sharepointIds.listItemUniqueId", "sharepointIds.listItemUniqueId (fallback)"
            elif s_lc == "createdby":
                internal, resolution = "createdBy.user.displayName", "meta:createdBy name"
            elif s_lc == "lastmodifiedby":
                internal, resolution = "lastModifiedBy.user.displayName", "meta:lastModifiedBy name"
            elif s_lc == "weburl":
                internal, resolution = "webUrl", "top-level:webUrl"

            # Normale Felder
            if internal is None:
                internal, resolution = _resolve_to_internal_field(src_raw, by_name_ci)

            if internal is None:
                mapping_table.append({
                    "Source_Column": src_raw,
                    "internal_Column": None,
                    "Translated_Column": alias,
                    "resolution": "missing",
                })
                missing_aliases.append(alias)
                continue

            result.append({"source": internal, "alias": alias})
            mapping_table.append({
                "Source_Column": src_raw,
                "internal_Column": internal,
                "Translated_Column": alias,
                "resolution": resolution,
            })

        # Sicherstellen, dass webUrl evtl. mitkommt (für Diagnose nützlich) – optional
        return result, mapping_table, missing_aliases

    def _collect_selects(columns_for_request: List[Dict[str, str]], selective: bool) -> Tuple[List[str], List[str]]:
        """
        Trennt top-level selects und fields selects.
        - selective=False → expand=fields (ohne $select)
        """
        top_level: List[str] = []
        field_sel: List[str] = []
        for c in columns_for_request:
            src = c["source"]
            if src.startswith("fields."):
                if selective:
                    field_sel.append(src.split(".", 1)[1])
            else:
                top_level.append(src.split(".", 1)[0])
        # sharepointIds fast immer sinnvoll (GUID-Fallback)
        if "sharepointIds" not in top_level:
            top_level.append("sharepointIds")
        # id ist überhaupt nützlich
        if "id" not in top_level:
            top_level.append("id")
        return sorted(set(top_level)), sorted(set(field_sel))

    def _build_odata_params(
        top_level_select: List[str],
        field_select: List[str],
        *,
        add_meta: bool,
        include_weburl: bool,
        include_content_type: bool,
        filter: Optional[str],
        orderby: Optional[str],
        search: Optional[str],
        expand_extra: Optional[Union[str, Sequence[str], Sequence[Expand]]],
        selective: bool,
        page_size_hint: Optional[int],
    ) -> Dict[str, Any]:
        q = OData()
        # Top-Level-Select
        tl = list(top_level_select)
        if add_meta:
            # created/modified timestamps
            for t in ("createdDateTime", "lastModifiedDateTime"):
                if t not in tl:
                    tl.append(t)
        if include_weburl and "webUrl" not in tl:
            tl.append("webUrl")
        if include_content_type and "contentType" not in tl:
            tl.append("contentType")
        if tl:
            q.select(*tl)

        # Expand 'fields'
        if selective and field_select:
            q.expand(Expand("fields", select=field_select))
        else:
            q.expand(Expand("fields"))

        # Zusatz-Expands
        if expand_extra:
            if isinstance(expand_extra, (list, tuple)):
                for e in expand_extra:
                    if isinstance(e, Expand):
                        q.expand(e)
                    else:
                        q.expand(Expand(str(e)))
            else:
                q.expand(Expand(str(expand_extra)))

        # Filter normalisieren (fields/<expr>)
        filt = None
        if filter and filter.strip():
            f = filter.strip()
            if not f.lower().startswith("fields/"):
                filt = "fields/" + f
            else:
                filt = f
            q.filter(filt)

        if orderby:
            q.orderby(orderby)
        if search:
            q.search(search)
        if page_size_hint:
            q.top(int(page_size_hint))

        return q.to_params()

    def _dump_schema_and_one_item(hostname: str, site_path_graph: str, list_title: str) -> None:
        try:
            url_cols = f"/sites/{hostname}:/{site_path_graph}:/lists/{quote(list_title)}/columns?$select=name,displayName,hidden,readOnly,required"
            if log:
                log.info("Schema: columns", url=url_cols)
            cols = gc.get_json(url_cols)
            if log:
                for c in cols.get("value", []):
                    log.info("col", name=c.get("name"), displayName=c.get("displayName"), hidden=c.get("hidden"), readOnly=c.get("readOnly"), required=c.get("required"))
        except Exception as ex:
            if log:
                log.warning("Schema columns failed", error=str(ex))

        try:
            url_item = (
                f"/sites/{hostname}:/{site_path_graph}:/lists/{quote(list_title)}/items"
                "?$expand=fields&$select=id,webUrl,sharepointIds,contentType,createdDateTime,lastModifiedDateTime&$top=1"
            )
            if log:
                log.info("Schema: sample item", url=url_item)
            j = gc.get_json(url_item)
            it = (j.get("value") or [None])[0]
            if not it:
                if log: log.info("sample", note="empty list")
                return
            # top-level keys
            for k in ["id", "webUrl", "createdDateTime", "lastModifiedDateTime", "contentType"]:
                if k in it and log:
                    log.info("sample.top", key=k, value=it[k])
            # sharepointIds
            if "sharepointIds" in it and log:
                spids = it["sharepointIds"]
                for k, v in spids.items():
                    log.info("sample.sharepointIds", key=k, value=v)
            # fields
            f = it.get("fields") or {}
            for k in sorted(f.keys()):
                v = f[k]
                s = str(v)
                if len(s) > 200:
                    s = s[:200] + " …"
                log.info("sample.fields", key=k, value=s)
        except Exception as ex:
            if log:
                log.warning("Schema sample failed", error=str(ex))

    def _pause_if_requested(missing_cols: List[str]) -> None:
        if not pause_on_missing or not missing_cols:
            return
        try:
            inp = input(f"\nFehlende Spalten erkannt: {', '.join(missing_cols)}\n[Enter] weiter • [q] Abbruch: ").strip().lower()
            if inp.startswith("q"):
                raise KeyboardInterrupt("Abbruch durch Benutzer")
        except KeyboardInterrupt:
            raise
        except Exception:
            # Non-interaktiv → einfach weiter
            pass

    def _row_from_item(
        it: Dict[str, Any],
        *,
        columns_for_request: Optional[List[Dict[str, str]]],
        want_created_name: bool,
        want_modified_name: bool,
        unknown_fields: str,
        selective: bool,
    ) -> Tuple[Dict[str, Any], Dict[str, str]]:
        """
        Baut eine Zeile aus einem Graph-Item. Gibt zusätzlich eine Map alias->used_path zurück.
        - Wenn columns_for_request angegeben: verwende deren Aliasreihenfolge.
        - Andernfalls (columns="*"): nehme alle fields.*, filtere @odata.*, GUID strip.
        """
        used_paths: Dict[str, str] = {}
        row: Dict[str, Any] = {}

        # Basis
        row["id"] = it.get("id")

        # Meta-Namen
        if want_created_name:
            row["CreatedByName"] = deep_get(it, "createdBy.user.displayName")
            used_paths["CreatedByName"] = "createdBy.user.displayName"
        if want_modified_name:
            row["ModifiedByName"] = deep_get(it, "lastModifiedBy.user.displayName")
            used_paths["ModifiedByName"] = "lastModifiedBy.user.displayName"

        fields = it.get("fields") or {}

        if columns_for_request:
            # Explizite Auswahl/Mappings
            for m in columns_for_request:
                src = m["source"]
                alias = m["alias"]

                val = None
                used = None

                if src == "id":
                    val = it.get("id")
                    used = "id"
                elif src == "webUrl":
                    val = it.get("webUrl")
                    used = "webUrl"
                elif src == "createdBy.user.displayName":
                    val = deep_get(it, "createdBy.user.displayName")
                    used = "createdBy.user.displayName"
                elif src == "lastModifiedBy.user.displayName":
                    val = deep_get(it, "lastModifiedBy.user.displayName")
                    used = "lastModifiedBy.user.displayName"
                elif src == "sharepointIds.listItemUniqueId":
                    val = deep_get(it, "sharepointIds.listItemUniqueId")
                    used = "sharepointIds.listItemUniqueId"
                elif src.startswith("fields."):
                    key = src.split(".", 1)[1]
                    if key in fields:
                        val = fields.get(key)
                        used = src
                    else:
                        # Heuristik: encoded guess
                        guess = sp_encode_internal_name(key)
                        if guess in fields:
                            val = fields.get(guess)
                            used = f"fields.{guess} (guess)"
                        # Sonderfall GUID-Fallback
                        if val is None and key.lower() == "guid":
                            val = deep_get(it, "sharepointIds.listItemUniqueId")
                            used = "sharepointIds.listItemUniqueId (fallback)"
                else:
                    # generisches deep_get (z. B. contentType.*, sharepointIds.*)
                    val = deep_get(it, src)
                    used = src

                # GUID strip
                if alias.lower() == "guid" and isinstance(val, str):
                    val = strip_guid_braces(val)

                row[alias] = val
                if used:
                    used_paths[alias] = used

        else:
            # columns="*": alle Felder mitnehmen (unknown_fields steuert)
            for k, v in fields.items():
                if isinstance(k, str) and k.startswith("@"):
                    continue
                if k.lower() == "guid" and isinstance(v, str):
                    v = strip_guid_braces(v)
                row[k] = v
            # Optional: unbekannte Felder droppen (hier wären "alle" → drop heißt: nichts tun)

        return row, used_paths

    # =========================================================================
    # Effektive Parameter / Vorbereitung
    # =========================================================================
    if not isinstance(gc, GraphClient):
        raise TypeError("gc must be a GraphClient")

    u = urlsplit(site_url.rstrip("/"))
    base_url = f"{u.scheme}://{u.netloc}"
    site_path_graph = u.path.lstrip("/")
    hostname = u.netloc

    cols_in = _columns_from_value(columns)
    cols_in = _ensure_guid_in_columns(cols_in)
    want_created_name, want_modified_name, cols_for_select = _detect_meta_flags(
        cols_in, mapping, add_created_modified_names
    )
    # selective = True, wenn konkrete Felder selektiert werden sollen
    selective = bool(cols_for_select or mapping)

    # =========================================================================
    # Columns-Metadaten laden (für Mapping & Reihenfolge)
    # =========================================================================
    cols_meta: List[Dict[str, Any]] = _fetch_columns_meta(gc, hostname, site_path_graph, list_title)
    by_name_ci, order_list = _build_name_maps(cols_meta)

    # =========================================================================
    # Mapping normalisieren (columns/aliases + heuristik) → columns_for_request
    # =========================================================================
    columns_for_request: Optional[List[Dict[str, str]]] = None
    mapping_table: List[Dict[str, Any]] = []
    missing_aliases: List[str] = []

    if mapping:
        columns_for_request, mapping_table, missing_aliases = _normalize_mapping(None, None, mapping, by_name_ci)
    elif cols_for_select:
        # columns + aliases
        columns_for_request, mapping_table, missing_aliases = _normalize_mapping(cols_for_select, aliases, None, by_name_ci)
    else:
        columns_for_request, mapping_table, missing_aliases = None, [], []

    if missing_aliases and debug_schema_dump and log:
        log.warning("missing columns detected", missing=missing_aliases)
        _dump_schema_and_one_item(hostname, site_path_graph, list_title)
    if missing_aliases:
        _pause_if_requested(missing_aliases)

    # =========================================================================
    # OData-Params bauen
    # =========================================================================
    if columns_for_request:
        top_sel, fld_sel = _collect_selects(columns_for_request, selective=True)
    else:
        top_sel, fld_sel = _collect_selects(
            [{"source": "id", "alias": "id"}], selective=False
        )

    params = _build_odata_params(
        top_sel, fld_sel,
        add_meta=add_meta,
        include_weburl=include_weburl,
        include_content_type=include_content_type,
        filter=filter,
        orderby=orderby,
        search=search,
        expand_extra=expand,
        selective=bool(columns_for_request),
        page_size_hint=page_size_hint,
    )

    # =========================================================================
    # Abruf
    # =========================================================================
    url_items = f"/sites/{hostname}:/{site_path_graph}:/lists/{quote(list_title)}/items"

    if log:
        log.info("GET list items", url=url_items, params=params, selective=bool(columns_for_request))

    items: List[Dict[str, Any]] = []
    pages = 0
    for it in gc.get_paged(url_items, params=params, item_path="value", page_size_hint=None):
        items.append(it)
        if top is not None and len(items) >= top:
            items = items[:top]
            pages += 1  # die letzte (abgeschnittene) Seite zählen
            break
        # Seitenzählung approximiert über Items; exakter wäre get_paged(page_path=None)
        # hier erhöhen wir erst am Ende; alternativ könnte man JSON-Seiten yielden
    # (Keine exakte Page-Zählung nötig; wir liefern Counts unten.)

    # =========================================================================
    # In DataFrame transformieren + Resolution-Report
    # =========================================================================
    rows: List[Dict[str, Any]] = []
    resolution_map_accum: Dict[str, str] = {}

    for it in items:
        row, used_paths = _row_from_item(
            it,
            columns_for_request=columns_for_request,
            want_created_name=want_created_name,
            want_modified_name=want_modified_name,
            unknown_fields=unknown_fields,
            selective=bool(columns_for_request),
        )
        # Unknown fields bei "*" droppen?
        if not columns_for_request and unknown_fields == "drop":
            keep_keys = {"id"}
            if want_created_name:
                keep_keys.add("CreatedByName")
            if want_modified_name:
                keep_keys.add("ModifiedByName")
            # plus Felder lt. order_list
            keep_keys.update(order_list)
            row = {k: v for k, v in row.items() if k in keep_keys}
        # Resolution-Map sammeln (nur erstes Mapping je Alias merken)
        for alias, path in (used_paths or {}).items():
            if alias not in resolution_map_accum:
                resolution_map_accum[alias] = path
        rows.append(row)

    df = pd.DataFrame(rows)

    # =========================================================================
    # Type-Coercion & TZ-Policy (nur wenn gewünscht)
    # =========================================================================
    if type_map:
        df = coerce_types_df(df, type_map, tz_policy=tz_policy)

    # =========================================================================
    # Deterministische Spaltenreihenfolge
    # =========================================================================
    if columns_for_request:
        # exakte Aliasreihenfolge
        alias_order = [m["alias"] for m in columns_for_request]
        head = []
        # Falls Meta-Namen gewünscht, Einsortierung:
        if want_created_name and "CreatedByName" not in alias_order:
            head.append("CreatedByName")
        if want_modified_name and "ModifiedByName" not in alias_order:
            head.append("ModifiedByName")
        df = reorder_columns_df(df, head=head + ["id"], tail=[])
        # anschließend Aliasreihenfolge erzwingen, plus übrige
        cols = [c for c in alias_order if c in df.columns]
        rest = [c for c in df.columns if c not in cols]
        df = df.loc[:, cols + rest]
    else:
        # "*" – Kopf & Meta, dann lt. Columns-Metadaten
        head = ["id", "GUID", "Created", "Modified"]
        if want_created_name:
            head.append("CreatedByName")
        if want_modified_name:
            head.append("ModifiedByName")
        df = reorder_columns_df(df, head=head, tail=None)
        # Optional: restliche nach order_list sortieren (nur vorhandene)
        mid_head = [c for c in df.columns if c not in head]
        desired_mid = [c for c in order_list if c in mid_head]
        tail = [c for c in mid_head if c not in desired_mid]
        df = df.loc[:, head + desired_mid + tail]

    # =========================================================================
    # Info/Diagnose zusammenstellen
    # =========================================================================
    info: Dict[str, Any] = {
        "url": url_items,
        "params": params,
        "site_url": site_url,
        "list_title": list_title,
        "selective": bool(columns_for_request),
        "items": len(items),
        "rows": 0 if df is None else len(df),
        "warnings": [],
        "mapping_table": mapping_table,
        "resolution_report": [{"alias": k, "used_source": v} for k, v in resolution_map_accum.items()],
        "columns_effective": [m["source"] for m in (columns_for_request or [])],
        "aliases_effective": [m["alias"] for m in (columns_for_request or [])],
        "tz_policy": tz_policy,
        "unknown_fields": unknown_fields,
    }

    if missing_aliases:
        info["warnings"].append({"missing_columns": missing_aliases})

    return df, info
