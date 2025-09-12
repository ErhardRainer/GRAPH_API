# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.config.sql_config — SQL-Settings (JSON + ENV) für SQL Server
===============================================================================
Zweck
-----
Liest und schreibt SQL-Server-Einstellungen (inkl. Auth-Shorthand) in eine
`config.json` und/oder via Umgebungsvariablen und normalisiert sie für
`graphfw.io.writers.sql_writer.build_engine(...)`.

Highlights
----------
- Dot-Path-Resolver für Knotenpunkte, z. B. "connections.sql_prod"
- ENV-Overrides (case-insensitive), z. B. `GRAPHFW_SQLSERVER`, `Graphfw_SQLServer`
- `auth`-Shorthand: "sql", "trusted", "aad-password", "aad-integrated",
  "aad-interactive", "aad-msi", "aad-sp"
- Flexible `params`: String **oder** Dict → wird zu "k=v&k2=v2" normalisiert
- `SQLSettings.to_engine_args()` liefert fertige Argumente für `build_engine`
- **Neu:** `save_sql_settings(...)` — Knoten anlegen/aktualisieren (Datei wird bei
  Bedarf erstellt); mit `overwrite` lässt sich steuern, ob bestehende Keys
  überschrieben werden.

Beispiel (JSON)
---------------
{
  "connections": {
    "sql_prod": {
      "server": "myserver.database.windows.net",
      "db_name": "BI_RAW",
      "username": "svc_user",
      "password": "SECRET",
      "driver": "ODBC Driver 18 for SQL Server",
      "auth": "aad-password",
      "params": { "TrustServerCertificate": "yes" }
    }
  }
}

Beispiel (ENV)
--------------
GRAPHFW_SQLSERVER=myserver.database.windows.net
GRAPHFW_SQL_DB=BI_RAW
GRAPHFW_SQL_USER=svc_user
GRAPHFW_SQL_PWD=SECRET
GRAPHFW_SQL_DRIVER=ODBC Driver 18 for SQL Server
GRAPHFW_SQL_AUTH=aad-password
GRAPHFW_SQL_PARAMS=TrustServerCertificate=yes&Encrypt=yes

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 1.1.0 (2025-09-12)

Änderungsprotokoll
------------------
2025-09-12 - ER - Erstveröffentlichung (aus core.config extrahiert).
2025-09-12 - ER - Neu: save_sql_settings(config_path, node, settings, overwrite)
                   erstellt/aktualisiert den angegebenen Knoten in der JSON.
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple, Union
import json
import os
import tempfile
import urllib.parse

# Modulweite Version
__version__ = "1.1.0"


@dataclass(frozen=True)
class SQLSettings:
    """Normalisierte SQL-Einstellungen für build_engine(...)."""
    server: str
    db_name: str
    username: Optional[str] = None
    password: Optional[str] = None
    driver: str = "ODBC Driver 17 for SQL Server"
    params: Optional[str] = None   # bereits als "k=v&k2=v2" normalisiert

    def to_engine_args(self) -> Tuple[Dict[str, Any], str, Optional[str], Optional[str]]:
        """
        Liefert Argumente für graphfw.io.writers.sql_writer.build_engine:
            (cfg_dict, db_name, username, password)
        cfg_dict: {"server":..., "driver":..., "params":...}
        """
        cfg: Dict[str, Any] = {"server": self.server, "driver": self.driver}
        if self.params:
            cfg["params"] = self.params
        return cfg, self.db_name, self.username, self.password

    def as_dict(self, *, mask_secrets: bool = True) -> Dict[str, Any]:
        d = asdict(self)
        if mask_secrets and d.get("password"):
            d["password"] = "****"
        return d


# ------------------------------ Internals ------------------------------------

_AUTH_TO_PARAMS: Dict[str, str] = {
    "sql": "",
    "trusted": "Trusted_Connection=yes",
    "aad-password": "Authentication=ActiveDirectoryPassword",
    "aad-integrated": "Authentication=ActiveDirectoryIntegrated",
    "aad-interactive": "Authentication=ActiveDirectoryInteractive",
    "aad-msi": "Authentication=ActiveDirectoryMsi",
    "aad-sp": "Authentication=ActiveDirectoryServicePrincipal",
}

_ENV_KEYS: Dict[str, Iterable[str]] = {
    "server": (
        "GRAPHFW_SQLSERVER", "GRAPHFW_SQL_SERVER", "SQLSERVER", "SQL_SERVER",
        "Graphfw_SQLServer",
    ),
    "db_name": (
        "GRAPHFW_SQL_DB", "GRAPHFW_SQL_DATABASE", "SQL_DB", "SQL_DATABASE",
        "Graphfw_SQLDB",
    ),
    "username": (
        "GRAPHFW_SQL_USER", "GRAPHFW_SQL_USERNAME", "SQL_USER", "SQL_USERNAME",
        "Graphfw_SQLUser",
    ),
    "password": (
        "GRAPHFW_SQL_PWD", "GRAPHFW_SQL_PASSWORD", "SQL_PWD", "SQL_PASSWORD",
        "Graphfw_SQLPwd",
    ),
    "driver": (
        "GRAPHFW_SQL_DRIVER", "SQL_DRIVER",
    ),
    "params": (
        "GRAPHFW_SQL_PARAMS", "SQL_PARAMS",
    ),
    "auth": (
        "GRAPHFW_SQL_AUTH", "SQL_AUTH",
    ),
}


def _first_env(keys: Iterable[str]) -> Optional[str]:
    """Sucht den ersten gesetzten ENV-Wert (case-insensitive) aus einer Kandidatenliste."""
    if not keys:
        return None
    lowered = {k.lower(): k for k in os.environ.keys()}
    for key in keys:
        k = key.strip()
        if not k:
            continue
        v = os.environ.get(k)
        if v is not None:
            return v
        real = lowered.get(k.lower())
        if real and os.environ.get(real) is not None:
            return os.environ[real]
    return None


def _dot_get(d: Mapping[str, Any], path: str) -> Optional[Mapping[str, Any]]:
    """Holt einen verschachtelten Knoten mittels Dot-Path ("a.b.c")."""
    cur: Any = d
    for seg in (path or "").split("."):
        seg = seg.strip()
        if not seg:
            continue
        if not isinstance(cur, Mapping) or seg not in cur:
            return None
        cur = cur[seg]
    return cur if isinstance(cur, Mapping) else None


def _load_json(path: Union[str, Path]) -> Mapping[str, Any]:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8"))


def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    # Atomarer Write: zuerst Temp-Datei, dann rename
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as tmp:
        json.dump(data, tmp, indent=2, ensure_ascii=False)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def _normalize_params(params: Union[str, Mapping[str, Any], None]) -> Optional[str]:
    """
    Normalisiert `params` zu einem `k=v&k2=v2`-String.
    - dict → URL-encoded join
    - str  → unverändert (leading & wird entfernt)
    """
    if params is None:
        return None
    if isinstance(params, str):
        s = params.strip()
        if not s:
            return None
        return s.lstrip("&")
    if isinstance(params, Mapping):
        parts: List[str] = []
        for k, v in params.items():
            k_s = str(k).strip()
            if not k_s:
                continue
            v_s = "" if v is None else str(v)
            parts.append(f"{urllib.parse.quote_plus(k_s)}={urllib.parse.quote_plus(v_s)}")
        return "&".join(parts) if parts else None
    return None


def _merge_params(*values: Optional[str]) -> Optional[str]:
    """
    Führt mehrere Param-Strings zu einem zusammen, vermeidet doppelte Keys rudimentär.
    Spaltet auf '&', nimmt die erste Vorkommnis eines Keys (stable).
    """
    kv_pairs: List[Tuple[str, str]] = []
    seen: set[str] = set()
    for val in values:
        if not val:
            continue
        for piece in val.split("&"):
            piece = piece.strip()
            if not piece:
                continue
            if "=" in piece:
                k, v = piece.split("=", 1)
            else:
                k, v = piece, ""
            k_norm = urllib.parse.unquote_plus(k).lower()
            if k_norm in seen:
                continue
            seen.add(k_norm)
            kv_pairs.append((k, v))
    if not kv_pairs:
        return None
    return "&".join([f"{k}={v}" if v != "" else k for k, v in kv_pairs])


def _node_segments(node: str) -> List[str]:
    segs = [s.strip() for s in (node or "").split(".") if s.strip()]
    if not segs:
        raise ValueError("A non-empty node path is required (e.g., 'connections.sql_prod').")
    return segs


# ------------------------------ Public API: Load ------------------------------


def load_sql_settings(*,
                      config_path: Optional[Union[str, Path]] = None,
                      node: str = "sql",
                      env_override: bool = True) -> Tuple[SQLSettings, Dict[str, Any]]:
    """
    Lädt SQL-Settings aus JSON (optional) und überschreibt sie mit ENV (optional).

    Parameter
    ---------
    config_path : str|Path|None
        Pfad zur JSON-Datei. Wenn None oder nicht vorhanden, werden nur ENV gelesen.
    node : str
        Dot-Path zum Knotenpunkt in der JSON (z. B. "connections.sql_prod").
    env_override : bool
        Wenn True, überschreiben ENV-Variablen die JSON-Werte.

    Rückgabe
    --------
    (settings, info)
        settings : SQLSettings (für build_engine geeignet)
        info     : Diagnostics (source:"json|env|json+env", node_path, used_env_vars, warnings)
    """
    info: Dict[str, Any] = {"node_path": node, "used_env_vars": {}, "warnings": []}
    base: Dict[str, Any] = {}

    # 1) JSON laden & zum Knoten navigieren
    if config_path is not None and Path(config_path).exists():
        try:
            cfg = _load_json(config_path)
            node_map = _dot_get(cfg, node) if node else cfg
            if node_map is None:
                info["warnings"].append(f"Node '{node}' not found in JSON; using empty settings.")
            else:
                base = dict(node_map)
            info["source"] = "json"
            info["config_path"] = str(config_path)
        except Exception as ex:
            info["warnings"].append(f"JSON load error: {type(ex).__name__}: {ex}")
            info["source"] = "env"
    else:
        info["source"] = "env"

    # 2) ENV-Overrides (optional)
    env: Dict[str, Optional[str]] = {}
    if env_override:
        for field, keys in _ENV_KEYS.items():
            val = _first_env(keys)
            if val is not None:
                env[field] = val.strip()
                info["used_env_vars"][field] = True

    # 3) Felder einsammeln (ENV > JSON)
    def pick(name: str, default: Optional[str] = None) -> Optional[str]:
        return (env.get(name) if name in env else base.get(name, default))  # type: ignore[return-value]

    server = str(pick("server", "") or "").strip()
    db_name = str(pick("db_name", "") or "").strip()
    username = str(pick("username", "") or "").strip() or None
    password = str(pick("password", "") or "").strip() or None
    driver = str(pick("driver", "") or "").strip() or "ODBC Driver 17 for SQL Server"

    # auth → params (Shorthand)
    auth = (pick("auth") or "").strip().lower() or None
    auth_params = _AUTH_TO_PARAMS.get(auth, "") if auth else ""

    # params normalisieren; JSON kann dict|str liefern, ENV nur str
    params_json = _normalize_params(base.get("params"))
    params_env = _normalize_params(env.get("params")) if "params" in env else None
    params = _merge_params(params_json, auth_params, params_env)

    # Minimalvalidierung
    if not server:
        info["warnings"].append("Missing 'server' (JSON+ENV).")
    if not db_name:
        info["warnings"].append("Missing 'db_name' (JSON+ENV).")

    settings = SQLSettings(
        server=server,
        db_name=db_name,
        username=username,
        password=password,
        driver=driver,
        params=params,
    )
    return settings, info


# ------------------------------ Public API: Save ------------------------------


def save_sql_settings(*,
                      config_path: Union[str, Path],
                      node: str,
                      settings: Union[SQLSettings, Mapping[str, Any]],
                      overwrite: bool = False) -> Tuple[bool, Dict[str, Any]]:
    """
    Erstellt/aktualisiert einen Knoten in `config.json`.

    Verhalten
    ---------
    - Existiert die Datei nicht, wird sie neu erstellt.
    - `node` ist Pflicht (Dot-Path, z. B. "connections.sql_prod").
    - Existiert der Zielknoten **nicht**, wird er angelegt.
    - Existiert der Zielknoten **und** ist ein Mapping:
        • overwrite=False  → **merge ohne Überschreiben**; vorhandene Keys bleiben,
                             neue Keys werden ergänzt (konfligierende Keys -> skipped_keys).
        • overwrite=True   → **vollständiges Überschreiben** des Knotens durch `settings`.
    - Existiert der Zielknoten, ist aber **kein Mapping**:
        • overwrite=False  → Fehlermeldung (ok=False).
        • overwrite=True   → Ersetze den Wert komplett.

    Parameter
    ---------
    config_path : Pfad zur `config.json` (wird erstellt, wenn nicht vorhanden)
    node        : Dot-Path zum Knoten (Pflicht!)
    settings    : `SQLSettings` oder Mapping mit Feldern (server, db_name, …)
    overwrite   : siehe Verhalten oben

    Rückgabe
    --------
    (ok, info)
        ok   : True/False
        info : { "config_path", "node", "created_file", "created_nodes": [...],
                 "overwritten": bool, "skipped_keys": [...], "warnings": [...], "error"?: str }
    """
    info: Dict[str, Any] = {
        "config_path": str(config_path),
        "node": node,
        "created_file": False,
        "created_nodes": [],
        "overwritten": False,
        "skipped_keys": [],
        "warnings": [],
    }
    try:
        if isinstance(settings, SQLSettings):
            value: Dict[str, Any] = {
                "server": settings.server,
                "db_name": settings.db_name,
                "username": settings.username,
                "password": settings.password,
                "driver": settings.driver,
                "params": settings.params,
            }
            # entferne None-Felder
            value = {k: v for k, v in value.items() if v is not None}
        elif isinstance(settings, Mapping):
            value = {str(k): v for k, v in settings.items()}
        else:
            raise TypeError("settings must be SQLSettings or a mapping")

        # Datei laden oder Grundgerüst
        path = Path(config_path)
        if path.exists():
            root: Dict[str, Any] = dict(_load_json(path))
        else:
            root = {}
            info["created_file"] = True

        # zum Parent-Knoten navigieren / erstellen
        segs = _node_segments(node)
        cur = root
        for i, seg in enumerate(segs[:-1]):
            if seg not in cur or not isinstance(cur[seg], Mapping):
                cur[seg] = {}
                info["created_nodes"].append(".".join(segs[: i + 1]))
            cur = cur[seg]  # type: ignore[index]

        leaf = segs[-1]
        if leaf not in cur:
            # brandneu anlegen
            cur[leaf] = value
        else:
            existing = cur[leaf]
            if isinstance(existing, Mapping) and isinstance(value, Mapping):
                if overwrite:
                    cur[leaf] = value
                    info["overwritten"] = True
                else:
                    # Merge ohne Überschreiben: nur fehlende Keys ergänzen
                    merged = dict(existing)
                    for k, v in value.items():
                        if k in merged:
                            info["skipped_keys"].append(k)
                        else:
                            merged[k] = v
                    cur[leaf] = merged
            else:
                if overwrite:
                    cur[leaf] = value
                    info["overwritten"] = True
                else:
                    info["error"] = "Node exists and is not a mapping; set overwrite=True to replace."
                    return False, info

        # Datei atomar schreiben
        _write_json_atomic(path, root)
        return True, info

    except Exception as ex:
        info["error"] = f"{type(ex).__name__}: {ex}"
        return False, info

# ------------------------------ Version Hooks --------------------------------
# Bequemer Zugriff: load_sql_settings.__version__, save_sql_settings.__version__,
# und SQLSettings.__version__
SQLSettings.__version__ = __version__               # type: ignore[attr-defined]
load_sql_settings.__version__ = __version__         # type: ignore[attr-defined]
save_sql_settings.__version__ = __version__         # type: ignore[attr-defined]

# Public API
__all__ = ["SQLSettings", "load_sql_settings", "save_sql_settings", "__version__"]