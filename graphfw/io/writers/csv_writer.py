# csv_writer.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.io.writers.csv_writer — CSV-Writer & Pfadgenerator
===============================================================================
Zweck:
    - Einheitliche CSV-Ausgabe mit verlässlicher Namenskonvention:
        <SiteToken>_<ListToken>_<YYYYMMDD>_<hhmmss>.csv
      (Excel-freundliches UTF-8-SIG-Encoding)
    - Kapselt Ordneranlage, Dateinamens-Sanitizing und Rückgabe eines
      Output-Infos (Pfad, Zeilen, Encoding).

Abhängigkeiten:
    * Standardbibliothek; pandas-ähnliche DataFrame API (df.to_csv).

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib.parse import urlsplit

from graphfw.core.util import sanitize_for_filename  # passt ggf. an dein Package an


def site_token_for_filename(site_url: str) -> str:
    """
    Erzeugt einen stabilen Token aus einer Site-URL:
      host + letzter Pfadbestandteil (z. B. 'contoso.sharepoint.com_sites-TeamA')
    """
    u = urlsplit((site_url or "").rstrip("/"))
    host = sanitize_for_filename(u.netloc or "host")
    last = sanitize_for_filename((u.path or "").rstrip("/").split("/")[-1] or host)
    return f"{host}_{last}"


def build_csv_path(
    *,
    site_url: str,
    list_title: str,
    out_dir: Union[str, Path],
    timestamp: bool = True,
    suffix: str = ".csv",
) -> Path:
    """
    Erzeugt den Zielpfad für eine CSV-Datei. Ordner wird NICHT angelegt.
    """
    out_dir = Path(out_dir)
    site_tok = site_token_for_filename(site_url)
    list_tok = sanitize_for_filename(list_title)
    if timestamp:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"{site_tok}_{list_tok}_{ts}{suffix}"
    else:
        fname = f"{site_tok}_{list_tok}{suffix}"
    return out_dir / fname


def write_csv(
    df: Any,
    *,
    site_url: str,
    list_title: str,
    out_dir: Union[str, Path],
    timestamp: bool = True,
    encoding: str = "utf-8-sig",
    index: bool = False,
    date_format: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Schreibt ein DataFrame als CSV in 'out_dir' mit standardisiertem Dateinamen.

    Rückgabe:
        {"path": Path, "rows": int, "encoding": str}
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    path = build_csv_path(site_url=site_url, list_title=list_title, out_dir=out_dir, timestamp=timestamp)
    # df wird als pandas-kompatibel angenommen
    df.to_csv(path, index=index, encoding=encoding, date_format=date_format)
    return {"path": path, "rows": (0 if getattr(df, "empty", False) else len(df)), "encoding": encoding}


__all__ = ["build_csv_path", "write_csv", "site_token_for_filename"]
