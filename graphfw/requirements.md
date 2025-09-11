# Installation der Requirements

Diese Anleitung erklärt, wie du die **Python‑Abhängigkeiten** für das Projekt/Framework installierst – sowohl minimal (Core) als auch für optionale Komponenten wie SQL, Notebooks oder Parquet.

---

## Voraussetzungen

* **Python** ≥ 3.9 (empfohlen: 3.10/3.11/3.12)
* **pip** aktuell halten:

  ```bash
  python -m pip install --upgrade pip
  ```
* (Empfohlen) **Virtuelle Umgebung** verwenden:

  * macOS/Linux:

    ```bash
    python -m venv .venv
    source .venv/bin/activate
    ```
  * Windows (PowerShell):

    ```powershell
    python -m venv .venv
    .\.venv\Scripts\Activate.ps1
    ```

---

## Wo liegen die Requirements‑Dateien?

Lege die Dateien idealerweise **im Repo‑Root** ab:

```
GRAPH_API/
├─ graphfw/
├─ notebooks/
├─ requirements.txt              # Core (msal, requests, pandas, dateutil)
├─ requirements-sql.txt          # optional: SQL (SQLAlchemy, Treiber)
├─ requirements-notebooks.txt    # optional: Jupyter
├─ requirements-parquet.txt      # optional: Parquet/Arrow
└─ requirements-dev.txt          # optional: Dev/Lint/Test
```

> Alternative: Unterordner `requirements/` verwenden (z. B. `requirements/base.txt`, `requirements/sql.txt`, …). Die Befehle unten musst du dann entsprechend anpassen (z. B. `-r requirements/base.txt`).

---

## Installationsvarianten

### 1) **Core Runtime** (SharePoint/AAD/Teams/Outlook – ohne Extras)

```bash
pip install -r requirements.txt
```

### 2) Core **+ SQL‑Export**

```bash
pip install -r requirements.txt -r requirements-sql.txt
```

### 3) Core **+ Notebook‑Demos**

```bash
pip install -r requirements.txt -r requirements-notebooks.txt
```

### 4) Core **+ Parquet/Arrow**

```bash
pip install -r requirements.txt -r requirements-parquet.txt
```

### 5) Core **+ Dev‑Tools (Lint/Type/Tests)**

```bash
pip install -r requirements.txt -r requirements-dev.txt
```

### 6) Kombinationen

Du kannst mehrere Dateien kombinieren, z. B. **Core + SQL + Notebooks**:

```bash
pip install -r requirements.txt -r requirements-sql.txt -r requirements-notebooks.txt
```

---

## Optional: Reproduzierbare Builds mit `constraints.txt`

Wenn du exakt getestete Versionen pinnen willst, lege zusätzlich eine `constraints.txt` an und installiere so:

```bash
pip install -r requirements.txt -c constraints.txt
```

> In `constraints.txt` stehen exakte Versionsnummern; `requirements*.txt` definieren nur die Pakete (und ggf. Versionsbereiche).

---

## Jupyter/Notebook‑Szenarien

Verwende `%pip` innerhalb des Notebooks, damit im **aktuellen Kernel** installiert wird:

```python
%pip install -q -r requirements.txt
# oder kombiniert:
%pip install -q -r requirements.txt -r requirements-notebooks.txt
```

Falls du ohne Installation arbeiten willst, kannst du den Repo‑Pfad temporär injizieren:

```python
import sys
sys.path.insert(0, r"C:\\pfad\\zum\\repo")  # Ordner, der die Mappe 'graphfw' enthält
```

---

## Verifikation

```bash
python -c "import pandas, requests, msal; print('Requirements OK')"
```

Oder ein Minimal‑Snippet:

```python
from graphfw.core.auth import TokenProvider
from graphfw.core.http import GraphClient
print('graphfw import OK')
```

---

## Häufige Probleme & Lösungen

* **`ModuleNotFoundError` nach Installation**
  Stelle sicher, dass die **richtige virtuelle Umgebung** aktiv ist. Starte ggf. Terminal/Kernel neu.

* **Kompilations-/Wheel‑Fehler bei DB‑Treibern**
  Unter Windows ggf. passenden ODBC‑Treiber installieren (z. B. „ODBC Driver 17 for SQL Server“). Alternativ Plattform‑spezifischen Treiber wählen.

* **Proxy/Firewall**
  Setze ggf. `HTTP_PROXY`/`HTTPS_PROXY` oder nutze Offline‑Wheels (unternehmensinterne Indices/Artifactory).

* **`pip` zu alt**
  `python -m pip install --upgrade pip` ausführen und erneut installieren.

---

## Deinstallation

```bash
pip uninstall -y -r <(sed 's/#.*//' requirements.txt | awk 'NF')
```

> Windows: Pakete einzeln deinstallieren oder `pip freeze > installed.txt` und daraus deinstallieren.

Praktisch ist meist: **virtuelle Umgebung löschen** und neu erstellen (`.venv` entfernen, dann wieder `python -m venv .venv`).

---

## Best Practices

* **Virtuelle Umgebungen** pro Projekt/Repo halten die Pakete sauber getrennt.
* In CI/CD Pipelines stets auf definierte Dateien referenzieren (Root‑`requirements*.txt`).
* Für Produktivsysteme Versionen pinnen (Constraints oder feste Versionsbereiche).

---

**Fertig!** Mit den Befehlen oben hast du alle Varianten im Griff – vom schlanken Core‑Setup bis zur Notebook‑ oder SQL‑fähigen Umgebung.
