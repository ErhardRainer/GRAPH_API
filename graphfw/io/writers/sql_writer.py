# -*- coding: utf-8 -*-
"""
graphfw.io.writers.sql_writer
-----------------------------

Robuster DataFrame->SQL-Writer (SQLAlchemy + pyodbc) mit:
- Engine-Erstellung (MS SQL Server, ODBC Driver 17+)
- Optionalem TRUNCATE vor Insert
- Automatischer Schema-/Tabellenanlage
- Optionaler Schema-Evolution: fehlende Spalten werden per ALTER TABLE ergänzt
- Optionales Recreate: DROP TABLE + Neuaufbau aus DataFrame
- Optionales Spaltentyp-Alignment (String-Längen an DF anpassen)
- Optionaler Stored-Procedure-Call nach dem Insert
- Deterministischem Verhalten & aussagekräftigem `info`-Dict

Neu:
- `recreate: bool` — droppt Tabelle (falls vorhanden) und legt sie neu an.
- `align_columns: bool` (Alias: `alignColumn`, `alighnColumn`) — passt
  (N)VARCHAR-Längen nach oben an, falls DF-Strings länger sind als die
  aktuelle Spaltenlänge. Bei Bedarf bis NVARCHAR(MAX).

Hinweise
--------
- Aus Sicherheitsgründen werden Identifier (Schema/Tabellen-/Spaltennamen)
  strikt validiert und korrekt quotiert.
- Das Typ-Alignment beschränkt sich bewusst auf **String-Spalten** (VARCHAR /
  NVARCHAR). Numeric-/Datetime-Konvertierungen sind riskant und werden nicht
  automatisch geändert.

Beispiel
--------
from graphfw.io.writers.sql_writer import build_engine, write_sql
import pandas as pd

engine = build_engine({"server": "myserver"}, db_name="BI_RAW",
                      username="svc_user", password="***")

df = pd.DataFrame({"id":[1,2], "name":["a","b"*50]})
ok, info = write_sql(
    df,
    engine=engine,
    schema="dbo",
    table="Demo",
    truncate=False,
    evolve_on_new_columns=True,
    align_columns=True,   # VARCHAR/NVARCHAR verbreitern, falls nötig
)
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional, Tuple, Iterable, Set, List

import re
import time
import pandas as pd
from sqlalchemy import MetaData, Table, Column, text, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.types import String, Integer, Float, DateTime, Boolean
from sqlalchemy import create_engine
from urllib.parse import quote_plus


# ----------------------------- Engine-Building -------------------------------

@dataclass(frozen=True)
class _EngineConfig:
    server: str
    db_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    driver: str = "ODBC Driver 17 for SQL Server"
    params: Optional[str] = None  # z.B. "TrustServerCertificate=yes"


def _encode(user: Optional[str], pwd: Optional[str]) -> Tuple[str, str]:
    return quote_plus(user or ""), quote_plus(pwd or "")


def build_engine(cfg: Dict[str, Any], db_name: str,
                 username: Optional[str] = None, password: Optional[str] = None) -> Engine:
    """
    Erstellt eine SQLAlchemy-Engine für MS SQL Server via pyodbc.

    cfg: { "server": "host\\instance | host", "driver"?: "...", "params"?: "k=v&k2=v2" }
    db_name: Zieldatenbank
    username/password: optional; wenn im cfg enthalten, werden diese ignoriert.

    Rückgabe: Engine
    """
    server = str(cfg["server"]).strip()
    driver = str(cfg.get("driver", "ODBC Driver 17 for SQL Server")).strip()
    params = str(cfg.get("params", "")).strip()
    user = str(username or cfg.get("username", "")).strip() or None
    pwd = str(password or cfg.get("password", "")).strip() or None

    if user and pwd:
        u, p = _encode(user, pwd)
        param_q = f"&{params}" if params else ""
        url = f"mssql+pyodbc://{u}:{p}@{server}/{db_name}?driver={quote_plus(driver)}{param_q}"
    else:
        # Trusted Connection / Integrated Security (sofern ODBC/OS-konfiguriert)
        param_q = f"&{params}" if params else ""
        url = f"mssql+pyodbc://@{server}/{db_name}?driver={quote_plus(driver)}{param_q}"

    return create_engine(url, fast_executemany=True, pool_pre_ping=True)


# ----------------------------- Identifier-Utils ------------------------------

_VALID_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _is_valid_identifier(name: str) -> bool:
    return bool(_VALID_IDENT.match(name or ""))


def _quote_ident(name: str) -> str:
    """
    SQL Server-konformes Quoting mit [] und Escape von ] -> ]].
    Erwartet vorvalidierte Identifier (alphanum + _; Beginn mit Buchstabe/_).
    """
    safe = str(name).replace("]", "]]")
    return f"[{safe}]"


# ----------------------------- Typ-Mapping ----------------------------------

def _sqlalchemy_type_from_dtype(dtype: Any):
    s = str(dtype)
    if s == "int64":
        return Integer()
    if s == "float64":
        return Float()
    if s == "bool":
        return Boolean()
    if s.startswith("datetime"):
        return DateTime()
    return String()


def _tsql_type_from_dtype(dtype: Any) -> str:
    """
    Liefert T-SQL-Typen für CREATE/ALTER TABLE (Basis-Mapping).
    """
    s = str(dtype)
    if s == "int64":
        return "INT"
    if s == "float64":
        return "FLOAT"
    if s == "bool":
        return "BIT"
    if s.startswith("datetime"):
        return "DATETIME2"
    # Fallback für object/string
    return "NVARCHAR(MAX)"


# ----------------------------- DDL-Helpers ----------------------------------

def _ensure_schema(engine: Engine, schema: str, info: Dict[str, Any]) -> None:
    if not _is_valid_identifier(schema):
        raise ValueError(f"Invalid schema name: {schema!r}")
    schema_q = _quote_ident(schema)
    stmt = text(
        f"""
        IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = :schema_name)
        EXEC('CREATE SCHEMA {schema_q}');
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt, {"schema_name": schema})
    # wir markieren nicht zuverlässig, ob neu erstellt (würde zusätzliche Query erfordern)
    info["schema_created"] = info.get("schema_created") or False


def _table_exists(engine: Engine, schema: str, table: str) -> bool:
    insp = inspect(engine)
    return insp.has_table(table_name=table, schema=schema)


def _existing_columns(engine: Engine, schema: str, table: str) -> Set[str]:
    insp = inspect(engine)
    cols = set()
    for col in insp.get_columns(table, schema=schema) or []:
        cols.add(str(col.get("name")))
    return cols


def _create_table(engine: Engine, schema: str, table: str, df: pd.DataFrame) -> None:
    metadata = MetaData(schema=schema)
    cols = [Column(str(c), _sqlalchemy_type_from_dtype(t)) for c, t in zip(df.columns, df.dtypes)]
    Table(table, metadata, *cols, extend_existing=True)
    metadata.create_all(engine)


def _drop_table_if_exists(engine: Engine, schema: str, table: str) -> None:
    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    stmt = text(
        f"""
        IF OBJECT_ID('{schema}.{table}', 'U') IS NOT NULL
            DROP TABLE {schema_q}.{table_q};
        """
    )
    with engine.begin() as conn:
        conn.execute(stmt)


def _add_missing_columns(engine: Engine, schema: str, table: str,
                         columns_to_add: Iterable[Tuple[str, Any]],
                         info: Dict[str, Any]) -> None:
    if not columns_to_add:
        return
    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    added = []
    with engine.begin() as conn:
        for col_name, dtype in columns_to_add:
            if not _is_valid_identifier(col_name):
                info.setdefault("warnings", []).append(f"Skipped invalid column name: {col_name!r}")
                continue
            col_q = _quote_ident(col_name)
            tsql_type = _tsql_type_from_dtype(dtype)
            stmt = f"ALTER TABLE {schema_q}.{table_q} ADD {col_q} {tsql_type} NULL"
            conn.execute(text(stmt))
            added.append({"column": col_name, "type": tsql_type})
    if added:
        info["columns_added"] = info.get("columns_added", []) + added


def _get_column_metadata(engine: Engine, schema: str, table: str) -> Dict[str, Dict[str, Any]]:
    """
    Liefert Metadaten je Spalte:
      { colname: {"data_type": "nvarchar", "max_len": 100, "is_nullable": True} }
    CHARACTER_MAXIMUM_LENGTH: -1 bedeutet NVARCHAR(MAX)/VARCHAR(MAX).
    """
    q = text("""
        SELECT
            c.COLUMN_NAME,
            c.DATA_TYPE,
            c.CHARACTER_MAXIMUM_LENGTH,
            c.IS_NULLABLE
        FROM INFORMATION_SCHEMA.COLUMNS c
        WHERE c.TABLE_SCHEMA = :schema AND c.TABLE_NAME = :table
    """)
    meta: Dict[str, Dict[str, Any]] = {}
    with engine.connect() as conn:
        rows = conn.execute(q, {"schema": schema, "table": table}).mappings().all()
        for r in rows:
            meta[str(r["COLUMN_NAME"])] = {
                "data_type": str(r["DATA_TYPE"]).lower(),
                "max_len": None if r["CHARACTER_MAXIMUM_LENGTH"] is None else int(r["CHARACTER_MAXIMUM_LENGTH"]),
                "is_nullable": str(r["IS_NULLABLE"]).upper() == "YES",
            }
    return meta


def _compute_needed_string_length(series: pd.Series) -> int:
    """
    Berechnet die benötigte Zeichenlänge für Strings einer DF-Spalte.
    Nicht-Strings werden in Strings konvertiert (wie es SQL NVARCHAR abbildet).
    """
    if series is None or series.empty:
        return 0
    # Konvertiere zu str, ignoriere NaN/None
    s = series.dropna().astype(str)
    if s.empty:
        return 0
    return int(s.map(len).max())


def _alter_varchar_length(engine: Engine, schema: str, table: str,
                          col: str, target_len: Optional[int],
                          prefer_nvarchar: bool, keep_nullability: bool,
                          current_nullable: bool,
                          info: Dict[str, Any]) -> None:
    """
    Führt ALTER COLUMN für (N)VARCHAR durch. target_len=None -> NVARCHAR(MAX).
    """
    schema_q = _quote_ident(schema)
    table_q = _quote_ident(table)
    col_q = _quote_ident(col)

    dtype = "NVARCHAR" if prefer_nvarchar else "VARCHAR"
    if target_len is None:
        type_sql = f"{dtype}(MAX)"
    else:
        type_sql = f"{dtype}({target_len})"

    null_sql = "NULL" if current_nullable or keep_nullability else "NOT NULL"
    stmt = f"ALTER TABLE {schema_q}.{table_q} ALTER COLUMN {col_q} {type_sql} {null_sql}"
    with engine.begin() as conn:
        conn.execute(text(stmt))

    info.setdefault("columns_altered", []).append({
        "column": col,
        "new_type": type_sql,
        "kept_nullability": keep_nullability,
    })


# ----------------------------- Hauptfunktion ---------------------------------

def write_sql(df: pd.DataFrame, *,
              engine: Engine,
              schema: str,
              table: str,
              truncate: bool = True,
              stored_procedure: Optional[str] = None,
              chunksize: Optional[int] = None,
              evolve_on_new_columns: bool = False,
              recreate: bool = False,
              align_columns: bool = False,
              **kwargs) -> Tuple[bool, Dict[str, Any]]:
    """
    Schreibt einen DataFrame in eine SQL-Tabelle.

    Parameter
    ---------
    df : pandas.DataFrame
        Zu schreibende Daten. Bei leerem DF wird `False` zurückgegeben.
    engine : sqlalchemy.Engine
        Offene Engine (z. B. via `build_engine` erzeugt).
    schema : str
        Zielschema (wird bei Bedarf angelegt).
    table : str
        Zieltabellenname (wird bei Bedarf angelegt).
    truncate : bool, default True
        Vor dem Insert `TRUNCATE TABLE <schema>.<table>`.
    stored_procedure : Optional[str], default None
        Optionaler Stored Procedure-Name (z. B. "dbo.sp_ProcessX") nach dem Insert.
    chunksize : Optional[int]
        Optionaler Chunksize für `to_sql`.
    evolve_on_new_columns : bool, default False
        Wenn True und die Tabelle existiert, werden fehlende Spalten aus `df`
        per `ALTER TABLE ... ADD` ergänzt.
    recreate : bool, default False
        Wenn True, wird die Tabelle (falls vorhanden) gedroppt und vollständig
        aus dem DataFrame neu angelegt (DDL + Insert).
    align_columns : bool, default False
        Passt (N)VARCHAR-Längen nach oben an, wenn DF-Strings länger sind.
        Hinweis: Es werden **keine** numerischen/zeitlichen Typ-Änderungen vorgenommen.

    Zusätzliche Kompatibilitäts-Aliase (kwargs)
    -------------------------------------------
    - alignColumn / alighnColumn: bool (gleiches Verhalten wie align_columns)

    Rückgabe
    --------
    (ok, info) : Tuple[bool, dict]
        ok   : True/False (Erfolg)
        info : Diagnostics (sql, rowcount, timings, schema_created, table_created,
                           columns_added, columns_altered, warnings, error)
    """
    # Aliase für Schreibvarianten (User-Wunsch)
    if "alignColumn" in kwargs and isinstance(kwargs["alignColumn"], bool):
        align_columns = kwargs["alignColumn"]
    if "alighnColumn" in kwargs and isinstance(kwargs["alighnColumn"], bool):
        align_columns = kwargs["alighnColumn"]

    start = time.time()
    info: Dict[str, Any] = {
        "schema": schema,
        "table": table,
        "truncate": bool(truncate),
        "stored_procedure": stored_procedure or None,
        "rowcount": 0,
        "timings": {},
        "warnings": [],
        "sql": [],
        "schema_created": None,
        "table_created": None,
        "columns_added": [],
        "columns_altered": [],
        "recreate": bool(recreate),
        "align_columns": bool(align_columns),
        "evolve_on_new_columns": bool(evolve_on_new_columns),
    }

    # Validierung von Schema/Tabellenname
    if not _is_valid_identifier(schema):
        raise ValueError(f"Invalid schema name: {schema!r}")
    if not _is_valid_identifier(table):
        raise ValueError(f"Invalid table name: {table!r}")

    if df is None or df.empty:
        info["warnings"].append("Empty DataFrame – nothing to write.")
        return False, info

    # 1) Schema sicherstellen
    t_schema = time.time()
    _ensure_schema(engine, schema, info)
    info["timings"]["ensure_schema_s"] = round(time.time() - t_schema, 3)

    # 2) Recreate-Logik oder Ensure-Table
    t_table = time.time()
    existed_before = _table_exists(engine, schema, table)
    if recreate and existed_before:
        _drop_table_if_exists(engine, schema, table)
        existed_before = False  # fällt durch zur Neuerstellung
        info["sql"].append(f"DROP TABLE {_quote_ident(schema)}.{_quote_ident(table)}")

    if not existed_before:
        _create_table(engine, schema, table, df)
    info["table_created"] = (not existed_before)
    info["timings"]["ensure_table_s"] = round(time.time() - t_table, 3)

    # 3) Schema-Evolution (fehlende Spalten ergänzen), nur wenn nicht gerade neu erstellt
    if existed_before and evolve_on_new_columns and not recreate:
        t_evo = time.time()
        existing = _existing_columns(engine, schema, table)
        missing = [(c, t) for c, t in zip(df.columns, df.dtypes) if str(c) not in existing]
        _add_missing_columns(engine, schema, table, missing, info)
        info["timings"]["evolve_columns_s"] = round(time.time() - t_evo, 3)

    # 4) Optional: Spaltentyp-Alignment (Strings)
    if (existed_before or not recreate) and align_columns:
        t_align = time.time()
        meta = _get_column_metadata(engine, schema, table)
        # Iteriere über DF-Spalten mit String-Inhalt
        alterations: List[Tuple[str, Optional[int], bool, bool]] = []  # (col, new_len|None, prefer_nvarchar, current_nullable)
        for col_name in df.columns:
            if not _is_valid_identifier(str(col_name)):
                info["warnings"].append(f"Skipping alignment for invalid column name: {col_name!r}")
                continue
            if col_name not in meta:
                continue  # neue Spalten werden ggf. via evolve_on_new_columns hinzugefügt
            m = meta[col_name]
            dt = (m["data_type"] or "").lower()
            if dt not in ("varchar", "nvarchar"):
                continue  # nur Strings
            cur_len = m["max_len"]  # -1 -> MAX
            cur_nullable = bool(m["is_nullable"])

            needed = _compute_needed_string_length(df[col_name])
            if needed <= 0:
                continue
            # -1 = MAX -> bereits ausreichend
            if isinstance(cur_len, int) and cur_len == -1:
                continue
            if cur_len is None:
                # defensiv: wenn keine Länge verfügbar, erweitern auf MAX
                alterations.append((col_name, None, dt == "nvarchar", cur_nullable))
                continue
            if needed <= cur_len:
                continue  # passt bereits

            # Ziel-Länge bestimmen: bis 4000 -> NVARCHAR(n), darüber -> NVARCHAR(MAX)
            if needed > 4000:
                new_len = None  # -> MAX
            else:
                new_len = needed

            # Bevorzugt ursprünglichen Typ (varchar vs nvarchar) beibehalten
            prefer_nvarchar = (dt == "nvarchar")
            alterations.append((col_name, new_len, prefer_nvarchar, cur_nullable))

        for col, new_len, prefer_nvarchar, cur_nullable in alterations:
            _alter_varchar_length(
                engine, schema, table,
                col=col,
                target_len=new_len,
                prefer_nvarchar=prefer_nvarchar,
                keep_nullability=True,         # Nullability wird beibehalten
                current_nullable=cur_nullable,
                info=info,
            )
        info["timings"]["align_columns_s"] = round(time.time() - t_align, 3)

    try:
        # 5) TRUNCATE (optional) – überspringen, wenn gerade recreate (Tabelle ist leer)
        if truncate and not (recreate and info["table_created"]):
            t_tr = time.time()
            stmt = f"TRUNCATE TABLE {_quote_ident(schema)}.{_quote_ident(table)}"
            info["sql"].append(stmt)
            with engine.begin() as conn:
                conn.execute(text(stmt))
            info["timings"]["truncate_s"] = round(time.time() - t_tr, 3)

        # 6) Insert
        t_ins = time.time()
        df.to_sql(table, engine, schema=schema, if_exists="append", index=False, chunksize=chunksize)
        info["rowcount"] = int(len(df))
        info["timings"]["insert_s"] = round(time.time() - t_ins, 3)

        # 7) Optional: Stored Procedure
        if stored_procedure:
            t_sp = time.time()
            info["sql"].append(f"EXEC {stored_procedure}")
            with engine.begin() as conn:
                conn.execute(text(f"EXEC {stored_procedure}"))
            info["timings"]["stored_procedure_s"] = round(time.time() - t_sp, 3)

        info["timings"]["total_s"] = round(time.time() - start, 3)
        return True, info

    except Exception as ex:
        info["error"] = f"{type(ex).__name__}: {ex}"
        info["timings"]["total_s"] = round(time.time() - start, 3)
        return False, info
