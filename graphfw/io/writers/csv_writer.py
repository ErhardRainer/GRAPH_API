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
    - directory:   Pfadangabe (str | os.PathLike | pathlib.Path | None) —
                   Zielordner für die Datei (plattformneutral). Bei None: cwd.

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
Version: 2.2.0 (2025-09-12)
===============================================================================
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Any, Optional, Union

from graphfw.core.util import sanitize_for_filename

# Typalias für Pfadangaben
PathLike = Union[str, os.PathLike[str], Path]


def build_csv_path(
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
) -> Path:
    """
    Erzeugt den Zielpfad (im aktuellen Arbeitsverzeichnis) für die CSV-Datei.

    Hinweis: Diese Funktion erzeugt **nur den Dateinamen im cwd**. Für ein
    abweichendes Verzeichnis nutze `write_csv(..., directory=...)`.
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
    directory: Optional[PathLike] = None,
) -> Path:
    """
    Schreibt ein DataFrame als CSV in `directory` (oder `cwd`, falls None) und
    gibt den vollständigen Pfad zurück.

    `directory` ist plattformneutral (Windows & Linux) dank `pathlib.Path`.
    `~` wird aufgelöst, relative Pfade sind erlaubt.
    """
    # 1) Basis-Dateiname (nur Name) gemäß Namensschema erzeugen
    name_only = build_csv_path(prefix=prefix, postfix=postfix, timestamp=timestamp).name

    # 2) Zielverzeichnis auflösen (Standard: aktuelles Arbeitsverzeichnis)
    base_dir = Path.cwd() if directory is None else Path(directory).expanduser()

    # 3) Zielpfad zusammensetzen
    target = base_dir / name_only

    # 4) Eindeutigen Namen bestimmen, falls nicht überschrieben werden soll
    if target.exists() and not overwrite:
        target = _next_free_path(target)

    # 5) Verzeichnis anlegen und CSV schreiben
    target.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(target, index=index, encoding=encoding, date_format=date_format)

    return target


# --------------------------- Hilfsfunktionen (intern) ---------------------------


def _next_free_path(path: Path, *, width: int = 3) -> Path:
    """
    Liefert einen eindeutigen Pfad, indem ein numerischer Suffix angehängt wird.
    Beispiel: file.csv -> file_001.csv, file_002.csv, ...
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
