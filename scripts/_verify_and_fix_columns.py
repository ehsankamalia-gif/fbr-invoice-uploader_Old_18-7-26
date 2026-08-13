"""Verify the 9 invoice formatting columns exist in app_configurations."""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_database_url
from sqlalchemy import create_engine, inspect

db_url = get_database_url()
engine = create_engine(db_url)

EXPECTED = [
    "invoice_font_family",
    "invoice_font_field_size_pt",
    "invoice_font_label_size_pt",
    "invoice_font_weight_field",
    "invoice_font_weight_label",
    "invoice_business_name_size_pt",
    "invoice_business_name_weight",
    "invoice_color_label",
    "invoice_mono_font_family",
]

insp = inspect(engine)
cols = {c["name"] for c in insp.get_columns("app_configurations")}
print(f"Total columns in app_configurations: {len(cols)}")
missing = []
for c in EXPECTED:
    if c in cols:
        print(f"  OK   {c}")
    else:
        print(f"  MISS {c}")
        missing.append(c)

if missing:
    print(f"\nATTEMPTING TO ADD MISSING: {missing}")
    DEFS = {
        "invoice_font_family": "VARCHAR(200) DEFAULT 'Arial, sans-serif'",
        "invoice_font_field_size_pt": "INT DEFAULT 11",
        "invoice_font_label_size_pt": "INT DEFAULT 9",
        "invoice_font_weight_field": "INT DEFAULT 600",
        "invoice_font_weight_label": "INT DEFAULT 500",
        "invoice_business_name_size_pt": "INT DEFAULT 16",
        "invoice_business_name_weight": "INT DEFAULT 800",
        "invoice_color_label": "VARCHAR(20) DEFAULT '#555555'",
        "invoice_mono_font_family": "VARCHAR(200) DEFAULT 'Consolas, \\'Courier New\\', monospace'",
    }
    from sqlalchemy import text
    # NOTE: MySQL auto-commits DDL, so no transaction wrapping needed.
    with engine.connect() as conn:
        for c in missing:
            sql = f"ALTER TABLE app_configurations ADD COLUMN {c} {DEFS[c]}"
            print(f"  RUN: {sql}")
            conn.execute(text(sql))
        # Final check
    insp2 = inspect(engine)
    cols2 = {c["name"] for c in insp2.get_columns("app_configurations")}
    still_missing = [c for c in EXPECTED if c not in cols2]
    if still_missing:
        print(f"\nERROR: STILL MISSING {still_missing}")
        sys.exit(1)
    print("\nALL 9 INVOICE FORMATTING COLUMNS VERIFIED PRESENT.")
else:
    print("\nALL 9 INVOICE FORMATTING COLUMNS ARE PRESENT.")

engine.dispose()
