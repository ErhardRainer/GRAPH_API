# logbuffer.py
# -*- coding: utf-8 -*-
"""
===============================================================================
graphfw.core.logbuffer — Print + Log-Puffer → DataFrame
===============================================================================
Zweck:
    - Einfache, abhängige-lose Logging-Hilfe, die
        * sofort auf die Konsole schreibt (print)
        * und parallel strukturierte Log-Einträge puffert.
    - Später kann der Puffer als pandas-DataFrame exportiert werden (falls pandas
      installiert ist) oder als reine Liste von dicts weiterverarbeitet werden.

Besonderheiten:
    - Maskiert sensible Schlüssel (client_secret, password, token, …)
    - Level: DEBUG/INFO/WARNING/ERROR
    - ISO8601 Zeitstempel

Beispiel:
    lb = LogBuffer()
    lb.info("Starte Job", job="sp_list", site=site_url)
    ...
    df_logs = lb.to_df()   # falls pandas vorhanden

Autor: dein Projekt
Version: 1.0.0 (2025-09-11)
===============================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from .util import mask_secrets  # relative Import innerhalb graphfw.core


@dataclass
class LogBuffer:
    """
    Kleiner Logger:
        - echo: sofort in Konsole ausgeben
        - mask_keys: Keys, deren Werte in context maskiert werden
    """
    echo: bool = True
    mask_keys: Sequence[str] = field(default=("client_secret", "password", "secret", "token"))

    _entries: List[Dict[str, Any]] = field(default_factory=list, init=False)

    # ------------------------------ Basis-API ---------------------------------

    def log(self, level: str, message: str, **context: Any) -> None:
        """Allgemeiner Logeintrag."""
        ts = datetime.now(timezone.utc).isoformat()
        ctx_masked = mask_secrets(context, mask_keys=self.mask_keys) if context else {}
        entry = {"ts": ts, "level": level.upper(), "message": message, **ctx_masked}
        self._entries.append(entry)
        if self.echo:
            # Kompakte Mensch-Lesbarkeit
            kv = " ".join(f"{k}={v}" for k, v in ctx_masked.items())
            print(f"[{entry['level']}] {entry['ts']} {entry['message']}" + (f" | {kv}" if kv else ""))

    # ------------------------------ Komfort-API -------------------------------

    def debug(self, message: str, **context: Any) -> None:
        self.log("DEBUG", message, **context)

    def info(self, message: str, **context: Any) -> None:
        self.log("INFO", message, **context)

    def warning(self, message: str, **context: Any) -> None:
        self.log("WARNING", message, **context)

    def error(self, message: str, **context: Any) -> None:
        self.log("ERROR", message, **context)

    # ------------------------------ Export-API --------------------------------

    def to_list(self) -> List[Dict[str, Any]]:
        """Rohdaten (Liste von dicts)."""
        return list(self._entries)

    def to_df(self):
        """Export nach pandas.DataFrame (falls pandas vorhanden)."""
        try:
            import pandas as pd  # noqa
        except Exception:
            return self.to_list()
        return pd.DataFrame(self._entries)

    # ------------------------------ Extras ------------------------------------

    def __len__(self) -> int:
        return len(self._entries)

    def clear(self) -> None:
        self._entries.clear()


__all__ = ["LogBuffer"]
