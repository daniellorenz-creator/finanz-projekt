#!/usr/bin/env python3
"""
UBS Privatkonto CHF PDF Kontoauszug -> Supabase Import Script

Verarbeitet alle PDFs die 'UBS' im Dateinamen enthalten (Grossschreibung egal).
Ein PDF kann mehrere Monatsauszüge enthalten.

Verwendung:
  python import_ubs_pdf.py             # Live-Import
  python import_ubs_pdf.py --dry-run   # Vorschau ohne Datenbankänderungen

WICHTIG -- einmalig in Supabase SQL Editor ausführen, bevor der
Import läuft (fügt UBS-spezifische Typen zur CHECK-Constraint hinzu):

    ALTER TABLE transactions
    DROP CONSTRAINT IF EXISTS transactions_transaction_type_check;

    ALTER TABLE transactions
    ADD CONSTRAINT transactions_transaction_type_check
    CHECK (transaction_type IN (
        'Einzahlung','Umtausch','Kartenbezahlung','Transfer',
        'Rückerstattung','Geldautomat','Gebühr','Belastung','Sonstiges',
        'Lastschrift','Gutschrift','Euro-Überweisung','Darlehen','Abschluss',
        'Dauerauftrag','E-Banking-Auftrag'
    ));
"""

import hashlib
import os
import re
import sys
from dataclasses import dataclass, field
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

UBS_ACCOUNT = {
    "name":         "UBS Privatkonto CHF",
    "bank_name":    "UBS",
    "account_ref":  "CH20 0029 2292 1712 4740 H",
    "currency":     "CHF",
    "account_type": "giro",
}

# ── Transaktionstypen ─────────────────────────────────────────────────────────
# ALL-CAPS Typ aus PDF -> normalisierter DB-Typ
UBS_TYPE_MAP: dict[str, str] = {
    "LASTSCHRIFT":                         "Lastschrift",
    "DAUERAUFTRAG":                        "Dauerauftrag",
    "GUTSCHRIFT":                          "Gutschrift",
    "E-BANKING-AUFTRAG":                   "E-Banking-Auftrag",
    "PAYNET-AUFTRAG":                      "E-Banking-Auftrag",
    "SALDO DIENSTLEISTUNGSPREISABSCHLUSS": "Abschluss",
    "SALAEREINGANG":                       "Gutschrift",
    "VERGUETUNG":                          "Gutschrift",
}

# Diese Typen sind Eingänge (positive Beträge), alle anderen Ausgaben
CREDIT_TYPES = {"Gutschrift"}

TYPE_CATEGORY_MAP: dict[str, str] = {
    "Gutschrift":        "Gehalt / Eingang",
    "Lastschrift":       "Sonstiges",
    "Dauerauftrag":      "Überweisung",
    "E-Banking-Auftrag": "Überweisung",
    "Abschluss":         "Bankgebühren",
}

MERCHANT_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["apple", "mediamarkt", "galaxus", "pc high", "pc-high"],     "Elektronik"),
    (["bäckerei", "pizza", "restaurant", "cafe", "kaffi",
      "buffet", "grill"],                                           "Restaurant / Cafe"),
    (["sympany", "swica", "vivao", "allianz", "krankenvers",
      "apotheke", "tierarzt", "arzt", "labor", "klinik",
      "baloise", "axa versicherung"],                               "Gesundheit"),
    (["esso", "aral", "tankstelle", "naturenergie",
      "stadtwerke", "strom", "gas", "energie"],                     "Energie / Tanken"),
    (["parkhaus", "easypark", "motorfahrzeugkontrolle",
      "motorfahrzeug", "kfz"],                                      "Parkgebühren / KFZ"),
    (["coop", "migros", "aldi", "edeka", "rewe",
      "lidl", "netto", "dm drogerie"],                              "Lebensmittel"),
    (["amazon", "zalando", "ikea", "bauhaus", "ebay", "paypal"],   "Shopping"),
    (["telefonica", "o2", "telekom", "vodafone"],                   "Telekommunikation"),
    (["spotify", "netflix", "openai"],                              "Abonnements"),
    (["sbb", "deutsche bahn", "db regio", "mvg"],                   "Transport"),
    (["hotel", "booking.com", "airbnb"],                            "Reise / Hotel"),
    (["finanz", "steuerverwaltung", "steuerbezug",
      "finanzamt", "zollamt"],                                      "Behörden / Steuern"),
    (["hausgeld", "kommunalbauten", "wohnungseigentum"],             "Wohnen / Hausgeld"),
    (["miete", "ralph mueller", "mueller ralph"],                    "Miete"),
    (["mobiliere", "mobilier", "zuerich versicherung",
      "zurich versicherung", "schweizerische mobiliar"],            "Versicherung"),
    (["dienstleistungspreisabschluss", "ubs kundenkarte"],          "Bankgebühren"),
    (["staeubli", "staubli", "endress+hauser", "endress hauser"],   "Gehalt / Eingang"),
    (["revolut"],                                                    "Überweisung"),
]

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
    {"name": "Überweisung",         "flow_type": "transfer"},
    {"name": "Sonstiges",           "flow_type": "expense"},
]

# ── Regex-Muster ───────────────────────────────────────────────────────────────

# Kontoauszug-Periode: "01.01.2024 - 31.01.2024 / Monatlich..."
# oder Folgeseite: "Kontoauszug 01.01.2024-31.01.2024"
STMT_HEADER_RE = re.compile(
    r'\d{2}\.\d{2}\.(\d{4})\s*[-–]\s*\d{2}\.\d{2}\.\d{4}'
)

# Spalten-Header der Transaktionsliste
COLUMN_HDR_RE = re.compile(r'Datum\s+Informationen\s+Belastungen')

# Abschlusszeile der Transaktionsliste
UMSATZ_RE = re.compile(r'^Umsatztotal')

# Fusszeilen (außerhalb data_section werden sie sowieso ignoriert)
FOOTER_RE = re.compile(
    r'^(?:Formular ohne Unterschrift|GNZKOA[A-Z0-9])',
    re.IGNORECASE
)

# Transaktionszeile: DD.MM.YY TYP Betrag DD.MM.YY Kontostand
# Betrag im Schweizer Format: Leerzeichen als Tausender-Trennzeichen, Punkt als Dezimal
# Beispiele: "479.80", "3 110.40", "12 531.63"
TX_RE = re.compile(
    r'^(\d{2}\.\d{2}\.\d{2})'               # Bu-Datum
    r'\s+'
    r'([A-Z][A-Z\s\-]+?)'                   # Typ (ALL CAPS, lazy)
    r'\s+'
    r'(\d{1,3}(?:\s\d{3})*\.\d{2})'        # Betrag (CHF-Format)
    r'\s+'
    r'(\d{2}\.\d{2}\.\d{2})'               # Valuta
    r'\s+'
    r'(\d{1,3}(?:\s\d{3})*\.\d{2})'        # Kontostand
    r'\s*$'
)

# Zeilen die mit Datum beginnen, aber keine Transaktion sind (Anfangssaldo etc.)
DATE_START_RE = re.compile(r'^\d{2}\.\d{2}\.\d{2}\s+')


# ── Datenklasse ────────────────────────────────────────────────────────────────

@dataclass
class Transaction:
    bu_date:    str            # 'DD.MM.YY' roh
    wert_date:  str            # 'DD.MM.YY' roh
    tx_type:    str            # normalisierter DB-Typ
    amount:     Decimal        # immer positiv
    payee:      str = ""
    desc_lines: list[str] = field(default_factory=list)

    @property
    def signed_amount(self) -> Decimal:
        return self.amount if self.tx_type in CREDIT_TYPES else -self.amount

    @property
    def full_description(self) -> str:
        return " | ".join(self.desc_lines) if self.desc_lines else ""


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def row_hash(source_file: str, bu_date: str, amount: Decimal,
             currency: str, description: str) -> str:
    key = "|".join([source_file, bu_date, str(amount), currency, description[:80]])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def parse_amount(s: str) -> Decimal:
    """'3 110.40' -> Decimal('3110.40')  (Leerzeichen = Tausender-Trenner)"""
    return Decimal(s.replace(" ", ""))


def parse_date(dmy: str) -> str:
    """'15.01.24' -> '2024-01-15'"""
    m = re.match(r'(\d{2})\.(\d{2})\.(\d{2})', dmy)
    day, month, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return date(2000 + yy, month, day).isoformat()


def extract_tx_type(raw: str) -> str:
    return UBS_TYPE_MAP.get(raw.strip(), "Sonstiges")


def extract_payee(desc_lines: list[str]) -> str:
    """Ersten sinnvollen Empfängernamen aus den Beschreibungszeilen ermitteln.
    Überspringt UBS-interne Marker (OEB1W, INNERT, E-BILL)."""
    skip = re.compile(r'^(?:OEB1W|INNERT\s+\d|E-BILL\s*$)', re.IGNORECASE)
    for line in desc_lines:
        if not skip.match(line):
            return line
    return desc_lines[0] if desc_lines else ""


def guess_category(tx_type: str, payee: str) -> str:
    combined = (payee or "").lower()
    for keywords, cat in MERCHANT_CATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            return cat
    return TYPE_CATEGORY_MAP.get(tx_type, "Sonstiges")


# ── PDF-Parser ─────────────────────────────────────────────────────────────────

def parse_pdf(filepath: Path) -> list[Transaction]:
    """
    Liest alle Transaktionen aus einem UBS Privatkonto CHF PDF.
    Ein PDF kann mehrere Monatsauszüge enthalten.
    in_data_section wird pro Seite zurückgesetzt.
    """
    transactions: list[Transaction] = []
    current_tx: Optional[Transaction] = None

    def flush(tx: Optional[Transaction]):
        if tx is None:
            return
        if tx.desc_lines and not tx.payee:
            tx.payee = extract_payee(tx.desc_lines)
        transactions.append(tx)

    with pdfplumber.open(filepath) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2, y_tolerance=3)
            if not text:
                continue

            in_data_section = False  # pro Seite zurücksetzen

            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue

                # Fusszeilen immer ignorieren
                if FOOTER_RE.match(stripped):
                    continue

                # Spalten-Header: ab hier kommen Transaktionen
                if COLUMN_HDR_RE.match(stripped):
                    in_data_section = True
                    continue

                if not in_data_section:
                    continue

                # Ende der Transaktionsliste
                if UMSATZ_RE.match(stripped):
                    in_data_section = False
                    continue

                # Transaktionszeile
                m = TX_RE.match(stripped)
                if m:
                    flush(current_tx)
                    bu_raw, type_raw, amount_raw, wert_raw, _balance = m.groups()
                    current_tx = Transaction(
                        bu_date=bu_raw,
                        wert_date=wert_raw,
                        tx_type=extract_tx_type(type_raw),
                        amount=parse_amount(amount_raw),
                    )
                    continue

                # Zeilen mit Datumsprefix die keine Transaktion sind
                # (Anfangssaldo, Schlusssaldo) → überspringen
                if DATE_START_RE.match(stripped):
                    continue

                # Beschreibungszeile zur aktuellen Transaktion
                if current_tx is not None:
                    current_tx.desc_lines.append(stripped)

    flush(current_tx)
    return transactions


# ── Datenbank-Helfer ───────────────────────────────────────────────────────────

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
            self._account_id = "dry-ubs"
            return self._account_id
        result = (
            self.client.table("accounts")
            .select("id")
            .eq("name", UBS_ACCOUNT["name"])
            .execute()
        )
        if result.data:
            self._account_id = result.data[0]["id"]
        else:
            ins = self.client.table("accounts").insert(UBS_ACCOUNT).execute()
            self._account_id = ins.data[0]["id"]
            print(f"  Konto angelegt: {UBS_ACCOUNT['name']}")
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
            cat_name = guess_category("Lastschrift", raw_name)
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
            "source_bank":   "UBS",
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
            bu_iso   = parse_date(tx.bu_date)
            wert_iso = parse_date(tx.wert_date)

            dt = date.fromisoformat(bu_iso)
            if period_from is None or dt < period_from:
                period_from = dt
            if period_to is None or dt > period_to:
                period_to = dt

            merchant_id = None
            if tx.payee and tx.tx_type in ("Lastschrift", "Dauerauftrag", "E-Banking-Auftrag"):
                merchant_id = db.get_or_create_merchant(tx.payee)

            cat_name = guess_category(tx.tx_type, tx.payee)
            cat_id   = db.category_id(cat_name)

            full_desc = tx.full_description
            src_hash  = row_hash(filename, bu_iso, tx.amount, "CHF", full_desc)

            payload = {
                "account_id":       account_id,
                "transaction_type": tx.tx_type,
                "started_at":       bu_iso + "T00:00:00+00:00",
                "completed_at":     wert_iso + "T00:00:00+00:00",
                "description":      full_desc or None,
                "amount":           str(tx.signed_amount),
                "fee":              "0",
                "currency":         "CHF",
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
            print(f"  [FEHLER] {tx.bu_date} {tx.tx_type}: {exc}")
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

    pdf_files = sorted(
        f for f in SCRIPT_DIR.glob("*.pdf")
        if re.search(r'UBS', f.name, re.IGNORECASE) and "Kontoauszug" not in f.name
        or re.match(r'0292000017124740H0000_Kontoauszug_', f.name)
    )
    if not pdf_files:
        sys.exit("Keine UBS PDFs im Ordner gefunden.")

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
