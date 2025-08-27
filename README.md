# Microsoft Graph API – Übersicht & Beispiele

Die **Microsoft Graph API** ist die zentrale Schnittstelle zu fast allen Microsoft-365-Diensten.  
Damit können Daten aus **Azure Active Directory (Entra ID)**, **SharePoint**, **Teams**, **Outlook**, **Intune** u.v.m. abgerufen, erstellt oder verändert werden.  

Diese Sammlung zeigt eine strukturierte Übersicht der wichtigsten Bereiche mit typischen Endpunkten und wird mit **praktischen Beispielen in Jupyter Notebooks** ergänzt.

---

## 📚 Hauptbereiche der Graph API

### 🔹 Azure Active Directory (Entra ID)
- Benutzer (Profile, Gruppen, Fotos, Lizenzen)
- Gruppen (Mitglieder, Besitzer, dynamische Regeln)
- Rollen und App-Registrierungen
- Anmeldungen & Directory-Audit-Logs

➡️ [Notebook: Azure AD Beispiele](azure_ad.ipynb)

fertige Lösungen
- [MonitoringAD](Solution\MonitoringAD.ipynb) **planning** - ein python Script inklusive Power BI, damit man Änderungen im AD tracken kann (User, Gruppen, Lizenzen usw.)
---

### 🔹 SharePoint & OneDrive (in diesem Abschnitt wird alternativ auch die Verwendung der Sharepoint REST API erklärt)

➡️[Übersicht der APIs von SharePoint](sharepoint_APIs.ipynb)

- Sites & Metadaten ➡️[Notebook: SharePoint_Sites Beispiele](sharepoint_Sites.ipynb)
- Listen (inkl. Paging) ➡️[Notebook: SharePoint_Lists_ Beispiele](sharepoint_Lists.ipynb) 
- Libraries (inkl. Paging) ➡️[Notebook: SharePoint_Libraries Beispiele](sharepoint_Libraries.ipynb)
- Dokumente & Dateien (Upload/Download) ➡️[Notebook: SharePoint_Upload/Download Beispiele](sharepoint_UpdloadDownload.ipynb)
- Berechtigungen auf Site- und Item-Ebene ➡️[Notebook: SharePoint_Permissions Beispiele](sharepoint_Permissions.ipynb)

**fertige Lösungen**
- [SharePoint2SQL](Solution/Sharepoint2SQLUserPW.ipynb) *fertig (alte Lösung)* - ein umfangreiches python Script, das es ermöglicht über eine SQL-Tabelle zu konfigurieren, welche SharePoint Listen auf den SQL-Server gesynct werden sollen. (unidirektional) Wurde durch das nachfolgende Skript abgelöst.
- [SharePoint Graph-API sync to SQL](Solution\Sharepoint2SQL.ipynb) *fertig (neue Lösung)* - ein umfangreiches python Script, das es ermöglicht über eine SQL-Tabelle zu konfigurieren, welche SharePoint Listen auf den SQL-Server gesynct werden sollen. (unidirektional)
- [SharePoint SQL bidirectional sync](Solution\Sharepoint2SQL_bidirectional.ipynb) *planning* - ein umfangreiches python Script, das bidirectional eine SharePoint Liste und SQL-Tabele syncronisiert.
- [FileShare2Libarary](Solution\Sharepoint2Library.ipynb) *planning* - ein umfangreiches pyhton Script, das eine SharePoint Biblitothek und ein Netzlaufwerk syncron hält.

---

### 🔹 Exchange / Outlook
- E-Mails lesen/senden
- Kalender & Termine
- Kontakte

➡️ [Notebook: Outlook Beispiele](outlook.ipynb)

---

### 🔹 Microsoft Teams
- Teams & Channels
- Mitglieder
- Chats & Nachrichten

➡️ [Notebook: Teams Beispiele](teams.ipynb)

---

### 🔹 Intune / Endpoint Management
- Geräteinformationen (Compliance, Konfiguration)
- Apps & Policies

➡️ [Notebook: Intune Beispiele](intune.ipynb)

---

### 🔹 Reports & Analytics
- Office 365 Nutzungsstatistiken (Teams, SharePoint, Exchange)
- Teams User Activity

➡️ [Notebook: Reports Beispiele](reports.ipynb)

---

### 🔹 Planner & To Do
- Planner: Pläne & Tasks
- Microsoft To Do: Aufgabenlisten

➡️ [Notebook: Planner/ToDo Beispiele](planner_todo.ipynb)

---

### 🔹 Security & Compliance
- Defender Alerts
- Security Incidents

➡️ [Notebook: Security Beispiele](security.ipynb)

---

## 🗂 Übersichtstabelle – Dienste & Endpunkte

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

## 🔑 Hinweise zu Berechtigungen
- **Delegated Permissions** → Zugriff auf eigene Daten (`/me/...`)
- **Application Permissions** → Zugriff auf Organisationsweite Daten (Admin-Consent notwendig)
- Typische Scopes: `User.Read.All`, `Sites.Read.All`, `Mail.Read`, `Calendars.Read`

---

## 🚀 Nächste Schritte
- [ ] Erste Abfragen mit `requests` und `MSAL` in Python
- [ ] Notebooks für jeden Bereich ergänzen
- [ ] Best Practices zu Paging, Delta Queries und Webhooks dokumentieren
