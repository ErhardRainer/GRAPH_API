# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.io.writers.excel_writer — Minimalistischer Excel-Writer
===============================================================================
Zweck:
    - Vereinfachter Export eines DataFrames als Excel-Datei (.xlsx).
    - Einheitliches Namensschema:
        <prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].xlsx
    - Gibt den *vollständigen Pfad* der erzeugten Datei zurück.

Parameter (öffentlich):
    - prefix:      str        — erster Namensbestandteil (Dateinamen-sicher)
    - postfix:     str|None   — optionaler letzter Bestandteil (Dateinamen-sicher)
    - timestamp:   bool       — ob Datum/Uhrzeit *zwischen* prefix und postfix steht
    - index:       bool       — Index mitschreiben (Default: False)
    - date_format: str|None   — Nummernformat für Datumszellen (optional, best effort)
    - sheet_name:  str        — Blattname (Default: "Sheet1")
    - engine:      str|None   — pandas-Excel-Engine (z. B. "openpyxl" oder "xlsxwriter")
    - overwrite:   bool       — existierende Datei überschreiben (Default: False)

Rückgabe:
    - write_excel(...): pathlib.Path

Abhängigkeiten:
    * Standardbibliothek; pandas-kompatible DataFrame API (df.to_excel).
    * Für .xlsx wird in der Regel ein Engine-Paket benötigt (z. B. openpyxl).

Autor: dein Projekt
Version: 1.0.0 (2025-09-12)
===============================================================================
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from graphfw.core.util import sanitize_for_filename


def _compose_filename(prefix: str, postfix: Optional[str], add_ts: bool, ext: str) -> str:
    parts = [sanitize_for_filename(prefix)]
    if add_ts:
        parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
    if postfix:
        parts.append(sanitize_for_filename(postfix))
    stem = "_".join([p for p in parts if p])
    return f"{stem}.{ext.lstrip('.')}"


def _next_free_path(path: Path, *, width: int = 3) -> Path:
    stem, suffix = path.stem, path.suffix or ".xlsx"
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_{i:0{width}d}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def build_excel_path(
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
) -> Path:
    """
    Erzeugt den Zielpfad (im aktuellen Arbeitsverzeichnis) für die Excel-Datei.

    Returns
    -------
    Path
        Vollständiger Pfad (Datei wird nicht erstellt).
    """
    filename = _compose_filename(prefix, postfix, timestamp, "xlsx")
    return Path.cwd() / filename


def write_excel(
    df: Any,
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
    index: bool = False,
    date_format: Optional[str] = None,
    sheet_name: str = "Sheet1",
    engine: Optional[str] = None,
    overwrite: bool = False,
) -> Path:
    """
    Schreibt ein DataFrame als Excel (.xlsx) in das aktuelle Arbeitsverzeichnis (cwd).

    Returns
    -------
    Path
        Pfad der erzeugten Excel-Datei.
    """
    target = build_excel_path(prefix=prefix, postfix=postfix, timestamp=timestamp)
    if target.exists() and not overwrite:
        target = _next_free_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Schreiben. Optionales Nummernformat für Datumsspalten wird (falls Engine unterstützt)
    # über einen ExcelWriter-Kontext gesetzt.
    # Hinweis: Für 'openpyxl' oder 'xlsxwriter' muss die jeweilige Engine installiert sein.
    if date_format is None and engine is None:
        # Einfachster Weg: direkt to_excel
        df.to_excel(target, index=index, sheet_name=sheet_name, engine=engine)
        return target

    # Feinsteuerung, z. B. Dateiformate
    import pandas as pd  # lokale Importierung, um harte Abhängigkeiten zu vermeiden

    with pd.ExcelWriter(target, engine=engine) as writer:
        df.to_excel(writer, index=index, sheet_name=sheet_name)
        if date_format:
            try:
                wb = writer.book  # type: ignore[attr-defined]
                ws = writer.sheets.get(sheet_name)  # type: ignore[attr-defined]
                # Formatierung je nach Engine unterschiedlich
                if writer.engine == "xlsxwriter":  # type: ignore[attr-defined]
                    fmt = wb.add_format({"num_format": date_format})  # type: ignore[union-attr]
                    # Spaltenbreite & Format grob setzen (alle Datenzellen)
                    # Hinweis: DataFrame beginnt bei Zeile 1 (Header) -> Daten ab Zeile 2
                    # Wir setzen Format für alle Spalten; feinere Steuerung wäre Schema-abhängig.
                    ncols = df.shape[1] + (1 if index else 0)
                    ws.set_column(0, ncols, None, fmt)  # type: ignore[union-attr]
                elif writer.engine == "openpyxl":  # type: ignore[attr-defined]
                    from openpyxl.styles import numbers  # type: ignore[import-not-found]
                    # openpyxl: Zellformatierung iterieren (einfach gehalten)
                    for row in ws.iter_rows(min_row=2):  # type: ignore[union-attr]
                        for cell in row:
                            cell.number_format = date_format or numbers.FORMAT_DATE_YYYYMMDD2
            except Exception:
                # Best-effort: Wenn Formatierung nicht möglich ist, schreiben wir trotzdem die Datei.
                pass

    return target


__all__ = ["build_excel_path", "write_excel"]
