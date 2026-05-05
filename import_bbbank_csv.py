#!/usr/bin/env python3
"""
BBBank CSV-Kontoauszug → Supabase Import Script
Verarbeitet alle Umsaetze_DE*.csv-Dateien im gleichen Ordner.

Verwendung:
  python import_bbbank_csv.py             # Live-Import
  python import_bbbank_csv.py --dry-run   # Vorschau ohne Datenbankänderungen
"""

import csv
import hashlib
import os
import sys
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
DRY_RUN = "--dry-run" in sys.argv
SCRIPT_DIR = Path(__file__).parent

BBBANK_ACCOUNT = {
    "name":         "BBBank EUR",
    "bank_name":    "BBBank",
    "account_ref":  "DE50 6609 0800 0009 5059 20",
    "currency":     "EUR",
    "account_type": "giro",
}

BBBANK_TYPE_MAP: dict[str, str] = {
    "Gutschrift":          "Gutschrift",
    "Da-Gutschrift":       "Gutschrift",
    "Lastschrift":         "Lastschrift",
    "Euro-Überweisung":    "Euro-Überweisung",
    "Überweisung":         "Euro-Überweisung",
    "Darlehen":            "Darlehen",
    "Abschluss":           "Abschluss",
    "Entgelt":             "Abschluss",
    "Auszahlung girocard": "Geldautomat",
    "Auszahlung":          "Geldautomat",
}

TYPE_CATEGORY_MAP: dict[str, str] = {
    "Gutschrift":       "Gehalt / Eingang",
    "Lastschrift":      "Sonstiges",
    "Euro-Überweisung": "Überweisung",
    "Darlehen":         "Überweisung",
    "Abschluss":        "Bankgebühren",
    "Geldautomat":      "Sonstiges",
}

MERCHANT_CATEGORY_RULES: list[tuple[list[str], str]] = [
    (["apple", "mediamarkt", "galaxus"],                          "Elektronik"),
    (["bäckerei", "pizza", "restaurant", "cafe", "kaffi",
      "buffet", "gourmets", "siam thai", "grill"],                "Restaurant / Cafe"),
    (["allianz", "dkv", "krankenvers", "apotheke",
      "tierarzt", "arzt", "labor", "klinik", "optiker"],          "Gesundheit"),
    (["esso", "aral", "tankstelle", "naturenergie",
      "stadtwerke", "strom", "gas", "energie"],                   "Energie / Tanken"),
    (["parkhaus", "easypark", "parking", "kfz"],                  "Parkgebühren / KFZ"),
    (["coop", "migros", "aldi", "edeka", "rewe", "lidl",
      "netto", "penny", "dm drogerie", "rossmann", "kaufland"],   "Lebensmittel"),
    (["amazon", "zalando", "ikea", "bauhaus", "ebay", "paypal",
      "kleinanzeigen"],                                            "Shopping"),
    (["telefonica", "o2", "telekom", "vodafone"],                  "Telekommunikation"),
    (["spotify", "netflix", "prime video",
      "amazon digital", "openai"],                                 "Abonnements"),
    (["deutsche bahn", "db regio", "mvg", "rnv", "vag"],          "Transport"),
    (["hotel", "booking.com", "airbnb"],                           "Reise / Hotel"),
    (["bundesamt", "finanzamt", "gemeinde", "landkreis",
      "stadtkasse", "zollamt", "kreiskasse"],                      "Behörden / Steuern"),
    (["hausgeld", "kommunalbauten", "wohnungseigentum",
      "wohnungsverwaltung"],                                       "Wohnen / Hausgeld"),
    (["miete", "mietrecht"],                                       "Miete"),
    (["vhv", "versicherung", "bhw"],                               "Versicherung"),
    (["abschluss", "zinsen", "entgelt"],                           "Bankgebühren"),
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
    {"name": "Sonstiges",           "flow_type": "expense"},
    {"name": "Überweisung",         "flow_type": "transfer"},
]


def parse_date(s: str) -> str:
    """'30.04.2026' → '2026-04-30'"""
    d, m, y = s.strip().split(".")
    return date(int(y), int(m), int(d)).isoformat()


def parse_amount(s: str) -> Optional[Decimal]:
    if not s or not s.strip():
        return None
    try:
        return Decimal(s.strip().replace(".", "").replace(",", "."))
    except InvalidOperation:
        return None


def normalize_type(raw: str) -> str:
    raw = raw.strip()
    for key, mapped in BBBANK_TYPE_MAP.items():
        if raw.startswith(key):
            return mapped
    return "Sonstiges"


def guess_category(tx_type: str, payee: str, purpose: str) -> str:
    combined = (payee + " " + purpose).lower()
    for keywords, cat in MERCHANT_CATEGORY_RULES:
        if any(kw in combined for kw in keywords):
            return cat
    return TYPE_CATEGORY_MAP.get(tx_type, "Sonstiges")


def row_hash(source_file: str, bu_date: str, amount: Decimal,
             payee: str, purpose: str) -> str:
    key = "|".join([source_file, bu_date, str(amount), payee[:60], purpose[:80]])
    return hashlib.sha256(key.encode()).hexdigest()[:32]


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
        result = self.client.table("accounts").select("id").eq("name", BBBANK_ACCOUNT["name"]).execute()
        if result.data:
            self._account_id = result.data[0]["id"]
        else:
            ins = self.client.table("accounts").insert(BBBANK_ACCOUNT).execute()
            self._account_id = ins.data[0]["id"]
            print(f"  Konto angelegt: {BBBANK_ACCOUNT['name']}")
        return self._account_id

    def seed_categories(self):
        for cat in CATEGORIES:
            existing = self.client.table("categories").select("id").eq("name", cat["name"]).execute()
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
        existing = self.client.table("merchants").select("id").eq("raw_name", raw_name).execute()
        if existing.data:
            mid = existing.data[0]["id"]
        else:
            cat_name = "Sonstiges"
            for keywords, cat in MERCHANT_CATEGORY_RULES:
                if any(kw in raw_name.lower() for kw in keywords):
                    cat_name = cat
                    break
            ins = self.client.table("merchants").insert({
                "raw_name":     raw_name,
                "display_name": raw_name,
                "category_id":  self.category_id(cat_name),
            }).execute()
            mid = ins.data[0]["id"]
        self._merchants[raw_name] = mid
        return mid

    def upsert_transaction(self, payload: dict) -> Optional[str]:
        src_hash = payload["source_hash"]
        if DRY_RUN:
            return f"dry-tx-{src_hash[:8]}"
        existing = self.client.table("transactions").select("id").eq("source_hash", src_hash).execute()
        if existing.data:
            return None
        ins = self.client.table("transactions").insert(payload).execute()
        return ins.data[0]["id"]

    def log_import(self, filename: str, period_from, period_to,
                   rows_ok: int, rows_skip: int, rows_err: int):
        status = "success" if rows_err == 0 else ("partial" if rows_ok > 0 else "error")
        payload = {
            "filename":      filename,
            "file_type":     "csv",
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


def parse_csv(filepath: Path) -> list[dict]:
    rows = []
    with open(filepath, encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f, delimiter=";")
        for i, raw in enumerate(reader, start=2):
            rows.append({
                "_row":       i,
                "bu_date":    raw.get("Buchungstag", "").strip(),
                "wert_date":  raw.get("Valutadatum", "").strip(),
                "payee":      raw.get("Name Zahlungsbeteiligter", "").strip(),
                "tx_type_raw": raw.get("Buchungstext", "").strip(),
                "purpose":    raw.get("Verwendungszweck", "").strip(),
                "amount_raw": raw.get("Betrag", "").strip(),
                "currency":   raw.get("Waehrung", "EUR").strip(),
                "balance_raw": raw.get("Saldo nach Buchung", "").strip(),
            })
    return rows


def import_file(filepath: Path, db: DB) -> dict:
    filename = filepath.name
    print(f"\n{'-' * 60}")
    print(f"  {filename}")
    print(f"{'-' * 60}")

    rows = parse_csv(filepath)
    print(f"  {len(rows)} Zeilen gelesen")

    account_id = db.get_or_create_account()
    ok = skip = err = 0
    period_from = period_to = None

    for row in rows:
        try:
            amount = parse_amount(row["amount_raw"])
            if amount is None:
                print(f"  [WARNUNG] Zeile {row['_row']}: Betrag nicht lesbar, übersprungen")
                err += 1
                continue

            bu_iso   = parse_date(row["bu_date"])
            wert_iso = parse_date(row["wert_date"]) if row["wert_date"] else bu_iso

            dt = date.fromisoformat(bu_iso)
            if period_from is None or dt < period_from:
                period_from = dt
            if period_to is None or dt > period_to:
                period_to = dt

            tx_type  = normalize_type(row["tx_type_raw"])
            payee    = row["payee"]
            purpose  = row["purpose"]

            merchant_id = None
            if payee and tx_type in ("Lastschrift", "Euro-Überweisung", "Gutschrift",
                                     "Darlehen", "Geldautomat"):
                merchant_id = db.get_or_create_merchant(payee)

            cat_name = guess_category(tx_type, payee, purpose)
            cat_id   = db.category_id(cat_name)

            description = " | ".join(filter(None, [payee, purpose])) or None
            balance     = parse_amount(row["balance_raw"])
            src_hash    = row_hash(filename, bu_iso, amount, payee, purpose)

            payload = {
                "account_id":       account_id,
                "transaction_type": tx_type,
                "started_at":       bu_iso + "T00:00:00+00:00",
                "completed_at":     wert_iso + "T00:00:00+00:00",
                "description":      description,
                "amount":           str(amount),
                "fee":              "0",
                "currency":         row["currency"],
                "status":           "ABGESCHLOSSEN",
                "balance_after":    str(balance) if balance is not None else None,
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
            print(f"  [FEHLER] Zeile {row['_row']}: {exc}")
            err += 1

    print(f"  Transaktionen : {ok:>4} neu | {skip:>4} übersprungen | {err:>3} Fehler")
    db.log_import(filename, period_from, period_to, ok, skip, err)
    return {"ok": ok, "skip": skip, "err": err}


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

    csv_files = sorted(SCRIPT_DIR.glob("Umsaetze_DE*.csv"))
    if not csv_files:
        sys.exit("Keine Umsaetze_DE*.csv-Dateien im Ordner gefunden.")

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
