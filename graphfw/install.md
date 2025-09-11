# GraphFW – Installation & Einbindung

Die **GraphFW**‑Bibliothek ist ein modulares Python‑Framework für die Microsoft Graph API (Azure AD/Entra, SharePoint, Teams, Outlook, Intune, Planner, …).
Diese Anleitung zeigt **alle** praxisrelevanten Wege, GraphFW in Skripte, Notebooks und Projekte einzubinden – **mit** und **ohne** klassische Installation.

> Wichtige Modulpfade:  `graphfw/core/*`, `graphfw/domains/sharepoint/*`, `graphfw/io/writers/*`, `graphfw/params/*`

---

## Inhalt

1. [Voraussetzungen](#voraussetzungen)
2. [Schnellstart (Empfohlen)](#schnellstart-empfohlen)
3. [Installationsvarianten](#installationsvarianten)

   3.1 [Lokales Repo – „editable“](#31-lokales-repo--editable)
   
   3.2 [Aus GitHub installieren (ohne Klonen)](#32-aus-github-installieren-ohne-klonen)
   
   3.3 [Ohne Installation nutzen (PYTHONPATH/syspath)](#33-ohne-installation-nutzen-pythonpathsyspath)
   
   3.4 [Git‑Submodule](#34-git-submodule)
   
   3.5 [Vendoring (Kopieren ins Projekt)](#35-vendoring-kopieren-ins-projekt)
   
   3.6 [ZIP‑Import „on the fly“](#36-zip-import-on-the-fly)
   
   3.7 [Install in Zielordner (`--target`)](#37-install-in-zielordner---target)
   
   3.8 [Jupyter/Notebook‑spezifisch](#38-jupyternotebook-spezifisch)
   
   3.9 [Dauerhaft im Suchpfad (.pth)](#39-dauerhaft-im-suchpfad-pth)
   
5. [Konfiguration (Credentials)](#konfiguration-credentials)
6. [Verifikation & Beispiel](#verifikation--beispiel)
7. [Versionierung, Pinning & Updates](#versionierung-pinning--updates)
8. [Deinstallation](#deinstallation)
9. [Troubleshooting](#troubleshooting)
10. [Sicherheitshinweise](#sicherheitshinweise)

---

## Voraussetzungen

* **Python** ≥ 3.9 (empfohlen 3.10/3.11/3.12)
* **Abhängigkeiten** (Minimum):

```bash
pip install requests msal pandas
```

(Weitere Libs nur bei Bedarf, z. B. SQL/Parquet.)

---

## Schnellstart (Empfohlen)

Wenn das Repo **packaging‑fähig** ist (mit `pyproject.toml`), installiere direkt aus GitHub **ohne Klonen**:

```bash
# Paket im Repo‑Root
pip install "graphfw @ git+https://github.com/ErhardRainer/graphfw@main"

# Paket als Unterordner (Monorepo), Beispiel: graphfw liegt unter /graphfw
pip install "graphfw @ git+https://github.com/ErhardRainer/GRAPH_API@main#subdirectory=graphfw"
```

> **Tipp:** Statt `@main` besser **Tag** oder **Commit‑Hash** pinnen (z. B. `@v0.2.3` oder `@3f1c2ab`).

---

## Installationsvarianten

### 3.1 Lokales Repo – „editable“

```bash
# Repo klonen
git clone https://github.com/ErhardRainer/GRAPH_API.git
cd GRAPH_API/graphfw

# Entwicklungsinstallation (Codeänderungen wirken sofort)
pip install -e .
```

### 3.2 Aus GitHub installieren (ohne Klonen)

Ohne lokalen Clone – funktioniert, wenn ein Packaging‑Setup vorhanden ist:

```bash
# Repo-Root ist Paket
pip install "graphfw @ git+https://github.com/ErhardRainer/graphfw@v0.1.0"

# Monorepo-Unterordner als Paket
pip install "graphfw @ git+https://github.com/ErhardRainer/GRAPH_API@main#subdirectory=graphfw"
```

### 3.3 Ohne Installation nutzen (PYTHONPATH/sys.path)

**Temporär pro Aufruf**

```bash
# macOS/Linux
PYTHONPATH=/pfad/zum/repo python dein_script.py

# Windows PowerShell
$env:PYTHONPATH="C:\\pfad\\zum\\repo"; python dein_script.py

# Windows CMD
set PYTHONPATH=C:\pfad\zum\repo
python dein_script.py
```

**In Jupyter**

```python
import sys
sys.path.insert(0, r"C:\pfad\zum\repo")  # Ordner, der die Mappe 'graphfw' enthält
```

### 3.4 Git‑Submodule

Saubere Kopplung ohne Packaging:

```bash
git submodule add https://github.com/ErhardRainer/graphfw vendor/graphfw
```

Dann Projekt‑Root oder `vendor/` zum Suchpfad hinzufügen (z. B. via `PYTHONPATH` oder `sys.path.insert`).

### 3.5 Vendoring (Kopieren ins Projekt)

Kopiere den Ordner **`graphfw/`** direkt in dein Projekt (neben deinen Skripten).
Achte auf `__init__.py` in den Paketordnern.

### 3.6 ZIP‑Import „on the fly“

Lade das GitHub‑ZIP zur Laufzeit und füge es dem Suchpfad hinzu – **ohne Installation**:

```python
import sys, io, zipfile, tempfile, requests, os

ZIP_URL = "https://github.com/ErhardRainer/GRAPH_API/archive/refs/heads/main.zip"
tmpdir = tempfile.mkdtemp(prefix="graphfw_")

zdata  = io.BytesIO(requests.get(ZIP_URL, timeout=60).content)
zipfile.ZipFile(zdata).extractall(tmpdir)

repo_root = os.path.join(tmpdir, "GRAPH_API-main")  # ggf. anpassen
sys.path.insert(0, repo_root)                         # enthält den Ordner 'graphfw/'
```

### 3.7 Install in Zielordner (`--target`)

```bash
pip install --target ./.vendor "graphfw @ git+https://github.com/ErhardRainer/graphfw@main"
```

Dann im Code:

```python
import sys
sys.path.insert(0, "./.vendor")
```

### 3.8 Jupyter/Notebook‑spezifisch

**Variante A – Magics:**

```python
%pip install -q "graphfw @ git+https://github.com/ErhardRainer/graphfw@main"
```

**Variante B – Pfad injizieren:**

```python
import sys
sys.path.insert(0, r"C:\pfad\zum\repo")
```

### 3.9 Dauerhaft im Suchpfad (.pth)

Lege in deinem `site-packages` eine Datei z. B. `graphfw_dev.pth` an, deren **Inhalt** nur der absolute Pfad zum Repo ist:

```
C:\pfad\zum\repo
```

Damit wird der Pfad dauerhaft in den Python‑Suchpfad aufgenommen – ohne Paketinstallation.

---

## Konfiguration (Credentials)

GraphFW nutzt für App‑Authentifizierung (Client‑Credentials‑Flow) eine `config.json`.

**Beispiel `config.json`:**

```json
{
  "azuread": {
    "tenant_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "client_secret": "YOUR_SECRET"
  }
}
```

**Minimaler Einstiegscode:**

```python
from graphfw.core.auth import TokenProvider
from graphfw.core.http import GraphClient

from graphfw.domains.sharepoint.lists.items import list_df

CONFIG_JSON = r"C:\\python\\Scripts\\config.json"
SITE_URL    = "https://contoso.sharepoint.com/sites/TeamA"
LIST_TITLE  = "My Custom List"

# Auth & HTTP
tp = TokenProvider.from_json(CONFIG_JSON)
gc = GraphClient(tp)

# Daten abrufen
df, info = list_df(gc, site_url=SITE_URL, list_title=LIST_TITLE, columns="*")
print(df.head())
```

---

## Verifikation & Beispiel

**Importtest:**

```python
python -c "from graphfw.core.http import GraphClient; print('OK')"
```

**SharePoint‑Beispiel (mit CSV‑Export):**

```python
from graphfw.core.auth import TokenProvider
from graphfw.core.http import GraphClient
from graphfw.domains.sharepoint.lists.items import list_df
from graphfw.io.writers.csv_writer import build_csv_path, write_csv

CONFIG_JSON = r"C:\\python\\Scripts\\config.json"
SITE_URL    = "https://contoso.sharepoint.com/sites/TeamA"
LIST_TITLE  = "My Custom List"

gc = GraphClient(TokenProvider.from_json(CONFIG_JSON))

df, info = list_df(gc, site_url=SITE_URL, list_title=LIST_TITLE, columns="*")

csv_path = build_csv_path(df, site_url=SITE_URL, list_title=LIST_TITLE, out_dir="./exports", timestamp=True)
write_csv(df, csv_path)
print("CSV gespeichert:", csv_path)
```

---

## Versionierung, Pinning & Updates

* In produktiven Umgebungen **immer pinnen**:

```text
# requirements.txt
graphfw @ git+https://github.com/ErhardRainer/graphfw@v0.2.3
```

* Alternativ **Commit‑Hash** verwenden: `@<hash>`
* Update auf neuere Version: einfach Versions‑Tag anpassen und erneut `pip install -r requirements.txt`.

---

## Deinstallation

```bash
pip uninstall graphfw
```

Bei „ohne Installation“‑Varianten: Pfadeinträge (`PYTHONPATH`, `.pth`, `sys.path.insert`) oder den `vendor/`‑Ordner entfernen.

---

## Troubleshooting

* **ModuleNotFoundError: graphfw**
  Pfad stimmt nicht. Prüfe, ob der **Repo‑Root** (der Ordner, der `graphfw/` enthält) im Suchpfad liegt.

* **ImportError nach Update**
  Alte Bytecode‑Dateien (`__pycache__`) entfernen, Kernel/Interpreter neu starten.

* **Auth/HTTP‑Fehler**
  Prüfe `config.json`, Tenant/App‑Berechtigungen (Graph **Application** Permissions, z. B. `Sites.Read.All`).

* **Notebook findet Paket nicht**
  Verwende `%pip install ...` im **gleichen Kernel** oder setze `sys.path.insert` in der ersten Zelle.

---

## Sicherheitshinweise

* **Secrets** (Client Secret) niemals committen. `config.json` außerhalb der Versionskontrolle halten (z. B. `.gitignore`).
* **Least Privilege**: Nur benötigte Graph‑Scopes (Application/Delegated) vergeben.
* Logs/Diagnoseausgaben dürfen **keine** Secrets enthalten.

---

**Viel Erfolg mit GraphFW!**
Wenn du eine CI/CD‑ oder Docker‑Integration möchtest, füge die passende Variante (GitHub‑Install oder `--target`) in deine Pipeline ein und pinne auf einen Tag/Commit.
