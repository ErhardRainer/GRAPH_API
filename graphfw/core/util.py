# util.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.util — Helfer: TZ-Policy, GUID-Strip, Encoding, SP-Name-Encoding
===============================================================================
Zweck:
    - Datum/Zeit Normalisierung gemäß tz_policy (z. B. 'utc', 'utc+2', 'local')
    - GUID-Klammern entfernen
    - UTF-8-Konsolenerkennung
    - SharePoint-InternalName Encoding (" "→_x0020_, "-"→_x002d_, "/"→_x002f_)
    - Dateinamen-Sanitizer
    - Masking sensibler Felder (Secrets)
    - Deep-Get (obj['a']['b']...), Typ-Coercion (optional, pandas)

Abhängigkeiten:
    * Standardbibliothek; pandas optional (für Type-Coercion/DF-Funktionen)

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from typing import Any, Dict, Iterable, Mapping, Optional, Sequence, Tuple, Union
from datetime import datetime, timezone, timedelta
import sys
import locale
import re

# ------------------------------ UTF-8 / Console -------------------------------

def supports_utf8_stdout() -> bool:
    enc = (getattr(sys.stdout, "encoding", None) or locale.getpreferredencoding(False) or "").lower()
    return "utf" in enc


ELLIPSIS = "…" if supports_utf8_stdout() else "..."


# ------------------------------ GUID / Masking --------------------------------

def strip_guid_braces(value: Any) -> Any:
    """Entfernt führende/abschließende { } in GUID-Strings."""
    if isinstance(value, str) and len(value) >= 2 and value[0] == "{" and value[-1] == "}":
        return value[1:-1]
    return value


def mask_secrets(d: Mapping[str, Any], *, mask_keys: Sequence[str] = ("client_secret", "password", "secret", "token")) -> Dict[str, Any]:
    """
    Gibt eine Kopie von 'd' zurück, in der Werte unterhalb bestimmter Keys maskiert sind.
    - Fall-insensitiver Key-Vergleich (enthält-Logik).
    """
    out: Dict[str, Any] = {}
    for k, v in d.items():
        k_lc = str(k).lower()
        if any(m in k_lc for m in mask_keys):
            out[k] = "***"
        else:
            out[k] = v
    return out


# ------------------------------ SharePoint Encoding ---------------------------

def sp_encode_internal_name(s: str) -> str:
    """
    Heuristik, um von Anzeigenamen Richtung internalName zu mappen:
        " " -> _x0020_, "-" -> _x002d_, "/" -> _x002f_
    Hinweis: Das ist eine Heuristik; die tatsächlichen internen Namen hängen
    von der Liste ab. Für robustes Mapping immer Columns-Metadaten nutzen.
    """
    return (s.replace(" ", "_x0020_")
             .replace("-", "_x002d_")
             .replace("/", "_x002f_"))


# ------------------------------ DateTime / TZ-Policy --------------------------

_ISO_Z_RE = re.compile(r"Z$")

def parse_iso_datetime(value: Union[str, datetime]) -> Optional[datetime]:
    """
    Parst ISO-8601 Datumsstrings in einen timezone-aware datetime (UTC).
    - Unterstützt 'Z' Suffix.
    - Gibt bei Unlesbarkeit None zurück.
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        # Stelle sicher, dass wir 'aware' in UTC haben
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    s = str(value).strip()
    if not s:
        return None
    try:
        # Python <3.11 zickt bei 'Z' -> ersetzen
        s = _ISO_Z_RE.sub("+00:00", s)
        dt = datetime.fromisoformat(s)
        # Wenn naive: als UTC interpretieren
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def parse_tz_policy(tz_policy: str) -> timezone:
    """
    'utc' → UTC
    'utc+2' / 'utc-5' → feste Offset-Zeitzone
    'local' → lokale System-TZ
    """
    s = (tz_policy or "utc").strip().lower()
    if s == "utc":
        return timezone.utc
    if s == "local":
        return datetime.now().astimezone().tzinfo or timezone.utc
    if s.startswith("utc+"):
        try:
            hours = float(s[4:])
            return timezone(timedelta(hours=hours))
        except Exception:
            return timezone.utc
    if s.startswith("utc-"):
        try:
            hours = float(s[4:])
            return timezone(timedelta(hours=-hours))
        except Exception:
            return timezone.utc
    return timezone.utc


def apply_tz_policy(value: Union[str, datetime, None], tz_policy: str = "utc", *, return_naive: bool = True) -> Optional[datetime]:
    """
    Konvertiert einen Zeitwert gemäß tz_policy und gibt standardmäßig
    einen *naiven* datetime (ohne tzinfo) zurück – praktisch für DataFrames.

    Beispiele:
        apply_tz_policy("2025-09-01T12:34:56Z", "utc+2") -> 2025-09-01 14:34:56 (naiv)
        apply_tz_policy(dt_obj, "utc", return_naive=False) -> aware UTC datetime
    """
    if value is None:
        return None
    dt_utc = parse_iso_datetime(value)
    if dt_utc is None:
        return None
    target_tz = parse_tz_policy(tz_policy)
    dt = dt_utc.astimezone(target_tz)
    return dt.replace(tzinfo=None) if return_naive else dt


# ------------------------------ Dateinamen / Pfade ----------------------------

_SAFE_CHARS_RE = re.compile(r"[^A-Za-z0-9\-_.]")

def sanitize_for_filename(value: str) -> str:
    """Entfernt kritische Zeichen und normiert Mehrfach-Unterstriche."""
    val = (value or "").strip().replace(" ", "_")
    val = _SAFE_CHARS_RE.sub("_", val)
    val = re.sub(r"_+", "_", val).strip("_")
    return val or "NA"


# ------------------------------ Deep-Get / DF-Utils ---------------------------

def deep_get(obj: Any, path: str, default: Any = None) -> Any:
    """Navigiert 'a.b.c' in dicts; gibt default zurück, wenn Segment fehlt."""
    cur = obj
    for seg in path.split("."):
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        else:
            return default
    return cur


def coerce_types_df(df, mapping: Mapping[str, str], *, tz_policy: str = "utc") -> Any:
    """
    Optionale Typumwandlung in DataFrames gemäß mapping:
        - "datetime": ISO -> datetime (tz_policy, naiv per Default)
        - "int", "float", "bool", "str": einfache Umwandlungen (fehlertolerant)
    Abhängig von pandas; bei Importfehler wird das DF unverändert zurückgegeben.
    """
    try:
        import pandas as pd  # noqa
    except Exception:
        return df

    if df is None or getattr(df, "empty", False):
        return df

    for col, typ in mapping.items():
        if col not in df.columns:
            continue
        series = df[col]
        try:
            if typ == "datetime":
                df[col] = series.apply(lambda x: apply_tz_policy(x, tz_policy=tz_policy, return_naive=True))
            elif typ == "int":
                df[col] = pd.to_numeric(series, errors="coerce").astype("Int64")
            elif typ == "float":
                df[col] = pd.to_numeric(series, errors="coerce")
            elif typ == "bool":
                df[col] = series.map(lambda v: str(v).strip().lower() in ("1","true","t","y","yes"))
            elif typ == "str":
                df[col] = series.astype(str)
        except Exception:
            # stillschweigend fortfahren; optional könnte man loggen
            pass
    return df


def reorder_columns_df(df, head: Optional[Sequence[str]] = None, tail: Optional[Sequence[str]] = None) -> Any:
    """
    Bestimmt eine deterministische Spaltenreihenfolge:
        - 'head' Spalten zuerst (in angegebener Reihenfolge, wenn vorhanden)
        - dann alle restlichen in bestehender Reihenfolge
        - 'tail' Spalten zuletzt (in angegebener Reihenfolge, wenn vorhanden)
    """
    try:
        import pandas as pd  # noqa
    except Exception:
        return df

    cols = list(df.columns)
    head = [c for c in (head or []) if c in cols]
    tail = [c for c in (tail or []) if c in cols]
    mid = [c for c in cols if c not in head and c not in tail]
    new_order = head + mid + tail
    return df.loc[:, new_order]


__all__ = [
    "supports_utf8_stdout",
    "ELLIPSIS",
    "strip_guid_braces",
    "mask_secrets",
    "sp_encode_internal_name",
    "parse_iso_datetime",
    "parse_tz_policy",
    "apply_tz_policy",
    "sanitize_for_filename",
    "deep_get",
    "coerce_types_df",
    "reorder_columns_df",
]
