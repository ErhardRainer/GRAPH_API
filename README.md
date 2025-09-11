# Microsoft Graph API – Übersicht, Beispiele & Framework

Die **Microsoft Graph API** ist die zentrale Schnittstelle zu fast allen Microsoft‑365‑Diensten (Entra ID/Azure AD, SharePoint, Teams, Outlook/Exchange, Intune u.v.m.). Diese README kombiniert **theoretische Grundlagen**, **Notebook‑Beispiele** und ein **modulares Python‑Framework** zur Wiederverwendung.

---
## Konfigurationsdatei
Alle Skripte (nicht die fertigen Lösungen) erfordern eine config.json, um die Passwörter udgl. zu speichern. ➡️ [Notebook: Umgang mit der config.json](https://github.com/ErhardRainer/GRAPH_API/blob/main/00_General/config_json.ipynb).
Das ist aber nicht die beste Lösung für den produktiven Einsatz.

## 🧩 Application (App‑Registrierung)
Für API‑Aufrufe werden benötigt: **TenantID**, **ApplicationID (ClientID)** und **ClientSecret** (oder Zertifikat). Außerdem passende **Graph‑Berechtigungen** (Delegated oder Application) mit Admin‑Consent.
➡️ **Notebook:** [`test_Application.ipynb`](test_Application.ipynb)

## 📚 Hauptbereiche der Graph API

### 🔹 01 - Azure Active Directory (Entra ID)
- Benutzer (Profile, Gruppen, Fotos, Lizenzen)
- Gruppen (Mitglieder, Besitzer, dynamische Regeln)
- Rollen und App-Registrierungen
- Anmeldungen & Directory-Audit-Logs

➡️ [Notebook: Azure AD auslesen](azure_ad.Read.ipynb)

➡️ [Notebook: Azure AD User bearbeiten](azure_ad.User.ipynb)

➡️ [Notebook: Azure AD Gruppen bearbeiten](azure_ad.Group.ipynb)

➡️ [Notebook: Azure AD Rollen bearbeiten](azure_ad.Rolls.ipynb)

fertige Lösungen
- [MonitoringAD](https://github.com/ErhardRainer/MONITORING_AzureActiveDirectory) **planning** - eine gesamt Lösung, die ein AD-Monitoring Dashboard als Ergebnis hat
---

### 🔹 02 - SharePoint & OneDrive (in diesem Abschnitt wird alternativ auch die Verwendung der Sharepoint REST API erklärt)

➡️[Übersicht der APIs von SharePoint](sharepoint_APIs.ipynb)

- Sites & Metadaten ➡️[Notebook: SharePoint_Sites Beispiele](sharepoint_Sites.ipynb)
     - SharePoint-Site: Listen, Dokumentenbiblotheken einer SharePoint Seite auslesen [ListSharepointObjects.py](SharePoint\ListSharepointObjects.py)
- Listen (inkl. Paging) ➡️[Notebook: SharePoint_Lists_ Beispiele](sharepoint_Lists.ipynb)
     - SharePoint-Liste auslesen und in pandas Dataframe schreiben mittels GraphAPI [SharePointList2DF.py](https://github.com/ErhardRainer/GRAPH_API/blob/main/02_Sharepoint/SharePointList2DF.py.md)
     - SharePoint-Liste: alle möglichen Spalten der Graph-API auslesen [SharePointListColumns.py](https://github.com/ErhardRainer/GRAPH_API/blob/main/Sharepoint/SharePointListColumns.py.md)
     - 
- Libraries (inkl. Paging) ➡️[Notebook: SharePoint_Libraries Beispiele](sharepoint_Libraries.ipynb)
- Dokumente & Dateien (Upload/Download) ➡️[Notebook: SharePoint_Upload/Download Beispiele](sharepoint_UpdloadDownload.ipynb)
- Berechtigungen auf Site- und Item-Ebene ➡️[Notebook: SharePoint_Permissions Beispiele](sharepoint_Permissions.ipynb)

**fertige Lösungen**
- [SharePoint2SQL](solutions/Sharepoint2SQLUserPW.ipynb) *fertig (alte Lösung)* - ein umfangreiches python Script, das es ermöglicht über eine SQL-Tabelle zu konfigurieren, welche SharePoint Listen auf den SQL-Server gesynct werden sollen. (unidirektional) Wurde durch das nachfolgende Skript abgelöst.
- [SharePoint Graph-API sync to SQL](solutions/Sharepoint2SQL.ipynb) *fertig (neue Lösung)* - ein umfangreiches python Script, das es ermöglicht über eine SQL-Tabelle zu konfigurieren, welche SharePoint Listen auf den SQL-Server gesynct werden sollen. (unidirektional)
- [SharePoint SQL bidirectional sync](solutions/Sharepoint2SQL_bidirectional.ipynb) *planning* - ein umfangreiches python Script, das bidirectional eine SharePoint Liste und SQL-Tabele syncronisiert.
- [FileShare2Libarary](solutions/Sharepoint2Library.ipynb) *planning* - ein umfangreiches pyhton Script, das eine SharePoint Biblitothek und ein Netzlaufwerk syncron hält.

---

### 🔹 03 - Exchange / Outlook
- E-Mails lesen/senden
- Kalender & Termine
- Kontakte

➡️ [Notebook: Outlook Beispiele](outlook.ipynb)

---

### 🔹 04 - Microsoft Teams
- Teams & Channels
- Mitglieder
- Chats & Nachrichten

➡️ [Notebook: Teams Beispiele](teams.ipynb)

---

### 🔹 05 - Intune / Endpoint Management
- Geräteinformationen (Compliance, Konfiguration)
- Apps & Policies

➡️ [Notebook: Intune Beispiele](intune.ipynb)

---

### 🔹 06 - Reports & Analytics
- Office 365 Nutzungsstatistiken (Teams, SharePoint, Exchange)
- Teams User Activity

➡️ [Notebook: Reports Beispiele](reports.ipynb)

---

### 🔹 07 - Planner & To Do
- Planner: Pläne & Tasks
- Microsoft To Do: Aufgabenlisten

➡️ [Notebook: Planner/ToDo Beispiele](planner_todo.ipynb)

---

### 🔹 08 - Security & Compliance
- Defender Alerts
- Security Incidents

➡️ [Notebook: Security Beispiele](security.ipynb)

---

## 🗂 Übersichtstabelle – Dienste & Endpunkte (v1.0)

| Dienst / Bereich         | Typische Endpunkte (v1.0)                                   | Beispiele für Abrufbare Daten |
|--------------------------|-------------------------------------------------------------|--------------------------------|
| **Azure AD / Entra ID** | `/users`, `/groups`, `/directoryRoles`                      | Benutzer, Gruppen, Rollen |
|                          | `/applications`, `/servicePrincipals`                      | App-Registrierungen, Service Principals |
|                          | `/auditLogs/signIns`, `/auditLogs/directoryAudits`         | Sign-Ins, Audit-Logs |
| **SharePoint / OneDrive** | `/sites/{id}`, `/sites/{id}/lists`, `/drives/{id}`        | Sites, Listen, Dokumente |
| **Outlook / Exchange**   | `/me/messages`, `/me/events`, `/me/contacts`               | E-Mails, Kalender, Kontakte |
| **Microsoft Teams**      | `/teams`, `/teams/{id}/channels`, `/chats`                 | Teams, Channels, Chats |
| **Intune / Endpoint**    | `/deviceManagement/managedDevices`                         | Geräteinformationen |
| **Reports & Analytics**  | `/reports/getOffice365ActiveUserDetail`                    | O365 Nutzungsstatistiken |
| **Planner / To Do**      | `/planner/plans`, `/me/todo/lists`                         | Pläne & Aufgaben |
| **Security / Compliance**| `/security/alerts`, `/security/incidents`                  | Security Alerts & Incidents |

---

> Berechtigungen: Delegated vs. Application; typische Scopes u. a. `User.Read.All`, `Sites.Read.All`, `Mail.Read`, `Calendars.Read` (Admin‑Consent bei Application erforderlich).

---

## 🧱 Graph Framework (Python)

Ein modulares Framework, das Auth, HTTP, Retry, OData, Parameter & Output bündelt. Ziel: **einheitliche Clients** für AAD, SharePoint, Exchange, Teams, Intune, Planner, Analytics – mit wiederverwendbaren Pipelines.

### 🎯 Ziele

* **Einheitlicher Kern** (MSAL‑Auth, HTTP‑Client mit Retry/Throttling/Paging, OData‑Builder)
* **Domänen‑Clients**: AAD, SharePoint, Exchange, Teams, Intune, Planner, Analytics
* **Parameter‑Resolver**: CLI/JSON/Config (später SP‑Liste) – schema‑getrieben
* **Outputs**: Writer‑Adapter (CSV, später Parquet/Excel/SQL)
* **Diagnose**: konsistente `info`‑Objekte & Log‑Puffer (als DataFrame exportierbar)
* [**Benennung der Funktionen**:](https://github.com/ErhardRainer/GRAPH_API/blob/main/graphfw/domains/README.md)

### 🧩 Architektur

```
graphfw/
  core/
    auth.py       # MSAL, TokenCache (in-memory/optional persistent)
    http.py       # GraphClient (Retry 429/5xx, Retry-After, Paging)
    odata.py      # $select/$expand/$filter/$orderby/$search Builder
    util.py       # TZ-Policy, GUID-Strip, UTF‑8, SP-Name-Encoding, Masking
    logbuffer.py  # print + Buffer → .to_df()
  domains/
     sharepoint/lists/items.py
     uva.
  params/
    schema.py, resolve.py
  io/writers/
    csv_writer.py       # write_csv(), build_csv_path()
    # parquet_writer.py, excel_writer.py, sql_writer.py (optional)
```

### ⬇️ Download & Installation

Du kannst Framework & Notebooks **im selben Repo** führen. Zwei Wege zur Einbindung:

**A) Lokal als Paket installieren (empfohlen)**

```bash
# Im Repo‑Root (enthält graphfw/)
python -m pip install -U pip
pip install -e .
# oder (falls kein pyproject vorhanden):
pip install -e ./graphfw
```

Alternative Installationsmethoden: [Installation](https://github.com/ErhardRainer/GRAPH_API/blob/main/graphfw/install.md)

**B) Direkter Import im Notebook/Script (ohne Installation)**

```python
import sys
sys.path.append("./graphfw")  # relativer Pfad zum Modulordner
from core.http import GraphClient
```

**Basis‑Abhängigkeiten** (je nach Use‑Case):
Installation der Requriements: [Requirements](https://github.com/ErhardRainer/GRAPH_API/blob/main/graphfw/requirements.md)
```bash
pip install msal requests pandas
# optional Writer/SQL
pip install sqlalchemy pyodbc openpyxl pyarrow
```

### ⚡ QuickStart (SharePoint Items → CSV)

```python
from pathlib import Path
from graphfw.core.auth import TokenProvider   # liest azuread aus config.json
from graphfw.core.http import GraphClient
from graphfw.domains.sp.client import SharePointClient
from graphfw.io.writers.csv_writer import write_csv

# 1) Auth
tp = TokenProvider.from_json("config.json")
client = GraphClient(token_provider=tp)

# 2) Domain-Client
sp = SharePointClient(client)

# 3) Daten laden
df, info = sp.get_list_items_df(
    site_url="https://contoso.sharepoint.com/sites/TeamA",
    list_title="My Custom List",
    columns="*",            # oder z. B. ["ID","Title","GUID","createdBy","lastModifiedBy"]
    filter=None,
    top=None
)

# 4) Schreiben
out = write_csv(df, site_url="https://contoso.sharepoint.com/sites/TeamA",
                list_title="My Custom List", out_dir=Path("out"))
print(out)
```

> **Namenskonvention (CSV):** `Site_ListName_YYYYMMDD_hhmmss.csv` (UTF‑8‑SIG; Excel‑freundlich).

### 📓 Framework-Notebooks (Erklärungen & Demos)

* **Überblick & Richtlinien**  
  [`notebooks/framework/000_framework_overview.ipynb`](notebooks/framework/000_framework_overview.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/000_framework_overview.ipynb)
  * **Auth & HTTP (MSAL, Retry, Paging, OData)**  
    [`notebooks/framework/001_auth_and_http.ipynb`](notebooks/framework/001_auth_and_http.ipynb) ·
    [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/001_auth_and_http.ipynb)
  * **Parameter-Resolver (CLI/JSON/Config/SP-Liste)**  
    [`notebooks/framework/002_params_resolver.ipynb`](notebooks/framework/002_params_resolver.ipynb) ·
    [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/002_params_resolver.ipynb)
  * **Writers (CSV/Parquet/SQL) & Namenskonventionen**  
    [`notebooks/framework/003_writers_csv_sql.ipynb`](notebooks/framework/003_writers_csv_sql.ipynb) ·
    [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/003_writers_csv_sql.ipynb)

* **SharePoint: Sites, Lists, Libraries …**  
  [`notebooks/framework/100_sharepoint.ipynb`](notebooks/framework/100_sharepoint.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/100_sharepoint.ipynb)
  * **SharePoint: Items → DataFrame (`get_list_items_df`)**  
    [`notebooks/framework/101_sharepoint_lists_items.ipynb`](notebooks/framework/101_sharepoint_lists_items.ipynb) ·
    [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/101_sharepoint_lists_items.ipynb)
  * **SharePoint: Columns / Schema-Inspector**  
    [`notebooks/framework/102_sharepoint_list_columns.ipynb`](notebooks/framework/102_sharepoint_list_columns.ipynb) ·
    [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/102_sharepoint_list_columns.ipynb)

* **AAD / Entra: Users & Groups**  
  [`notebooks/framework/200_aad_users_groups.ipynb`](notebooks/framework/200_aad_users_groups.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/200_aad_users_groups.ipynb)

* **Teams: Channels & Messages**  
  [`notebooks/framework/300_teams_channels_messages.ipynb`](notebooks/framework/300_teams_channels_messages.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/300_teams_channels_messages.ipynb)

* **Exchange: Mail / Calendar**  
  [`notebooks/framework/400_exchange_mail_calendar.ipynb`](notebooks/framework/400_exchange_mail_calendar.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/400_exchange_mail_calendar.ipynb)

* **Intune: Devices & Compliance**  
  [`notebooks/framework/500_intune_devices.ipynb`](notebooks/framework/500_intune_devices.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/500_intune_devices.ipynb)

* **Planner: Plans & Tasks**  
  [`notebooks/framework/600_planner_tasks.ipynb`](notebooks/framework/600_planner_tasks.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/600_planner_tasks.ipynb)

* **Analytics / Reports**  
  [`notebooks/framework/700_analytics_reports.ipynb`](notebooks/framework/700_analytics_reports.ipynb) ·
  [nbviewer](https://nbviewer.org/github/ErhardRainer/GRAPH_API/blob/main/notebooks/framework/700_analytics_reports.ipynb)

> Hinweis: In den Demos werden die `graphfw`-Module **verwendet**.


---

## 🚀 Changes

Changelog: [`CHANGES.md`](CHANGES.md)

---

### Hinweise zu Berechtigungen & Sicherheit

* **Delegated** (Benutzerkontext) vs. **Application** (App‑Kontext, Org‑weit; Admin‑Consent nötig)
* Secrets niemals in Logs/Output – für Produktion: Key Vault/Managed Identity
* Throttling/Retry beachten (HTTP 429/5xx; `Retry‑After` befolgen)
