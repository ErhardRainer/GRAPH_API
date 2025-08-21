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

➡️ [Notebook: Azure AD Beispiele](notebooks/azure_ad.ipynb)

---

### 🔹 SharePoint & OneDrive
- Sites & Metadaten
- Listen & Libraries (inkl. Paging)
- Dokumente & Dateien (Upload/Download)
- Berechtigungen auf Site- und Item-Ebene

➡️ [Notebook: SharePoint Beispiele](notebooks/sharepoint.ipynb)

---

### 🔹 Exchange / Outlook
- E-Mails lesen/senden
- Kalender & Termine
- Kontakte

➡️ [Notebook: Outlook Beispiele](notebooks/outlook.ipynb)

---

### 🔹 Microsoft Teams
- Teams & Channels
- Mitglieder
- Chats & Nachrichten

➡️ [Notebook: Teams Beispiele](notebooks/teams.ipynb)

---

### 🔹 Intune / Endpoint Management
- Geräteinformationen (Compliance, Konfiguration)
- Apps & Policies

➡️ [Notebook: Intune Beispiele](notebooks/intune.ipynb)

---

### 🔹 Reports & Analytics
- Office 365 Nutzungsstatistiken (Teams, SharePoint, Exchange)
- Teams User Activity

➡️ [Notebook: Reports Beispiele](notebooks/reports.ipynb)

---

### 🔹 Planner & To Do
- Planner: Pläne & Tasks
- Microsoft To Do: Aufgabenlisten

➡️ [Notebook: Planner/ToDo Beispiele](notebooks/planner_todo.ipynb)

---

### 🔹 Security & Compliance
- Defender Alerts
- Security Incidents

➡️ [Notebook: Security Beispiele](notebooks/security.ipynb)

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
