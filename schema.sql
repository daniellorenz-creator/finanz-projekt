-- ============================================================
-- Supabase Schema – Finanzdaten (Revolut + UBS + Raiffeisen)
-- ============================================================

-- 1. KONTEN
-- ─────────────────────────────────────────────────────────────
CREATE TABLE accounts (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name         TEXT        NOT NULL,          -- "Revolut CHF", "UBS", ...
  bank_name    TEXT,                          -- "Revolut", "UBS", "Raiffeisen"
  account_ref  TEXT,                          -- Kontonummer (maskiert)
  currency     TEXT        NOT NULL,          -- "CHF", "EUR", "USD", "CAD"
  account_type TEXT        DEFAULT 'wallet',  -- "wallet", "giro", "savings"
  is_active    BOOLEAN     DEFAULT TRUE,
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 2. KATEGORIEN (hierarchisch)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE categories (
  id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  name       TEXT        NOT NULL,
  parent_id  UUID        REFERENCES categories(id),
  flow_type  TEXT        NOT NULL CHECK (flow_type IN ('income','expense','exchange','transfer')),
  icon       TEXT,
  color      TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- 3. HÄNDLER
-- ─────────────────────────────────────────────────────────────
CREATE TABLE merchants (
  id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  raw_name     TEXT        NOT NULL UNIQUE,   -- Originalname aus CSV/PDF
  display_name TEXT,                          -- bereinigter Anzeigename
  category_id  UUID        REFERENCES categories(id),
  country_code TEXT,                          -- "CH", "DE", "CA", ...
  created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 4. WÄHRUNGSTAUSCH
-- ─────────────────────────────────────────────────────────────
CREATE TABLE currency_exchanges (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id    UUID        NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
  from_currency TEXT        NOT NULL,         -- "CHF"
  to_currency   TEXT        NOT NULL,         -- "EUR"
  from_amount   NUMERIC(15,2) NOT NULL,
  to_amount     NUMERIC(15,2),
  exchange_rate NUMERIC(15,6),                -- berechnet: to_amount / from_amount
  exchanged_at  TIMESTAMPTZ NOT NULL,
  fee           NUMERIC(15,2) DEFAULT 0,
  created_at    TIMESTAMPTZ DEFAULT NOW()
);

-- 5. TRANSAKTIONEN (zentrale Tabelle)
-- ─────────────────────────────────────────────────────────────
CREATE TABLE transactions (
  id               UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id       UUID        NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,

  -- Zeitstempel
  started_at       TIMESTAMPTZ NOT NULL,
  completed_at     TIMESTAMPTZ,

  -- Typ & Status
  transaction_type TEXT        NOT NULL CHECK (transaction_type IN (
    'Einzahlung','Umtausch','Kartenbezahlung','Transfer',
    'Rückerstattung','Geldautomat','Gebühr','Belastung','Sonstiges'
  )),
  status           TEXT        NOT NULL CHECK (status IN ('ABGESCHLOSSEN','STORNIERT')),

  -- Beträge (negativ = Ausgabe)
  amount           NUMERIC(15,2) NOT NULL,
  fee              NUMERIC(15,2) DEFAULT 0,
  currency         TEXT        NOT NULL,
  balance_after    NUMERIC(15,2),             -- NULL wenn STORNIERT

  -- Verknüpfungen
  description      TEXT,                      -- Originaltext aus Quelle
  merchant_id      UUID        REFERENCES merchants(id),
  category_id      UUID        REFERENCES categories(id),
  exchange_id      UUID        REFERENCES currency_exchanges(id),

  -- Import-Nachvollziehbarkeit
  source_file      TEXT,                      -- Dateiname der Quelle
  source_hash      TEXT        UNIQUE,        -- SHA-256 für Idempotenz

  created_at       TIMESTAMPTZ DEFAULT NOW()
);

-- 6. IMPORT-LOG
-- ─────────────────────────────────────────────────────────────
CREATE TABLE import_log (
  id            UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
  filename      TEXT        NOT NULL,
  file_type     TEXT        CHECK (file_type IN ('csv','pdf')),
  source_bank   TEXT,
  period_from   DATE,
  period_to     DATE,
  rows_imported INT         DEFAULT 0,
  rows_skipped  INT         DEFAULT 0,
  status        TEXT        CHECK (status IN ('success','partial','error')),
  errors        JSONB,
  imported_at   TIMESTAMPTZ DEFAULT NOW()
);

-- ── Indexes ───────────────────────────────────────────────────────────────────
CREATE INDEX idx_tx_account      ON transactions(account_id);
CREATE INDEX idx_tx_started      ON transactions(started_at DESC);
CREATE INDEX idx_tx_type         ON transactions(transaction_type);
CREATE INDEX idx_tx_currency     ON transactions(currency);
CREATE INDEX idx_tx_merchant     ON transactions(merchant_id);
CREATE INDEX idx_tx_status       ON transactions(status);
CREATE INDEX idx_tx_source_hash  ON transactions(source_hash);

-- ── Views ─────────────────────────────────────────────────────────────────────

-- Monatliche Zusammenfassung
CREATE VIEW monthly_summary AS
SELECT
  a.name                                          AS account,
  DATE_TRUNC('month', t.started_at)              AS month,
  t.currency,
  SUM(CASE WHEN t.amount > 0 THEN t.amount ELSE 0 END) AS einnahmen,
  SUM(CASE WHEN t.amount < 0 THEN ABS(t.amount) ELSE 0 END) AS ausgaben,
  SUM(t.fee)                                      AS gebuehren,
  COUNT(*)                                        AS anzahl
FROM transactions t
JOIN accounts a ON a.id = t.account_id
WHERE t.status = 'ABGESCHLOSSEN'
GROUP BY a.name, DATE_TRUNC('month', t.started_at), t.currency
ORDER BY month DESC, account;

-- Top-Händler nach Ausgaben
CREATE VIEW top_merchants AS
SELECT
  COALESCE(m.display_name, t.description)        AS haendler,
  t.currency,
  COUNT(*)                                        AS kaeufe,
  SUM(ABS(t.amount))                             AS gesamt_ausgabe,
  AVG(ABS(t.amount))                             AS durchschnitt
FROM transactions t
LEFT JOIN merchants m ON m.id = t.merchant_id
WHERE t.transaction_type = 'Kartenbezahlung'
  AND t.status = 'ABGESCHLOSSEN'
GROUP BY COALESCE(m.display_name, t.description), t.currency
ORDER BY gesamt_ausgabe DESC;

-- Währungstausch-Übersicht
CREATE VIEW exchange_summary AS
SELECT
  DATE_TRUNC('month', ce.exchanged_at)           AS month,
  ce.from_currency,
  ce.to_currency,
  SUM(ce.from_amount)                            AS gesamt_von,
  SUM(ce.to_amount)                              AS gesamt_nach,
  AVG(ce.exchange_rate)                          AS avg_kurs,
  COUNT(*)                                        AS anzahl
FROM currency_exchanges ce
GROUP BY DATE_TRUNC('month', ce.exchanged_at), ce.from_currency, ce.to_currency
ORDER BY month DESC;

-- ── Row Level Security ────────────────────────────────────────────────────────
-- Aktivieren, sobald Auth eingerichtet ist:
-- ALTER TABLE accounts          ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE transactions      ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE merchants         ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE categories        ENABLE ROW LEVEL SECURITY;
-- ALTER TABLE currency_exchanges ENABLE ROW LEVEL SECURITY;
