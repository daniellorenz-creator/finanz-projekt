#!/usr/bin/env python3
"""
Revolut CSV → Supabase Import Script
Verarbeitet alle account-statement_*.csv aus dem gleichen Ordner.

Verwendung:
  python import_csv.py             # Live-Import
  python import_csv.py --dry-run   # Vorschau ohne Datenbankänderungen
"""

import csv
import hashlib
import os
import sys
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

# ── Umgebung laden ─────────────────────────────────────────────────────────────
load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DRY_RUN = "--dry-run" in sys.argv
SCRIPT_DIR = Path(__file__).parent


# ── Konto-Definitionen (Revolut Multi-Currency-Wallets) ───────────────────────
REVOLUT_ACCOUNTS: dict[str, dict] = {
    "CHF": {"name": "Revolut CHF", "bank_name": "Revolut", "currency": "CHF", "account_type": "wallet"},
    "EUR": {"name": "Revolut EUR", "bank_name": "Revolut", "currency": "EUR", "account_type": "wallet"},
    "USD": {"name": "Revolut USD", "bank_name": "Revolut", "currency": "USD", "account_type": "wallet"},
    "CAD": {"name": "Revolut CAD", "bank_name": "Revolut", "currency": "CAD", "account_type": "wallet"},
}

# ── Kategorien ─────────────────────────────────────────────────────────────────
CATEGORIES: list[dict] = [
    {"name": "Gehalt / Eingang",  "flow_type": "income"},
    {"name": "Lebensmittel",      "flow_type": "expense"},
    {"name": "Restaurant / Cafe", "flow_type": "expense"},
    {"name": "Gesundheit",        "flow_type": "expense"},
    {"name": "Tanken",            "flow_type": "expense"},
    {"name": "Parkgebühren",      "flow_type": "expense"},
    {"name": "Shopping",          "flow_type": "expense"},
    {"name": "Elektronik",        "flow_type": "expense"},
    {"name": "Transport",         "flow_type": "expense"},
    {"name": "Reise / Hotel",     "flow_type": "expense"},
    {"name": "Abonnements",       "flow_type": "expense"},
    {"name": "Zoll / Behörden",   "flow_type": "expense"},
    {"name": "Bankgebühren",      "flow_type": "expense"},
    {"name": "Sonstiges",         "flow_type": "expense"},
    {"name": "Währungstausch",    "flow_type": "exchange"},
    {"name": "Überweisung",       "flow_type": "transfer"},
]

# Händler-Schlüsselwörter → Kategorie (Reihenfolge ist wichtig: spezifischere zuerst)
MERCHANT_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (
        ["apple store", "mediamarkt", "galaxus"],
        "Elektronik",
    ),
    (
        ["bäckerei", "dorfbäckerei", "pizza", "restaurant", "kaffi", "bucheli",
         "buffet", "gourmets", "elvetino", "sv group", "angolo dolce", "lindt",
         "purdys", "wbz canteen", "siam thai", "grill", "troika", "new york fries",
         "hundert13", "muzio guido", "tapeó", "gastrosolutions", "marché",
         "toilet lounge", "acqra"],
        "Restaurant / Cafe",
    ),
    (
        ["apotheke", "tierarzt", "kleintierklinik", "volksversand"],
        "Gesundheit",
    ),
    (
        ["esso", "aral", "tankstelle", "union-tankhof", "sprit shop", "tc2000",
         "coop tankstelle"],
        "Tanken",
    ),
    (
        ["parkhaus", "parkhäuser", "easypark", "parking", "parké", "opéra"],
        "Parkgebühren",
    ),
    (
        ["coop", "migros", "aldi", "edeka", "mix markt", "whole foods",
         "rossmann", "miran food"],
        "Lebensmittel",
    ),
    (
        ["amazon", "zalando", "ikea", "bauhaus", "baywa", "metz mueller",
         "bonacelli", "hakade", "blumen", "babyone", "mein style",
         "dm drogerie", "pssst", "boutique", "wal villa", "mountain equipment",
         "carters", "rainer.eckl", "läderach", "gamestop", "ebay"],
        "Shopping",
    ),
    (
        ["openai", "spotify"],
        "Abonnements",
    ),
    (
        ["premium abo"],
        "Bankgebühren",
    ),
    (
        ["sbb", "deutsche bahn", "swiss post", "kiosk autogrill", "jet"],
        "Transport",
    ),
    (
        ["hotel", "booking.com", "park royal"],
        "Reise / Hotel",
    ),
    (
        ["bazg", "bundesamt für zoll", "zollamt", "gemeinde birsfelden",
         "bundesamt für justiz", "citizenimm", "pädagogische hochschule",
         "farnsburg"],
        "Zoll / Behörden",
    ),
]

# Transaktionstyp → Fallback-Kategorie (wenn kein Händler-Match)
TYPE_CATEGORY_MAP: dict[str, str] = {
    "Einzahlung":     "Gehalt / Eingang",
    "Umtausch":       "Währungstausch",
    "Transfer":       "Überweisung",
    "Rückerstattung": "Sonstiges",
    "Geldautomat":    "Sonstiges",
    "Gebühr":         "Bankgebühren",
    "Belastung":      "Bankgebühren",
}

VALID_TYPES = frozenset(TYPE_CATEGORY_MAP) | {"Kartenbezahlung"}


# ── Hilfsfunktionen ────────────────────────────────────────────────────────────

def row_hash(source_file: str, row: dict) -> str:
    """Deterministischer 32-Zeichen-Hash für Idempotenz beim Reimport."""
    key = "|".join([
        source_file,
        row.get("started_at", ""),
        str(row.get("amount", "")),
        row.get("currency", ""),
        row.get("description", ""),
    ])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


def parse_amount(s: str) -> Optional[Decimal]:
    if not s or not s.strip():
        return None
    try:
        return Decimal(s.strip().replace(",", "."))
    except InvalidOperation:
        return None


def parse_dt(s: str) -> Optional[str]:
    """'2024-01-03 09:13:20'  →  '2024-01-03T09:13:20+00:00'"""
    if not s or not s.strip():
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d %H:%M:%S").isoformat() + "+00:00"
    except ValueError:
        return None


def normalize_type(raw: str) -> str:
    """Bereinigt 'Geldautomat:' → 'Geldautomat'."""
    t = raw.strip().rstrip(":")
    return t if t in VALID_TYPES else "Sonstiges"


def guess_category(tx_type: str, description: str) -> str:
    """Bestimmt die Kategorie anhand Transaktionstyp und Händlerbeschreibung."""
    if tx_type in TYPE_CATEGORY_MAP:
        return TYPE_CATEGORY_MAP[tx_type]
    desc_lower = description.lower()
    for keywords, cat in MERCHANT_CATEGORY_RULES:
        if any(kw in desc_lower for kw in keywords):
            return cat
    return "Sonstiges"


def guess_merchant_category(name: str) -> str:
    name_lower = name.lower()
    for keywords, cat in MERCHANT_CATEGORY_RULES:
        if any(kw in name_lower for kw in keywords):
            return cat
    return "Sonstiges"


# ── Datenbank-Helfer ───────────────────────────────────────────────────────────

class DB:
    def __init__(self, client: Client):
        self.client = client
        self._accounts: dict[str, str] = {}   # currency → uuid
        self._categories: dict[str, str] = {} # name → uuid
        self._merchants: dict[str, str] = {}  # raw_name → uuid

    # ── Konten ────────────────────────────────────────────────────────────────
    def get_or_create_account(self, currency: str) -> str:
        if currency in self._accounts:
            return self._accounts[currency]

        if DRY_RUN:
            self._accounts[currency] = f"dry-{currency}"
            return self._accounts[currency]

        info = REVOLUT_ACCOUNTS.get(currency, {
            "name": f"Revolut {currency}",
            "bank_name": "Revolut",
            "currency": currency,
            "account_type": "wallet",
        })
        result = (
            self.client.table("accounts")
            .select("id")
            .eq("name", info["name"])
            .execute()
        )
        if result.data:
            acc_id = result.data[0]["id"]
        else:
            ins = self.client.table("accounts").insert(info).execute()
            acc_id = ins.data[0]["id"]
            print(f"  Konto angelegt: {info['name']}")

        self._accounts[currency] = acc_id
        return acc_id

    # ── Kategorien ────────────────────────────────────────────────────────────
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

    # ── Händler ───────────────────────────────────────────────────────────────
    def get_or_create_merchant(self, raw_name: str) -> str:
        if raw_name in self._merchants:
            return self._merchants[raw_name]

        if DRY_RUN:
            mid = f"dry-merchant-{raw_name[:12]}"
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
            cat_name = guess_merchant_category(raw_name)
            payload = {
                "raw_name":     raw_name,
                "display_name": raw_name,
                "category_id":  self.category_id(cat_name),
            }
            ins = self.client.table("merchants").insert(payload).execute()
            mid = ins.data[0]["id"]

        self._merchants[raw_name] = mid
        return mid

    # ── Währungstausch ────────────────────────────────────────────────────────
    def create_exchange(self, payload: dict) -> str:
        if DRY_RUN:
            return "dry-exchange"
        ins = self.client.table("currency_exchanges").insert(payload).execute()
        return ins.data[0]["id"]

    def link_exchange(self, tx_id: str, exchange_id: str):
        if not DRY_RUN:
            self.client.table("transactions").update(
                {"exchange_id": exchange_id}
            ).eq("id", tx_id).execute()

    # ── Transaktion ───────────────────────────────────────────────────────────
    def upsert_transaction(self, payload: dict) -> Optional[str]:
        """Idempotent: überspringt bereits vorhandene Zeilen (gleicher source_hash)."""
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
            return None  # bereits vorhanden

        ins = self.client.table("transactions").insert(payload).execute()
        return ins.data[0]["id"]

    # ── Import-Log ────────────────────────────────────────────────────────────
    def log_import(self, filename: str, period_from, period_to,
                   rows_ok: int, rows_skip: int, rows_err: int):
        status = "success" if rows_err == 0 else ("partial" if rows_ok > 0 else "error")
        payload = {
            "filename":      filename,
            "file_type":     "csv",
            "source_bank":   "Revolut",
            "period_from":   str(period_from) if period_from else None,
            "period_to":     str(period_to)   if period_to   else None,
            "rows_imported": rows_ok,
            "rows_skipped":  rows_skip,
            "status":        status,
            "errors":        {"error_count": rows_err} if rows_err else None,
        }
        if not DRY_RUN:
            self.client.table("import_log").insert(payload).execute()


# ── CSV-Parsing ────────────────────────────────────────────────────────────────

def parse_csv(filepath: Path) -> list[dict]:
    rows = []
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for i, raw in enumerate(reader, start=2):
            tx_type = normalize_type(raw.get("Art", ""))
            amount  = parse_amount(raw.get("Betrag", "")) or Decimal("0")
            fee     = parse_amount(raw.get("Gebühr", "")) or Decimal("0")

            # Sonderfall Belastung: Betrag=0, Gebühr=echter Wert
            if tx_type == "Belastung" and amount == 0 and fee > 0:
                amount = -fee
                fee = Decimal("0")

            balance_str = raw.get("Kontostand", "").strip()
            completed_str = raw.get("Datum des Abschlusses", "").strip()

            rows.append({
                "_row":        i,
                "type":        tx_type,
                "started_at":  raw.get("Datum des Beginns", "").strip(),
                "completed_at": completed_str,
                "description": raw.get("Beschreibung", "").strip(),
                "amount":      amount,
                "fee":         fee,
                "currency":    raw.get("Währung", "").strip(),
                "status":      raw.get("Status", "").strip(),
                "balance_after": parse_amount(balance_str),
            })
    return rows


# ── Haupt-Import ───────────────────────────────────────────────────────────────

def import_file(filepath: Path, db: DB) -> dict:
    filename = filepath.name
    print(f"\n{'-' * 60}")
    print(f"  {filename}")
    print(f"{'-' * 60}")

    rows = parse_csv(filepath)
    print(f"  {len(rows)} Zeilen gelesen")

    ok = skip = err = 0
    period_from = period_to = None

    # Umtausch-Kandidaten für späteres Paar-Matching:
    # started_at_str → list[{tx_id, currency, amount, account_id}]
    exchange_candidates: dict[str, list[dict]] = defaultdict(list)

    # ── 1. Alle Transaktionen importieren ─────────────────────────────────────
    for row in rows:
        try:
            currency   = row["currency"]
            tx_type    = row["type"]
            description = row["description"]
            account_id = db.get_or_create_account(currency)

            # Händler nur bei Karten-/Bargeldzahlungen
            merchant_id = None
            if tx_type in ("Kartenbezahlung", "Geldautomat") and description:
                merchant_id = db.get_or_create_merchant(description)

            cat_name = guess_category(tx_type, description)
            cat_id   = db.category_id(cat_name)

            # Zeitraum tracken
            if row["started_at"]:
                dt = datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M:%S").date()
                if period_from is None or dt < period_from:
                    period_from = dt
                if period_to is None or dt > period_to:
                    period_to = dt

            src_hash = row_hash(filename, row)

            payload = {
                "account_id":       account_id,
                "transaction_type": tx_type,
                "started_at":       parse_dt(row["started_at"]),
                "completed_at":     parse_dt(row["completed_at"]),
                "description":      description or None,
                "amount":           str(row["amount"]),
                "fee":              str(row["fee"]),
                "currency":         currency,
                "status":           row["status"],
                "balance_after":    str(row["balance_after"]) if row["balance_after"] is not None else None,
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
                if tx_type == "Umtausch":
                    exchange_candidates[row["started_at"]].append({
                        "tx_id":      tx_id,
                        "currency":   currency,
                        "amount":     row["amount"],
                        "account_id": account_id,
                        "started_at": row["started_at"],
                    })

        except Exception as exc:
            print(f"  [FEHLER] Zeile {row['_row']}: {exc}")
            err += 1

    # ── 2. Umtausch-Paare verknüpfen ──────────────────────────────────────────
    exchanges_linked = 0
    for ts, candidates in exchange_candidates.items():
        # Suche: eine ausgehende (negativ) + eine eingehende (positiv) Seite
        from_side = next((c for c in candidates if c["amount"] < 0), None)
        to_side   = next((c for c in candidates if c["amount"] > 0), None)

        if not (from_side and to_side):
            continue

        from_amt = abs(from_side["amount"])
        to_amt   = to_side["amount"]
        rate = (to_amt / from_amt).quantize(Decimal("0.000001")) if from_amt else None

        exchange_payload = {
            "account_id":    from_side["account_id"],
            "from_currency": from_side["currency"],
            "to_currency":   to_side["currency"],
            "from_amount":   str(from_amt),
            "to_amount":     str(to_amt),
            "exchange_rate": str(rate) if rate else None,
            "exchanged_at":  parse_dt(from_side["started_at"]),
            "fee":           "0",
        }
        try:
            exchange_id = db.create_exchange(exchange_payload)
            db.link_exchange(from_side["tx_id"], exchange_id)
            db.link_exchange(to_side["tx_id"],   exchange_id)
            exchanges_linked += 1
        except Exception as exc:
            print(f"  [Exchange-Fehler] {ts}: {exc}")

    print(f"  Transaktionen : {ok:>4} neu | {skip:>4} übersprungen | {err:>3} Fehler")
    print(f"  Tausch-Paare  : {exchanges_linked:>4} verknüpft")

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

    print("\nKategorien laden / anlegen…")
    if not DRY_RUN:
        db.seed_categories()
    else:
        for cat in CATEGORIES:
            db._categories[cat["name"]] = f"dry-{cat['name'][:10]}"
        print(f"  {len(db._categories)} Kategorien (dry-run)")

    csv_files = sorted(SCRIPT_DIR.glob("account-statement_*.csv"))
    if not csv_files:
        sys.exit("Keine account-statement_*.csv-Dateien im Ordner gefunden.")

    print(f"\n{len(csv_files)} CSV-Datei(en) gefunden:")
    for f in csv_files:
        print(f"  - {f.name}")

    total = {"ok": 0, "skip": 0, "err": 0}
    for f in csv_files:
        result = import_file(f, db)
        for k in total:
            total[k] += result[k]

    print(f"\n{'=' * 60}")
    print(
        f"  GESAMT  {total['ok']} importiert | "
        f"{total['skip']} übersprungen | "
        f"{total['err']} Fehler"
    )
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    main()
