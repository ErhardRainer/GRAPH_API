# Domains – Funktionsbenennung & Implementierungsregeln

Dieses Dokument legt die **Namenskonvention**, **Ordnerstruktur** und **Entwicklungsregeln** für alle Domänenmodule unter `graphfw/domains/` fest (z. B. **SharePoint**, **AAD/Entra**, **Teams**, **Outlook**, **Intune**, **Planner**, **Analytics**, **Security**).

Ziel: **konsistente, vorhersagbare API** – am Namen ist erkennbar *was*, *woher* und *in welcher Form* geliefert wird.

---

## 1) Namensschema

**Allgemeine Regel**
`<domain>.<resource>[.<subresource>].<action>[_<format>]`

* **domain** ∈ `{sharepoint, aad, teams, outlook, intune, planner, analytics, security}`
* **resource/subresource**: i. d. R. **Plural** wie in Graph (z. B. `lists.items`, `users`, `groups.members`)
  → Modulnamen: **niemals** Python-Reservierte (statt `list` → `lists`, statt `file` → `files`).
* **action**: `get` (ein Objekt), `list` (Sammlung), `iter` (Generator), `create`, `update`, `delete`, `export`, `sync`, …
* **\_format** (Suffix, optional): `_df` → `pandas.DataFrame`, `_json` → native Python-Struktur, `_iter` → Generator, `_csv` → Export.
* **Filter-/Lookup-Spezifikation**: über **`by_…`** (z. B. `get_by_id_df`, `list_by_upn_df`, `list_by_filter_df`).

**Beispiele**

* `sharepoint.lists.items.list_df(...)`
* `aad.users.get_by_id_df(user_id, ...)`
* `teams.teams.channels.list_df(team_id, ...)`
* `outlook.users.mail.list_df(user_upn, folder_id=None, ...)`

---

## 2) Ordner- & Modulstruktur

```
graphfw/
  domains/
    sharepoint/
      lists/
        items.py       # list_df(), iter(), get_by_id_df(), ...
        columns.py     # list_df() – Schema/Spalten
      drives/
        items.py       # Bibliotheken/DriveItems
      __init__.py
    aad/
      users.py         # list_df(), get_by_id_df(), ...
      groups.py        # list_df(), members.list_df(), owners.list_df()
      __init__.py
    teams/
      teams.py         # list_df(), channels.list_df(), members.list_df()
      chats.py         # list_df(), messages.list_df()
      __init__.py
    outlook/
      mail.py          # users.mail.*
      events.py        # users.events.*
      contacts.py      # users.contacts.*
    intune/
      devices.py
      apps.py
    planner/
      plans.py
      buckets.py
      tasks.py
    analytics/
      reports.py
    security/
      alerts.py
      incidents.py
```

> **Hinweis:** Mehrstufige Ressourcen (z. B. `groups.members`) können entweder als **Untermodul** (`groups/members.py`) oder als **Unterklasse** innerhalb `groups.py` realisiert werden. Entscheidend ist, dass die **öffentlichen Funktionsnamen** dem Schema entsprechen.

---

## 3) Funktionssignaturen – Standardparameter

* **SharePoint**

  * `site_url: str`, `list_title: str`, `drive_id: str`, `item_id: str|int`
  * OData: `select`, `expand`, `filter`, `orderby`, `top`, `search`
  * Komfort: `columns` (intern. Namen oder `"*"`), `tz_policy='utc+2'`
* **AAD**

  * `user_id|user_upn`, `group_id`
  * OData wie oben, wo sinnvoll (`$filter`, `$select`, `$top`)
* **Teams**

  * `team_id`, `channel_id`, `chat_id`
* **Outlook**

  * `user_id|user_upn`, optionale Container (`folder_id`, `calendar_id`)

**Rückgaben**

* `_df` → `(pd.DataFrame, info: dict)` mit Diagnosedaten (z. B. URL, Versuche, Paging, Spalten-Mapping, Warnungen)
* `_json` → `(dict|list, info: dict)`
* `_iter` → `Iterator[dict]` + separat `info` (nach Laufzeit optional)

---

## 4) Implementierungsregeln

### 4.1 HTTP/Graph-Client

* Verwende **`graphfw.core.http.GraphClient`** (Retry: 429/5xx, `Retry-After`, Exponential Backoff, Paging via `@odata.nextLink`).
* Setze `ConsistencyLevel: eventual`, wenn `$search`/`$count` benutzt werden.

### 4.2 OData & Parameter

* Nutze **`graphfw.core.odata.OData`** und/oder erlaube einfache Parametereingabe (`select=[...]`, `filter=...`).
* Normalisiere Keys (`select` → `$select`) in `GraphClient` – bereits unterstützt.

### 4.3 DataFrames

* **Deterministische Spaltenreihenfolge**:
  Explizite `columns` exakt übernehmen; bei `*` → `['id','guid'] + rest` (SharePoint) bzw. domänenspezifische Kopf-/Schlusslisten.
* **GUID-Stripping**: geschweifte Klammern `{}` entfernen (SharePoint `GUID`).
* **TZ-Policy**: DateTime-Felder gem. `tz_policy` normalisieren (Default `utc+2`), standardmäßig **naiv** (ohne Offset) zurückgeben.
* **Unbekannte Felder**: bei `*` per Default **mitnehmen** (Diagnosefreundlich), optional `unknown_fields='drop'` erlauben.

### 4.4 Fehler & Logging

* Wirf **aussagekräftige Exceptions** (inkl. Status/Response-Text).
* Unterstütze optional **`log: LogBuffer`** – sofortiger `print` + Puffer (`to_df()`).
* `info`-Objekt befüllen: `{"url":..., "attempt":..., "retries":..., "warnings":[...], ...}`.

### 4.5 Typisierung & Docs

* **Type Hints** konsequent (`-> tuple[pd.DataFrame, dict]`).
* **Docstrings** mit Parametertabelle, Rückgabe, Beispiele (mind. ein Minimalbeispiel).

---

## 5) Funktionsnamen – Referenz pro Domäne

### 5.1 SharePoint

* **Sites**

  * `sharepoint.sites.list_df(site_collection_url=None, ...)`
  * `sharepoint.sites.get_by_id_json(site_id)`
* **Lists**

  * `sharepoint.lists.list_df(site_url, ...)`
  * `sharepoint.lists.columns.list_df(site_url, list_title)`
    *(Schema/Spalten; Inspector)*
* **List Items**

  * `sharepoint.lists.items.list_df(site_url, list_title, columns="*", filter=None, orderby=None, expand=None, tz_policy='utc+2', ...)`
  * `sharepoint.lists.items.get_by_id_df(site_url, list_title, item_id)`
  * `sharepoint.lists.items.iter(site_url, list_title, ...)`
* **Drives / Files**

  * `sharepoint.drives.list_df(site_url)`
  * `sharepoint.drives.items.list_df(drive_id, path=None, ...)`
  * `sharepoint.files.get_json(item_id|path, drive_id=None)` / `download(...)` / `upload(...)`

### 5.2 AAD / Entra

* **Users**: `aad.users.list_df(...)`, `aad.users.get_by_id_df(user_id)`, `aad.users.get_by_upn_df(user_upn)`
* **Groups**: `aad.groups.list_df(...)`, `aad.groups.members.list_df(group_id)`, `aad.groups.owners.list_df(group_id)`
* **Apps/SPs**: `aad.applications.list_df(...)`, `aad.service_principals.list_df(...)`
* **Audit**: `aad.audit.signins.list_df(...)`, `aad.audit.directory.list_df(...)`

### 5.3 Teams

* **Teams**: `teams.teams.list_df(...)`, `teams.teams.get_by_id_df(team_id)`
* **Channels**: `teams.teams.channels.list_df(team_id)`
* **Members**: `teams.teams.members.list_df(team_id)`
* **Chats/Messages**: `teams.chats.list_df(...)`, `teams.chats.messages.list_df(chat_id, ...)`, `teams.teams.channels.messages.list_df(team_id, channel_id, ...)`

### 5.4 Outlook/Exchange

* **Mail**: `outlook.users.mail.list_df(user_id|user_upn, folder_id=None, filter=None, ...)`
* **Events**: `outlook.users.events.list_df(user_id|user_upn, calendar_id=None, date_range=None, ...)`
* **Contacts**: `outlook.users.contacts.list_df(user_id|user_upn, ...)`

### 5.5 Intune

* `intune.devices.list_df(...)`, `intune.apps.list_df(...)`, `intune.policies.configuration.list_df(...)`, `intune.compliance.list_df(...)`

### 5.6 Planner

* `planner.plans.list_df(owner_id=None, group_id=None, ...)`
* `planner.buckets.list_df(plan_id)`
* `planner.tasks.list_df(plan_id=None, bucket_id=None, assigned_to=None, ...)`

### 5.7 Analytics/Reports

* `analytics.o365.active_users.list_df(period='D7'|...)`
* `analytics.teams.user_activity.list_df(period='D7'|...)`
* `analytics.sharepoint.activity.list_df(period='D7'|...)`

### 5.8 Security

* `security.alerts.list_df(filter=None, ...)`
* `security.incidents.list_df(filter=None, ...)`

---

## 6) Docstring-Vorlage (copy‑paste)

```python
def sharepoint_lists_items_list_df(gc: GraphClient, *, site_url: str, list_title: str, columns="*", filter=None, orderby=None, expand=None, tz_policy="utc+2", top=None, log: LogBuffer|None = None) -> tuple[pd.DataFrame, dict]:
    """SharePoint: List Items → DataFrame.

    Parameters
    ----------
    gc : GraphClient
        Authentifizierter Graph-Client (siehe graphfw.core.http).
    site_url : str
        "https://tenant.sharepoint.com/sites/TeamA".
    list_title : str
        Anzeigename der Liste.
    columns : list[str] | "*"
        Interne Feldnamen oder "*" für alle Felder. Bei "*" werden Meta‑Felder
        (CreatedByName/ModifiedByName) automatisch ergänzt.
    filter, orderby, expand : str | list[str] | None
        OData‑Parameter.
    tz_policy : str
        Zeitzonen‑Policy (z. B. 'utc', 'utc+2', 'local').
    top : int | None
        Optionales clientseitiges Limit.
    log : LogBuffer | None
        Optionaler Logpuffer.

    Returns
    -------
    (df, info) : tuple[pandas.DataFrame, dict]
        DataFrame mit deterministischer Spaltenordnung + Diagnose‑Info.
    """
```

---

## 7) Minimalbeispiel – Aufrufkonvention

```python
from graphfw.core.auth import TokenProvider
from graphfw.core.http import GraphClient
from graphfw.domains.sharepoint.lists.items import list_df as sp_lists_items_list_df

# Auth & Client
tp = TokenProvider.from_json("config.json")
gc = GraphClient(tp)

# Call
df, info = sp_lists_items_list_df(
    gc,
    site_url="https://contoso.sharepoint.com/sites/TeamA",
    list_title="My Custom List",
    columns="*",
    orderby="fields/Modified desc",
)

print(info)
print(df.head())
```

---

## 8) Deprecation & Versionierung

* Alte Funktionsnamen (z. B. `get_list_items_df`) als **Thin‑Wrapper** beibehalten:

  * Ausgabe einer **`DeprecationWarning`** mit Verweis auf neuen Namen.
  * Geplantes Entferndatum im Code dokumentieren.
* Versionierung je Domain‑Modul (SemVer‑ähnlich), Breaking Changes im Changelog.

---

## 9) Tests & Qualität

* **Unit‑Tests** pro Modul (Responses mocken; keine Live‑Tokens).
* **Typing** via `mypy` toleriert; `ruff/flake8` Stilprüfung empfohlen.
* **Notebook‑Demos** in `notebooks/framework/` referenzieren die echten Modul‑Funktionen.

---

## 10) Checkliste bei neuen Funktionen

* [ ] Name folgt Schema `domain.resource.subresource.action_format`
* [ ] Signatur konsistent (Standardparameter + **`log: LogBuffer|None`**)
* [ ] HTTP über `GraphClient` (Retry/ConsistencyLevel/Paging)
* [ ] OData über `OData` oder saubere `params`
* [ ] DataFrame: deterministische Spalten, GUID‑Strip, TZ‑Policy
* [ ] `info` mit URL, Versuchsanzahl, Paging‑Infos, Warnungen
* [ ] Docstring (Parametertabelle, Rückgabe, Beispiel)
* [ ] Unit‑Test & Beispiel in Notebook

---

Mit diesen Regeln bleibt das Framework **einheitlich** und **erweiterbar** – neue Domänen oder Endpunkte fügen sich sauber in die bestehende Struktur ein und sind für Nutzer sofort erkennbar und wiederverwendbar.
