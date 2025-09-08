# -*- coding: utf-8 -*-
"""
===============================================================================
SharePoint Columns Inspector (Microsoft Graph) — SQL-free
===============================================================================
Description (EN):
    This script queries a SharePoint list via Microsoft Graph and returns a
    pandas DataFrame with ALL column definitions of the list (internal name,
    display name, detected type/facet, required/readonly/hidden flags, etc.).
    No SQL is involved.

    You can run it from the command line and optionally export the result
    to CSV. All outputs are in English.

Key features:
    - Reads Azure AD application credentials from a JSON config file.
    - Fetches SharePoint list columns using Microsoft Graph (app permissions).
    - Detects SharePoint column "type" from Graph facets (choice, lookup, …).
    - Optional CSV export (timestamped by default).
    - Flexible CLI: a PassParameter switch controls if CLI params are required.

Requirements:
    pip install msal requests pandas

Permissions (app registration in Entra ID / Azure AD):
    Microsoft Graph (Application):
        - Sites.Read.All  (minimum)
      (Depending on your tenant and lists, additional permissions might be required.)

Usage examples:
    # 1) No CLI parameters needed (uses in-script defaults):
    python sp_columns_inspector.py

    # 2) CLI parameters optional (PassParameter defaults to 0, still uses defaults if missing):
    python sp_columns_inspector.py --site "https://contoso.sharepoint.com/sites/TeamA" --list "My Custom List"

    # 3) Enforce all params (PassParameter=1). If any required is missing, script errors out:
    python sp_columns_inspector.py --passparam 1 --config "C:\\python\\Scripts\\config.json" \
           --site "https://contoso.sharepoint.com/sites/TeamA" --list "My Custom List" --export "C:\\temp\\columns.csv"

Example config.json:
{
  "azuread": {
    "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_secret": "YOUR_SECRET"
  }
}

Version history:
    v1.3 (2025-09-08)  Added PassParameter switch; full script output; robust defaults/validation.
    v1.2 (2025-09-08)  CLI args, CSV export function, English output, header added.
    v1.1 (2025-09-08)  Inlined helper functions into the main fetch function.
    v1.0 (2025-09-08)  Initial Graph-based column schema fetch (no SQL).
===============================================================================
"""

# =============================================================================
# Imports
# =============================================================================
import argparse
import json
import sys
import locale
from pathlib import Path
from typing import Dict, Any, List, Tuple

import requests
import pandas as pd
import msal
from urllib.parse import urlsplit, urlparse, quote

# =============================================================================
# Console / UTF-8 helpers
# =============================================================================
def _supports_utf8_stdout() -> bool:
    enc = (sys.stdout.encoding or locale.getpreferredencoding(False) or "").lower()
    return "utf" in enc

ELLIPSIS = "…" if _supports_utf8_stdout() else "..."

# =============================================================================
# (2) Credentials loader as a single function (with inner helpers)
#     Reads: TENANT_ID, CLIENT_ID, CLIENT_SECRET from config.json
# =============================================================================
def load_credentials(config_path: str) -> Tuple[str, str, str]:
    """
    Loads AAD app credentials from JSON config and returns (tenant_id, client_id, client_secret).

    This function encapsulates its own inner helpers so it is self-contained.
    """
    def _read_json(p: str) -> Dict[str, Any]:
        path = Path(p)
        if not path.exists():
            raise FileNotFoundError(f"Config file not found: {p}")
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as ex:
            raise RuntimeError(f"Failed to parse JSON config at '{p}': {ex}")

    def _extract(creds: Dict[str, Any]) -> Tuple[str, str, str]:
        try:
            section = creds["azuread"]
            tenant_id     = section["tenant_id"]
            client_id     = section["client_id"]
            client_secret = section["client_secret"]
            return tenant_id, client_id, client_secret
        except KeyError as ke:
            raise KeyError(f"Missing key in config.azuread: {ke}")

    cfg = _read_json(config_path)
    return _extract(cfg)

# =============================================================================
# Auth / URL
# =============================================================================
def _acquire_graph_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    authority = f"https://login.microsoftonline.com/{tenant_id}"
    app = msal.ConfidentialClientApplication(
        client_id=client_id, authority=authority, client_credential=client_secret
    )
    token_result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in token_result:
        raise RuntimeError(f"Token error while acquiring Graph token: {token_result}")
    return token_result["access_token"]

def _normalize_paths_from_site_url(site_url: str) -> Tuple[str, str, str]:
    """
    site_url example: https://contoso.sharepoint.com/sites/TeamA
    -> returns (base_url, site_path, site_path_graph)
    """
    u = urlsplit(site_url.rstrip("/"))
    base_url = f"{u.scheme}://{u.netloc}"
    site_path = u.path
    site_path_graph = site_path.lstrip("/")
    return base_url, site_path, site_path_graph

# =============================================================================
# Core: Fetch SharePoint list columns (with inner helper functions)
# =============================================================================
def fetch_sharepoint_list_columns_df(tenant_id: str,
                                     client_id: str,
                                     client_secret: str,
                                     site_url: str,
                                     list_title: str,
                                     timeout: int = 60) -> pd.DataFrame:
    """
    Returns a DataFrame with the columns of a SharePoint list, including types and flags.
    Columns:
        internalName, displayName, type, required, readOnly, hidden, indexed, enforceUnique, details
    """

    # --- inner helpers (scoped to this function) ------------------------------
    def detect_column_type(col: Dict[str, Any]) -> str:
        # Graph facets: boolean, calculated, choice, currency, dateTime, hyperlinkOrPicture,
        # lookup, number, personOrGroup, text, location, term, thumbnail, etc.
        if "choice" in col:
            ch = col.get("choice") or {}
            if ch.get("allowMultipleSelections"):
                return "multiChoice"
            return "choice"
        facet_order = [
            "calculated","boolean","choice","multiChoice","currency",
            "dateTime","hyperlinkOrPicture","lookup","number",
            "personOrGroup","text","location","term","thumbnail","contentType"
        ]
        for f in facet_order:
            if f in col:
                return f
        return "unknown"

    def summarize_facet_details(col_type: str, col: Dict[str, Any]) -> str:
        try:
            if col_type in ("choice", "multiChoice"):
                choices = (col.get("choice") or {}).get("choices") or []
                return f"choices=[{', '.join(map(str, choices))}]"
            if col_type == "lookup":
                lk = col.get("lookup") or {}
                return f"lookup:listId={lk.get('listId')}, columnName={lk.get('columnName')}"
            if col_type == "personOrGroup":
                pg = col.get("personOrGroup") or {}
                return f"allowMultiple={pg.get('allowMultiple')}, chooseFrom={pg.get('allowedUserType')}"
            if col_type == "dateTime":
                dt = col.get("dateTime") or {}
                return f"displayAs={dt.get('displayAs')}, format={dt.get('format')}"
            if col_type == "number":
                nb = col.get("number") or {}
                return f"decimals={nb.get('decimalPlaces')}, min={nb.get('minimum')}, max={nb.get('maximum')}"
            if col_type == "currency":
                cu = col.get("currency") or {}
                return f"locale={cu.get('locale')}, symbol={cu.get('symbol')}"
            if col_type == "hyperlinkOrPicture":
                hp = col.get("hyperlinkOrPicture") or {}
                return f"isPicture={hp.get('isPicture')}"
            if col_type == "calculated":
                ca = col.get("calculated") or {}
                return f"formula={ca.get('formula')}"
            if col_type == "text":
                tx = col.get("text") or {}
                return f"maxLength={tx.get('maxLength')}"
        except Exception:
            return ""
        return ""
    # -------------------------------------------------------------------------

    token = _acquire_graph_token(tenant_id, client_id, client_secret)
    base_url, _, site_path_graph = _normalize_paths_from_site_url(site_url)
    hostname = urlparse(base_url).netloc

    url = (f"https://graph.microsoft.com/v1.0/sites/{hostname}:/{site_path_graph}:/"
           f"lists/{quote(list_title)}/columns?$top=200")

    cols: List[Dict[str, Any]] = []
    with requests.Session() as s:
        s.headers.update({"Authorization": f"Bearer {token}", "Accept": "application/json"})
        next_url = url
        while next_url:
            r = s.get(next_url, timeout=timeout)
            r.raise_for_status()
            j = r.json()
            cols.extend(j.get("value", []))
            next_url = j.get("@odata.nextLink")

    rows = []
    for c in cols:
        col_type = detect_column_type(c)
        details  = summarize_facet_details(col_type, c)
        rows.append({
            "internalName":  c.get("name"),
            "displayName":   c.get("displayName"),
            "type":          col_type,
            "required":      c.get("required"),
            "readOnly":      c.get("readOnly"),
            "hidden":        c.get("hidden"),
            "indexed":       c.get("indexed"),
            "enforceUnique": c.get("enforceUniqueValues"),
            "details":       details
        })

    df = pd.DataFrame(rows, columns=[
        "internalName","displayName","type","required","readOnly",
        "hidden","indexed","enforceUnique","details"
    ])
    return df

# =============================================================================
# (3) CSV export as a function (with inner helpers)
# =============================================================================
def export_csv(df: pd.DataFrame, export_path: str, timestamp: bool = True) -> Path:
    """
    Exports the DataFrame to CSV. If timestamp=True, appends a datestamp to the filename.
    Returns the final Path.
    """
    from datetime import datetime

    def _ensure_parent(path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

    def _with_timestamp(p: Path) -> Path:
        if not timestamp:
            return p
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = f"{p.stem}_{ts}"
        return p.with_name(stem + p.suffix)

    p = Path(export_path)
    p = _with_timestamp(p)
    _ensure_parent(p)
    df.to_csv(p, index=False, encoding="utf-8-sig")
    return p

# =============================================================================
# CLI / Main
# =============================================================================
def parse_args(argv: List[str]) -> argparse.Namespace:
    """
    PassParameter controls whether other params are mandatory:
      - 0 (default): parameters are optional; script may fall back to defaults.
      - 1: parameters are enforced (config, site, list). Missing ones will error out.
    """
    parser = argparse.ArgumentParser(
        description="Fetch SharePoint list column schema via Microsoft Graph and optionally export to CSV."
    )
    parser.add_argument("--passparam", dest="PASSPARAM", type=int, default=0,
                        help="Set to 1 to enforce required parameters; 0 to allow using in-script defaults. Default: 0")
    parser.add_argument("--config", dest="CONFIG_PATH", required=False,
                        help="Path to JSON config file with AAD credentials.")
    parser.add_argument("--site", dest="SITE_URL", required=False,
                        help="SharePoint site URL, e.g. https://contoso.sharepoint.com/sites/TeamA")
    parser.add_argument("--list", dest="LIST_TITLE", required=False,
                        help="SharePoint list title (display name).")
    parser.add_argument("--export", dest="EXPORT_CSV", required=False, default=None,
                        help="Optional CSV output path (e.g. C:\\temp\\columns.csv). If omitted, prints to console.")
    return parser.parse_args(argv)

def main(argv: List[str] = None) -> int:
    """
    Main entrypoint. Supports both CLI-driven execution and in-script defaults.
    Behavior is controlled via PassParameter:
      - PassParameter = 0 (default): CLI params are optional. Missing values fall back to DEFAULTS.
      - PassParameter = 1: CLI params are mandatory. Missing ones will cause an error.
    """

    # -------------------------------------------------------------------------
    # (A) Fixed defaults (edit here to hardcode parameters)
    # -------------------------------------------------------------------------
    DEFAULTS = {
        "CONFIG_PATH": r"C:\python\Scripts\config.json",
        "SITE_URL":    "https://contoso.sharepoint.com/sites/TeamA",
        "LIST_TITLE":  "My Custom List",
        "EXPORT_CSV":  None   # e.g. r"C:\temp\columns.csv" or None for console only
    }

    # -------------------------------------------------------------------------
    # (B) Parse CLI args (non-required; validation happens based on PassParameter)
    # -------------------------------------------------------------------------
    args = parse_args(argv or sys.argv[1:])
    passparam = int(args.PASSPARAM or 0)

    # -------------------------------------------------------------------------
    # (C) Resolve parameters depending on PassParameter
    # -------------------------------------------------------------------------
    if passparam == 1:
        # Enforce required parameters via validation
        missing = []
        if not args.CONFIG_PATH: missing.append("--config")
        if not args.SITE_URL:    missing.append("--site")
        if not args.LIST_TITLE:  missing.append("--list")
        if missing:
            print(f"[error] PassParameter=1 requires parameters: {', '.join(missing)}")
            return 2

        CONFIG_PATH = args.CONFIG_PATH
        SITE_URL    = args.SITE_URL
        LIST_TITLE  = args.LIST_TITLE
        EXPORT_CSV  = args.EXPORT_CSV  # optional even when passparam=1
    else:
        # Use CLI if provided, otherwise fall back to defaults
        CONFIG_PATH = args.CONFIG_PATH or DEFAULTS["CONFIG_PATH"]
        SITE_URL    = args.SITE_URL    or DEFAULTS["SITE_URL"]
        LIST_TITLE  = args.LIST_TITLE  or DEFAULTS["LIST_TITLE"]
        EXPORT_CSV  = args.EXPORT_CSV  if args.EXPORT_CSV is not None else DEFAULTS["EXPORT_CSV"]

    # -------------------------------------------------------------------------
    # (D) Execute
    # -------------------------------------------------------------------------
    try:
        print(f"[info] Using CONFIG_PATH: {CONFIG_PATH}")
        tenant_id, client_id, client_secret = load_credentials(CONFIG_PATH)

        print(f"[info] Fetching columns for list '{LIST_TITLE}' on site '{SITE_URL}' {ELLIPSIS}")
        df = fetch_sharepoint_list_columns_df(
            tenant_id, client_id, client_secret,
            SITE_URL, LIST_TITLE, timeout=60
        )

        if EXPORT_CSV:
            out_path = export_csv(df, EXPORT_CSV, timestamp=True)
            print(f"[ok] CSV exported to: {out_path}")
        else:
            if df.empty:
                print("[warn] No columns returned (DataFrame is empty).")
            else:
                with pd.option_context("display.max_rows", 500, "display.max_colwidth", 120):
                    print(df.to_string(index=False))

        return 0
    except Exception as ex:
        print(f"[error] {ex}")
        return 1

# =============================================================================
# Entrypoint
# =============================================================================
if __name__ == "__main__":
    sys.exit(main())
