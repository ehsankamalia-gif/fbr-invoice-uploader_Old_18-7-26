"""
Debug: Read .env values directly and print
"""
import sys, os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
os.chdir(str(PROJECT_ROOT))

# Direct file read as a dict to bypass dotenv issues
env_path = PROJECT_ROOT / ".env"
env_dict = {}
with open(env_path, "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env_dict[k.strip()] = v.strip().strip('"').strip("'")

print("=== .env file direct parse ===")
for key in sorted(env_dict.keys()):
    if key.startswith("FBR_"):
        if key.endswith("_TOKEN") or key.endswith("_SECRET_KEY"):
            val = (env_dict[key] or "")[:10] + "..."
        else:
            val = env_dict[key]
        print(f"  {key} = {val}")

print("\n=== Expected prefixes ===")
for env_name in ["SANDBOX", "PROD"]:
    prefix = f"FBR_{env_name}"
    print(f"\n[{prefix}] Expected:")
    for suffix in ["POS_ID", "USIN", "PCT_CODE", "AUTH_TOKEN", "BASE_URL", "ITEM_CODE", "ITEM_NAME"]:
        k = f"{prefix}_{suffix}"
        v = env_dict.get(k, "<MISSING>")
        if "TOKEN" in suffix:
            v = (v or "")[:10] + "..."
        print(f"  {suffix:12s} = {v}")

# Now do the actual population using the env_dict
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
import os; os.chdir(str(PROJECT_ROOT))

from app.db.session import SessionLocal
from app.services.settings_service import settings_service

print("\n=== Now saving directly using the settings_service API + values from dict ===")
db = SessionLocal()
try:
    mapping = [
        ("SANDBOX",
            lambda: {
                "env": "SANDBOX",
                "base_url": env_dict.get("FBR_SANDBOX_API_BASE_URL"),
                "pos_id": env_dict.get("FBR_SANDBOX_POS_ID"),
                "usin": env_dict.get("FBR_SANDBOX_USIN"),
                "token": env_dict.get("FBR_SANDBOX_AUTH_TOKEN"),
                "secret_key": env_dict.get("FBR_SANDBOX_SECRET_KEY", ""),
                "tax_rate": env_dict.get("FBR_SANDBOX_TAX_RATE", "18.0"),
                "pct_code": env_dict.get("FBR_SANDBOX_PCT_CODE", "8711.2010"),
                "invoice_type": env_dict.get("FBR_SANDBOX_INVOICE_TYPE", "Standard"),
                "discount": env_dict.get("FBR_SANDBOX_DISCOUNT", "0.0"),
                "pos_fee": env_dict.get("FBR_SANDBOX_POS_FEE", "1.0"),
                "item_code": env_dict.get("FBR_SANDBOX_ITEM_CODE", ""),
                "item_name": env_dict.get("FBR_SANDBOX_ITEM_NAME", ""),
                "business_name": env_dict.get("FBR_SANDBOX_BUSINESS_NAME", "Ehsan Trader"),
            },
            False,
        ),
        ("PRODUCTION",
            lambda: {
                "env": "PRODUCTION",
                "base_url": env_dict.get("FBR_PROD_API_BASE_URL"),
                "pos_id": env_dict.get("FBR_PROD_POS_ID"),
                "usin": env_dict.get("FBR_PROD_USIN"),
                "token": env_dict.get("FBR_PROD_AUTH_TOKEN"),
                "secret_key": env_dict.get("FBR_PROD_SECRET_KEY", ""),
                "tax_rate": env_dict.get("FBR_PROD_TAX_RATE", "18.0"),
                "pct_code": env_dict.get("FBR_PROD_PCT_CODE", "8711.2010"),
                "invoice_type": env_dict.get("FBR_PROD_INVOICE_TYPE", "Standard"),
                "discount": env_dict.get("FBR_PROD_DISCOUNT", "0.0"),
                "pos_fee": env_dict.get("FBR_PROD_POS_FEE", "1.0"),
                "item_code": env_dict.get("FBR_PROD_ITEM_CODE", ""),
                "item_name": env_dict.get("FBR_PROD_ITEM_NAME", ""),
                "business_name": env_dict.get("FBR_PROD_BUSINESS_NAME", "Ehsan Trader"),
            },
            True,
        ),
    ]

    for env_name, getter, activate in mapping:
        d = getter()
        print(f"\nSaving {env_name}: pos_id={d['pos_id']} usin={d['usin']} pct={d['pct_code']} pos_fee={d['pos_fee']}")
        settings_service.save_environment(**d)
        if activate:
            settings_service.set_active_environment(env_name)

    # Reload
    from app.db.models import FBRConfiguration
    rows = db.query(FBRConfiguration).all()
    print("\n=== Final state in DB ===")
    for r in rows:
        print(f"[{r.environment}] active={r.is_active}")
        print(f"  base_url = {r.api_base_url}")
        print(f"  pos_id   = {r.pos_id}")
        print(f"  usin     = {r.usin}")
        print(f"  tax_rate = {r.tax_rate}")
        print(f"  pos_fee  = {r.pos_fee}")
        print(f"  pct_code = {r.pct_code}")
        print(f"  inv_type = {r.invoice_type}")
        print(f"  discount = {r.discount}")
        print(f"  item_cd  = {r.item_code}")
        print(f"  item_nm  = {r.item_name}")
        print(f"  business = {r.business_name}")
        print()
finally:
    db.close()

print("DONE.")
