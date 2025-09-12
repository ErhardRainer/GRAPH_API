# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.io.writers.xml_writer — Robuster XML-Writer (pandas-kompatibel)
===============================================================================
Zweck:
    - Export einer Tabellenstruktur (pandas.DataFrame-kompatibel) als XML-Datei.
    - Einheitliches Namensschema:
        <prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].xml
    - Gibt den *vollständigen Pfad* der erzeugten Datei zurück.

Wichtig:
    - Diese Implementierung reicht *kein* unbekanntes Argument an
      DataFrame.to_xml weiter. Insbesondere wird `date_format` NICHT an
      pandas.to_xml übergeben (Workaround für Fehlermeldung
      "unexpected keyword argument 'date_format'").
    - Falls `DataFrame.to_xml` nicht verfügbar ist (pandas < 1.3), greift
      ein Fallback auf xml.etree.ElementTree.

Öffentliche API:
    - build_xml_path(...)
    - write_xml(...)

Parameter (write_xml):
    - df:              pandas-kompatibles DataFrame (muss .to_dict('records') o.ä. unterstützen)
    - prefix:          str        — erster Namensbestandteil (Dateinamen-sicher)
    - postfix:         str|None   — optionaler letzter Bestandteil (Dateinamen-sicher)
    - timestamp:       bool       — ob Datum/Uhrzeit zwischen prefix und postfix steht
    - directory:       str|pathlib.Path|None — Zielverzeichnis (Default: None → CWD).
                         • Unterstützt Windows- und Linux-Pfade.
                         • Relative Pfade werden gegen CWD aufgelöst.
    - encoding:        str        — Text-Encoding (Default: "utf-8")
    - index:           bool       — Index mitschreiben (Default: False)
    - date_format:     str|None   — Vorformatierung von Datums-/Datetime-Spalten via strftime(fmt)
    - root_name:       str        — Wurzel-Element (Default: "data")
    - row_name:        str        — Zeilen-Element (Default: "row")
    - xml_declaration: bool       — XML-Deklaration schreiben (Default: True)
    - pretty_print:    bool       — Einrückungen/Zeilenumbrüche (Default: True)
    - overwrite:       bool       — existierende Datei überschreiben (Default: False)

Rückgabe:
    - write_xml(...): pathlib.Path (absoluter Pfad)

Abhängigkeiten:
    * Standardbibliothek; optional pandas (falls vorhanden).

Autor: graphfw
Version: 1.3.0 (2025-09-12)
===============================================================================
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Optional, Union

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


def _normalize_directory(directory: Optional[Union[str, Path]]) -> Path:
    """
    Normalisiert das Zielverzeichnis:
    - None  -> CWD
    - str/Path (relativ) -> relativ zu CWD
    - Rückgabe ist stets ein *absoluter* Path (existiert u.U. noch nicht).
    """
    if directory is None or (isinstance(directory, str) and not directory.strip()):
        base = Path.cwd()
    else:
        base = Path(directory)
        if not base.is_absolute():
            base = Path.cwd() / base
    # resolve ohne strict, damit Pfad auch ohne Existenz absolut wird
    try:
        base = base.expanduser().resolve(strict=False)
    except Exception:
        base = base.expanduser()
    return base


def build_xml_path(
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
    directory: Optional[Union[str, Path]] = None,
) -> Path:
    """
    Erzeugt den Zielpfad für die XML-Datei.

    Parameters
    ----------
    prefix : str
        Erster Namensbestandteil.
    postfix : Optional[str], default None
        Optionaler letzter Namensbestandteil.
    timestamp : bool, default True
        Ob Datum/Uhrzeit zwischen prefix und postfix steht.
    directory : str | Path | None, default None
        Zielverzeichnis (Windows- und Linux-kompatibel). Relative Pfade werden
        gegen CWD aufgelöst.

    Returns
    -------
    Path
        Absoluter Pfad (Datei wird nicht erstellt).
    """
    filename = _compose_filename(prefix, postfix, timestamp, "xml")
    target_dir = _normalize_directory(directory)
    return target_dir / filename


def _apply_date_format_if_requested(df: Any, fmt: Optional[str]) -> Any:
    """
    Gibt eine Kopie des DF zurück, in der Datums-/Datetime-Spalten via strftime(fmt)
    in Strings konvertiert wurden. Wenn fmt None ist oder pandas fehlt, wird df unverändert
    zurückgegeben.
    """
    if not fmt:
        return df
    try:
        import pandas as pd  # noqa: F401
        from pandas.api.types import is_datetime64_any_dtype  # type: ignore
    except Exception:
        # Fallback: keine Formatierung möglich
        return df

    try:
        out = df.copy()
    except Exception:
        # falls kein echtes DF, einfach zurückgeben
        return df

    for col in getattr(out, "columns", []):
        s = out[col]
        # reine datetime64*-Spalten
        try:
            if is_datetime64_any_dtype(s):
                out[col] = s.dt.strftime(fmt)
                continue
        except Exception:
            pass
        # object-Spalten mit überwiegend datetime-ähnlichen Werten
        try:
            if getattr(s, "dtype", None) == "object":
                conv = pd.to_datetime(s, errors="coerce")  # type: ignore[name-defined]
                non_na = getattr(conv, "notna", lambda: False)()
                if int(non_na.sum()) >= max(1, int(0.5 * len(s))):
                    out[col] = conv.dt.strftime(fmt).where(conv.notna(), s)
        except Exception:
            # best-effort, bei Fehlern Spalte unverändert lassen
            pass
    return out


def _infer_columns_from_like_df(df: Any) -> Iterable[str]:
    cols = getattr(df, "columns", None)
    if cols is not None:
        return list(cols)
    # Minimal-Fallback: versuche aus erstem Record
    records = None
    try:
        records = list(df)  # type: ignore[assignment]
    except Exception:
        pass
    if records and isinstance(records[0], dict):
        return list(records[0].keys())
    return []


def _write_xml_fallback(
    df: Any,
    target: Path,
    *,
    encoding: str,
    index: bool,
    root_name: str,
    row_name: str,
    xml_declaration: bool,
    pretty_print: bool,
) -> None:
    """
    Fallback ohne pandas.to_xml: nutzt xml.etree.ElementTree
    """
    import xml.etree.ElementTree as ET

    root = ET.Element(root_name)

    # Records erzeugen
    try:
        records = df.to_dict(orient="records")  # pandas-like
    except Exception:
        # generischer Versuch
        try:
            records = [dict(r) for r in df]  # Iterable[Mapping]
        except Exception:
            raise TypeError(
                "write_xml: df ist nicht DataFrame-kompatibel (erwartet .to_dict('records') "
                "oder Iterable[Mapping])."
            )

    cols = list(_infer_columns_from_like_df(df))
    for rec in records:
        row_el = ET.SubElement(root, row_name)
        # deterministische Spaltenreihenfolge
        keys = cols if cols else list(rec.keys())
        for k in keys:
            v = rec.get(k, None)
            # None -> leeres Element
            child = ET.SubElement(row_el, str(k))
            if v is None:
                child.text = ""
            else:
                child.text = str(v)

        if index:
            # optional Index als Attribut (nicht implementiert im Fallback)
            pass

    # Pretty Print optional
    if pretty_print:
        try:
            # Einrückung (Python 3.9+)
            ET.indent(root, space="  ")  # type: ignore[attr-defined]
        except Exception:
            pass

    tree = ET.ElementTree(root)
    with open(target, "wb") as f:
        if xml_declaration:
            tree.write(f, encoding=encoding, xml_declaration=True)
        else:
            tree.write(f, encoding=encoding, xml_declaration=False)


def _to_xml_compat(
    df: Any,
    target: Path,
    *,
    encoding: str,
    index: bool,
    root_name: str,
    row_name: str,
    xml_declaration: bool,
    pretty_print: bool,
) -> None:
    """
    Ruft DataFrame.to_xml auf, filtert aber strikt nur die Parameter durch,
    die die jeweilige pandas-Version auch unterstützt. Falls .to_xml fehlt,
    nutzt der Fallback-Writer.
    """
    to_xml = getattr(df, "to_xml", None)
    if to_xml is None:
        _write_xml_fallback(
            df,
            target,
            encoding=encoding,
            index=index,
            root_name=root_name,
            row_name=row_name,
            xml_declaration=xml_declaration,
            pretty_print=pretty_print,
        )
        return

    # Nur unterstützte Parameter durchreichen
    try:
        import inspect

        sig = inspect.signature(to_xml)
        allowed = set(sig.parameters.keys())
        kwargs = {
            "path_or_buffer": target if "path_or_buffer" in allowed else target,
            "index": index if "index" in allowed else None,
            "encoding": encoding if "encoding" in allowed else None,
            "root_name": root_name if "root_name" in allowed else None,
            "row_name": row_name if "row_name" in allowed else None,
            "xml_declaration": xml_declaration if "xml_declaration" in allowed else None,
            "pretty_print": pretty_print if "pretty_print" in allowed else None,
        }
        # Entferne None-Keys und Keys, die nicht erlaubt sind
        clean_kwargs = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
        to_xml(**clean_kwargs)
    except Exception:
        # jede unerwartete Inkompatibilität -> robuster Fallback
        _write_xml_fallback(
            df,
            target,
            encoding=encoding,
            index=index,
            root_name=root_name,
            row_name=row_name,
            xml_declaration=xml_declaration,
            pretty_print=pretty_print,
        )


def write_xml(
    df: Any,
    *,
    prefix: str,
    postfix: Optional[str] = None,
    timestamp: bool = True,
    directory: Optional[Union[str, Path]] = None,
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
    Schreibt ein DataFrame als XML.

    Notes
    -----
    - `date_format` wird *vor* dem Schreiben angewandt (strftime) und NICHT
      an pandas.to_xml übergeben (vermeidet TypeError bei älteren pandas).
    - `directory` erlaubt plattformunabhängig (Windows/Linux) absolute oder relative
      Zielverzeichnisse. Der Rückgabepfad ist absolut.

    Returns
    -------
    Path
        Absoluter Pfad der erzeugten XML-Datei.

    Examples
    --------
    >>> # df ist ein pandas.DataFrame
    >>> path = write_xml(df, prefix="Export", postfix="Orders", timestamp=True,
    ...                  directory="out/xml", root_name="items", row_name="item")
    >>> path.exists()
    True
    """
    target = build_xml_path(
        prefix=prefix,
        postfix=postfix,
        timestamp=timestamp,
        directory=directory,
    )

    if target.exists() and not overwrite:
        target = _next_free_path(target)

    # Zielordner anlegen
    target.parent.mkdir(parents=True, exist_ok=True)

    # Vorformatierung von Datumsfeldern (NICHT an to_xml weiterreichen!)
    df_to_write = _apply_date_format_if_requested(df, date_format)

    # pandas >= 1.3: to_xml vorhanden; sonst Fallback
    _to_xml_compat(
        df_to_write,
        target,
        encoding=encoding,
        index=index,
        root_name=root_name,
        row_name=row_name,
        xml_declaration=xml_declaration,
        pretty_print=pretty_print,
    )

    return target


__all__ = ["build_xml_path", "write_xml"]
