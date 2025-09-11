# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.io.writers.csv_writer — Minimalistischer CSV-Writer
===============================================================================
Zweck:
    - Stark vereinfachte Schnittstelle für CSV-Export.
    - Dateiname wird aus Prefix/Postfix aufgebaut, optional mit Timestamp.
    - Gibt den *vollständigen Pfad* der erzeugten Datei zurück.

Namensschema (aktualisiert):
    <prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].csv

Parameter (öffentlich):
    - prefix:      str      — erster Namensbestandteil (wird für Dateinamen saniert)
    - postfix:     str|None — optionaler dritter Bestandteil (wird saniert)
    - timestamp:   bool     — ob Datum/Uhrzeit *zwischen* prefix und postfix angehängt
    - encoding:    str      — CSV-Encoding (Default: "utf-8-sig")
    - index:       bool     — DataFrame-Index mitschreiben (Default: False)
    - date_format: str|None — pandas date_format (Default: None)
    - overwrite:   bool     — existierende Datei überschreiben (Default: False)

Rückgabe:
    - build_csv_path(...): pathlib.Path
    - write_csv(...):      pathlib.Path (Pfad der erzeugten Datei)

Abhängigkeiten:
    * Standardbibliothek; pandas-kompatible DataFrame API (df.to_csv).
    * graphfw.core.util.sanitize_for_filename

Sicherheits-/Robustheitsverhalten:
    - Wenn overwrite=False und die Zieldatei existiert, wird automatisch ein
      eindeutiger Suffix _001, _002, ... angehängt.
    - Prefix/Postfix werden Dateinamen-sicher gemacht.
    - Schreibvorgang ist deterministisch bzgl. Namensaufbau.

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 2.1.0 (2025-09-12)
===============================================================================
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from graphfw.core.util import sanitize_for_filename


def build_csv_path(
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
) -> Path:
    """
    Erzeugt den Zielpfad (im aktuellen Arbeitsverzeichnis) für die CSV-Datei.

    Parameter
    ----------
    prefix : str
        Erster Namensbestandteil; wird für Dateinamen saniert.
    postfix : str | None, optional
        Optionaler dritter Bestandteil; wird saniert. Falls leer/None, ausgelassen.
    timestamp : bool, default True
        Ob ein Zeitstempel YYYYMMDD_hhmmss angehängt wird (zwischen prefix und postfix).

    Returns
    -------
    Path
        Vollständiger Pfad im aktuellen Arbeitsverzeichnis (cwd).

    Beispiele
    --------
    >>> build_csv_path(prefix="SiteA", postfix="ListB", timestamp=True).name
    'SiteA_20250912_133001_ListB.csv'
    """
    def _compose_filename(prefix_: str, postfix_: Optional[str], add_ts: bool) -> str:
        # Reihenfolge: prefix, (timestamp), (postfix)
        parts = [sanitize_for_filename(prefix_)]
        if add_ts:
            parts.append(datetime.now().strftime("%Y%m%d_%H%M%S"))
        if postfix_:
            parts.append(sanitize_for_filename(postfix_))
        stem = "_".join([p for p in parts if p])
        return f"{stem}.csv"

    filename = _compose_filename(prefix, postfix, timestamp)
    return Path.cwd() / filename


def write_csv(
    df: Any,
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
    encoding: str = "utf-8-sig",
    index: bool = False,
    date_format: Optional[str] = None,
    overwrite: bool = False,
) -> Path:
    """
    Schreibt ein DataFrame als CSV in das aktuelle Arbeitsverzeichnis (cwd).

    Parameter
    ----------
    df : Any
        Pandas-kompatibles DataFrame mit .to_csv(...).
    prefix : str
        Erster Namensbestandteil; wird für Dateinamen saniert.
    postfix : str | None, optional
        Optionaler dritter Bestandteil; wird saniert.
    timestamp : bool, default True
        Ob ein Zeitstempel YYYYMMDD_hhmmss *zwischen* prefix und postfix angehängt wird.
    encoding : str, default "utf-8-sig"
        Encoding für die CSV-Datei (Excel-freundlich).
    index : bool, default False
        DataFrame-Index mitschreiben.
    date_format : str | None, optional
        Format-String für Datumswerte (pandas-Option).
    overwrite : bool, default False
        Bei True wird eine existierende Datei überschrieben.
        Bei False wird automatisch ein numerischer Suffix angehängt (_001, _002, ...).

    Returns
    -------
    Path
        Vollständiger Pfad der erzeugten Datei.

    Raises
    ------
    OSError
        Falls das Schreiben fehlschlägt.
    """
    target = build_csv_path(prefix=prefix, postfix=postfix, timestamp=timestamp)

    if target.exists() and not overwrite:
        target = _next_free_path(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=index, encoding=encoding, date_format=date_format)

    return target


# --------------------------- Hilfsfunktionen (intern) ---------------------------


def _next_free_path(path: Path, *, width: int = 3) -> Path:
    """
    Liefert einen eindeutigen Pfad, indem ein numerischer Suffix angehängt wird.
    Beispiel: file.csv -> file_001.csv, file_002.csv, ...

    Parameter
    ----------
    path : Path
        Ausgangspfad.
    width : int, default 3
        Breite der führenden Nullen.

    Returns
    -------
    Path
        Nächster nicht existierender Pfad.
    """
    stem = path.stem
    suffix = path.suffix or ".csv"
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}_{counter:0{width}d}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


__all__ = ["build_csv_path", "write_csv"]
