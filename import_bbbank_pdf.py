#!/usr/bin/env python3
"""
BBBank PDF Kontoauszug -> Supabase Import Script
Verarbeitet alle *Kontoauszug*.pdf Dateien im gleichen Ordner.

Ein PDF kann mehrere Monate enthalten (Sammeldatei).
Jahr und Monat werden aus dem Kontoauszug-Header jeder Seite gelesen.

Verwendung:
  python import_bbbank_pdf.py             # Live-Import
  python import_bbbank_pdf.py --dry-run   # Vorschau ohne Datenbankänderungen

WICHTIG -- einmalig in Supabase SQL Editor ausführen, bevor der
Import läuft (erweitert den CHECK um BBBank-Typen):

    ALTER TABLE transactions
    DROP CONSTRAINT IF EXISTS transactions_transaction_type_check;

    ALTER TABLE transactions
    ADD CONSTRAINT transactions_transaction_type_check
    CHECK (transaction_type IN (
        'Einzahlung','Umtausch','Kartenbezahlung','Transfer',
        'Rückerstattung','Geldautomat','Gebühr','Belastung','Sonstiges',
        'Lastschrift','Gutschrift','Euro-Überweisung','Darlehen','Abschluss'
    ));
"""

import hashlib
import os
import re
import sys
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

import pdfplumber
from dotenv import load_dotenv
from supabase import create_client, Client

# ── Konfiguration ──────────────────────────────────────────────────────────────
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DRY_RUN = "--dry-run" in sys.argv
SCRIPT_DIR = Path(__file__).parent

# BBBank-Kontodaten
BBBANK_ACCOUNT = {
    "name":         "BBBank EUR",
    "bank_name":    "BBBank",
    "account_ref":  "DE50 6609 0800 0009 5059 20",
    "currency":     "EUR",
    "account_type": "giro",
}

# ── Regex-Muster ───────────────────────────────────────────────────────────────

# Kontoauszug-Kopfzeile: "Kontoauszug Nr. 1/2024" oder "Ko nto aus zug Nr. 8/2025" (pdfplumber-Artefakt)
STMT_HEADER_RE = re.compile(
    r'K\s*o\s*n\s*t\s*o\s*a\s*u\s*s\s*z\s*u\s*g\s+Nr\.\s*(\d{1,2})/(\d{4})'
)

# Transaktionszeile: 02.01. 02.01. Euro-Überweisung PN:801 1.234,56 S
TX_RE = re.compile(
    r'^(\d{2}\.\d{2}\.)'   # Bu-Tag
    r'\s+'
    r'(\d{2}\.\d{2}\.)'   # Wert
    r'\s+'
    r'(.+?)'              # Typ + PN:NNN (lazy)
    r'\s+'
    r'([\d.]+,\d{2})'     # Betrag (deutsches Format)
    r'\s+'
    r'([SH])'             # S=Soll (Ausgabe), H=Haben (Einnahme)
    r'\s*$'
)

# Saldozeilen
OPEN_BAL_RE  = re.compile(r'^alter Kontostand',         re.IGNORECASE)
CLOSE_BAL_RE = re.compile(r'^neuer Kontostand',          re.IGNORECASE)
CARRY_RE     = re.compile(r'^[Üü]bertrag (?:auf|von) Blatt', re.IGNORECASE)
COLUMN_HDR   = re.compile(r'^Bu-Tag\s+Wert\s+Vorgang')

# Fußzeilen (ignorieren)
FOOTER_RE = re.compile(
    r'^(?:\d{4}$|K\d{7,}|5M\s+Bitte|Bitte beachten|'
    r'Wir w[üu]nschen|Ihr BBBank|Bankleitzahl|BBBank eG|'
    r'EUR-Konto Kontonummer|IBAN:\s+DE|79098 Freiburg|'
    r'79104 Freiburg|Sautierstr\.|Herrn Ihr Kredit|'
    r'Sollzins|BBBank-Gehaltskonto|000$)',
    re.IGNORECASE
)

# ── Transaktionstypen ─────────────────────────────────────────────────────────
# Raw-Typ (PN:xxx entfernt) → normalisierter DB-Typ
BBBANK_TYPE_MAP: dict[str, str] = {
    "Gutschrift":         "Gutschrift",
    "Da-Gutschrift":      "Gutschrift",     # Dauerauftrag-Gutschrift
    "Lastschrift":        "Lastschrift",
    "Euro-Überweisung":   "Euro-Überweisung",
    "Überweisung":        "Euro-Überweisung",
    "Darlehen":           "Darlehen",
    "Abschluss":          "Abschluss",
    "Entgelt":            "Abschluss",      # z.B. "Entgelt Girocard"
    "Auszahlung girocard": "Geldautomat",   # Bargeldauszahlung per girocard
    "Auszahlung":         "Geldautomat",    # fallback
}

# Typ → Fallback-Kategorie
TYPE_CATEGORY_MAP: dict[str, str] = {
    "Gutschrift":       "Gehalt / Eingang",
    "Lastschrift":      "Sonstiges",
    "Euro-Überweisung": "Überweisung",
    "Darlehen":         "Überweisung",
    "Abschluss":        "Bankgebühren",
}

# Händler-Schlüsselwörter → Kategorie (aus import_csv.py übernommen + BBBank-spezifische)
MERCHANT_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["apple", "mediamarkt", "galaxus"],                       "Elektronik"),
    (["bäckerei", "pizza", "restaurant", "cafe", "kaffi",
      "buffet", "gourmets", "siam thai", "grill", "troika",
      "new york fries"],                                        "Restaurant / Cafe"),
    (["allianz", "dkv", "krankenvers", "apotheke",
      "tierarzt", "arzt", "labor", "klinik", "clotten",
      "optiker", "sanitäts"],                                   "Gesundheit"),
    (["esso", "aral", "tankstelle", "naturenergie",
      "stadtwerke", "strom", "gas", "energie"],                 "Energie / Tanken"),
    (["parkhaus", "parkhäuser", "easypark",
      "stadtkasse", "kfz"],                                     "Parkgebühren / KFZ"),
    (["coop", "migros", "aldi", "edeka", "rewe",
      "lidl", "netto", "penny", "mix markt",
      "dm drogerie", "rossmann"],                               "Lebensmittel"),
    (["amazon", "zalando", "ikea", "bauhaus",
      "metz mueller", "bonacelli", "ebay", "paypal"],           "Shopping"),
    (["telefonica", "o2", "telekom", "vodafone"],               "Telekommunikation"),
    (["spotify", "netflix", "prime video",
      "amazon digital", "openai"],                              "Abonnements"),
    (["sbb", "deutsche bahn", "db regio",
      "mvg", "rnv", "vag freiburg"],                            "Transport"),
    (["hotel", "booking.com", "airbnb", "hilton"],              "Reise / Hotel"),
    (["bundesamt", "finanzamt", "gemeinde",
      "landkreis", "stadtkasse", "kreissparkasse",
      "zollamt"],                                               "Behörden / Steuern"),
    (["weg ", "hausgeld", "kommunalbauten",
      "wohnungseigentum", "wohnungsverwaltung"],                "Wohnen / Hausgeld"),
    (["miete", "mietrecht", "rzesnik"],                         "Miete"),
    (["vhv", "versicherung", "versicherungs"],                  "Versicherung"),
    (["abschluss", "zinsen", "entgelt kontoführung"],           "Bankgebühren"),
]


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def row_hash(source_file: str, bu_date: str, amount: Decimal,
             currency: str, description: str) -> str:
    key = "|".join([source_file, bu_date, str(amount), currency, description[:80]])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def parse_amount(s: str) -> Decimal:
    """'1.234,56' -> Decimal('1234.56')"""
    return Decimal(s.replace(".", "").replace(",", "."))


def parse_date(dm: str, stmt_month: int, stmt_year: int) -> str:
    """'15.01.' -> '2024-01-15', berücksichtigt Jahreswechsel.
    Klemmt 30.02. (BBBank Abschluss-Konvention) auf den letzten gültigen Tag."""
    m = re.match(r'(\d{2})\.(\d{2})\.', dm)
    day, month = int(m.group(1)), int(m.group(2))
    year = stmt_year
    if stmt_month == 1 and month == 12:
        year -= 1   # Jan-Kontoauszug, Dez-Datum → Vorjahr
    elif stmt_month == 12 and month == 1:
        year += 1   # Dez-Kontoauszug, Jan-Datum → Folgejahr
    max_day = monthrange(year, month)[1]
    day = min(day, max_day)  # z.B. 30.02. → 28/29
    return date(year, month, day).isoformat()


def extract_tx_type(raw_vorgang: str) -> str:
    """'Euro-Überweisung PN:801' -> 'Euro-Überweisung'"""
    cleaned = re.sub(r'\s+PN:\d+.*$', '', raw_vorgang).strip()
    # Abschluss lt. Anlage N → Abschluss
    cleaned = re.sub(r'^Abschluss\s+.*', 'Abschluss', cleaned)
    for key, mapped in BBBANK_TYPE_MAP.items():
        if cleaned.startswith(key):
            return mapped
    return "Sonstiges"


def guess_category(tx_type: str, payee: str) -> str:
    """Bestimmt Kategorie anhand Typ und erstem Empfängernamen."""
    combined = (payee or "").lower()
    for keywords, cat in MERCHANT_CATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            return cat
    return TYPE_CATEGORY_MAP.get(tx_type, "Sonstiges")


def is_footer_line(line: str) -> bool:
    """Zeile ist Teil der Seitenkopf/-fußzeile und wird ignoriert."""
    return bool(FOOTER_RE.match(line))


# ── PDF-Parser ─────────────────────────────────────────────────────────────────

class Transaction:
    __slots__ = ("bu_date", "wert_date", "tx_type", "amount", "sh",
                 "payee", "desc_lines", "stmt_nr", "stmt_year")

    def __init__(self, bu_date, wert_date, tx_type, amount, sh, stmt_nr, stmt_year):
        self.bu_date   = bu_date      # 'DD.MM.' raw
        self.wert_date = wert_date    # 'DD.MM.' raw
        self.tx_type   = tx_type      # normalized type
        self.amount    = amount       # Decimal, always positive
        self.sh        = sh           # 'S' or 'H'
        self.payee     = ""           # first description line
        self.desc_lines: list[str] = []
        self.stmt_nr   = stmt_nr
        self.stmt_year = stmt_year

    @property
    def signed_amount(self) -> Decimal:
        return -self.amount if self.sh == "S" else self.amount

    @property
    def full_description(self) -> str:
        return " | ".join(self.desc_lines) if self.desc_lines else ""


def parse_pdf(filepath: Path) -> list[Transaction]:
    """
    Liest alle Transaktionen aus einem BBBank-PDF.
    Ein PDF kann mehrere Monatsauszüge enthalten.
    """
    transactions: list[Transaction] = []
    current_tx: Optional[Transaction] = None
    stmt_nr = 0
    stmt_year = 0
    in_data_section = False

    def flush(tx: Optional[Transaction]):
        if tx is not None:
            transactions.append(tx)

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if not text:
                continue

            lines = text.splitlines()
            page_has_data = False

            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue

                # ── Kontoauszug-Header: Monat/Jahr aktualisieren ──────────────
                m = STMT_HEADER_RE.search(stripped)
                if m:
                    stmt_nr   = int(m.group(1))
                    stmt_year = int(m.group(2))
                    continue

                # ── Spalten-Header: ab hier kommen Transaktionen ─────────────
                if COLUMN_HDR.match(stripped):
                    in_data_section = True
                    page_has_data = True
                    continue

                if not in_data_section:
                    continue

                # ── Saldo- und Übertragszeilen ────────────────────────────────
                if OPEN_BAL_RE.match(stripped) or CLOSE_BAL_RE.match(stripped):
                    continue
                if CARRY_RE.match(stripped):
                    continue

                # ── Fußzeilen ─────────────────────────────────────────────────
                if is_footer_line(stripped):
                    continue

                # ── Transaktionsstart ─────────────────────────────────────────
                m = TX_RE.match(stripped)
                if m:
                    flush(current_tx)
                    bu_raw, wert_raw, vorgang_raw, betrag_raw, sh = m.groups()
                    tx_type = extract_tx_type(vorgang_raw)
                    amount  = parse_amount(betrag_raw)
                    current_tx = Transaction(
                        bu_date=bu_raw, wert_date=wert_raw,
                        tx_type=tx_type, amount=amount, sh=sh,
                        stmt_nr=stmt_nr, stmt_year=stmt_year,
                    )
                    continue

                # ── Beschreibungszeile zur aktuellen Transaktion ──────────────
                if current_tx is not None:
                    current_tx.desc_lines.append(stripped)
                    if not current_tx.payee:
                        current_tx.payee = stripped

            # Seite wechselt → data_section auf dieser Seite schließen
            in_data_section = False

    flush(current_tx)
    return transactions


# ── Datenbank-Helfer ───────────────────────────────────────────────────────────

CATEGORIES: list[dict] = [
    {"name": "Gehalt / Eingang",    "flow_type": "income"},
    {"name": "Lebensmittel",        "flow_type": "expense"},
    {"name": "Restaurant / Cafe",   "flow_type": "expense"},
    {"name": "Gesundheit",          "flow_type": "expense"},
    {"name": "Energie / Tanken",    "flow_type": "expense"},
    {"name": "Parkgebühren / KFZ",  "flow_type": "expense"},
    {"name": "Shopping",            "flow_type": "expense"},
    {"name": "Elektronik",          "flow_type": "expense"},
    {"name": "Transport",           "flow_type": "expense"},
    {"name": "Reise / Hotel",       "flow_type": "expense"},
    {"name": "Abonnements",         "flow_type": "expense"},
    {"name": "Telekommunikation",   "flow_type": "expense"},
    {"name": "Behörden / Steuern",  "flow_type": "expense"},
    {"name": "Wohnen / Hausgeld",   "flow_type": "expense"},
    {"name": "Miete",               "flow_type": "expense"},
    {"name": "Versicherung",        "flow_type": "expense"},
    {"name": "Bankgebühren",        "flow_type": "expense"},
    {"name": "Sonstiges",           "flow_type": "expense"},
    {"name": "Überweisung",         "flow_type": "transfer"},
]


class DB:
    def __init__(self, client: Optional[Client]):
        self.client = client
        self._account_id: Optional[str] = None
        self._categories: dict[str, str] = {}
        self._merchants: dict[str, str] = {}

    def get_or_create_account(self) -> str:
        if self._account_id:
            return self._account_id

        if DRY_RUN:
            self._account_id = "dry-bbbank"
            return self._account_id

        result = (
            self.client.table("accounts")
            .select("id")
            .eq("name", BBBANK_ACCOUNT["name"])
            .execute()
        )
        if result.data:
            self._account_id = result.data[0]["id"]
        else:
            ins = self.client.table("accounts").insert(BBBANK_ACCOUNT).execute()
            self._account_id = ins.data[0]["id"]
            print(f"  Konto angelegt: {BBBANK_ACCOUNT['name']}")

        return self._account_id

    def seed_categories(self):
        for cat in CATEGORIES:
            existing = (
                self.client.table("categories")
                .select("id")
                .eq("name", cat["name"])
                .execute()
            )
            if existing.data:
                self._categories[cat["name"]] = existing.data[0]["id"]
            else:
                ins = self.client.table("categories").insert(cat).execute()
                self._categories[cat["name"]] = ins.data[0]["id"]
        print(f"  {len(self._categories)} Kategorien bereit")

    def category_id(self, name: str) -> Optional[str]:
        return self._categories.get(name)

    def get_or_create_merchant(self, raw_name: str) -> str:
        if raw_name in self._merchants:
            return self._merchants[raw_name]

        if DRY_RUN:
            mid = f"dry-m-{raw_name[:12]}"
            self._merchants[raw_name] = mid
            return mid

        existing = (
            self.client.table("merchants")
            .select("id")
            .eq("raw_name", raw_name)
            .execute()
        )
        if existing.data:
            mid = existing.data[0]["id"]
        else:
            cat_name = "Sonstiges"
            combined = raw_name.lower()
            for keywords, cat in MERCHANT_CATEGORY_RULES:
                if any(kw in combined for kw in keywords):
                    cat_name = cat
                    break
            payload = {
                "raw_name":     raw_name,
                "display_name": raw_name,
                "category_id":  self.category_id(cat_name),
            }
            ins = self.client.table("merchants").insert(payload).execute()
            mid = ins.data[0]["id"]

        self._merchants[raw_name] = mid
        return mid

    def upsert_transaction(self, payload: dict) -> Optional[str]:
        """Gibt None zurück wenn bereits vorhanden (source_hash)."""
        src_hash = payload["source_hash"]

        if DRY_RUN:
            return f"dry-tx-{src_hash[:8]}"

        existing = (
            self.client.table("transactions")
            .select("id")
            .eq("source_hash", src_hash)
            .execute()
        )
        if existing.data:
            return None

        ins = self.client.table("transactions").insert(payload).execute()
        return ins.data[0]["id"]

    def log_import(self, filename: str, period_from, period_to,
                   rows_ok: int, rows_skip: int, rows_err: int):
        status = "success" if rows_err == 0 else ("partial" if rows_ok > 0 else "error")
        payload = {
            "filename":      filename,
            "file_type":     "pdf",
            "source_bank":   "BBBank",
            "period_from":   str(period_from) if period_from else None,
            "period_to":     str(period_to)   if period_to   else None,
            "rows_imported": rows_ok,
            "rows_skipped":  rows_skip,
            "status":        status,
            "errors":        {"error_count": rows_err} if rows_err else None,
        }
        if not DRY_RUN:
            self.client.table("import_log").insert(payload).execute()


# ── Haupt-Import ───────────────────────────────────────────────────────────────

def import_file(filepath: Path, db: DB) -> dict:
    filename = filepath.name
    print(f"\n{'-' * 60}")
    print(f"  {filename}")
    print(f"{'-' * 60}")

    transactions = parse_pdf(filepath)
    if not transactions:
        print("  Keine Transaktionen gefunden.")
        return {"ok": 0, "skip": 0, "err": 0}

    print(f"  {len(transactions)} Transaktionen geparst")

    account_id = db.get_or_create_account()
    ok = skip = err = 0
    period_from = period_to = None

    for tx in transactions:
        try:
            if not tx.stmt_year:
                print(f"  [WARNUNG] Kein Jahreskontext fuer Transaktion: {tx.bu_date} {tx.payee}")
                err += 1
                continue

            bu_iso   = parse_date(tx.bu_date,   tx.stmt_nr, tx.stmt_year)
            wert_iso = parse_date(tx.wert_date, tx.stmt_nr, tx.stmt_year)

            # Zeitraum tracken
            dt = date.fromisoformat(bu_iso)
            if period_from is None or dt < period_from:
                period_from = dt
            if period_to is None or dt > period_to:
                period_to = dt

            # Händler (nur bei Lastschrift und Überweisung sinnvoll)
            merchant_id = None
            if tx.payee and tx.tx_type in ("Lastschrift", "Euro-Überweisung", "Darlehen"):
                merchant_id = db.get_or_create_merchant(tx.payee)

            cat_name = guess_category(tx.tx_type, tx.payee)
            cat_id   = db.category_id(cat_name)

            full_desc = tx.full_description
            src_hash  = row_hash(filename, bu_iso, tx.amount, "EUR", full_desc)

            payload = {
                "account_id":       account_id,
                "transaction_type": tx.tx_type,
                "started_at":       bu_iso + "T00:00:00+00:00",
                "completed_at":     wert_iso + "T00:00:00+00:00",
                "description":      full_desc or None,
                "amount":           str(tx.signed_amount),
                "fee":              "0",
                "currency":         "EUR",
                "status":           "ABGESCHLOSSEN",
                "balance_after":    None,
                "merchant_id":      merchant_id,
                "category_id":      cat_id,
                "source_file":      filename,
                "source_hash":      src_hash,
            }

            tx_id = db.upsert_transaction(payload)
            if tx_id is None:
                skip += 1
            else:
                ok += 1

        except Exception as exc:
            print(f"  [FEHLER] {tx.bu_date} {tx.payee[:30] if tx.payee else ''}: {exc}")
            err += 1

    print(f"  Transaktionen : {ok:>4} neu | {skip:>4} uebersprungen | {err:>3} Fehler")

    db.log_import(filename, period_from, period_to, ok, skip, err)
    return {"ok": ok, "skip": skip, "err": err}


# ── Einstiegspunkt ─────────────────────────────────────────────────────────────

def main():
    if DRY_RUN:
        print("=" * 60)
        print("  DRY-RUN -- keine Datenbankänderungen")
        print("=" * 60)
        db = DB(None)
    else:
        if not SUPABASE_URL or not SUPABASE_KEY:
            sys.exit(
                "FEHLER: SUPABASE_URL und SUPABASE_SERVICE_KEY fehlen.\n"
                "Erstelle eine .env-Datei (siehe .env.example)."
            )
        client = create_client(SUPABASE_URL, SUPABASE_KEY)
        db = DB(client)

    print("\nKategorien laden / anlegen...")
    if not DRY_RUN:
        db.seed_categories()
    else:
        for cat in CATEGORIES:
            db._categories[cat["name"]] = f"dry-{cat['name'][:10]}"
        print(f"  {len(db._categories)} Kategorien (dry-run)")

    pdf_files = sorted(SCRIPT_DIR.glob("*Kontoauszug*.pdf"))
    if not pdf_files:
        # Fallback: alle PDFs ausser UBS
        pdf_files = sorted(
            f for f in SCRIPT_DIR.glob("*.pdf")
            if "UBS" not in f.name and "ubs" not in f.name.lower()
        )
    if not pdf_files:
        sys.exit("Keine BBBank-Kontoauszug-PDFs im Ordner gefunden.")

    print(f"\n{len(pdf_files)} PDF-Datei(en) gefunden:")
    for f in pdf_files:
        print(f"  - {f.name}")

    total = {"ok": 0, "skip": 0, "err": 0}
    for f in pdf_files:
        result = import_file(f, db)
        for k in total:
            total[k] += result[k]

    print(f"\n{'=' * 60}")
    print(
        f"  GESAMT  {total['ok']} importiert | "
        f"{total['skip']} uebersprungen | "
        f"{total['err']} Fehler"
    )
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
