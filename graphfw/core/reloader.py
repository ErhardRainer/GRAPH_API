"""
graphfw.core.reloader
=====================

Utility zum **Reloaden von Python-Modulen** (z. B. nach Code-Änderungen im laufenden
Notebook/Prozess) und zum **Rückgeben einer kompakten Versionsübersicht** als
`pandas.DataFrame`.

Warum als eigenes Modul?
- **Single Responsibility**: Klare Trennung von Reloading-/Diagnose-Hilfen gegenüber
  HTTP/OData/Domain-Code.
- **Wiederverwendbarkeit**: Zentraler Ort für Tools, die in Notebooks, CLI-Skripten
  oder Tests genutzt werden.
- **Testbarkeit**: Einfache, deterministische Funktionen mit klaren Rückgabewerten.

Versionen
v1.0.1 Überarbeitungen
    - **Robustere Versionserkennung**: `_to_version_str` wandelt Werte wie `("2","2","0")`,
    `2.2`, `["2","2","0"]` o. ä. in Strings um. Fallback weiterhin `"(n/a)"`.
    - **Aussagekräftiger bei Fehlern**: Falls `importlib.reload(...)` fehlschlägt, steht
    in der Tabelle **"Version after" = "(error)"** (statt "(n/a)"), und die Fehlerdetails
    sind in `info["errors"]` sowie optional in der **"Error"**-Spalte sichtbar
    (`include_error=True`).
    - **Optionale Pfad-/Fehlerspalten**: `show_paths=True` fügt *File before/after* ein,
    `include_error=True` fügt *Error* ein.
    - **Deterministische Reihenfolge**: Ausgabe folgt exakt der Reihenfolge der Eingabe.
v1.0.0 - initale Version
Funktionen
----------
- `reload_df(module_names, *, show_paths=False, tolerant=True, include_error=False)
   -> tuple[pd.DataFrame, dict]`

    Lädt/Reloaded angegebene Modulnamen und liefert einen DataFrame:

        | Module                                   | Version before | Version after |
        |------------------------------------------|----------------|---------------|
        | graphfw.domains.sharepoint.lists.columns | 2.1.0          | 2.2.0         |

    Optional:
      - `show_paths=True`  → Spalten *File before*, *File after*
      - `include_error=True` → Spalte *Error* mit kompaktem Fehlersummary

Hinweise
--------
- **Versionsermittlung**: Reihenfolge `__version__` | `VERSION` | `version`.
  Werte werden zu String normalisiert.
- **Sicherheit**: Es werden keine Secrets geloggt oder Tokens verarbeitet.
- **Determinismus**: Die Reihenfolge der Ausgabe entspricht der Eingabereihenfolge.

Beispiel
--------
>>> from graphfw.core.reloader import reload_df
>>> df, info = reload_df([
...     "graphfw.domains.sharepoint.lists.columns",
... ])
>>> print(df)

Diagnose (empfohlen)
--------------------
>>> df, info = reload_df(
...     ["graphfw.domains.sharepoint.lists.columns"],
...     show_paths=True,
...     include_error=True
... )
>>> print(df)
>>> print(info["errors"])
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib
import types
from typing import Iterable, Sequence, Tuple, Dict, Any, Optional, List
import traceback
import pandas as pd
from datetime import datetime


__all__ = ["reload_df"]
__version__ = "1.0.1"

@dataclass
class _ModReport:
    """Interner Datensatz je Modul für die tabellarische Ausgabe + Diagnostics."""
    name: str
    version_before: str
    version_after: str
    file_before: str
    file_after: str
    reloaded: bool
    error: Optional[str]


def _to_version_str(val: Any) -> str:
    """
    Normalisiert verschiedene Versionstypen zu einem String.
    Beispiele:
      - "2.2.0"        -> "2.2.0"
      - (2, 2, 0)      -> "2.2.0"
      - ["2","2","0"]  -> "2.2.0"
      - 2.2            -> "2.2"
    """
    if val is None:
        return "(n/a)"
    if isinstance(val, str):
        s = val.strip()
        return s or "(n/a)"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (list, tuple)):
        try:
            return ".".join(str(x) for x in val)
        except Exception:
            return str(val)
    return str(val)


def _safe_get_version(mod: Optional[types.ModuleType]) -> str:
    """
    Ermittelt eine menschenlesbare Versionsangabe eines Moduls, ohne Funktionsaufrufe
    auszuführen. Reihenfolge: __version__ | VERSION | version. Sonst '(n/a)'.
    """
    if not isinstance(mod, types.ModuleType):
        return "(n/a)"
    for attr in ("__version__", "VERSION", "version"):
        if hasattr(mod, attr):
            return _to_version_str(getattr(mod, attr))
    return "(n/a)"


def _safe_get_file(mod: Optional[types.ModuleType]) -> str:
    """Gibt den Moduldateipfad zurück, wenn verfügbar."""
    if not isinstance(mod, types.ModuleType):
        return "(n/a)"
    return getattr(mod, "__file__", "(n/a)") or "(n/a)"


def _import_or_none(name: str) -> Optional[types.ModuleType]:
    """Importiert ein Modul, gibt None bei Fehler zurück (Fehler wird später erfasst)."""
    try:
        return importlib.import_module(name)
    except Exception:
        return None


def reload_df(
    module_names: Sequence[str] | Iterable[str],
    *,
    show_paths: bool = False,
    tolerant: bool = True,
    include_error: bool = False,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Reloadet die angegebenen Module (per `importlib.reload`) und liefert eine kompakte
    Übersicht als DataFrame.

    Parameter
    ---------
    module_names : Sequence[str] | Iterable[str]
        Vollqualifizierte Modulnamen (z. B. "graphfw.domains.sharepoint.lists.columns").
        Die Reihenfolge in der Eingabe bestimmt die Reihenfolge in der Ausgabe.
    show_paths : bool, default False
        Wenn True, werden zusätzliche Spalten `File before` und `File after` ausgegeben.
    tolerant : bool, default True
        Wenn True, werden Import-/Reload-Fehler pro Modul erfasst und die Verarbeitung
        für die übrigen Module fortgesetzt. Wenn False, wird beim ersten Fehler eine
        Exception geworfen.
    include_error : bool, default False
        Wenn True, ergänzt die Ausgabe eine Spalte `Error` mit einer kompakten
        Fehlermeldung (leer bei Erfolg).

    Rückgabe
    --------
    (df, info) : tuple[pandas.DataFrame, dict]
        df   : DataFrame mit Spalten:
               - Immer: "Module", "Version before", "Version after"
               - Zusätzlich, wenn show_paths=True: "File before", "File after"
               - Zusätzlich, wenn include_error=True: "Error"
        info : Diagnostik-Dict mit u. a.:
               - "attempted": Liste der Modulnamen
               - "timestamp": ISO-Zeitstempel
               - "reports"  : Liste der internen Report-Datensätze (inkl. Fehlertext)
               - "errors"   : Mapping modulname -> error (falls vorhanden)
               - "success"  : Anzahl erfolgreicher Reloads
               - "failed"   : Anzahl Fehlversuche

    Beispiel
    --------
    >>> from graphfw.core.reloader import reload_df
    >>> df, info = reload_df([
    ...     "graphfw.domains.sharepoint.lists.columns",
    ... ])
    >>> df
    """
    names: List[str] = list(module_names)
    reports: List[_ModReport] = []
    errors: Dict[str, str] = {}

    for name in names:
        # Zustand VOR dem Reload erfassen (falls schon importiert)
        mod_before = _import_or_none(name)
        ver_before = _safe_get_version(mod_before)
        file_before = _safe_get_file(mod_before)

        ver_after = "(n/a)"
        file_after = "(n/a)"
        reloaded = False
        err_text: Optional[str] = None

        try:
            # Erstimport, falls bisher nicht importiert
            if mod_before is None:
                mod_before = importlib.import_module(name)
                ver_before = _safe_get_version(mod_before)
                file_before = _safe_get_file(mod_before)

            # Reload
            mod_after = importlib.reload(mod_before)
            reloaded = True
            ver_after = _safe_get_version(mod_after)
            file_after = _safe_get_file(mod_after)

        except Exception as e:
            tb = traceback.format_exc(limit=2)
            err_text = f"{e.__class__.__name__}: {e}"
            if tb:
                # letzte Zeile reicht als kompakter Hinweis
                err_text = err_text + " | " + (tb.strip().splitlines()[-1] or "")
            errors[name] = err_text
            if not tolerant:
                # Im nicht-toleranten Modus direkt eskalieren
                raise
            # Sprechendere Ausgabe im DF bei Fehler
            ver_after = "(error)"
            file_after = file_before

        reports.append(
            _ModReport(
                name=name,
                version_before=ver_before,
                version_after=ver_after,
                file_before=file_before,
                file_after=file_after,
                reloaded=reloaded,
                error=err_text,
            )
        )

    # DataFrame bauen – Standardansicht mit exakt den gewünschten Spaltennamen
    data = {
        "Module": [r.name for r in reports],
        "Version before": [r.version_before for r in reports],
        "Version after": [r.version_after for r in reports],
    }
    if show_paths:
        data["File before"] = [r.file_before for r in reports]
        data["File after"] = [r.file_after for r in reports]
    if include_error:
        data["Error"] = [r.error or "" for r in reports]

    df = pd.DataFrame(data)

    info: Dict[str, Any] = {
        "attempted": names,
        "timestamp": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "reports": [r.__dict__ for r in reports],
        "errors": errors,
        "success": sum(1 for r in reports if r.error is None and r.reloaded),
        "failed": sum(1 for r in reports if r.error is not None),
    }
    return df, info
