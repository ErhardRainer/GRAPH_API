# -*- coding: utf-8 -*-
# Re-exports für Kernklassen und Subpackages

from .auth import TokenProvider
from .http import GraphClient
from .odata import OData, Expand
from .util import *  # optional: nur wenn gewünscht
from .logbuffer import LogBuffer

# Subpackages als Attribute verfügbar machen (kein Selbst-Import!)
from . import config as config          # setzt graphfw/core/config/__init__.py voraus
from . import odbc_utils as odbc_utils  # setzt graphfw/core/odbc_utils.py voraus

# Kuratierte Re-Exports aus odbc_utils (optional, bequem)
from .odbc_utils import (
    list_odbc_drivers,
    list_odbc_data_sources,
    diagnose_sql_connection,
    diagnose_with_fallbacks,
)

__all__ = [
    "TokenProvider",
    "GraphClient",
    "OData",
    "Expand",
    "LogBuffer",
    "config",
    "odbc_utils",              # Submodul bleibt erreichbar
    # kuratierte Shortcuts:
    "list_odbc_drivers",
    "list_odbc_data_sources",
    "diagnose_sql_connection",
    "diagnose_with_fallbacks",
]
