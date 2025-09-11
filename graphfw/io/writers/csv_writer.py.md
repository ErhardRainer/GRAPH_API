# csv_writer.py — Dokumentation & Beispiele (aktualisiert)

Diese Markdown‑Seite beschreibt die vereinfachte CSV‑Writer‑Schnittstelle im Modul `graphfw.io.writers.csv_writer`.

> **Kurzfassung:**
> Mit `write_csv(...)` exportierst du ein DataFrame als CSV mit Namen nach dem Schema
> `"<prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].csv"`.
> Es wird der **vollständige Pfad** der erzeugten Datei zurückgegeben.

---

## Inhalt

* [Voraussetzungen](#voraussetzungen)
* [API](#api)

  * [`build_csv_path`](#build_csv_path)
  * [`write_csv`](#write_csv)
* [Benennungsschema](#benennungsschema)
* [Schnellstart](#schnellstart)
* [Beispiel: erzeugte Dateinamen](#beispiel-erzeugte-dateinamen)
* [Beispiel: CSV‑Dateiinhalt](#beispiel-csv-dateiinhalt)
* [Typische Varianten](#typische-varianten)
* [Fehlerszenarien & Verhalten](#fehlerszenarien--verhalten)
* [Best Practices](#best-practices)

---

## Voraussetzungen

* Python 3.9+
* Ein pandas‑kompatibles DataFrame‑Objekt (z. B. `pandas.DataFrame`) mit Methode `.to_csv(...)`.
* Modulpfad: `graphfw/io/writers/csv_writer.py`

---

## API

### `build_csv_path`

Erzeugt den Zielpfad (im aktuellen Arbeitsverzeichnis, *cwd*) anhand von Namensteilen.

```python
from graphfw.io.writers.csv_writer import build_csv_path

path = build_csv_path(prefix="Contoso_SiteA", postfix="List_Projects", timestamp=True)
print(path)
# → /aktuelles/arbeitsverzeichnis/Contoso_SiteA_20250912_133001_List_Projects.csv
```

**Parameter**

* `prefix: str` – Erster Namensbestandteil (wird für Dateinamen saniert).
* `postfix: str | None` – Optionaler zweiter Bestandteil (wird saniert).
* `timestamp: bool = True` – Fügt `YYYYMMDD_hhmmss` **zwischen** `prefix` und `postfix` an.

**Rückgabe**

* `pathlib.Path` – Vollständiger Pfad (Datei wird **nicht** erstellt).

---

### `write_csv`

Schreibt ein DataFrame als CSV in das aktuelle Arbeitsverzeichnis und gibt den vollständigen Pfad zurück.

```python
from graphfw.io.writers.csv_writer import write_csv
import pandas as pd

df = pd.DataFrame({"Id": [1, 2], "Title": ["Alpha", "Beta"], "Created": ["2025-09-12", "2025-09-12"]})

csv_path = write_csv(
    df,
    prefix="Contoso_SiteA",
    postfix="List_Projects",
    timestamp=True,          # Dateiname mit Zeitstempel (zwischen prefix und postfix)
    encoding="utf-8-sig",   # Excel-freundlich
    index=False,             # Indexspalte nicht mitschreiben
    date_format=None,        # Optionales Datumsformat für pandas
    overwrite=False,         # Falls Datei existiert: automatisch _001, _002, ...
)
print("CSV geschrieben nach:", csv_path)
```

**Parameter**

* `prefix: str` – Erster Namensbestandteil (wird saniert).
* `postfix: str | None = None` – Optionaler zweiter Bestandteil.
* `timestamp: bool = True` – `YYYYMMDD_hhmmss` **zwischen** `prefix` und `postfix` in den Dateinamen einfügen.
* `encoding: str = "utf-8-sig"` – Standard‑Encoding (Excel‑geeignet).
* `index: bool = False` – DataFrame‑Index mitschreiben.
* `date_format: str | None = None` – pandas‑`date_format` für Datumsspalten.
* `overwrite: bool = False` – Vorhandene Datei überschreiben (True) oder eindeutig machen (`_001`, `_002`, …).

**Rückgabe**

* `pathlib.Path` – Pfad der **erzeugten** CSV‑Datei.

---

## Benennungsschema

`<prefix>[_<YYYYMMDD>_<hhmmss>][_<postfix>].csv`

**Beispiele**

* `Contoso_SiteA_20250912_133001_List_Projects.csv`
* `Export_20250103_081500_Users.csv`
* `AuditTrail.csv` *(wenn `timestamp=False` und kein `postfix` übergeben)*

> **Hinweis:** `prefix`/`postfix` werden automatisch für Dateinamen bereinigt (unerlaubte/ungünstige Zeichen werden ersetzt).

---

## Schnellstart

```python
from graphfw.io.writers.csv_writer import write_csv
import pandas as pd

# Beispiel-DataFrame
orders = pd.DataFrame([
    {"OrderId": 1001, "Customer": "Fabrikam", "Amount": 199.90, "Created": "2025-09-12"},
    {"OrderId": 1002, "Customer": "Contoso",  "Amount":  49.00, "Created": "2025-09-12"},
])

# 1) Standardexport mit Zeitstempel (zwischen prefix und postfix)
p1 = write_csv(orders, prefix="Sales", postfix="Orders", timestamp=True)
print(p1.name)  # Sales_20250912_133001_Orders.csv

# 2) Stabiler Name ohne Zeitstempel (potenzielles Overwrite steuern)
p2 = write_csv(orders, prefix="Sales", postfix="Orders", timestamp=False, overwrite=False)
print(p2.name)  # ggf. Sales_Orders.csv oder Sales_Orders_001.csv

# 3) Überschreiben explizit erlauben
p3 = write_csv(orders, prefix="Sales", postfix="Orders", timestamp=False, overwrite=True)
print(p3.name)  # Sales_Orders.csv
```

---

## Beispiel: erzeugte Dateinamen

Angenommen, aktuelles Datum/Zeit ist **2025‑09‑12 13:30:01** und *cwd* ist `/export`.

| Aufruf (relevant)                                                            | Ergebnis-Dateiname                                |
| ---------------------------------------------------------------------------- | ------------------------------------------------- |
| `prefix="Contoso_SiteA"`, `postfix="List_Projects"`, `timestamp=True`        | `Contoso_SiteA_20250912_133001_List_Projects.csv` |
| `prefix="AuditTrail"`, `timestamp=False`                                     | `AuditTrail.csv`                                  |
| `prefix="AuditTrail"`, `timestamp=False`, Datei existiert, `overwrite=False` | `AuditTrail_001.csv` *(bzw. `_002`, …)*           |

Vollständiger Pfad entspricht dann z. B. `/export/Contoso_SiteA_20250912_133001_List_Projects.csv`.

---

## Beispiel: CSV‑Dateiinhalt

Für das im Schnellstart gezeigte `orders`‑DataFrame ergibt sich z. B. folgendes CSV (mit `encoding="utf-8-sig"`, `index=False`):

```csv
OrderId,Customer,Amount,Created
1001,Fabrikam,199.9,2025-09-12
1002,Contoso,49.0,2025-09-12
```

Mit `index=True` sähe der Anfang so aus:

```csv
,OrderId,Customer,Amount,Created
0,1001,Fabrikam,199.9,2025-09-12
1,1002,Contoso,49.0,2025-09-12
```

Mit `date_format="%Y-%m-%d"` formatiert pandas Datumsspalten entsprechend, z. B. `2025-09-12`.

---

## Typische Varianten

**Ohne Postfix, mit Zeitstempel**

```python
path = write_csv(df, prefix="Inventory", timestamp=True)
# Inventory_20250912_133001.csv
```

**Mit Postfix und Zeitstempel**

```python
path = write_csv(df, prefix="Inventory", postfix="Reports", timestamp=True)
# Inventory_20250912_133001_Reports.csv
```

**Fester Name ohne Zeitstempel, Duplikate vermeiden**

```python
path = write_csv(df, prefix="Inventory", postfix="Reports", timestamp=False, overwrite=False)
# Inventory_Reports.csv oder Inventory_Reports_001.csv, falls bereits vorhanden
```

**Explizites Überschreiben (vorsichtig einsetzen)**

```python
path = write_csv(df, prefix="Inventory", postfix="Reports", timestamp=False, overwrite=True)
# Überschreibt Inventory_Reports.csv, falls vorhanden
```

---

## Fehlerszenarien & Verhalten

* **Datei existiert & `overwrite=False`** → automatischer Suffix `_001`, `_002`, … bis eindeutiger Name gefunden wird.
* **Ungültige Zeichen in `prefix`/`postfix`** → werden automatisch bereinigt (sanitizing), damit ein gültiger Dateiname entsteht.
* **Ordner nicht vorhanden** → wird bei Bedarf erstellt (über `Path.mkdir(parents=True, exist_ok=True)`).
* **Schreibfehler (z. B. Berechtigungen)** → Exception von `df.to_csv(...)`/`OSError` propagiert.

---

## Best Practices

* Für Excel‑Kompatibilität `encoding="utf-8-sig"` belassen.
* Für reproduzierbare Exporte ohne Overwrite‑Risiko `timestamp=True` verwenden.
* Für Snapshots mit klarer Reihenfolge: kombinierte `prefix`/`postfix` mit semantischen Tokens nutzen, z. B. `prefix="HR"`, `postfix="Users_DE"`.
* `date_format` nur setzen, wenn du sicher bist, dass alle relevanten Spalten als Datum interpretiert werden.
