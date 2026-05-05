# Finanz-Dashboard

Persönliches Finanz-Dashboard auf Basis von Next.js und Supabase.  
Importiert Kontodaten von Revolut, BBBank und UBS und stellt sie visuell dar.

**Produktion:** https://dashboard-zeta-five-37.vercel.app  
**Repository:** https://github.com/daniellorenz-creator/finanz-projekt

---

## Architektur

```
finanz-projekt/
├── dashboard/              ← Next.js App (Vercel-Projekt "dashboard")
│   ├── app/
│   │   ├── page.tsx        ← Datenabruf (Supabase, Pagination)
│   │   ├── components/
│   │   │   ├── Dashboard.tsx        ← Haupt-Layout, State, Filter
│   │   │   ├── MonthlyChart.tsx     ← ComposedChart (Einnahmen/Ausgaben/Schulden/Fixkosten)
│   │   │   ├── FixkostenCard.tsx    ← Fixkosten-Erkennung & Eingabe
│   │   │   └── TransactionTable.tsx ← Transaktions-Tabelle mit Drill-down
│   │   └── api/auth/[...nextauth]/  ← GitHub OAuth Handler
│   ├── auth.ts             ← NextAuth v5 Konfiguration
│   ├── proxy.ts            ← Auth-Middleware
│   ├── lib/
│   │   ├── supabase.ts     ← Supabase Client (anon key)
│   │   └── types.ts        ← TypeScript-Typen
│   └── .vercel/project.json ← Vercel Projekt-ID (dashboard)
├── import_csv.py           ← Revolut CSV → Supabase
├── import_bbbank_csv.py    ← BBBank CSV (Umsaetze_DE*.csv) → Supabase
├── import_bbbank_pdf.py    ← BBBank PDF Kontoauszüge → Supabase
├── import_ubs_pdf.py       ← UBS PDF Kontoauszüge → Supabase
├── schema.sql              ← Supabase Datenbankschema
├── requirements.txt        ← Python-Abhängigkeiten
└── vercel.json             ← Vercel builds-Konfiguration (Root-Projekt)
```

---

## Datenbank (Supabase)

Tabellen: `accounts`, `categories`, `merchants`, `transactions`, `currency_exchanges`, `import_log`

Row Level Security ist auf allen Tabellen aktiv. Das Dashboard nutzt den `anon`-Key (read-only).

**Konten:**
| Name | Bank | Währung | Typ |
|---|---|---|---|
| Revolut EUR | Revolut | EUR | wallet |
| Revolut CHF | Revolut | CHF | wallet |
| Revolut USD | Revolut | USD | wallet |
| Revolut CAD | Revolut | CAD | wallet |
| BBBank EUR | BBBank | EUR | giro |
| UBS Privatkonto CHF | UBS | CHF | giro |

---

## Datenimport

### Revolut CSV
```bash
# Datei kopieren (Namensschema: account-statement_*.csv)
cp <datei>.csv finanz-projekt/

cd finanz-projekt
python import_csv.py             # Live-Import
python import_csv.py --dry-run   # Vorschau
```

### BBBank CSV
```bash
# Datei kopieren (Namensschema: Umsaetze_DE*.csv)
cp <datei>.csv finanz-projekt/

python import_bbbank_csv.py
python import_bbbank_csv.py --dry-run
```

### BBBank PDF
```bash
# PDFs in Projektordner kopieren (*Kontoauszug*.pdf)
python import_bbbank_pdf.py
python import_bbbank_pdf.py --dry-run
```

### UBS PDF
```bash
# PDFs in Projektordner kopieren
# Unterstützte Muster: UBS_*.pdf, 0292000017124740H0000_Kontoauszug_*.pdf
python import_ubs_pdf.py
python import_ubs_pdf.py --dry-run
```

**Python-Abhängigkeiten installieren:**
```bash
pip install -r requirements.txt
```

**.env Datei** (im Projektordner, nicht im Git):
```
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
```

---

## Dashboard lokal starten

```bash
cd dashboard
npm install
npm run dev
# → http://localhost:3000
```

**`.env.local`** (in `dashboard/`, nicht im Git):
```
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
NEXTAUTH_SECRET=...
AUTH_GITHUB_ID=...
AUTH_GITHUB_SECRET=...
NEXTAUTH_URL=http://localhost:3000
```

---

## Deployment

```bash
cd dashboard
vercel --prod
```

> Wichtig: Immer aus dem `dashboard/`-Unterordner deployen (dort liegt `.vercel/project.json`).

---

## Features

- **Monatsdiagramm** mit 4 Serien: Einnahmen / Ausgaben / Schulden / Fixkosten
- **Drill-down** per Klick auf einen Monat → Transaktionsliste
- **Fixkosten-Karte:** manuelle Eingabe + automatische Erkennung wiederkehrender Positionen, Durchschnitt **pro Jahr** (nicht global)
- **Schulden-Karte:** konfigurierbare Keywords, Fortschrittsbalken
- **Filter:** interne Überweisungen ausblenden, eigene Keywords
- **GitHub OAuth Login** (nur `daniellorenz-creator` erlaubt)
- **Alle Einstellungen** (Filter, Fixkosten, Schulden-Keywords) in localStorage gespeichert

---

## Auth

- Provider: GitHub OAuth
- Erlaubter Account: `daniellorenz-creator`
- Callback URL: `https://dashboard-zeta-five-37.vercel.app/api/auth/callback/github`
- Session-Dauer: 8 Stunden
