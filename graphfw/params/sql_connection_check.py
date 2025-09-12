from __future__ import annotations

import json
import os
import shutil
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import text  # type: ignore

# Projekt-Utilities (existieren laut Repo-Beschreibung)
from graphfw.params.resolve import load_sql_settings
from graphfw.core.util import list_odbc_drivers, list_odbc_data_sources  # Anzeige, keine harte Abhängigkeit

# Konstante: Pfad zur bestehenden Konfiguration
try:
    from graphfw.params.resolve import CONFIG_PATH  # bevorzugte Quelle
except Exception:
    CONFIG_PATH = "config.json"


# =========================
#   Mini-Diagnose Helpers
# =========================

def quick_check(engine) -> Any:
    """Führt SELECT 1 aus und gibt das Ergebnis zurück."""
    with engine.connect() as c:
        return c.execute(text("SELECT 1")).scalar()


def show_settings(settings) -> None:
    """Gibt zentrale Settings ohne Secrets aus (kompakt)."""
    d = settings.as_dict(mask_secrets=True)
    keys = ("server", "db_name", "username", "driver", "dsn", "params")
    print({k: d[k] for k in keys if k in d})


def _first_ok_attempt(diag: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Erstes erfolgreiches Attempt aus der Diagnose finden."""
    for att in diag.get("attempts", []):
        if att.get("ok"):
            return att
    return None


def _normalize_settings_dict(settings) -> Dict[str, Any]:
    """
    Konvertiert Settings-Objekt in Dict (ohne Secrets, mit Standardfeldern).
    Zielt auf ein kompaktes, stabiles Set von Schlüsseln für config.json.
    """
    d = settings.as_dict(mask_secrets=False) if hasattr(settings, "as_dict") else dict(settings or {})
    norm = {
        "server": d.get("server") or d.get("host") or d.get("hostname"),
        "db_name": d.get("db_name") or d.get("database") or d.get("db"),
        "username": d.get("username") or d.get("user") or d.get("uid"),
        "driver": d.get("driver") or d.get("provider"),
        "dsn": d.get("dsn"),
        "trusted_connection": d.get("trusted_connection"),
        "encrypt": d.get("encrypt"),
        "params": d.get("params") or d.get("options"),
    }
    return {k: v for k, v in norm.items() if v not in (None, "")}


def _extract_from_attempt(att: Dict[str, Any]) -> Dict[str, Any]:
    """Feldwerte aus einem Diagnose-Attempt ableiten (best-effort)."""
    candidates = {
        "driver": att.get("driver") or att.get("provider"),
        "dsn": att.get("dsn"),
        "server": att.get("server") or att.get("host"),
        "db_name": att.get("database") or att.get("db"),
        "username": att.get("username") or att.get("user"),
        "trusted_connection": att.get("trusted_connection"),
        "encrypt": att.get("encrypt"),
        "params": att.get("params"),
    }
    return {k: v for k, v in candidates.items() if v not in (None, "")}


def _merge_preferring_left(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    """Merge zweier Dicts: Werte aus a haben Vorrang, b füllt Lücken."""
    out = dict(a)
    for k, v in b.items():
        if k not in out or out[k] in (None, ""):
            out[k] = v
    return out


def build_config_candidate(settings, diag: Dict[str, Any]) -> Dict[str, Any]:
    """
    Erzeugt einen sinnvollen config.json-Eintrag auf Basis der Settings + Diagnose.
    - Bevorzugt den ersten erfolgreichen Attempt.
    - Gibt niemals Password aus (nur Platzhalter).
    - DSN-basiert, wenn möglich; sonst explizite Felder.
    """
    base = _normalize_settings_dict(settings)
    best = _first_ok_attempt(diag)
    from_attempt = _extract_from_attempt(best) if best else {}
    merged = _merge_preferring_left(from_attempt, base)

    has_dsn = bool(merged.get("dsn"))

    config_entry: Dict[str, Any] = {}
    if has_dsn:
        config_entry["dsn"] = merged["dsn"]
        for opt in ("trusted_connection", "encrypt"):
            if opt in merged:
                config_entry[opt] = merged[opt]
        if "params" in merged:
            config_entry["params"] = merged["params"]
    else:
        for key in ("driver", "server", "db_name", "username"):
            if key in merged:
                config_entry[key] = merged[key]
        for opt in ("trusted_connection", "encrypt"):
            if opt in merged:
                config_entry[opt] = merged[opt]
        if "params" in merged:
            config_entry["params"] = merged["params"]

    # Passwort nur als Platzhalter setzen, wenn nicht Trusted_Connection
    if not config_entry.get("trusted_connection", False):
        config_entry["password"] = "<<<SET_SECRET_HERE>>>"

    ordered_keys: List[str] = [
        "dsn", "driver", "server", "db_name", "username", "password",
        "trusted_connection", "encrypt", "params",
    ]
    config_entry = {k: config_entry[k] for k in ordered_keys if k in config_entry}
    return config_entry


def render_config_json(node: str, entry: Dict[str, Any]) -> str:
    """
    JSON-Block für die config.json erzeugen:
    {
      "sql": {
        "<node>": { ... }
      }
    }
    """
    payload = {"sql": {node: entry}}
    return json.dumps(payload, ensure_ascii=False, indent=2)


# =====================================
#   NEU: Config tatsächlich aktualisieren
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
        # Cleanup tmpfile if replace failed
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise ConfigUpdateError(f"config.json konnte nicht geschrieben werden: {path} ({ex})") from ex


def _mask_password(v: Any) -> Any:
    if isinstance(v, str) and v and len(v) > 0:
        return "******"
    return v


def _validate_entry(entry: Dict[str, Any]) -> None:
    """
    Validiert minimale Struktur:
    - Entweder DSN ODER (driver + server + db_name) vorhanden.
    - username empfehlenswert bei SQL-Auth (wenn trusted_connection=False).
    - password darf fehlen (z. B. ENV/Secrets), darf aber nicht versehentlich leerer String sein.
    """
    if "dsn" in entry and entry["dsn"]:
        pass  # ok (DSN deckt Details ab)
    else:
        need = [k for k in ("driver", "server", "db_name") if not entry.get(k)]
        if need:
            raise ConfigUpdateError(f"Ungültiger SQL-Eintrag: fehlende Felder {need}. "
                                    f"Erforderlich: DSN ODER (driver, server, db_name).")
    if entry.get("trusted_connection") is False:
        # SQL-Auth: username empfohlen
        if not entry.get("username"):
            # kein harter Fehler – warnen durch Exception-Message? wir lassen zu, aber Hinweis im Info-Objekt
            pass
        if "password" in entry and entry.get("password") == "":
            raise ConfigUpdateError("Password ist leerer String. Entfernen oder Placeholder/Secret verwenden.")


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

    Regeln
    ------
    - Struktur unter `"sql"` wird angelegt, falls nicht vorhanden.
    - Update nur für den spezifizierten `node`.
    - Wenn `keep_existing_password=True` und `new_entry.password` ist ein Platzhalter
      oder fehlt, wird ein vorhandenes Passwort NICHT überschrieben.
    - Optionales `create_backup`: legt `<config>.bak-YYYYmmddHHMMSS` an.
    - `dry_run=True`: schreibt NICHT, liefert aber das resultierende Dict (Preview).

    Parameters
    ----------
    config_path : str
        Pfad zur config.json.
    node : str
        Ziel-Knoten unter `"sql"`.
    new_entry : dict
        Bereits validierter Eintrag (z. B. aus `build_config_candidate`).
    create_backup : bool
        Vor dem Schreiben eine Backup-Kopie erstellen.
    keep_existing_password : bool
        Vorhandenes Passwort behalten, wenn `new_entry` keins bereitstellt oder nur den Platzhalter enthält.
    dry_run : bool
        Kein persistenter Schreibvorgang, nur Simulation.

    Returns
    -------
    info : dict
        Informationen zum Update-Vorgang (`path`, `backup_path`, `previous_entry_masked`, `result_entry_masked`, `written`).
    """
    # Validieren (früh)
    _validate_entry(new_entry)

    # Bestehende Datei laden (oder leeres Dict)
    root = _load_json_file(config_path)

    if not isinstance(root, dict):
        raise ConfigUpdateError("Die Wurzel der config.json ist kein Objekt (Dict).")

    sql = root.get("sql")
    if sql is None or not isinstance(sql, dict):
        sql = {}
        root["sql"] = sql

    prev: Dict[str, Any] = {}
    if node in sql and isinstance(sql[node], dict):
        prev = dict(sql[node])

    # Passwort-Handling
    placeholder = "<<<SET_SECRET_HERE>>>"
    prev_password = prev.get("password")
    new_password = new_entry.get("password")
    merged_entry = dict(prev)
    merged_entry.update(new_entry)

    if keep_existing_password:
        # Falls der neue Eintrag kein Passwort mitliefert oder nur Placeholder → altes Passwort behalten
        if (new_password is None) or (isinstance(new_password, str) and new_password.strip() == placeholder):
            if prev_password:
                merged_entry["password"] = prev_password
            else:
                # Kein vorhandenes Passwort; wenn TrustedConnection, Passwort entfernen
                if merged_entry.get("trusted_connection", False):
                    merged_entry.pop("password", None)

    # Nochmals validieren nach Merge
    _validate_entry(merged_entry)

    # Schreiben vorbereiten
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    backup_path = None
    if not dry_run and create_backup and os.path.exists(config_path):
        backup_path = f"{config_path}.bak-{timestamp}"
        try:
            shutil.copy2(config_path, backup_path)
        except OSError as ex:
            raise ConfigUpdateError(f"Backup konnte nicht erstellt werden: {backup_path} ({ex})") from ex

    # Aktualisieren
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
#   Haupt-Workflow (unverändert + Flags)
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
    Lädt SQL-Settings, führt Diagnose durch und gibt optional einen validen config.json-Block zurück.
    Optional kann der Block **persistiert** (in config.json geschrieben) werden.

    Parameters
    ----------
    node : str
        Knotenname in der config.json (z. B. "prod", "dev" oder "default").
    show_drivers : bool
        Verfügbare ODBC-Treiber (SQL Server) auflisten.
    show_dsns : bool
        Registrierte ODBC-DSNs auflisten.
    return_config_json : bool
        Wenn True, wird ein JSON-Block (String) erzeugt.
    write_config : bool
        Wenn True, wird die echte config.json aktualisiert (siehe `apply_config_update`).
    config_path : str
        Pfad zur config.json.
    keep_existing_password : bool
        Beim Schreiben vorhandenes Passwort erhalten, falls `new_entry` keins/Platzhalter enthält.
    dry_run : bool
        Schreibvorgang simulieren (kein persistentes Update).

    Returns
    -------
    ok : bool
        True, wenn mindestens ein Diagnose-Versuch erfolgreich war.
    diag : dict
        Vollständige Diagnostik inklusive Versuche und Hinweisen.
    config_json : str | None
        JSON-Block für `config.json` (nur wenn `return_config_json=True`).
    write_info : dict | None
        Ergebnis des Schreibvorgangs (nur wenn `write_config=True`), andernfalls None.
    """
    print(f"\n=== Node: {node} ===")
    if show_drivers:
        print("ODBC-Treiber (SQL Server):", list_odbc_drivers())
    if show_dsns:
        print("ODBC-DSNs:", list_odbc_data_sources())

    settings, info = load_sql_settings(config_path=config_path, node=node, env_override=True)
    print("Quelle:", info.get("source"), "| Node:", info.get("node_path"))
    print("Settings:", settings.as_dict(mask_secrets=True))

    # Diagnose
    from graphfw.params.resolve import diagnose_with_fallbacks  # lokaler Import vermeidet Zyklus
    ok, diag = diagnose_with_fallbacks(settings)
    print(diag.get("summary", ""))
    for i, att in enumerate(diag.get("attempts", []), 1):
        status = "OK" if att.get("ok", False) else ("OK" if att.get("method", "").startswith(("pyodbc", "ado", "pymssql")) and "error" not in att else "ERR")
        print(
            f"  [{i:02d}] {att.get('method','?'):<18} | driver={att.get('driver') or att.get('provider')} "
            f"| dsn={att.get('dsn') or '-'} | params={att.get('params') or ''} | {att.get('duration_s','-')}s"
        )
        if "error" in att and att["error"]:
            print("       ", att["error"])
    if diag.get("suggestions"):
        print("\nHinweise:")
        for s in diag["suggestions"]:
            print(" -", s)

    # Konfigurationsvorschlag
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
