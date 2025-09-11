# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.io.writers.json_writer — Minimalistischer JSON-Writer
===============================================================================
Zweck:
    - Vereinfachter Export eines DataFrames als JSON-Datei.
    - Einheitliches Namensschema:
        <prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].json
    - Gibt den *vollständigen Pfad* der erzeugten Datei zurück.

Parameter (öffentlich):
    - prefix:      str        — erster Namensbestandteil (Dateinamen-sicher)
    - postfix:     str|None   — optionaler letzter Bestandteil (Dateinamen-sicher)
    - timestamp:   bool       — ob Datum/Uhrzeit *zwischen* prefix und postfix steht
    - encoding:    str        — Text-Encoding (Default: "utf-8")
    - index:       bool       — Index mitschreiben (Default: False)  [wirkt via reset_index()]
    - date_format: str|None   — pandas to_json-Option (z. B. "iso")
    - orient:      str        — pandas-Orientierung (Default: "records")
    - indent:      int|None   — JSON-Pretty-Print (Default: 2)
    - force_ascii: bool       — Nicht-ASCII mit \\u-Escapes (Default: False)
    - overwrite:   bool       — existierende Datei überschreiben (Default: False)

Rückgabe:
    - write_json(...): pathlib.Path

Abhängigkeiten:
    * Standardbibliothek; pandas-kompatible DataFrame API (df.to_json).

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
    stem, suffix = path.stem, path.suffix or ".json"
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_{i:0{width}d}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def build_json_path(
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
) -> Path:
    """
    Erzeugt den Zielpfad (im aktuellen Arbeitsverzeichnis) für die JSON-Datei.

    Returns
    -------
    Path
        Vollständiger Pfad (Datei wird nicht erstellt).
    """
    filename = _compose_filename(prefix, postfix, timestamp, "json")
    return Path.cwd() / filename


def write_json(
    df: Any,
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
    encoding: str = "utf-8",
    index: bool = False,
    date_format: Optional[str] = None,
    orient: str = "records",
    indent: Optional[int] = 2,
    force_ascii: bool = False,
    overwrite: bool = False,
) -> Path:
    """
    Schreibt ein DataFrame als JSON in das aktuelle Arbeitsverzeichnis (cwd).

    Returns
    -------
    Path
        Pfad der erzeugten JSON-Datei.
    """
    target = build_json_path(prefix=prefix, postfix=postfix, timestamp=timestamp)
    if target.exists() and not overwrite:
        target = _next_free_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Wenn Index gefordert ist, in Daten kopieren (to_json kennt 'index' nicht für alle Orients)
    df_to_write = df if index is False else df.reset_index()

    # pandas -> DataFrame.to_json unterstützt Pfad + Encoding ab neueren Versionen via open()
    text = df_to_write.to_json(
        orient=orient,
        date_format=date_format,
        force_ascii=force_ascii,
        indent=indent,
    )
    target.write_text(text, encoding=encoding)
    return target


__all__ = ["build_json_path", "write_json"]
