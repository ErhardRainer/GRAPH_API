# resolve.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.params.resolve — Job-Resolution: MODE + Quellen → valide Jobs
===============================================================================
Zweck:
    - Vereinheitlicht die Auflösung von Parametern aus mehreren Quellen:
        Priorität: CLI > Job-Eintrag (bei MODE=json) > JSON-Defaults > CONFIG-Block
    - Validiert/konvertiert anhand eines ParamSchema (siehe schema.py)
    - Liefert eine Liste "bereinigter" Jobs + Diagnosen (info)

Begriffe:
    MODE:
      - 'config' : Ein Job (CONFIG-Block + optionale CLI-Overrides)
      - 'params' : Ein Job (nur CLI, Credentials etc. extern)
      - 'json'   : Mehrere Jobs aus einem Parameter-JSON ('defaults' + 'jobs')

Struktur Parameter-JSON (Beispiel):
{
  "defaults": { "SITE_URL": "...", "COLUMNS": "*", "CreateCSV": true, ... },
  "jobs": [
    { "LIST_TITLE": "ListA", "TOP": 100 },
    { "SITE_URL": "https://...", "LIST_TITLE": "ListB", "FILTER": "Status eq 'Open'" }
  ]
}

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union
import json

from .schema import ParamSchema, default_sharepoint_job_schema


# ------------------------------ Dateilader JSON -------------------------------

def load_param_json(param_json_path: Union[str, Path]) -> Dict[str, Any]:
    p = Path(param_json_path)
    if not p.exists():
        raise FileNotFoundError(f"Parameter JSON not found: {param_json_path}")
    try:
        obj = json.loads(p.read_text(encoding="utf-8"))
    except Exception as ex:
        raise RuntimeError(f"Failed to parse parameter JSON '{param_json_path}': {ex}")
    if "jobs" not in obj or not isinstance(obj["jobs"], list):
        raise ValueError("Parameter JSON must contain a 'jobs' array.")
    if "defaults" in obj and not isinstance(obj["defaults"], dict):
        raise ValueError("'defaults' must be an object if present.")
    return obj


# ------------------------------ Hilfsfunktionen -------------------------------

def _ns_to_dict(ns: Any, keys: Sequence[str]) -> Dict[str, Any]:
    """Extrahiert nur relevante Keys aus einem argparse.Namespace (oder dict)."""
    out: Dict[str, Any] = {}
    if ns is None:
        return out
    if isinstance(ns, dict):
        src = ns
    else:
        src = vars(ns)
    for k in keys:
        if k in src and src[k] is not None:
            out[k] = src[k]
    return out


def _merge_priority(*sources: Dict[str, Any]) -> Dict[str, Any]:
    """
    Merged mehrere dicts; spätere Quellen überschreiben frühere.
    Beispiel: _merge_priority(CONFIG, JSON-defaults, JOB, CLI)
    """
    out: Dict[str, Any] = {}
    for src in sources:
        if not src:
            continue
        out.update(src)
    return out


@dataclass
class ResolveInfo:
    """Diagnose-Objekt zur Auflösung."""
    mode: str
    json_path: Optional[str] = None
    jobs_count: int = 0
    errors: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)


# ------------------------------ Hauptfunktion --------------------------------

def resolve_mode_and_jobs_generic(
    *,
    mode: str,
    cli: Optional[Any],
    config_block: Optional[Dict[str, Any]],
    param_json_path: Optional[Union[str, Path]] = None,
    schema: Optional[ParamSchema] = None,
    keys_of_interest: Optional[Sequence[str]] = None,
) -> Tuple[str, List[Dict[str, Any]], ResolveInfo]:
    """
    Ermittelt die effektive Job-Liste gemäß MODE & Quellen.

    Parameter:
        mode: 'config' | 'params' | 'json'
        cli: argparse.Namespace oder dict mit CLI-Args
        config_block: der CONFIG-Block im Skript (darf None sein)
        param_json_path: Pfad auf Parameter-JSON (für MODE='json')
        schema: ParamSchema (Default: default_sharepoint_job_schema())
        keys_of_interest: welche CLI-Keys übernommen werden (Default: SharePoint-Standard)

    Rückgabe:
        (mode, jobs_clean, info)
    """
    schema = schema or default_sharepoint_job_schema()
    info = ResolveInfo(mode=mode)

    # Standardfeldliste (SharePoint-Job)
    keys_of_interest = keys_of_interest or (
        "SITE_URL",
        "LIST_TITLE",
        "COLUMNS",
        "FILTER",
        "TOP",
        "CreateCSV",
        "CSVDir",
        "CSVFile",
        "Display",
        "TZPolicy",
        "UnknownFields",
    )

    # CONFIG-Block (kann None sein)
    cfg = dict(config_block or {})

    # CLI (nur relevante Keys)
    cli_dict = _ns_to_dict(cli, keys_of_interest)

    jobs_clean: List[Dict[str, Any]] = []
    errors_all: List[str] = []

    if mode == "json":
        if not param_json_path:
            raise ValueError("MODE='json' requires 'param_json_path'.")

        obj = load_param_json(param_json_path)
        info.json_path = str(param_json_path)

        json_defaults = obj.get("defaults", {})
        jobs = obj["jobs"]

        # Für jeden Job: CONFIG < JSON-defaults < JOB < CLI
        for job in jobs:
            merged = _merge_priority(cfg, json_defaults, job, cli_dict)
            clean, errs = schema.coerce_and_validate(merged)
            if errs:
                errors_all.extend([f"job: {job} -> " + e for e in errs])
            else:
                jobs_clean.append(clean)

        info.jobs_count = len(jobs_clean)

    elif mode == "params":
        # Ein Job: CONFIG < CLI
        merged = _merge_priority(cfg, cli_dict)
        clean, errs = schema.coerce_and_validate(merged)
        if errs:
            errors_all.extend(errs)
        else:
            jobs_clean.append(clean)
        info.jobs_count = len(jobs_clean)

    elif mode == "config":
        # Ein Job: nur CONFIG (plus CLI-Overrides falls übergeben)
        merged = _merge_priority(cfg, cli_dict)
        clean, errs = schema.coerce_and_validate(merged)
        if errs:
            errors_all.extend(errs)
        else:
            jobs_clean.append(clean)
        info.jobs_count = len(jobs_clean)

    else:
        raise ValueError(f"Unknown MODE: {mode!r}")

    info.errors = errors_all
    return mode, jobs_clean, info


__all__ = ["resolve_mode_and_jobs_generic", "load_param_json", "ResolveInfo"]
