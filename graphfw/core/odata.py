# odata.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.odata — Kompakter OData-Query-Builder für Microsoft Graph
===============================================================================
Zweck:
    - Hilft beim sauberen Zusammensetzen von $select, $expand, $filter, $orderby,
      $search, $count, $top, $skip.
    - Gibt am Ende ein dict (params) zurück, das direkt an GraphClient übergeben
      werden kann (GraphClient normalisiert Keys bei Bedarf zu '$…').

Beispiel:
    q = (OData()
            .select("id","displayName")
            .expand(Expand("members", select=["id","userPrincipalName"]))
            .filter("accountEnabled eq true")
            .orderby("displayName asc")
            .top(100))
    params = q.to_params()
    # -> {"$select":"id,displayName", "$expand":"members($select=id,userPrincipalName)", "$filter":"..."}

Autor: Erhard Rainer (www.erhard-rainer.com)
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, List, Optional, Dict


def _as_csv(values: Iterable[str]) -> str:
    return ",".join([str(v).strip() for v in values if str(v).strip()])


@dataclass
class Expand:
    """
    Repräsentiert einen $expand-Eintrag mit optionalen Unteroptionen.

    Beispiel:
        Expand("fields", select=["ID","Title"])
        Expand("members", select=["id","userPrincipalName"], filter="accountEnabled eq true")
    """
    entity: str
    select: Optional[List[str]] = field(default=None)
    orderby: Optional[str] = field(default=None)
    filter: Optional[str] = field(default=None)
    top: Optional[int] = field(default=None)
    count: Optional[bool] = field(default=None)
    search: Optional[str] = field(default=None)

    def to_string(self) -> str:
        opts: List[str] = []
        if self.select:
            opts.append(f"$select={_as_csv(self.select)}")
        if self.orderby:
            opts.append(f"$orderby={self.orderby.strip()}")
        if self.filter:
            opts.append(f"$filter={self.filter.strip()}")
        if self.top is not None:
            opts.append(f"$top={int(self.top)}")
        if self.count is not None:
            opts.append(f"$count={'true' if self.count else 'false'}")
        if self.search:
            # Achtung: $search erfordert oft ConsistencyLevel: eventual
            opts.append(f"$search={self.search.strip()}")

        if not opts:
            return self.entity.strip()

        inner = ";".join(opts)  # Semikolon-separiert in Expand-Optionen
        return f"{self.entity.strip()}({inner})"


class OData:
    """Fluent Builder für OData-Query-Parameter."""

    def __init__(self) -> None:
        self._select: List[str] = []
        self._expand: List[Expand] = []
        self._filter: Optional[str] = None
        self._orderby: Optional[str] = None
        self._search: Optional[str] = None
        self._count: Optional[bool] = None
        self._top: Optional[int] = None
        self._skip: Optional[int] = None

    # ------------------------------- Fluent API -------------------------------

    def select(self, *fields: str) -> "OData":
        self._select.extend([f for f in fields if f and str(f).strip()])
        return self

    def expand(self, *expands: Expand) -> "OData":
        self._expand.extend([e for e in expands if isinstance(e, Expand)])
        return self

    def filter(self, expr: str) -> "OData":
        self._filter = expr.strip()
        return self

    def orderby(self, expr: str) -> "OData":
        self._orderby = expr.strip()
        return self

    def search(self, term: str) -> "OData":
        self._search = term.strip()
        return self

    def count(self, enabled: bool = True) -> "OData":
        self._count = bool(enabled)
        return self

    def top(self, n: int) -> "OData":
        self._top = int(n)
        return self

    def skip(self, n: int) -> "OData":
        self._skip = int(n)
        return self

    # -------------------------------- Output ----------------------------------

    def to_params(self) -> Dict[str, str]:
        params: Dict[str, str] = {}
        if self._select:
            params["$select"] = _as_csv(self._select)
        if self._expand:
            params["$expand"] = ",".join([e.to_string() for e in self._expand])
        if self._filter:
            params["$filter"] = self._filter
        if self._orderby:
            params["$orderby"] = self._orderby
        if self._search:
            params["$search"] = self._search
        if self._count is not None:
            params["$count"] = "true" if self._count else "false"
        if self._top is not None:
            params["$top"] = str(self._top)
        if self._skip is not None:
            params["$skip"] = str(self._skip)
        return params

    # Kleines Extra
    def __repr__(self) -> str:
        return f"OData({self.to_params()})"


__all__ = ["OData", "Expand"]
