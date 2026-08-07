"""Idempotent migration to add per-feature SMS enable/disable toggles + any missing templates.

Run: python scripts/add_sms_feature_toggles.py
Safe to run multiple times.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_database_url
from sqlalchemy import create_engine, text

NEW_COLUMNS = [
    # Per-feature enable/disable booleans (default True so existing installs keep SMS flowing)
    ("invoice_sms_enabled", "TINYINT(1) DEFAULT 1"),
    ("booking_sms_enabled", "TINYINT(1) DEFAULT 1"),
    ("spare_credit_sms_enabled", "TINYINT(1) DEFAULT 1"),
    ("spare_debit_sms_enabled", "TINYINT(1) DEFAULT 1"),
    ("credit_sale_payment_sms_enabled", "TINYINT(1) DEFAULT 1"),
    ("finance_sale_installment_sms_enabled", "TINYINT(1) DEFAULT 1"),

    # Spare Ledger & Owner Phone SMS templates (if they don't already exist)
    ("owner_phone_number", "VARCHAR(20) DEFAULT NULL"),
    ("spare_ledger_credit_template", "VARCHAR(500) DEFAULT 'Spare Ledger: Credit received of Rs. {amount} via {source}. Reference: {reference}. Description: {description}'"),
    ("spare_ledger_debit_template", "VARCHAR(500) DEFAULT 'Spare Ledger: Debit/Order of Rs. {amount} via {source}. Reference: {reference}. Description: {description}'"),

    # Credit Ledger SMS templates (if not already added by previous migration)
    ("credit_sale_template", "VARCHAR(500) DEFAULT 'Dear {customer}, credit sale of {model} (Chassis: {chassis}) is confirmed. Credit: Rs. {credit_price}. Advance: Rs. {advance}. Balance: Rs. {balance}.'"),
    ("credit_payment_template", "VARCHAR(500) DEFAULT 'Dear {customer}, installment of Rs. {amount} received. Penalty: Rs. {penalty}. Discount: Rs. {discount}. Remaining balance: Rs. {balance}.'"),
    ("finance_sale_template", "VARCHAR(500) DEFAULT 'Dear {customer}, finance account {sale_id} for {model} (Chassis: {chassis}) is confirmed. Finance: Rs. {credit_price}. Down: Rs. {down}. Balance: Rs. {balance}.'"),
    ("finance_installment_template", "VARCHAR(500) DEFAULT 'Dear {customer}, installment of Rs. {amount} received for {sale_id}. New balance: Rs. {balance}.'"),
]


def column_exists(conn, table_name: str, column_name: str, is_sqlite: bool) -> bool:
    if is_sqlite:
        cur = conn.execute(text(f"PRAGMA table_info({table_name})"))
        for row in cur:
            if str(row[1]) == column_name:
                return True
        return False
    cur = conn.execute(text("""
        SELECT COUNT(*) FROM information_schema.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE()
          AND TABLE_NAME = :t
          AND COLUMN_NAME = :c
    """), {"t": table_name, "c": column_name})
    count = cur.scalar()
    return int(count or 0) > 0


def main():
    db_url = get_database_url()
    is_sqlite = "sqlite" in db_url
    engine = create_engine(db_url)
    print(f"Connected to database: {'sqlite' if is_sqlite else 'mysql/mariadb'}  ({db_url[:100]}{'...' if len(db_url) > 100 else ''})")

    with engine.connect() as conn:
        if not is_sqlite:
            try:
                conn.execute(text("COMMIT"))
            except Exception:
                pass

        applied = 0
        skipped = 0
        for col_name, col_def in NEW_COLUMNS:
            if column_exists(conn, "sms_configurations", col_name, is_sqlite):
                print(f"  Column {col_name} already exists — skipped.")
                skipped += 1
                continue
            # SQLite uses 1/0 for boolean TINYINT; use BOOLEAN/INTEGER defaults instead
            final_def = col_def
            if is_sqlite:
                final_def = (
                    col_def.replace("TINYINT(1)", "INTEGER")
                           .replace("DEFAULT 1", "DEFAULT 1")
                           .replace("DEFAULT 0", "DEFAULT 0")
                )
            sql = f"ALTER TABLE sms_configurations ADD COLUMN {col_name} {final_def}"
            print(f"  Adding column {col_name}...")
            conn.execute(text(sql))
            applied += 1
        try:
            conn.execute(text("COMMIT"))
        except Exception:
            pass
    print(f"Done. {applied} new column(s) added; {skipped} already existed.")


if __name__ == "__main__":
    main()
