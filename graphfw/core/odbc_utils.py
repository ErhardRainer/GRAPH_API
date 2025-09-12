# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.odbc_utils — ODBC-/SQL-Fallbacks & Diagnose
===============================================================================
Funktionen
----------
- list_odbc_drivers():     ODBC-Treiber auflisten (SQL Server priorisiert)
- list_odbc_data_sources():ODBC-DSNs auflisten
- diagnose_sql_connection(settings, ...): SQLAlchemy+pyodbc Diagnose (SELECT 1)
- try_pyodbc_direct(settings, ...):      pyodbc DSN-less ohne SQLAlchemy
- try_ado_msoledb(settings, ...):        ADO/OLE DB (Provider=MSOLEDBSQL), Windows-only
- try_pymssql(settings, ...):            pymssql TDS-Client (optional)
- diagnose_with_fallbacks(settings, ...):kombiniert alle Wege inkl. Hinweise

Voraussetzungen
---------------
- pyodbc + sqlalchemy (für ODBC/SQLAlchemy-Pfad)
- optional: pywin32 (win32com) für ADO/OLE DB
- optional: pymssql (TDS-Client)

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 1.1.0 (2025-09-12)
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple
import contextlib
import platform
import time

# Optionale Abhängigkeiten vorsichtig importieren
try:
    import pyodbc  # type: ignore
except Exception:
    pyodbc = None  # type: ignore

try:
    import win32com.client  # type: ignore
except Exception:
    win32com = None  # type: ignore

try:
    import pymssql  # type: ignore
except Exception:
    pymssql = None  # type: ignore

from sqlalchemy import text
from sqlalchemy.engine import Engine

# ---- Lazy Import: build_engine, damit wir keine Zyklen erzeugen -------------
def _build_engine(cfg: Dict[str, Any], db_name: str,
                  username: Optional[str], password: Optional[str]) -> Engine:
    from graphfw.io.writers.sql_writer import build_engine  # lazy import
    return build_engine(cfg, db_name=db_name, username=username, password=password)


def _mask(s: Optional[str], head: int = 4, tail: int = 2) -> str:
    if not s:
        return ""
    return (s[:head] + "…" + s[-tail:]) if len(s) > (head + tail) else "*" * len(s)


# --------------------------- Treiber/DSN Auflisten ----------------------------

def list_odbc_drivers(*, only_sql_server: bool = True, sort_sql_first: bool = True) -> List[str]:
    """Liefert installierte ODBC-Treiber (via pyodbc.drivers())."""
    if pyodbc is None:
        return []
    drivers = list(pyodbc.drivers())  # type: ignore[attr-defined]
    if only_sql_server:
        drivers = [d for d in drivers if "sql server" in d.lower()]
    if sort_sql_first:
        def _key(d: str) -> Tuple[int, int, str]:
            dl = d.lower()
            if "odbc driver 18 for sql server" in dl:
                return (0, 0, d)
            if "odbc driver 17 for sql server" in dl:
                return (0, 1, d)
            return (1, 9, d)
        drivers.sort(key=_key)
    return drivers


def list_odbc_data_sources() -> Dict[str, str]:
    """Liefert ODBC-Datenquellen (DSNs) als {name: driver}."""
    if pyodbc is None:
        return {}
    try:
        return dict(pyodbc.dataSources())  # type: ignore[attr-defined]
    except Exception:
        return {}


# ------------------------------ Diagnose (ODBC) -------------------------------

@dataclass(frozen=True)
class _Attempt:
    method: str
    driver: Optional[str]
    params: Optional[str]
    detail: str


def _merge_params(base_params: Optional[str], extra_params: Dict[str, Optional[str]]) -> str:
    """Ersetzt/ergänzt Query-Parameter (case-insensitive Keys)."""
    parts: List[Tuple[str, str]] = []
    seen = set()

    def _add(k: str, v: Optional[str]) -> None:
        kl = k.lower()
        if kl in seen:
            for i, (ek, _) in enumerate(parts):
                if ek.lower() == kl:
                    parts[i] = (k, "" if v is None else str(v))
                    return
        else:
            seen.add(kl)
            parts.append((k, "" if v is None else str(v)))

    if base_params:
        for piece in base_params.split("&"):
            piece = piece.strip()
            if not piece:
                continue
            if "=" in piece:
                k, v = piece.split("=", 1)
            else:
                k, v = piece, ""
            _add(k, v)

    for k, v in extra_params.items():
        _add(k, v)

    return "&".join(f"{k}={v}" if v != "" else k for k, v in parts)


def diagnose_sql_connection(settings, *,
                            try_driver_toggle: bool = True,
                            try_encrypt_toggle: bool = True,
                            try_trust_toggle: bool = True) -> Tuple[bool, Dict[str, Any]]:
    """
    Basispfad: SQLAlchemy + pyodbc. Testet SELECT 1 mit
    - Driver 18/17/… (falls vorhanden)
    - Encrypt / TrustServerCertificate toggles
    """
    drivers = list_odbc_drivers(only_sql_server=True, sort_sql_first=True) or []
    driver_candidates = []
    if settings.driver:
        driver_candidates.append(settings.driver)
    for d in drivers:
        if d not in driver_candidates:
            driver_candidates.append(d)
    if not driver_candidates:
        driver_candidates = ["ODBC Driver 17 for SQL Server"]

    encrypt_opts = [None] + ([True, False] if try_encrypt_toggle else [])
    trust_opts = [None] + ([True, False] if try_trust_toggle else [])

    results: List[Dict[str, Any]] = []
    success: Optional[Dict[str, Any]] = None

    for drv in driver_candidates:
        for enc in encrypt_opts:
            for tr in trust_opts:
                # nicht alle Kombinationen explodieren lassen
                if enc is None and tr is None and drv != driver_candidates[0]:
                    continue

                params = _merge_params(settings.params or "", {
                    "Encrypt": ("yes" if enc else "no") if enc is not None else None,
                    "TrustServerCertificate": ("yes" if tr else "no") if tr is not None else None
                })
                cfg = {"server": settings.server, "driver": drv}
                if params:
                    cfg["params"] = params

                t0 = time.time()
                err_txt = ""
                ok = False
                try:
                    eng = _build_engine(cfg, db_name=settings.db_name,
                                        username=settings.username, password=settings.password)
                    with eng.connect() as c:
                        _ = c.execute(text("SELECT 1")).scalar()
                    ok = True
                except Exception as ex:
                    err_txt = f"{type(ex).__name__}: {ex}"
                    if getattr(ex, "orig", None) is not None and hasattr(ex.orig, "args"):
                        with contextlib.suppress(Exception):
                            err_txt = f"{err_txt} | orig={ex.orig.args}"
                dt = round(time.time() - t0, 3)
                rec = {
                    "method": "sqlalchemy+pyodbc",
                    "driver": drv, "params": params, "ok": ok,
                    "duration_s": dt, "error": "" if ok else err_txt
                }
                results.append(rec)
                if ok and success is None:
                    success = rec

    suggestions: List[str] = []
    if not success:
        has_18456 = any("18456" in (r.get("error") or "") for r in results)
        if has_18456:
            suggestions += [
                "Fehler 18456 (Login failed) – Benutzer/Passwort prüfen, Login-Typ (SQL vs Windows) abgleichen.",
                "Falls Domänenkonto: 'Trusted_Connection=yes' verwenden (ohne Username/Password).",
                "Default-Datenbank des Logins prüfen; testweise DB explizit setzen.",
            ]
        enc_issue = any("SSL" in (r.get("error") or "") or "encrypt" in (r.get("error") or "").lower() for r in results)
        if enc_issue:
            suggestions += [
                "Encrypt=yes setzen (bes. Driver 17) und ggf. TrustServerCertificate=yes (Testumgebung).",
            ]
        drivers_all = list_odbc_drivers()
        if drivers_all:
            suggestions.append(f"Alternative ODBC-Treiber versuchen: {drivers_all}")
        else:
            suggestions.append("Keine SQL Server ODBC-Treiber gefunden – Driver 18/17 installieren.")

    info: Dict[str, Any] = {
        "summary": ("Verbindung OK" if success else "ODBC-Pfad gescheitert"),
        "attempts": results,
        "suggestions": suggestions,
        "settings_preview": {
            "server": settings.server,
            "db_name": settings.db_name,
            "username_masked": _mask(settings.username),
            "driver_initial": settings.driver,
            "params_initial": settings.params,
        }
    }
    return (success is not None), info


# ------------------------------- Fallback 1: pyodbc direct --------------------

def try_pyodbc_direct(settings, *, driver: Optional[str] = None,
                      encrypt: Optional[bool] = None,
                      trust: Optional[bool] = None,
                      timeout: int = 8) -> Tuple[bool, Dict[str, Any]]:
    """
    Direkter pyodbc-Connect (ohne SQLAlchemy), DSN-less.
    Baut eine klassische ODBC-Connection-String-Variante.
    """
    if pyodbc is None:
        return False, {"error": "pyodbc not installed"}
    drv = driver or settings.driver or (list_odbc_drivers() or ["ODBC Driver 17 for SQL Server"])[0]
    parts = [
        f"Driver={{{drv}}}",                 # <-- .format(...) entfernen!
        f"Server={settings.server}",
        f"Database={settings.db_name}",
    ]

    params = settings.params or ""
    # Trusted_Connection erkennen
    if "trusted_connection=yes" in params.lower():
        parts.append("Trusted_Connection=Yes")
    else:
        if settings.username:
            parts.append(f"Uid={settings.username}")
        if settings.password:
            parts.append(f"Pwd={settings.password}")

    def _flag(name: str, val: Optional[bool]) -> Optional[str]:
        if val is None:
            return None
        return f"{name}={'Yes' if val else 'No'}"

    extra = [_flag("Encrypt", encrypt), _flag("TrustServerCertificate", trust)]
    parts += [p for p in extra if p]

    # übrige params hinten anhängen (sofern nicht doppelt)
    for piece in (params.split("&") if params else []):
        piece = piece.strip()
        if not piece:
            continue
        k = piece.split("=")[0].strip().lower()
        if k in ("encrypt", "trustservercertificate", "trusted_connection"):
            continue
        parts.append(piece.replace("&", ";"))  # sicherheitshalber

    conn_str = ";".join(parts) + ";"

    t0 = time.time()
    try:
        cn = pyodbc.connect(conn_str, timeout=timeout)  # type: ignore[call-arg]
        cur = cn.cursor()
        cur.execute("SELECT 1")
        _ = cur.fetchone()
        cur.close()
        cn.close()
        return True, {
            "method": "pyodbc-direct",
            "driver": drv,
            "conn_str_masked": f"Driver={{{drv}}};Server={settings.server};Database={settings.db_name};Uid={_mask(settings.username)};Pwd=****;",
            "duration_s": round(time.time() - t0, 3),
        }
    except Exception as ex:
        return False, {
            "method": "pyodbc-direct",
            "driver": drv,
            "conn_str_masked": f"Driver={{{drv}}};Server={settings.server};Database={settings.db_name};Uid={_mask(settings.username)};Pwd=****;",
            "duration_s": round(time.time() - t0, 3),
            "error": f"{type(ex).__name__}: {ex}",
        }


# ------------------------------- Fallback 2: ADO/OLE DB -----------------------

def try_ado_msoledb(settings, *,
                    provider: str = "MSOLEDBSQL",
                    encrypt: Optional[bool] = True,
                    trust: Optional[bool] = None,
                    timeout: int = 8) -> Tuple[bool, Dict[str, Any]]:
    """
    ADO/OLE DB via MSOLEDBSQL (Windows-only). Nutzt win32com.
    - provider: "MSOLEDBSQL" (neuer OLE DB Provider for SQL Server)
    """
    if platform.system().lower() != "windows":
        return False, {"error": "ADO/OLE DB only available on Windows"}
    if win32com is None:
        return False, {"error": "pywin32 not installed (win32com.client)"}

    parts = [f"Provider={provider}", f"Data Source={settings.server}", f"Initial Catalog={settings.db_name}"]
    params = settings.params or ""
    if "trusted_connection=yes" in params.lower():
        parts.append("Integrated Security=SSPI")
    else:
        if settings.username:
            parts.append(f"User ID={settings.username}")
        if settings.password:
            parts.append(f"Password={settings.password}")
    if encrypt is not None:
        parts.append(f"Encrypt={'Yes' if encrypt else 'No'}")
    if trust is not None:
        parts.append(f"TrustServerCertificate={'Yes' if trust else 'No'}")

    conn_str = ";".join(parts) + ";"

    t0 = time.time()
    try:
        cn = win32com.client.Dispatch("ADODB.Connection")
        cn.CommandTimeout = timeout
        cn.ConnectionTimeout = timeout
        cn.Open(conn_str)
        rs = win32com.client.Dispatch("ADODB.Recordset")
        rs.Open("SELECT 1", cn)
        _ = rs.Fields.Item(0).Value  # noqa
        rs.Close()
        cn.Close()
        return True, {
            "method": "ado-msoledb",
            "provider": provider,
            "conn_str_masked": f"Provider={provider};Data Source={settings.server};Initial Catalog={settings.db_name};User ID={_mask(settings.username)};Password=****;",
            "duration_s": round(time.time() - t0, 3),
        }
    except Exception as ex:
        return False, {
            "method": "ado-msoledb",
            "provider": provider,
            "conn_str_masked": f"Provider={provider};Data Source={settings.server};Initial Catalog={settings.db_name};User ID={_mask(settings.username)};Password=****;",
            "duration_s": round(time.time() - t0, 3),
            "error": f"{type(ex).__name__}: {ex}",
        }


# ------------------------------- Fallback 3: pymssql --------------------------

def try_pymssql(settings, *, login_timeout: int = 8) -> Tuple[bool, Dict[str, Any]]:
    """
    Fallback via pymssql (FreeTDS). Erfordert Benutzer/Passwort (kein AAD/MSI).
    """
    if pymssql is None:
        return False, {"error": "pymssql not installed"}
    t0 = time.time()
    try:
        cn = pymssql.connect(
            server=str(settings.server),
            user=str(settings.username or ""),
            password=str(settings.password or ""),
            database=str(settings.db_name),
            login_timeout=login_timeout,
            timeout=login_timeout,
        )
        cur = cn.cursor()
        cur.execute("SELECT 1")
        _ = cur.fetchone()
        cur.close()
        cn.close()
        return True, {
            "method": "pymssql",
            "server": settings.server,
            "duration_s": round(time.time() - t0, 3),
        }
    except Exception as ex:
        return False, {
            "method": "pymssql",
            "server": settings.server,
            "duration_s": round(time.time() - t0, 3),
            "error": f"{type(ex).__name__}: {ex}",
        }


# ------------------------------- Orchestrator --------------------------------

def diagnose_with_fallbacks(settings) -> Tuple[bool, Dict[str, Any]]:
    """
    Orchestriert ODBC/SQLAlchemy + pyodbc-direct + ADO + pymssql.
    Gibt die erste erfolgreiche Variante zurück, plus detaillierte Versuche.
    """
    attempts: List[Dict[str, Any]] = []
    suggestions: List[str] = []

    # 1) ODBC/SQLAlchemy
    ok, base = diagnose_sql_connection(settings)
    attempts += base.get("attempts", [])
    if ok:
        return True, {"summary": "Verbindung OK (sqlalchemy+pyodbc)", "attempts": attempts, "suggestions": []}

    # 2) pyodbc-direct – probiere einige sinnvolle Kombis
    for enc in (True, False, None):
        for tr in (True, False, None):
            ok2, info2 = try_pyodbc_direct(settings, encrypt=enc, trust=tr)
            attempts.append(info2)
            if ok2:
                return True, {"summary": "Verbindung OK (pyodbc-direct)", "attempts": attempts, "suggestions": []}

    # 3) ADO/OLE DB (Windows)
    for tr in (True, False, None):
        ok3, info3 = try_ado_msoledb(settings, encrypt=True, trust=tr)
        attempts.append(info3)
        if ok3:
            return True, {"summary": "Verbindung OK (ADO/OLE DB)", "attempts": attempts, "suggestions": []}

    # 4) pymssql (falls vorhanden)
    ok4, info4 = try_pymssql(settings)
    attempts.append(info4)
    if ok4:
        return True, {"summary": "Verbindung OK (pymssql)", "attempts": attempts, "suggestions": []}

    # Hinweise verdichten (18456 etc.)
    if any("18456" in (str(a.get("error")) if a.get("error") else "") for a in attempts):
        suggestions += [
            "Fehler 18456 (Login failed): Login-Typ/Passwort/Default-DB prüfen; ggf. 'Trusted_Connection=yes' verwenden.",
        ]
    if not list_odbc_drivers():
        suggestions += ["Keine SQL Server ODBC-Treiber gefunden. Bitte 'ODBC Driver 18 for SQL Server' installieren."]
    if platform.system().lower() == "windows" and win32com is None:
        suggestions += ["ADO/OLE DB-Fallback nicht verfügbar (pywin32 fehlt). 'pip install pywin32' testen."]
    if pymssql is None:
        suggestions += ["pymssql-Fallback nicht verfügbar. 'pip install pymssql' (Achtung: projektabhängige Kompatibilität)."]

    return False, {"summary": "Alle Versuche fehlgeschlagen", "attempts": attempts, "suggestions": suggestions}
