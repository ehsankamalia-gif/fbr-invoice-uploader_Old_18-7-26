"""
Initialize FBR configurations DB rows from current .env variables.
Because fbr_configurations exists but has 0 rows (app runs on env-only so far).
"""
import sys, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import text
from app.db.session import SessionLocal
from app.services.settings_service import settings_service
from app.db.models import FBRConfiguration

print("Initializing FBR settings rows in DB from current .env / active settings...")

settings_service.initialize_if_connected()

db = SessionLocal()
try:
    # Force get settings for both envs (this reads from env if DB row not present)
    sb_env = settings_service.get_environment("SANDBOX")
    pr_env = settings_service.get_environment("PRODUCTION")

    # Now call save_environment for each env to actually persist them in DB
    envs_data = [
        ("SANDBOX", sb_env, False),
        ("PRODUCTION", pr_env, True),  # PRODUCTION is the active one per FBR_ENV=.env
    ]
    for env, data, make_active in envs_data:
        print(f"\nSaving {env}...")
        settings_service.save_environment(
            env=env,
            base_url=data.get("base_url"),
            pos_id=data.get("pos_id"),
            usin=data.get("usin"),
            token=data.get("token"),
            secret_key=data.get("secret_key"),
            tax_rate=data.get("tax_rate", "18.0"),
            pct_code=data.get("pct_code", "8711.2010"),
            invoice_type=data.get("invoice_type", "Standard"),
            discount=data.get("discount", "0.0"),
            pos_fee=data.get("pos_fee", "1.0"),
            item_code=data.get("item_code") or "",
            item_name=data.get("item_name") or "",
            business_name=data.get("business_name") or "Ehsan Trader",
        )
        if make_active:
            settings_service.set_active_environment(env)

    # Summary
    rows = db.query(FBRConfiguration).all()
    print(f"\n=== FBR Configurations in DB now: {len(rows)} ===")
    for r in rows:
        print(f"  [{r.environment}] active={r.is_active} pos_id={r.pos_id} usin={r.usin} pos_fee={r.pos_fee} pct={r.pct_code}")

    # Also touch invoices: count how many have fbr_invoice_number + not fiscalized
    print("\n=== Invoice counts ===")
    inv_sql = text("SELECT COUNT(*) AS c FROM invoices")
    c_inv = db.execute(inv_sql).scalar()
    print(f"Total invoices: {c_inv}")

    sql = text("""
        SELECT
          COUNT(*) AS c,
          SUM(CASE WHEN fbr_invoice_number IS NOT NULL AND TRIM(COALESCE(fbr_invoice_number,'')) <> '' THEN 1 ELSE 0 END) AS with_fbr,
          SUM(CASE WHEN is_fiscalized = 1 THEN 1 ELSE 0 END) AS fisc,
          SUM(CASE WHEN UPPER(COALESCE(sync_status,'')) = 'SYNCED' THEN 1 ELSE 0 END) AS synced
        FROM invoices
    """)
    row = db.execute(sql).mappings().first()
    print(f"  With FBR # : {row['with_fbr']}")
    print(f"  Fiscalized : {row['fisc']}")
    print(f"  Synced     : {row['synced']}")

    print("\nDONE - FBR configurations initialized.")
finally:
    db.close()
