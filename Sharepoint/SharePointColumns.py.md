# SharePointColumns.py – Repository-Dokumentation

[![Download Script](https://img.shields.io/badge/Download-SharePointColumns.py-yellow?logo=python&logoColor=white)](https://github.com/ErhardRainer/GRAPH_API/blob/main/Sharepoint/SharePointColumns.py)


## Problemstellung

In vielen Datenprojekten braucht man das **exakte Schema** einer SharePoint-Liste: _interne Spaltennamen, Datentypen (Facets) und Flags_ wie `required`, `readOnly`, `hidden`. Diese Informationen werden für Mapping, ETL/ELT, QA oder Schema-Drift-Erkennung benötigt.  
Manuell in der UI nachzusehen ist fehleranfällig und skaliert nicht. Das Skript **SharePointColumns.py** automatisiert diesen Schritt über **Microsoft Graph** – optional mit **CSV-Export** – und lässt sich sowohl **per CLI** als auch mit im Skript **hinterlegten Defaults** betreiben.

----------

## Grundprinzip

**Textuell**

1.  **Credentials** (`tenant_id`, `client_id`, `client_secret`) aus `config.json` lesen.
    
2.  **App-Token** für Microsoft Graph holen (Client-Credentials-Flow).
    
3.  **List Columns** via Graph-Endpoint abrufen:  
    `GET https://graph.microsoft.com/v1.0/sites/{hostname}:/{site_path}:/lists/{list_title}/columns?$top=200`  
    (inkl. Paging über `@odata.nextLink`).
    
4.  Pro Spalte **Facet** erkennen (z. B. `choice`, `lookup`, `dateTime` …), **Details** extrahieren (z. B. Choices) und in ein **pandas DataFrame** schreiben.
    
5.  **Ausgabe** auf Konsole oder optional **CSV-Export** mit Zeitstempel.
    
6.  **PassParameter** steuert, ob CLI-Parameter **verpflichtend** sind (`1`) oder **Defaults** verwendet werden dürfen (`0`, Standard).
    

**Kurz-Code**

```
tenant_id, client_id, client_secret = load_credentials(CONFIG_PATH)
df = fetch_sharepoint_list_columns_df(
    tenant_id, client_id, client_secret,
    SITE_URL, LIST_TITLE, timeout=60 ) # optional  if EXPORT_CSV:
    export_csv(df, EXPORT_CSV, timestamp=True)
``` 

----------

## Beschreibung der Lösung im Detail

### Kernfunktionen

-   `load_credentials(config_path) -> (tenant_id, client_id, client_secret)`  
    Liest `config.json` und liefert Azure AD App-Credentials zurück. Validiert Struktur, wirft klare Fehler bei fehlenden Keys.
    
-   `fetch_sharepoint_list_columns_df(tenant_id, client_id, client_secret, site_url, list_title, timeout=60) -> pd.DataFrame`  
    Holt alle Spaltendefinitionen der angegebenen Liste.  
    Enthaltene **Unterfunktionen** (nur innerhalb der Funktion sichtbar):
    
    -   `detect_column_type(col)` – erkennt den Spaltentyp anhand der Graph-Facets (inkl. `multiChoice`-Erkennung).
        
    -   `summarize_facet_details(col_type, col)` – extrahiert nützliche Zusatzinfos (z. B. Choice-Liste, Lookup-Ziel, Datumsformat).
        
    
    **DataFrame-Spalten:**
    
    -   `internalName`, `displayName`, `type`, `required`, `readOnly`, `hidden`, `indexed`, `enforceUnique`, `details`
        
-   `export_csv(df, export_path, timestamp=True) -> Path`  
    Exportiert das DataFrame als UTF-8-CSV, legt Verzeichnisse bei Bedarf an, ergänzt optional einen Zeitstempel im Dateinamen.
    

### CLI & Main-Logik

-   `parse_args(argv)` – akzeptiert:
    
    -   `--passparam` (`0`/`1`): steuert, ob Parameter verpflichtend sind.
        
    -   `--config`, `--site`, `--list`, `--export`
        
-   `main(argv=None)` – **Flexible Steuerung**:
    
    -   **Defaults** sind im Skript hinterlegt (`CONFIG_PATH`, `SITE_URL`, `LIST_TITLE`, `EXPORT_CSV=None`).
        
    -   **PassParameter = 0 (Default):** CLI-Args sind optional; fehlende Werte werden durch Defaults ersetzt.
        
    -   **PassParameter = 1:** `--config`, `--site`, `--list` **müssen** übergeben werden; bei Fehlen Abbruch mit Fehler.
        

### Authentifizierung & Berechtigungen

-   **MSAL Confidential Client** (Client Credentials Flow).
    
-   Scope: `https://graph.microsoft.com/.default`
    
-   App-Genehmigungen (Application): mind. **Sites.Read.All** (je nach Tenant ggf. mehr).
    
-   **config.json** Beispiel:
    
```
{  "azuread":
  {
    "tenant_id":  "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_id":  "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_secret":  "YOUR_SECRET"
  }
}
``` 
    

### API & Paging

-   Endpoint:  
    `GET /v1.0/sites/{hostname}:/{site_path_graph}:/lists/{list_title}/columns?$top=200`
    
-   Bei vielen Spalten folgt das Skript **@odata.nextLink** automatisch (Paging).
    

### Konsolenausgabe & Export

-   Alle Ausgaben sind **in Englisch** (Info/Warn/Error).
    
-   CSV-Encoding: `utf-8-sig` (Excel-freundlich).
    
-   Export-Dateiname erhält optional `_YYYYMMDD_HHMMSS`.
    

### Fehlerbehandlung & Validierung

-   Aussagekräftige Fehlermeldungen bei fehlender Config, ungültiger JSON-Struktur oder Token-Fehler.
    
-   HTTP-Fehler führen zu Exceptions inklusive Server-Response.
    

### Grenzen / Hinweise

-   Es werden **Spaltendefinitionen** (Schema) gelesen, **keine Listendaten**.
    
-   `list_title` ist der **Anzeigename** der Liste; bei Namensänderungen kann `getById` sinnvoller sein (kann auf Wunsch ergänzt werden).
    
-   Für Spezial-Feldtypen (z. B. Taxonomie) liefert `details` komprimierte Metadaten; bei Bedarf kann man die Roh-JSONs erweitern.
    

----------

## Beispielaufrufe

### 1) Ohne CLI-Parameter (nutzt im Skript hinterlegte Defaults)

```
python SharePointColumns.py
``` 

### 2) Optional einzelne Parameter überschreiben (PassParameter bleibt 0)

```
python SharePointColumns.py \
  --site "https://contoso.sharepoint.com/sites/Finance" \
  --list "Vendor Master"
``` 

### 3) CSV-Export aktivieren (PassParameter bleibt 0)

```
python SharePointColumns.py \
  --export  "C:\temp\sharepoint_columns.csv"
``` 

### 4) Strikte Übergabe erzwingen (PassParameter = 1)

```
python SharePointColumns.py \
  --passparam 1 \
  --config "C:\python\Scripts\config.json" \
  --site "https://contoso.sharepoint.com/sites/TeamA" \
  --list "My Custom List" \
  --export  "C:\temp\columns.csv"
``` 

### 5) Programmatic Use (als Modul)

```
from SharePointColumns import load_credentials, fetch_sharepoint_list_columns_df, export_csv

tenant_id, client_id, client_secret = load_credentials(r"C:\python\Scripts\config.json")
df = fetch_sharepoint_list_columns_df(
    tenant_id, client_id, client_secret, "https://contoso.sharepoint.com/sites/TeamA", "My Custom List" )
export_csv(df, r"C:\temp\columns.csv", timestamp=True)
``` 

----------
