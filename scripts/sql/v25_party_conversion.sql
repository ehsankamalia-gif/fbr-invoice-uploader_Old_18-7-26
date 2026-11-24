-- v25: Dealer -> Customer conversion support (MySQL).
--
-- The desktop app applies this automatically at startup (app/db/session.py,
-- migration v25). This script is the same change for running by hand.
--
-- 1) BACK UP FIRST. MySQL commits ALTER/CREATE immediately, so those steps
--    cannot be rolled back:
--      mysqldump -u root -p --single-transaction fbr_invoice_uploader > fbr_before_v25.sql
--
-- 2) Run:   mysql -u root -p fbr_invoice_uploader < v25_party_conversion.sql
--
-- A "party" is a row of `customers`; `customers.type` ('INDIVIDUAL'|'DEALER')
-- already is the party type, so no second party_type column is added.
-- Re-running is safe (guarded / only touches rows that are still NULL).

-- Remember: if a column below already exists, MySQL reports "Duplicate column"
-- - that just means it was already applied (the app's self-healing step may have
-- added it first); skip that statement.

ALTER TABLE customers ADD COLUMN converted_to_customer_at DATETIME NULL;

-- Snapshot taken at invoice creation; never recalculated from the party's type.
ALTER TABLE invoices ADD COLUMN invoice_party_type VARCHAR(20) NULL;
CREATE INDEX ix_invoices_invoice_party_type ON invoices (invoice_party_type);

CREATE TABLE IF NOT EXISTS party_type_history (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    party_id    INT NOT NULL,
    old_type    VARCHAR(20) NOT NULL,
    new_type    VARCHAR(20) NOT NULL,
    changed_at  DATETIME NOT NULL,
    changed_by  VARCHAR(100) NULL,
    INDEX ix_party_type_history_party_id (party_id),
    CONSTRAINT fk_party_type_history_party FOREIGN KEY (party_id) REFERENCES customers (id)
) ENGINE=InnoDB;

-- One-time backfill, in a transaction: freeze every existing invoice with its
-- buyer's CURRENT type, so all existing dealer invoices stay dealer invoices.
START TRANSACTION;
UPDATE invoices i
   JOIN customers c ON c.id = i.customer_id
   SET i.invoice_party_type = c.type
 WHERE i.invoice_party_type IS NULL;
UPDATE invoices SET invoice_party_type = 'INDIVIDUAL'
 WHERE invoice_party_type IS NULL AND customer_id IS NULL;
COMMIT;

-- Sanity check (expect no NULLs):
-- SELECT invoice_party_type, COUNT(*) FROM invoices GROUP BY invoice_party_type;
