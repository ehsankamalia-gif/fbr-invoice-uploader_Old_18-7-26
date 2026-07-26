"""
Repopulate FBR configurations from environment variables directly - forcing values.
The previous run created empty rows because get_environment returned the newly-created empty DB rows.
"""
import sys, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv
load_dotenv(PROJECT_ROOT / ".env", override=True)

from app.db.session import SessionLocal
from app.services.settings_service import settings_service
from app.db.models import FBRConfiguration

print("Force-reloading FBR configurations using environment fallbacks...")

# Bypass the cache by forcing env-only lookup
envs_to_save = ["SANDBOX", "PRODUCTION"]

db = SessionLocal()
try:
    for env in envs_to_save:
        # Use env-reader directly (not get_environment, which prefers DB)
        env_data = settings_service._read_fbr_settings_from_env(env)
        print(f"\n[{env}] from env:")
        print(f"  base_url = {env_data.get('base_url')}")
        print(f"  pos_id   = {env_data.get('pos_id')}")
        print(f"  usin     = {env_data.get('usin')}")
        print(f"  pos_fee  = {env_data.get('pos_fee')}")
        print(f"  token[:8]= {(env_data.get('token') or '')[:8]}...")
        print(f"  pct_code = {env_data.get('pct_code')}")
        print(f"  item_code= {env_data.get('item_code')}")
        print(f"  item_name= {env_data.get('item_name')}")

        # Force-save
        settings_service.save_environment(
            env=env,
            base_url=env_data.get("base_url"),
            pos_id=env_data.get("pos_id"),
            usin=env_data.get("usin"),
            token=env_data.get("token"),
            secret_key=env_data.get("secret_key"),
            tax_rate=env_data.get("tax_rate", "18.0"),
            pct_code=env_data.get("pct_code", "8711.2010"),
            invoice_type=env_data.get("invoice_type", "Standard"),
            discount=env_data.get("discount", "0.0"),
            pos_fee=env_data.get("pos_fee", "1.0"),
            item_code=env_data.get("item_code") or "",
            item_name=env_data.get("item_name") or "",
            business_name=env_data.get("business_name") or "Ehsan Trader",
        )
    # Set PRODUCTION active (per .env FBR_ENV=PRODUCTION)
    settings_service.set_active_environment("PRODUCTION")

    # Now re-read from DB
    print("\n=== FBR Configurations from DB ===")
    rows = db.query(FBRConfiguration).all()
    for r in rows:
        print(f"[{r.environment}] active={r.is_active}")
        print(f"  base_url = {r.api_base_url}")
        print(f"  pos_id   = {r.pos_id}")
        print(f"  usin     = {r.usin}")
        print(f"  pos_fee  = {r.pos_fee}")
        print(f"  pct_code = {r.pct_code}")
        print(f"  tax_rate = {r.tax_rate}")
        print(f"  discount = {r.discount}")
        print(f"  item_code= {r.item_code}")
        print(f"  item_name= {r.item_name}")
        print(f"  business = {r.business_name}")
        print()
finally:
    db.close()

print("DONE.")
