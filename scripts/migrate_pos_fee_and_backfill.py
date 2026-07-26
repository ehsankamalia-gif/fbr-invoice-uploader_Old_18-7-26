"""
One-time database migration:
1. Verify fbr_configurations table exists
2. Add pos_fee column if missing
3. Backfill USIN + verification on historical invoices
"""
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import inspect, text
from app.db.session import SessionLocal, engine
from app.db.models import Base, FBRConfiguration, Invoice

print("=" * 60)
print("Step 1: Check if fbr_configurations table exists")
print("=" * 60)
insp = inspect(engine)
tables = insp.get_table_names()
if "fbr_configurations" not in tables:
    print("fbr_configurations NOT FOUND. Creating all tables via Base.metadata.create_all()...")
    Base.metadata.create_all(bind=engine)
    print("Tables created. Re-querying...")
    insp = inspect(engine)
    tables = insp.get_table_names()

print(f"Tables found: {len(tables)}")
print(f"  - fbr_configurations: {'YES' if 'fbr_configurations' in tables else 'NO'}")
print(f"  - invoices: {'YES' if 'invoices' in tables else 'NO'}")

db = SessionLocal()
try:
    print()
    print("=" * 60)
    print("Step 2: Check if pos_fee column exists on fbr_configurations")
    print("=" * 60)
    cols = [c["name"] for c in insp.get_columns("fbr_configurations")]
    print(f"Current columns: {cols}")
    if "pos_fee" not in cols:
        print("pos_fee column MISSING -> adding now...")
        db.execute(text("ALTER TABLE fbr_configurations ADD COLUMN pos_fee FLOAT DEFAULT 1.0 NULL"))
        db.commit()
        print("Added pos_fee column. Default value set to 1.0")
        insp2 = inspect(engine)
        cols = [c["name"] for c in insp2.get_columns("fbr_configurations")]
    print(f"pos_fee present: {'YES' if 'pos_fee' in cols else 'NO'}")

    print()
    print("=" * 60)
    print("Step 3: Backfill pos_fee = 1.0 where NULL")
    print("=" * 60)
    rows_updated = db.execute(
        text("UPDATE fbr_configurations SET pos_fee = 1.0 WHERE pos_fee IS NULL OR pos_fee < 0")
    ).rowcount
    db.commit()
    print(f"FBR Config rows updated with pos_fee=1.0: {rows_updated}")

    # Show current configs
    cfgs = db.query(FBRConfiguration).all()
    print(f"\nFBR Configurations found: {len(cfgs)}")
    for c in cfgs:
        print(f"  [{c.environment}] active={c.is_active}  pos_id={c.pos_id}  pos_fee={c.pos_fee}  usin={c.usin}")

    print()
    print("=" * 60)
    print("Step 4: Backfill historical invoices (USIN, verified, sync_status)")
    print("=" * 60)
    inv_cols = [c["name"] for c in insp.get_columns("invoices")]
    print(f"Invoice columns count: {len(inv_cols)}")
    for field in ["usin", "fbr_invoice_number", "is_fiscalized", "sync_status", "fbr_response_message"]:
        print(f"  - {field}: {'YES' if field in inv_cols else 'NO'}")

    # 4a. Set USIN = fbr_invoice_number for already-fiscalized invoices
    backfill_sql_a = text("""
        UPDATE invoices
        SET usin = fbr_invoice_number
        WHERE fbr_invoice_number IS NOT NULL
          AND TRIM(COALESCE(fbr_invoice_number,'')) <> ''
          AND (usin IS NULL OR TRIM(usin) = '' OR LENGTH(usin) < 8 OR usin != fbr_invoice_number)
    """)
    result_a = db.execute(backfill_sql_a).rowcount
    db.commit()
    print(f"Backfilled USIN -> fbr_invoice_number for {result_a} invoices")

    # 4b. Set is_fiscalized=1, sync_status='SYNCED', fbr_response_message='Verified & Fiscalized - Backfilled' where we have fbr id
    backfill_sql_b = text("""
        UPDATE invoices
        SET is_fiscalized = 1,
            sync_status = 'SYNCED',
            fbr_response_message = 'Verified & Fiscalized (Backfilled)'
        WHERE fbr_invoice_number IS NOT NULL
          AND TRIM(COALESCE(fbr_invoice_number,'')) <> ''
          AND is_fiscalized != 1
    """)
    result_b = db.execute(backfill_sql_b).rowcount
    db.commit()
    print(f"Set fiscalized/SYNCED statuses: {result_b} invoices")

    # 4c. Print summary stats
    summary_sql = text("""
        SELECT
            COUNT(*) AS total,
            SUM(CASE WHEN fbr_invoice_number IS NOT NULL AND TRIM(fbr_invoice_number) <> '' THEN 1 ELSE 0 END) AS with_fbr_id,
            SUM(CASE WHEN COALESCE(is_fiscalized,0) = 1 THEN 1 ELSE 0 END) AS fiscalized_count,
            SUM(CASE WHEN UPPER(COALESCE(sync_status,'')) = 'SYNCED' THEN 1 ELSE 0 END) AS synced_count
        FROM invoices
    """)
    row = db.execute(summary_sql).mappings().first()
    print("\n--- Invoice Stats Summary ---")
    print(f"  Total invoices:            {row['total']}")
    print(f"  With FBR invoice number:   {row['with_fbr_id']}")
    print(f"  is_fiscalized=1:           {row['fiscalized_count']}")
    print(f"  sync_status=SYNCED:        {row['synced_count']}")

    print()
    print("=" * 60)
    print("DONE — All actions completed successfully")
    print("=" * 60)

finally:
    db.close()
