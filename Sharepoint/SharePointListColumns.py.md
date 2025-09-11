# SharePointColumns.py – Repository-Dokumentation (v2.1)

[![Download Script](https://img.shields.io/badge/Download-SharePointColumns.py-yellow?logo=python\&logoColor=white)](https://github.com/ErhardRainer/GRAPH_API/blob/main/Sharepoint/SharePointListColumns.py)

> **Kurzfassung / TL;DR**
> Dieses Skript liest **Spaltendefinitionen von SharePoint-Listen** (interner Name, Anzeigename, Facet/Typ, Flags) über **Microsoft Graph** aus und liefert ein **pandas DataFrame**. Optional erfolgt ein **CSV‑Export**.
> Es gibt **drei Betriebsmodi**: `config` (Script-Config-Block), `params` (reine CLI), `json` (Parameter-JSON für Einzel- oder Batchläufe).
> **CSV-Dateiname** wird automatisch als `Site_ListName_YYYYMMDD_hhmmss.csv` erzeugt.

---

## Problemstellung

In vielen Datenprojekten braucht man das **exakte Schema** einer SharePoint-Liste: *interne Spaltennamen, Datentypen (Facets) und Flags* wie `required`, `readOnly`, `hidden`. Diese Informationen werden für Mapping, ETL/ELT, QA oder Schema-Drift-Erkennung benötigt.
Manuell in der UI nachzusehen ist fehleranfällig und skaliert nicht. Das Skript **SharePointColumns.py** automatisiert diesen Schritt über **Microsoft Graph** – optional mit **CSV-Export** – und lässt sich **per CLI**, **über einen Config-Block** oder **via Parameter-JSON** betreiben.

---

## Grundprinzip

**Textuell**

1. **Credentials** (`tenant_id`, `client_id`, `client_secret`) aus `config.json` lesen.
2. **App-Token** für Microsoft Graph holen (Client-Credentials-Flow, MSAL).
3. **List Columns** via Graph-Endpoint abrufen:
   `GET https://graph.microsoft.com/v1.0/sites/{hostname}:/{site_path}:/lists/{list_title}/columns?$top=200`
   (inkl. Paging über `@odata.nextLink`).
4. Pro Spalte **Facet** erkennen (z. B. `choice`, `lookup`, `dateTime` …), relevante **Details** extrahieren (z. B. Choices) und in ein **pandas DataFrame** schreiben.
5. **Ausgabe** auf Konsole und/oder **CSV-Export**.

**Kurz-Code**

```python
tenant_id, client_id, client_secret = load_credentials(CONFIG_PATH)
df = fetch_sharepoint_list_columns_df(
    tenant_id, client_id, client_secret,
    SITE_URL, LIST_TITLE, timeout=60
)
# optional
out_path = export_csv_auto(df, SITE_URL, LIST_TITLE, Path(CSV_DIR), timestamp=True)
```

---

## Betriebsmodi

Das Skript unterstützt drei Modi. Die Auswahl erfolgt über `--mode` (CLI) oder den `CONFIG`‑Block (Default `config`).

### 1) MODE = `config`

* Parameter kommen aus dem **CONFIG‑Block** ganz oben im Skript (z. B. `SITE_URL`, `LIST_TITLE`, `CreateCSV`, `CSVDir`, `Display`).
* CLI‑Parameter können einzelne Werte **übersteuern** (z. B. nur `--list` tauschen).

### 2) MODE = `params`

* **Reiner CLI‑Modus**: `--site` und `--list` sind **erforderlich** (Credentials weiterhin aus `--config`).
* Ausgabe/Export steuerbar über `--createcsv`, `--csvdir`/`--csvfile`, `--display`.

### 3) MODE = `json`

* **Parameter-JSON** steuert einen oder mehrere **Jobs**.
* Ideal für **Batchläufe** über mehrere Listen und/oder Sites.
* CSV‑Zielpfad je Job oder global über `defaults`.

---

## Parameter-JSON: Aufbau & Beispiel

**Datei**: frei wählbar (z. B. `sp_jobs.json`), an das Skript via `--paramjson` übergeben.
**Wichtig**: Die **Credentials bleiben in der separaten** `config.json` (Azure AD App). Das Parameter-JSON enthält **keine Secrets**.

### Struktur

```json
{
  "defaults": {
    "CreateCSV": true,
    "Display": false,
    "CSVDir": "C:/temp/exports",
    "SITE_URL": "https://contoso.sharepoint.com/sites/TeamA"
  },
  "jobs": [
    {
      "LIST_TITLE": "My Custom List"
    },
    {
      "SITE_URL": "https://contoso.sharepoint.com/sites/HR",
      "LIST_TITLE": "Employees",
      "CreateCSV": true,
      "Display": true,
      "CSVDir": "C:/temp/hr"
    },
    {
      "SITE_URL": "https://contoso.sharepoint.com/sites/Finance",
      "LIST_TITLE": "Invoices",
      "CreateCSV": true,
      "CSVFile": "C:/temp/finance/invoices.csv",
      "Display": false
    }
  ]
}
```

### Feldbedeutung

* `defaults` (optional): Voreinstellungen für `jobs` (werden dort überschrieben, wenn gesetzt):

  * `SITE_URL`: Standard‑Site
  * `CreateCSV`: `true|false`
  * `Display`: `true|false`
  * `CSVDir`: Standard‑Ordner für CSVs
* `jobs` (Liste): Einträge für einzelne Läufe:

  * `SITE_URL` *(optional)* – fällt auf `defaults.SITE_URL` zurück
  * `LIST_TITLE` *(erforderlich)* – Anzeigename der SharePoint‑Liste
  * `CreateCSV`, `Display` *(optional)* – überschreiben `defaults`
  * `CSVDir` *(optional)* – Zielordner
  * `CSVFile` *(optional, Legacy‑Kompatibilität)*:

    * Zeigt `CSVFile` auf **Ordner** oder **ohne** `.csv`‑Endung → als **Ordner** interpretiert.
    * Zeigt `CSVFile` auf **Datei** → der **Ordner** wird verwendet, **Dateiname wird ignoriert**, da das Skript **immer** den Standardnamen erzeugt.

---

## CSV-Export & Dateinamensschema

* Der CSV‑Export wird über `CreateCSV` **aktiviert** (CLI/Config/JSON).
* Das Ziel wird als **Ordner** angegeben (`CSVDir`). `CSVFile` wird als Fallback akzeptiert (siehe Regeln oben).
* **Dateiname wird immer automatisch erzeugt**:
  **`Site_ListName_YYYYMMDD_hhmmss.csv`**

**Erzeugung der Tokens:**

* `Site` = Kombination aus **Hostname** und **letzter Site‑Pfadkomponente**.
  Beispiel: `https://contoso.sharepoint.com/sites/TeamA` → `contoso_sharepoint_com_TeamA`
* `ListName` = bereinigter Anzeigename der Liste (Leerzeichen → `_`, nur `[A-Za-z0-9-_]`).

**Beispiele:**

* Site: `https://contoso.sharepoint.com/sites/TeamA`, List: `My Custom List` →
  `contoso_sharepoint_com_TeamA_My_Custom_List_20250911_103522.csv`
* Site: `https://tenant.sharepoint.com/sites/HR`, List: `Employees` →
  `tenant_sharepoint_com_HR_Employees_20250911_103522.csv`

---

## Beschreibung der Lösung im Detail

### Kernfunktionen

* `load_credentials(config_path) -> (tenant_id, client_id, client_secret)`
  Liest `config.json` und liefert Azure AD App‑Credentials zurück. Validiert Struktur, wirft klare Fehler bei fehlenden Keys.

* `fetch_sharepoint_list_columns_df(tenant_id, client_id, client_secret, site_url, list_title, timeout=60) -> pd.DataFrame`
  Holt alle Spaltendefinitionen der angegebenen Liste.
  **Innere Helfer:**

  * `detect_column_type(col)` – erkennt Spaltentyp anhand der Graph‑Facets (inkl. `multiChoice`).
  * `summarize_facet_details(col_type, col)` – extrahiert Zusatzinfos (Choices, Lookup‑Ziel, Anzeigeformate …).
    **DataFrame‑Spalten:** `internalName`, `displayName`, `type`, `required`, `readOnly`, `hidden`, `indexed`, `enforceUnique`, `details`

* `export_csv_auto(df, site_url, list_title, out_dir, timestamp=True) -> Path`
  Export mit **automatischem Dateinamen** gemäß Schema `Site_ListName_YYYYMMDD_hhmmss.csv` (UTF‑8‑SIG, Ordner wird angelegt).

### CLI & Main-Logik (Auszug)

* `--mode {config|params|json}` – Betriebsmodus
* `--config` – Pfad zur **Credentials‑JSON**
* `--site`, `--list` – nur für `params`/`config` relevant
* `--createcsv 0|1`, `--csvdir PFAD`, `--csvfile PFAD`, `--display 0|1`
* `--paramjson PFAD` – Parameter‑JSON für `json`‑Modus

### Authentifizierung & Berechtigungen

* **MSAL Confidential Client** (Client‑Credentials‑Flow).
* Scope: `https://graph.microsoft.com/.default`
* App‑Genehmigungen (Application): mind. **Sites.Read.All** (je nach Tenant ggf. mehr).

**`config.json` Beispiel:**

```json
{
  "azuread": {
    "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_secret": "YOUR_SECRET"
  }
}
```

### API & Paging

* Endpoint:
  `GET /v1.0/sites/{hostname}:/{site_path_graph}:/lists/{list_title}/columns?$top=200`
* Bei vielen Spalten folgt das Skript **@odata.nextLink** automatisch (Paging).

### Konsolenausgabe & Export

* Log‑Meldungen: `[info]`, `[ok]`, `[warn]`, `[error]` (Englisch).
* CSV‑Encoding: `utf-8-sig` (Excel‑freundlich).
* Anzeige steuerbar über `Display` (Default: `true`).

### Fehlerbehandlung & Validierung

* Aussagekräftige Fehlermeldungen bei fehlender Config, ungültiger JSON‑Struktur oder Token‑Fehler.
* HTTP‑Fehler führen zu Exceptions inkl. Server‑Response.

### Grenzen / Hinweise

* Es werden **Spaltendefinitionen** (Schema) gelesen, **keine Listendaten**.
* `LIST_TITLE` ist der **Anzeigename**; bei häufigen Namenswechseln ggf. alternative Abfrage (z. B. über `listId`).
* Für spezielle Feldtypen (z. B. Taxonomie) liefert `details` komprimierte Metadaten; bei Bedarf Roh‑JSON erweitern.

---

## Beispiele / Aufrufe

### 1) MODE `config` – ohne CLI (reine Defaults)

```bash
python SharePointColumns.py
```

### 2) MODE `config` – einzelnen Wert via CLI überschreiben

```bash
python SharePointColumns.py --list "Vendor Master"
```

### 3) MODE `params` – reine CLI, inkl. CSV in Ordner `C:\temp`

```bash
python SharePointColumns.py \
  --mode params \
  --config "C:\\python\\Scripts\\config.json" \
  --site "https://contoso.sharepoint.com/sites/TeamA" \
  --list "My Custom List" \
  --createcsv 1 --csvdir "C:\\temp" --display 1
```

### 4) MODE `json` – Batch über Parameter‑JSON

```bash
python SharePointColumns.py \
  --mode json \
  --config "C:\\python\\Scripts\\config.json" \
  --paramjson "C:\\python\\Scripts\\sp_jobs.json"
```

---

## Version History

* **v2.1 (2025‑09‑11)**: Neuer **JSON‑Modus** (Batch), **CSV‑Dateinamen** strikt `Site_ListName_YYYYMMDD_hhmmss.csv`; `CSVDir` bevorzugt (Legacy‑`CSVFile` kompatibel).
* **v2.0 (2025‑09‑11)**: Zwei Modi (`config`/`params`); `CreateCSV`/`CSVFile`/`Display` via Config & CLI.
* **v1.3 (2025‑09‑08)**: `PassParameter`‑Switch; robustere Defaults/Validierung.
* **v1.2 (2025‑09‑08)**: CLI‑Args, CSV‑Export, englische Ausgaben, Header.
* **v1.1 (2025‑09‑08)**: Helper in Hauptfunktion integriert.
* **v1.0 (2025‑09‑08)**: Erstversion – Graph‑basierter Schema‑Fetch.
