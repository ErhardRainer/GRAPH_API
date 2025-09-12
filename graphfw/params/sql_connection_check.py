# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.params.sql_connection_check
===============================================================================
Autor: Erhard Rainer (ER)
Lizenz: MIT (sofern im Projekt nicht anders geregelt)

Zweck
-----
Diagnose- und Hilfsmodul für SQL-Verbindungsparameter in `config.json`.
Das Modul liest bestehende Einstellungen (inkl. optionaler ENV-Overrides),
führt eine Konnektivitätsdiagnose via `graphfw.core.odbc_utils` durch, leitet
daraus einen belastbaren Konfigurationskandidaten ab und kann diesen wahlweise:

  1) als JSON-Block ausgeben (zum Copy/Paste), oder
  2) **atomar** in die echte `config.json` schreiben (mit Backup, Dry-Run und
     sicherem Passwort-Handling).

Spezifische Unterstützung für dein JSON-Schema
----------------------------------------------
Pro Node werden u. a. diese Felder unterstützt:

    {
      "server": "myserver.domain.tld",
      "db_name": "BI_RAW",
      "username": "svc_user",
      "password": "CHANGE_ME",
      "driver": "ODBC Driver 18 for SQL Server",
      "auth": "sql" | "trusted" | "aad-password" | "aad-integrated"
              | "aad-interactive" | "aad-msi" | "aad-sp",
      "params": { ... }   # Dict, z.B. {"TrustServerCertificate": "yes", "Encrypt": "yes"}
    }

- `auth` wird beibehalten und in die Diagnose übersetzt (Trusted Connection etc.).
- `params` wird als **Dict** gelesen; für die Diagnose wird ein **ODBC-Query-String**
  erzeugt (z. B. `Encrypt=yes&TrustServerCertificate=yes`).

Sicherheitsprinzipien
---------------------
- **Keine Geheimnisse im Log**: Passwörter werden nie im Klartext ausgegeben;
  bei Vorschlägen wird der Platzhalter `<<<SET_SECRET_HERE>>>` gesetzt.
- **Passwort-Erhalt**: Beim Schreiben kann ein bestehendes Passwort beibehalten
  werden (`keep_existing_password=True`), wenn der neue Kandidat nur den
  Platzhalter liefert.
- **Atomare Writes**: Updates werden über eine temporäre Datei und `os.replace`
  durchgeführt; optional wird vorab ein Backup angelegt.

Öffentliche API
---------------
- `connect_and_check(node, *, show_drivers=True, show_dsns=True, return_config_json=True,
                     write_config=False, config_path=CONFIG_PATH, keep_existing_password=True,
                     dry_run=False) -> (ok: bool, diag: dict, config_json: str|None, write_info: dict|None)`

- `build_config_candidate(settings, diag) -> dict`
- `render_config_json(node, entry) -> str`
- `apply_config_update(*, config_path, node, new_entry, create_backup=True,
                       keep_existing_password=True, dry_run=False) -> dict`
- `quick_check(engine) -> Any` (optional, erfordert SQLAlchemy)
- `show_settings(settings) -> None` (maskierte Kurzansicht)

Fehlerklassen
-------------
- `ConfigUpdateError`: Les-/Schreib-/Merge-Fehler für `config.json`.

ENV-Overrides (Fallback-Loader)
-------------------------------
Falls das Projekt keinen eigenen Loader bereitstellt, werden u. a. diese
Umgebungsvariablen berücksichtigt (best effort):
  SQL_SERVER, DB_SERVER
  SQL_DATABASE, DB_NAME, DATABASE
  SQL_USERNAME, DB_USER, USER
  SQL_PASSWORD, DB_PASSWORD, PASSWORD
  SQL_DRIVER, ODBC_DRIVER
  SQL_DSN, ODBC_DSN
  SQL_AUTH    (sql|trusted|aad-password|aad-integrated|aad-interactive|aad-msi|aad-sp)
  SQL_TRUSTED_CONNECTION (1/true/yes)
  SQL_ENCRYPT (1/true/yes)
  SQL_PARAMS_JSON  (ganzer params-Dict als JSON-String)

Änderungsprotokoll (Change Log)
-------------------------------
2025-09-12 (ER)
  - **Integration `graphfw.core.odbc_utils`**: Diagnose, Treiber- und DSN-Auflistung
    laufen jetzt über das zentrale Modul (`diagnose_with_fallbacks`,
    `list_odbc_drivers`, `list_odbc_data_sources`).
  - Settings-Adapter eingeführt, der `auth`/`params` (Dict) in das von
    `odbc_utils` erwartete Attr-Format (inkl. `params`-Querystring) überführt.
  - Bestehende API, Sicherheits- und Schreiblogik unverändert beibehalten.

2025-09-12 (ER)
  - Anpassung an das JSON-Schema (auth/params als Dict), erweiterte Validierung.
  - Robuste Loader-Fallbacks, atomare Writes/Backup, Secret-Erhalt.

2025-09-11 (ER)
  - `build_config_candidate(...)`: deterministische Schlüsselreihenfolge; Passwort-
    Platzhalter nur bei nicht-Trusted-Connection.

2025-09-10 (ER)
  - Erste Version: Diagnose-Orchestrierung, JSON-Vorschlag, `quick_check(...)`,
    `show_settings(...)`.

===============================================================================
"""

from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

# Optional: nur für quick_check; kann entfernt werden wenn nicht genutzt
try:
    from sqlalchemy import text  # type: ignore
except Exception:  # pragma: no cover
    text = None  # type: ignore

# Zentrale ODBC-Diagnose & Utilities
from graphfw.core import odbc_utils  # nutzt: list_odbc_drivers, list_odbc_data_sources, diagnose_with_fallbacks

# =========================
#   Kompatibler Settings-Loader
# =========================
_LOAD_SQL_SETTINGS = None
_LOAD_SETTINGS_GENERIC = None
_CONFIG_PATH_FROM_RESOLVE = None
try:
    from graphfw.params.resolve import load_sql_settings as _LOAD_SQL_SETTINGS  # type: ignore
except Exception:
    pass

try:
    from graphfw.params.resolve import load_settings as _LOAD_SETTINGS_GENERIC  # type: ignore
except Exception:
    pass

try:
    from graphfw.params.resolve import CONFIG_PATH as _CONFIG_PATH_FROM_RESOLVE  # type: ignore
except Exception:
    pass

CONFIG_PATH = (
    _CONFIG_PATH_FROM_RESOLVE
    if _CONFIG_PATH_FROM_RESOLVE
    else os.environ.get("GRAPHFW_CONFIG_PATH", "config.json")
)


class _SimpleSettings:
    """Minimaler Settings-Wrapper mit as_dict(mask_secrets=...) kompatibel zur bisherigen Nutzung."""
    def __init__(self, data: Dict[str, Any]) -> None:
        self._data = dict(data or {})

    def as_dict(self, *, mask_secrets: bool = True) -> Dict[str, Any]:
        d = dict(self._data)
        if mask_secrets:
            for k in ("password", "pwd", "secret"):
                if k in d and isinstance(d[k], str) and d[k]:
                    d[k] = "******"
        return d


def _split_node_path(node_path: str) -> List[str]:
    return [p for p in (node_path or "").split(".") if p]


def _simple_load_sql_settings(config_path: str, node: str, env_override: bool = True) -> Tuple[_SimpleSettings, Dict[str, Any]]:
    """
    Sehr einfacher Loader: liest JSON, nimmt root['sql'][*node_parts*] und packt es in _SimpleSettings.
    env_override=True: überschreibt mit ENV-Variablen (z. B. SQL_*), inkl. SQL_AUTH und SQL_PARAMS_JSON.
    """
    info: Dict[str, Any] = {"source": os.path.abspath(config_path), "node_path": f"sql.{node}"}
    if not os.path.exists(config_path):
        data = {}
    else:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)

    cur: Any = data.get("sql", {})
    for part in _split_node_path(node):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            cur = {}
            break

    if not isinstance(cur, dict):
        cur = {}

    # ENV-Overrides (best-effort)
    if env_override:
        env_map = {
            "server": ["SQL_SERVER", "DB_SERVER"],
            "db_name": ["SQL_DATABASE", "DB_NAME", "DATABASE"],
            "username": ["SQL_USERNAME", "DB_USER", "USER"],
            "password": ["SQL_PASSWORD", "DB_PASSWORD", "PASSWORD"],
            "driver": ["SQL_DRIVER", "ODBC_DRIVER"],
            "dsn": ["SQL_DSN", "ODBC_DSN"],  # falls DSN genutzt wird
            "auth": ["SQL_AUTH"],
            "trusted_connection": ["SQL_TRUSTED_CONNECTION"],
            "encrypt": ["SQL_ENCRYPT"],  # nur zur Kompatibilität; eigentl. in params
        }
        for key, env_keys in env_map.items():
            for ek in env_keys:
                if ek in os.environ and os.environ[ek] != "":
                    val: Any = os.environ[ek]
                    if key in ("trusted_connection", "encrypt"):
                        val = str(val).lower() in ("1", "true", "yes", "y")
                    cur[key] = val
                    break
        # params als JSON-Dict erlauben
        params_json = os.environ.get("SQL_PARAMS_JSON")
        if params_json:
            try:
                cur["params"] = json.loads(params_json)
            except Exception:
                pass

    return _SimpleSettings(cur), info


def load_sql_settings(config_path: str, node: str, env_override: bool = True):
    """
    Kompatibler Entry-Point: nutzt (in dieser Reihenfolge)
    - graphfw.params.resolve.load_sql_settings
    - graphfw.params.resolve.load_settings(section='sql')
    - _simple_load_sql_settings (dieses Modul)
    """
    if callable(_LOAD_SQL_SETTINGS):
        return _LOAD_SQL_SETTINGS(config_path=config_path, node=node, env_override=env_override)  # type: ignore
    if callable(_LOAD_SETTINGS_GENERIC):
        return _LOAD_SETTINGS_GENERIC(config_path=config_path, node=node, env_override=env_override, section="sql")  # type: ignore
    return _simple_load_sql_settings(config_path=config_path, node=node, env_override=env_override)


# =========================
#   Diagnose + Kandidat bauen
# =========================

def quick_check(engine) -> Any:
    """Führt SELECT 1 aus und gibt das Ergebnis zurück (nur mit SQLAlchemy verfügbar)."""
    if text is None:
        raise RuntimeError("SQLAlchemy nicht verfügbar – quick_check kann nicht ausgeführt werden.")
    with engine.connect() as c:
        return c.execute(text("SELECT 1")).scalar()


def show_settings(settings) -> None:
    """Kompakte, maskierte Ausgabe gängiger Felder."""
    d = settings.as_dict(mask_secrets=True)
    keys = ("server", "db_name", "username", "driver", "dsn", "auth", "params")
    print({k: d[k] for k in keys if k in d})


def _first_ok_attempt(diag: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    for att in diag.get("attempts", []):
        if att.get("ok"):
            return att
    return None


def _normalize_settings_dict(settings) -> Dict[str, Any]:
    d = settings.as_dict(mask_secrets=False) if hasattr(settings, "as_dict") else dict(settings or {})
    norm = {
        "server": d.get("server") or d.get("host") or d.get("hostname"),
        "db_name": d.get("db_name") or d.get("database") or d.get("db"),
        "username": d.get("username") or d.get("user") or d.get("uid"),
        "password": d.get("password") or d.get("pwd"),
        "driver": d.get("driver") or d.get("provider"),
        "dsn": d.get("dsn"),
        "auth": d.get("auth"),
        "trusted_connection": d.get("trusted_connection"),
        "encrypt": d.get("encrypt"),  # meist in params geführt
        "params": d.get("params") or d.get("options"),
    }
    # Nur nicht-leere Werte
    out = {k: v for k, v in norm.items() if v not in (None, "")}
    # Stelle sicher: params ist ein Dict (wenn vorhanden)
    if "params" in out and not isinstance(out["params"], dict):
        out["params"] = {"Raw": out["params"]}
    return out


def _dict_params_to_query(params: Optional[Dict[str, Any]]) -> str:
    """params-Dict -> ODBC-Querystring (k=v&...). Werte werden str()-konvertiert."""
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        if v is None:
            continue
        parts.append(f"{k}={v}")
    return "&".join(parts)


def _adapt_for_odbc_utils(settings) -> SimpleNamespace:
    """
    Baut ein Objekt mit Attributzugriff, wie es `core.odbc_utils` erwartet.
    - params wird als Querystring bereitgestellt (nicht Dict).
    - Trusted_Connection wird aus `auth`/'trusted_connection'/'params' heuristisch abgeleitet.
    """
    d = _normalize_settings_dict(settings)

    # params: Dict -> Querystring
    params_qs = _dict_params_to_query(d.get("params"))
    auth = str(d.get("auth") or "").lower()

    # Trusted_Connection Heuristik
    tc_flag = bool(d.get("trusted_connection"))
    if not tc_flag and auth == "trusted":
        tc_flag = True
    if tc_flag and "TrustedServerCertificate" not in params_qs and "Trusted_Connection" not in params_qs:
        # sicherstellen, dass die Info in params landet (odbc_utils prüft params.lower())
        add = "Trusted_Connection=yes"
        params_qs = (params_qs + "&" + add) if params_qs else add

    return SimpleNamespace(
        server=d.get("server"),
        db_name=d.get("db_name"),
        username=d.get("username"),
        password=d.get("password"),
        driver=d.get("driver"),
        dsn=d.get("dsn"),
        auth=d.get("auth"),
        params=params_qs,
        trusted_connection=tc_flag,
        encrypt=d.get("encrypt"),
    )


def _extract_from_attempt(att: Dict[str, Any]) -> Dict[str, Any]:
    candidates = {
        "driver": att.get("driver") or att.get("provider"),
        "dsn": att.get("dsn"),
        "server": att.get("server") or att.get("host"),
        "db_name": att.get("database") or att.get("db"),
        "username": att.get("username") or att.get("user"),
        "auth": att.get("auth"),
        "trusted_connection": att.get("trusted_connection"),
        "encrypt": att.get("encrypt"),
        "params": att.get("params"),
    }
    # params im Attempt kann auch String sein -> in Dict heben (best-effort)
    if isinstance(candidates.get("params"), str):
        raw = candidates["params"]
        d: Dict[str, str] = {}
        for piece in raw.split("&"):
            if not piece or "=" not in piece:
                continue
            k, v = piece.split("=", 1)
            d[k] = v
        candidates["params"] = d
    return {k: v for k, v in candidates.items() if v not in (None, "")}


def _merge_preferring_left(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(a)
    for k, v in b.items():
        if k not in out or out[k] in (None, ""):
            out[k] = v
    return out


def _infer_auth_from_flags(d: Dict[str, Any]) -> Optional[str]:
    if d.get("trusted_connection") is True:
        return "trusted"
    if d.get("username") and d.get("password"):
        return d.get("auth") or "sql"
    return d.get("auth")


def build_config_candidate(settings, diag: Dict[str, Any]) -> Dict[str, Any]:
    """
    Baut einen Kandidaten entsprechend deinem Schema (inkl. 'auth' und params als Dict).
    Gibt **keine** echten Passwörter aus – Platzhalter wenn nötig.
    """
    base = _normalize_settings_dict(settings)
    best = _first_ok_attempt(diag)
    from_attempt = _extract_from_attempt(best) if best else {}
    merged = _merge_preferring_left(from_attempt, base)

    has_dsn = bool(merged.get("dsn"))
    config_entry: Dict[str, Any] = {}

    if has_dsn:
        config_entry["dsn"] = merged["dsn"]

    for key in ("driver", "server", "db_name", "username", "auth", "trusted_connection"):
        if key in merged:
            config_entry[key] = merged[key]

    if "params" in merged and isinstance(merged["params"], dict):
        config_entry["params"] = merged["params"]

    if "auth" not in config_entry or not config_entry["auth"]:
        inferred = _infer_auth_from_flags(merged)
        if inferred:
            config_entry["auth"] = inferred

    auth = str(config_entry.get("auth") or "").lower()
    needs_password = auth in ("sql", "aad-password", "aad-sp")
    if needs_password and not config_entry.get("trusted_connection", False):
        config_entry["password"] = "<<<SET_SECRET_HERE>>>"

    ordered_keys: List[str] = [
        "dsn", "driver", "server", "db_name", "username", "password",
        "auth", "trusted_connection", "params",
    ]
    config_entry = {k: config_entry[k] for k in ordered_keys if k in config_entry}
    return config_entry


def render_config_json(node: str, entry: Dict[str, Any]) -> str:
    payload = {"sql": {node: entry}}
    return json.dumps(payload, ensure_ascii=False, indent=2)


# =====================================
#   Config schreiben (atomar)
# =====================================

class ConfigUpdateError(RuntimeError):
    """Fehler beim Lesen/Schreiben/Mergen der config.json."""


def _load_json_file(path: str) -> Dict[str, Any]:
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as ex:
        raise ConfigUpdateError(f"config.json ist kein gültiges JSON: {path} ({ex})") from ex
    except OSError as ex:
        raise ConfigUpdateError(f"config.json konnte nicht gelesen werden: {path} ({ex})") from ex


def _save_json_atomic(path: str, data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp_fd, tmp_path = tempfile.mkstemp(prefix=".config.json.", suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)  # atomic on same filesystem
    except OSError as ex:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise ConfigUpdateError(f"config.json konnte nicht geschrieben werden: {path} ({ex})") from ex


def _mask_password(v: Any) -> Any:
    if isinstance(v, str) and v:
        return "******"
    return v


def _validate_entry(entry: Dict[str, Any]) -> None:
    """
    Basale Validierung je nach 'auth'.
    """
    if "dsn" in entry and entry["dsn"]:
        pass
    else:
        need = [k for k in ("driver", "server", "db_name") if not entry.get(k)]
        if need:
            raise ConfigUpdateError(f"Ungültiger SQL-Eintrag: fehlende Felder {need}. "
                                    f"Erforderlich: DSN ODER (driver, server, db_name).")

    auth = str(entry.get("auth") or "").lower()
    if auth in ("sql", "aad-password", "aad-sp"):
        if entry.get("password", None) == "":
            raise ConfigUpdateError("Password ist leerer String. Entfernen oder Platzhalter/Secret verwenden.")


def apply_config_update(
    *,
    config_path: str,
    node: str,
    new_entry: Dict[str, Any],
    create_backup: bool = True,
    keep_existing_password: bool = True,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Schreibt/merged den SQL-Block in die echte config.json.
    """
    _validate_entry(new_entry)
    root = _load_json_file(config_path)
    if not isinstance(root, dict):
        raise ConfigUpdateError("Die Wurzel der config.json ist kein Objekt (Dict).")
    sql = root.get("sql")
    if not isinstance(sql, dict):
        sql = {}
        root["sql"] = sql
    prev: Dict[str, Any] = {}
    if node in sql and isinstance(sql[node], dict):
        prev = dict(sql[node])

    placeholder = "<<<SET_SECRET_HERE>>>"
    prev_password = prev.get("password")
    new_password = new_entry.get("password")
    merged_entry = dict(prev)
    merged_entry.update(new_entry)

    if keep_existing_password:
        if (new_password is None) or (isinstance(new_password, str) and new_password.strip() == placeholder):
            if prev_password:
                merged_entry["password"] = prev_password
            else:
                if str(merged_entry.get("auth", "")).lower() in ("trusted", "aad-integrated", "aad-interactive", "aad-msi"):
                    merged_entry.pop("password", None)

    _validate_entry(merged_entry)

    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = None
    if not dry_run and create_backup and os.path.exists(config_path):
        backup_path = f"{config_path}.bak-{timestamp}"
        shutil.copy2(config_path, backup_path)

    sql[node] = merged_entry
    if not dry_run:
        _save_json_atomic(config_path, root)

    info = {
        "path": os.path.abspath(config_path),
        "backup_path": os.path.abspath(backup_path) if backup_path else None,
        "previous_entry_masked": {k: (_mask_password(v) if k == "password" else v) for k, v in prev.items()},
        "result_entry_masked": {k: (_mask_password(v) if k == "password" else v) for k, v in merged_entry.items()},
        "written": not dry_run,
    }
    return info


# =====================================
#   Diagnose orchestrieren (odbc_utils)
# =====================================

def connect_and_check(
    node: str,
    *,
    show_drivers: bool = True,
    show_dsns: bool = True,
    return_config_json: bool = True,
    write_config: bool = False,
    config_path: str = CONFIG_PATH,
    keep_existing_password: bool = True,
    dry_run: bool = False,
) -> Tuple[bool, Dict[str, Any], Optional[str], Optional[Dict[str, Any]]]:
    """
    Lädt SQL-Settings, führt Diagnose (core.odbc_utils) durch und erzeugt/optional schreibt einen config.json-Block.
    """
    # optionale Anzeigen
    if show_drivers:
        print("ODBC-Treiber (SQL Server):", odbc_utils.list_odbc_drivers())
    if show_dsns:
        print("ODBC-DSNs:", odbc_utils.list_odbc_data_sources())

    settings, info = load_sql_settings(config_path=config_path, node=node, env_override=True)
    print("Quelle:", info.get("source"), "| Node:", info.get("node_path"))
    print("Settings:", settings.as_dict(mask_secrets=True))

    # Adapter -> odbc_utils
    s_adapt = _adapt_for_odbc_utils(settings)
    ok, diag = odbc_utils.diagnose_with_fallbacks(s_adapt)
    print(diag.get("summary", ""))
    for i, att in enumerate(diag.get("attempts", []), 1):
        print(
            f"  [{i:02d}] {att.get('method','?'):<18} | driver={att.get('driver') or att.get('provider') or '-'} "
            f"| dsn={att.get('dsn') or '-'} | params={att.get('params') or att.get('conn_str_masked') or ''} | {att.get('duration_s','-')}s"
        )
        if "error" in att and att["error"]:
            print("       ", att["error"])
    if diag.get("suggestions"):
        print("\nHinweise:")
        for s in diag["suggestions"]:
            print(" -", s)

    config_json: Optional[str] = None
    candidate_entry: Optional[Dict[str, Any]] = None
    if return_config_json or write_config:
        candidate_entry = build_config_candidate(settings, diag)
        if return_config_json:
            config_json = render_config_json(node, candidate_entry)
            print("\nVorschlag für config.json (einfügbar):\n")
            print(config_json)
            print("\nHinweis: Passwort ist als Platzhalter gesetzt. Bitte sicher hinterlegen (Secret/ENV).")

    write_info: Optional[Dict[str, Any]] = None
    if write_config and candidate_entry is not None:
        print(f"\nSchreibe Update nach {os.path.abspath(config_path)} (dry_run={dry_run}) …")
        write_info = apply_config_update(
            config_path=config_path,
            node=node,
            new_entry=candidate_entry,
            create_backup=True,
            keep_existing_password=keep_existing_password,
            dry_run=dry_run,
        )
        print("Update:", {k: write_info[k] for k in ("path", "backup_path", "written")})
        print("Ergebnis (maskiert):", write_info.get("result_entry_masked"))

    return ok, diag, config_json, write_info
