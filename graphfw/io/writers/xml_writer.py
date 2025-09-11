# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.io.writers.xml_writer — Minimalistischer XML-Writer
===============================================================================
Zweck:
    - Vereinfachter Export einer Tabellenstruktur (pandas-kompatibles DataFrame)
      als XML-Datei.
    - Einheitliches Namensschema:
        <prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].xml
    - Gibt den *vollständigen Pfad* der erzeugten Datei zurück.

Parameter (öffentlich):
    - prefix:      str        — erster Namensbestandteil (Dateinamen-sicher)
    - postfix:     str|None   — optionaler letzter Bestandteil (Dateinamen-sicher)
    - timestamp:   bool       — ob Datum/Uhrzeit *zwischen* prefix und postfix steht
    - encoding:    str        — Text-Encoding (Default: "utf-8")
    - index:       bool       — Index mitschreiben (Default: False)
    - date_format: str|None   — pandas-Option; z. B. "iso"
    - root_name:   str        — Wurzel-Element (Default: "data")
    - row_name:    str        — Zeilen-Element (Default: "row")
    - xml_declaration: bool   — XML-Deklaration schreiben (Default: True)
    - pretty_print: bool      — Einrückungen/Zeilenumbrüche (Default: True)
    - overwrite:   bool       — existierende Datei überschreiben (Default: False)

Rückgabe:
    - write_xml(...): pathlib.Path

Abhängigkeiten:
    * Standardbibliothek; pandas-kompatible DataFrame API (df.to_xml).

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
    stem, suffix = path.stem, path.suffix or ".xml"
    i = 1
    while True:
        candidate = path.with_name(f"{stem}_{i:0{width}d}{suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def build_xml_path(
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
) -> Path:
    """
    Erzeugt den Zielpfad (im aktuellen Arbeitsverzeichnis) für die XML-Datei.

    Returns
    -------
    Path
        Vollständiger Pfad (Datei wird nicht erstellt).
    """
    filename = _compose_filename(prefix, postfix, timestamp, "xml")
    return Path.cwd() / filename


def write_xml(
    df: Any,
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
    encoding: str = "utf-8",
    index: bool = False,
    date_format: Optional[str] = None,
    root_name: str = "data",
    row_name: str = "row",
    xml_declaration: bool = True,
    pretty_print: bool = True,
    overwrite: bool = False,
) -> Path:
    """
    Schreibt ein DataFrame als XML in das aktuelle Arbeitsverzeichnis (cwd).

    Returns
    -------
    Path
        Pfad der erzeugten XML-Datei.
    """
    target = build_xml_path(prefix=prefix, postfix=postfix, timestamp=timestamp)
    if target.exists() and not overwrite:
        target = _next_free_path(target)
    target.parent.mkdir(parents=True, exist_ok=True)

    # pandas >= 1.3: to_xml verfügbar
    df.to_xml(
        target,
        index=index,
        encoding=encoding,
        root_name=root_name,
        row_name=row_name,
        xml_declaration=xml_declaration,
        pretty_print=pretty_print,
        date_format=date_format,
    )
    return target


__all__ = ["build_xml_path", "write_xml"]
