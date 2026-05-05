# Session Handover — 05. Mai 2026

**Projekt:** Finanz-Dashboard  
**Repository:** https://github.com/daniellorenz-creator/finanz-projekt  
**Produktion:** https://dashboard-zeta-five-37.vercel.app

---

## Was wurde in dieser Session gemacht

### 1. Vercel Deployment repariert

**Problem:** `vercel.json` enthielt `rootDirectory: "dashboard"` — diese Property ist im Schema nicht erlaubt.

**Lösung 1 (gescheitert):** `buildCommand` + `outputDirectory` + `framework` → Vercel konnte Next.js nicht erkennen, weil `package.json` nicht im Root liegt.

**Lösung 2 (erfolgreich):** `builds`-Array in `vercel.json`:
```json
{
  "builds": [{ "src": "dashboard/package.json", "use": "@vercel/next" }]
}
```

**Weiteres Problem:** Deployments liefen gegen das falsche Vercel-Projekt (`finanz-projekt` statt `dashboard`).  
**Ursache:** `dashboard/.vercel/project.json` zeigt auf Projekt-ID `prj_vLrJ8atTKfIbVvprSJww9cTnjTTk` (Name: `dashboard`).  
**Fix:** Ab sofort immer aus `dashboard/` deployen: `cd dashboard && vercel --prod`

---

### 2. Revolut 2026 CSV importiert

**Datei:** `account-statement_2026-01-01_2026-04-30_de-de_685df4.csv`  
**Quelle:** `C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\Revolt\`  
**Ergebnis:** 490 neue Transaktionen, 6 Währungstausch-Paare, 0 Fehler

---

### 3. Neues Import-Skript: BBBank CSV (`import_bbbank_csv.py`)

Das bisherige `import_bbbank_pdf.py` liest nur PDFs. BBBank exportiert jetzt auch CSVs im Format:
```
Umsaetze_DE50660908000009505920_2026.04.30.csv
```

Spalten (semikolon-getrennt): `Buchungstag`, `Valutadatum`, `Name Zahlungsbeteiligter`, `Buchungstext`, `Verwendungszweck`, `Betrag`, `Waehrung`, `Saldo nach Buchung`

**Neues Skript erstellt:** `import_bbbank_csv.py`  
**Importiert:** 188 neue Transaktionen aus Q1/Q2 2026, 0 Fehler

**Für zukünftige BBBank-CSVs:** Datei (`Umsaetze_DE*.csv`) in Projektordner kopieren → `python import_bbbank_csv.py`

---

### 4. UBS 2026 PDFs importiert

**Neue Dateien:**
- `0292000017124740H0000_Kontoauszug_20260131132109065287.pdf` (Januar 2026)
- `0292000017124740H0000_Kontoauszug_20260228154326623461.pdf` (Februar 2026)
- `0292000017124740H0000_Kontoauszug_20260401204439027105.pdf` (März 2026)
- `0292000017124740H0000_Kontoauszug_20260501140026256103.pdf` (April 2026)

**Problem:** `import_ubs_pdf.py` filterte nur nach `UBS` im Dateinamen, die neuen Dateien heißen anders.  
**Fix:** Glob-Pattern erweitert um `0292000017124740H0000_Kontoauszug_*`:
```python
or re.match(r'0292000017124740H0000_Kontoauszug_', f.name)
```
**Ergebnis:** 20 neue Transaktionen, 176 bereits vorhandene übersprungen, 0 Fehler

---

### 5. Fixkosten pro Jahr statt globalem Durchschnitt (`FixkostenCard.tsx`)

**Vorher:** Ein einziger globaler Ø-Wert für alle Jahre → flache Linie im Chart.

**Nachher:**
- `kandidaten`-Algorithmus berechnet `schnittByJahr: Record<string, number>` (z.B. `{ "2024": 16.66, "2025": 19.99, "2026": 19.99 }`)
- `fixkostenByMonth` nutzt den jahresspezifischen Wert → Linie passt sich pro Jahr an
- **Tabelle** „Automatisch erkannt" zeigt jetzt eine Spalte pro Jahr statt einem einzigen Ø
- **Totals-Bereich** zeigt Fixkosten / Monat aufgeschlüsselt nach Jahr (z.B. `2024: 1.234,56 EUR | 2025: 1.456,78 EUR | 2026: 1.500,00 EUR`)

---

## Aktueller Transaktionsstand (Supabase)

| Bank | Zeitraum | Transaktionen |
|---|---|---|
| Revolut | Jan 2024 – Apr 2026 | ~2.328 |
| BBBank | bis Apr 2026 | ~188+ (PDF-Imports älter) |
| UBS | 2024 – Apr 2026 | ~196 |
| **Gesamt** | | **~2.700+** |

---

## Aktueller Stand aller Komponenten

| Komponente | Datei | Status |
|---|---|---|
| Hauptseite / Datenabruf | `dashboard/app/page.tsx` | ✅ Pagination, alle TX geladen |
| Dashboard-Layout | `dashboard/app/components/Dashboard.tsx` | ✅ Filter, State, Schulden, Fixkosten |
| Monatsdiagramm | `dashboard/app/components/MonthlyChart.tsx` | ✅ ComposedChart, 4 Serien, Toggles |
| Fixkosten-Karte | `dashboard/app/components/FixkostenCard.tsx` | ✅ Per-Jahr-Durchschnitt (diese Session) |
| Transaktions-Tabelle | `dashboard/app/components/TransactionTable.tsx` | ✅ Drill-down |
| Revolut Import | `import_csv.py` | ✅ |
| BBBank PDF Import | `import_bbbank_pdf.py` | ✅ |
| BBBank CSV Import | `import_bbbank_csv.py` | ✅ neu (diese Session) |
| UBS PDF Import | `import_ubs_pdf.py` | ✅ neues Dateinamenmuster ergänzt |
| Datenbankschema | `schema.sql` | ✅ |
| Auth (GitHub OAuth) | `dashboard/auth.ts`, `dashboard/proxy.ts` | ✅ |

---

## Bekannte Probleme

| Problem | Status | Hinweis |
|---|---|---|
| `vercel.json` nutzt veraltetes `builds`-API | Funktioniert, aber Warnung im Build-Log | Besser: Root Directory im Vercel-Dashboard setzen |
| PostCSS CVE (moderate severity) | Offen | Wartet auf Next.js Patch, kein sofortiger Handlungsbedarf |
| Zwei separate Vercel-Projekte | Unkritisch | `finanz-projekt` (Root) und `dashboard` — nur `dashboard` ist aktiv |

---

## Offene Punkte / Nächste Schritte

- [ ] **GitHub Secret Scanning** aktivieren: GitHub → Settings → Code security (2 Klicks)
- [ ] **Vercel Preview Environment Variables** setzen (aktuell nur Production)
- [ ] **Schulden-Karte verbessern:** Kategorie „Interne Überweisung" in Supabase anlegen für präzisere Erkennung statt Keyword-Matching
- [ ] **Mehrwährungs-Ansicht:** CHF/EUR im Chart gemeinsam darstellen (z.B. mit Wechselkurs-Konvertierung)
- [ ] **Budget-Funktion:** Monatliches Budget pro Kategorie setzen und Ist/Soll vergleichen
- [ ] **Regelmäßigen Datenimport** vereinfachen (evtl. Drag & Drop im Dashboard)

---

## Wichtige URLs

| Resource | URL / Pfad |
|---|---|
| Dashboard (Produktion) | https://dashboard-zeta-five-37.vercel.app |
| GitHub Repository | https://github.com/daniellorenz-creator/finanz-projekt |
| Vercel Projekt | https://vercel.com/daniellorenz-creators-projects/dashboard |
| Supabase | Zugangsdaten in `dashboard/.env.local` |

---

## Wichtige Pfade (lokal)

| Beschreibung | Pfad |
|---|---|
| Projektordner | `C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt` |
| Dashboard | `C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt\dashboard` |
| Revolut CSVs (Quelle) | `C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\Revolt\` |
| BBBank CSVs (Quelle) | `C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\BBBank\Girokonto\` |
| UBS PDFs (Quelle) | `C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\UBS\` |

---

## Deploy-Befehle

```bash
# Dashboard deployen (immer aus dashboard/ Ordner!)
cd "C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt\dashboard"
vercel --prod

# Revolut CSV importieren
cd "C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt"
python import_csv.py --dry-run   # erst Vorschau
python import_csv.py

# BBBank CSV importieren
python import_bbbank_csv.py --dry-run
python import_bbbank_csv.py

# UBS PDF importieren
python import_ubs_pdf.py --dry-run
python import_ubs_pdf.py
```
