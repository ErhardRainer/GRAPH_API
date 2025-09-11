# schema.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.params.schema — Parametrisierung: Schema, Coercion & Validierung
===============================================================================
Zweck:
    - Definiert ein leichtgewichtiges, dependency-freies "Schema-System" für
      Job-Parameter (z. B. SharePoint-List-Loads).
    - Bietet Typkonvertierung/Coercion (bool/int/columns/path/str) und
      Validierung (required/choices).
    - Optional: Aliase pro Feld (z. B. 'csvdir' → 'CSVDir').

Warum nicht Pydantic?
    - Um Abhängigkeiten gering zu halten, implementieren wir eine schlanke
      Coercion-/Validierungslogik. Eine spätere Pydantic-Integration ist
      problemlos möglich.

Begriffe:
    - "Job": Ein Parameter-Satz für eine Operation (z. B. "Lade Liste X").
    - "Schema": Deklariert Felder, Typen, Defaults, Requiredness.

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union


# ---------------------------- Coercion-Hilfsfunktionen ------------------------

def coerce_bool(val: Any, default: Optional[bool] = None) -> Optional[bool]:
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    s = str(val).strip().lower()
    if s in ("1", "true", "t", "y", "yes", "on"):
        return True
    if s in ("0", "false", "f", "n", "no", "off"):
        return False
    return default


def coerce_int(val: Any, default: Optional[int] = None) -> Optional[int]:
    if val is None or str(val).strip() == "":
        return default
    try:
        return int(val)
    except Exception:
        return default


def coerce_str(val: Any, default: Optional[str] = None) -> Optional[str]:
    if val is None:
        return default
    s = str(val)
    return s if s != "" else default


def coerce_path(val: Any, default: Optional[Path] = None) -> Optional[Path]:
    if val is None or str(val).strip() == "":
        return default
    try:
        return Path(str(val))
    except Exception:
        return default


def coerce_columns(val: Any, default: Optional[List[str]] = None) -> Optional[List[str]]:
    """
    Akzeptiert:
        - None oder "" oder "*"  → None (steht für "alle Felder")
        - List[str]               → normalisiert getrimmte Strings
        - Kommagetrennte Strings  → Liste
    """
    if val is None:
        return None
    if isinstance(val, list):
        cols = [str(c).strip() for c in val if str(c).strip()]
        return cols or None
    s = str(val).strip()
    if s == "" or s == "*":
        return None
    cols = [c.strip() for c in s.split(",") if c and c.strip()]
    return cols or None


# ------------------------------- Felddefinition -------------------------------

@dataclass
class Field:
    """
    Ein Feld im Schema mit Coercion-Strategie.
    kind:
        'str' | 'int' | 'bool' | 'path' | 'columns'
    """
    name: str
    kind: str
    required: bool = False
    default: Any = None
    choices: Optional[Sequence[Any]] = None
    aliases: Sequence[str] = field(default_factory=tuple)
    # Optional eigene Coercion-Funktion (überschreibt 'kind')
    coercer: Optional[Callable[[Any, Any], Any]] = None
    # Beschreibung (für Doku/Help-Text)
    help: str = ""

    def coerce(self, value: Any) -> Any:
        if self.coercer is not None:
            return self.coercer(value, self.default)

        if self.kind == "bool":
            return coerce_bool(value, self.default)
        if self.kind == "int":
            return coerce_int(value, self.default)
        if self.kind == "path":
            return coerce_path(value, self.default)
        if self.kind == "columns":
            return coerce_columns(value, self.default)
        # default: str
        return coerce_str(value, self.default)


@dataclass
class ParamSchema:
    """
    Sammlung von Feldern mit Coercion/Validierung.
    - Map von canonical name → Field
    - Aliase werden automatisch aufgelöst
    """
    fields: Dict[str, Field]

    # Map: alias_lower → canonical
    _alias_map: Dict[str, str] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        amap: Dict[str, str] = {}
        for canon, f in self.fields.items():
            amap[canon.lower()] = canon
            for a in f.aliases:
                amap[str(a).lower()] = canon
        self._alias_map = amap

    def canonical_key(self, key: str) -> Optional[str]:
        """Ermittelt den kanonischen Feldnamen für 'key' (inkl. Aliasauflösung)."""
        return self._alias_map.get(str(key).lower())

    def coerce_and_validate(self, raw: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
        """
        Wendet Coercion und Validierung an.
        - raw: beliebige Keys (inkl. Aliase)
        Rückgabe:
        - clean: nur bekannte Felder (kanonische Keys), coerced
        - errors: Liste Fehlertexte
        """
        clean: Dict[str, Any] = {}
        errors: List[str] = []

        # 1) Rohwerte sammeln (inkl. Aliasauflösung)
        provided: Dict[str, Any] = {}
        for k, v in (raw or {}).items():
            canon = self.canonical_key(k)
            if canon is None:
                continue  # unbekanntes Feld ignorieren
            provided[canon] = v

        # 2) Coercion & Defaults
        for canon, field in self.fields.items():
            val_raw = provided.get(canon, None)
            val = field.coerce(val_raw)
            if val is None and field.required:
                errors.append(f"Missing required parameter: {canon}")
            if val is not None and field.choices is not None:
                if val not in field.choices:
                    errors.append(f"Invalid value for {canon!r}: {val!r}. Allowed: {field.choices}")
            clean[canon] = val

        return clean, errors


# --------------------------- Vordefiniertes Schema ----------------------------

def default_sharepoint_job_schema() -> ParamSchema:
    """
    Standard-Schema für SharePoint-List-Loads (Items → DataFrame).
    - COLUMNS: None == '*' (alle Felder)
    - TOP: optional (clientseitiges Limit)
    - CreateCSV/Display: bool
    - CSVDir/CSVFile: Pfade (optional)
    - TZPolicy: String (z. B. 'utc+2')
    """
    fields = {
        "SITE_URL":   Field("SITE_URL", kind="str",  required=True,  help="SharePoint Site URL"),
        "LIST_TITLE": Field("LIST_TITLE", kind="str", required=True,  help="SharePoint List Display Title"),
        "COLUMNS":    Field("COLUMNS", kind="columns", required=False, default=None, help="None/'*' für alle Felder oder Liste interner Spalten"),
        "FILTER":     Field("FILTER", kind="str",  required=False, default=None, help="OData-Filter (z. B. Status eq 'Open')"),
        "TOP":        Field("TOP", kind="int",  required=False, default=None, help="Clientseitiges Zeilenlimit"),
        "CreateCSV":  Field("CreateCSV", kind="bool", required=False, default=False, aliases=("createcsv",), help="CSV-Export erzeugen"),
        "CSVDir":     Field("CSVDir", kind="path", required=False, default=None, aliases=("csvdir",), help="Export-Ordner"),
        "CSVFile":    Field("CSVFile", kind="path", required=False, default=None, aliases=("csvfile",), help="Legacy: Datei oder Ordner"),
        "Display":    Field("Display", kind="bool", required=False, default=True,  aliases=("display",), help="Vorschau/Anzeige aktiv"),
        "TZPolicy":   Field("TZPolicy", kind="str",  required=False, default="utc+2", aliases=("tz", "tz_policy"), help="Zeitzonen-Policy ('utc', 'utc+2', 'local')"),
        "UnknownFields": Field("UnknownFields", kind="str", required=False, default="keep", choices=("keep","drop"), help="Unbekannte Felder bei '*' mitnehmen oder verwerfen"),
    }
    return ParamSchema(fields=fields)


__all__ = [
    "Field",
    "ParamSchema",
    "coerce_bool",
    "coerce_int",
    "coerce_str",
    "coerce_path",
    "coerce_columns",
    "default_sharepoint_job_schema",
]
