# Start-Prompt für nächste Claude Code Session

Kopiere den folgenden Block als erste Nachricht in die neue Session:

---

```
Ich arbeite an meinem persönlichen Finanz-Dashboard Projekt.

## Projektübersicht
- Next.js Dashboard mit Supabase-Datenbank
- GitHub: daniellorenz-creator/finanz-projekt
- Produktion: https://dashboard-zeta-five-37.vercel.app
- Lokaler Pfad: C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt

## Wichtige Regeln
- Dashboard immer aus dem dashboard/-Unterordner deployen: cd dashboard && vercel --prod
- Vor jedem Import: --dry-run ausführen
- Python-Skripte laufen im Projektordner (nicht im dashboard/-Ordner)

## Datenquellen & Import-Skripte
- Revolut CSV:   account-statement_*.csv         → python import_csv.py
- BBBank CSV:    Umsaetze_DE*.csv                → python import_bbbank_csv.py
- BBBank PDF:    *Kontoauszug*.pdf               → python import_bbbank_pdf.py
- UBS PDF:       UBS_*.pdf / 0292000017124740H0000_Kontoauszug_*.pdf → python import_ubs_pdf.py

## Neue Dateien vor dem Import hierhin kopieren
- Revolut:  → C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt\
- BBBank:   → C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt\
- UBS:      → C:\Users\Daniel\OneDrive\Dokumente\18 KI\finanz-projekt\

## Originaldateien liegen hier
- Revolut:  C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\Revolt\
- BBBank:   C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\BBBank\Girokonto\
- UBS:      C:\Users\Daniel\OneDrive\Dokumente\08 Finanzen\01 Bank\UBS\

## Aktueller Stand (05.05.2026)
- ~2.700+ Transaktionen in Supabase (Revolut 2024–Apr 2026, BBBank bis Apr 2026, UBS 2024–Apr 2026)
- Fixkosten-Karte zeigt Durchschnitt pro Jahr (nicht global)
- GitHub OAuth Login aktiv (nur daniellorenz-creator erlaubt)
- RLS auf allen Supabase-Tabellen aktiv

## Offene Punkte (Priorität)
1. GitHub Secret Scanning aktivieren (GitHub → Settings → Code security)
2. Vercel Preview Environment Variables setzen
3. Schulden-Karte: Kategorie statt Keyword-Matching
4. Mehrwährungs-Ansicht (CHF + EUR im Chart)
5. Budget-Funktion pro Kategorie

## Vollständige Dokumentation
Siehe: docs/SESSION_HANDOVER_2026-05-05.md
```

---

## Hinweise zur Nutzung

- Den Prompt **unverändert** einfügen — Claude liest alle wichtigen Pfade und Regeln daraus
- Danach direkt die Aufgabe beschreiben, z.B.:
  - *„Ich habe neue Revolut-Daten, Dateiname: account-statement_2026-05-01_..."*
  - *„Bitte implementiere die Budget-Funktion"*
  - *„Es gibt einen neuen Fehler: ..."*
- Bei Deployment-Problemen zuerst prüfen: Wurde aus `dashboard/` deployed?
