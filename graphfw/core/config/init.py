# -*- coding: utf-8 -*-
"""
graphfw.core.config — Konfigurations-Subpackage

Aktuell:
- SQL: graphfw.core.config.sql_config (load_sql_settings, save_sql_settings, SQLSettings)

Public API (re-exports):
    from graphfw.core.config import load_sql_settings, save_sql_settings, SQLSettings
"""
from .sql_config import SQLSettings, load_sql_settings, save_sql_settings, __version__

__all__ = ["SQLSettings", "load_sql_settings", "save_sql_settings", "__version__"]
