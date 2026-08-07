"""Auto-update spare-ledger SMS templates in DB to include {balance} IF they still
contain the original shipped defaults without any {balance} or customization.

Only runs when exact known legacy defaults are present to avoid clobbering user edits.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_database_url
from sqlalchemy import create_engine, text

engine = create_engine(get_database_url())

OLD_CREDIT_TEMPLATE = (
    "Spare Ledger: Credit received of Rs. {amount} via {source}. Reference: {reference}. Description: {description}"
)
OLD_DEBIT_TEMPLATE = (
    "Spare Ledger: Debit/Order of Rs. {amount} via {source}. Reference: {reference}. Description: {description}"
)

NEW_CREDIT_TEMPLATE = (
    "Spare Ledger: Credit received of Rs. {amount} via {source}. Reference: {reference}. Description: {description}. Balance: Rs. {balance}"
)
NEW_DEBIT_TEMPLATE = (
    "Spare Ledger: Debit/Order of Rs. {amount} via {source}. Reference: {reference}. Description: {description}. Balance: Rs. {balance}"
)

with engine.connect() as conn:
    row = conn.execute(text("SELECT id, spare_ledger_credit_template, spare_ledger_debit_template FROM sms_configurations LIMIT 1")).fetchone()
    if row is None:
        print("No sms_configurations row exists — nothing to update.")
    else:
        _id, cur_credit, cur_debit = row
        updated = []
        if cur_credit is None or cur_credit.strip() == OLD_CREDIT_TEMPLATE:
            conn.execute(
                text("UPDATE sms_configurations SET spare_ledger_credit_template = :t WHERE id = :id"),
                {"t": NEW_CREDIT_TEMPLATE, "id": _id},
            )
            updated.append("spare_ledger_credit_template")
        elif "{balance}" not in (cur_credit or ""):
            print(f"WARNING: spare_ledger_credit_template has been customized (not shipping default) and does NOT include {{balance}}. Please update in settings UI to include . Balance: Rs. {{balance}}")
        if cur_debit is None or cur_debit.strip() == OLD_DEBIT_TEMPLATE:
            conn.execute(
                text("UPDATE sms_configurations SET spare_ledger_debit_template = :t WHERE id = :id"),
                {"t": NEW_DEBIT_TEMPLATE, "id": _id},
            )
            updated.append("spare_ledger_debit_template")
        elif "{balance}" not in (cur_debit or ""):
            print(f"WARNING: spare_ledger_debit_template has been customized (not shipping default) and does NOT include {{balance}}. Please update in settings UI to include . Balance: Rs. {{balance}}")
        try:
            conn.execute(text("COMMIT"))
        except Exception:
            pass
        if updated:
            print(f"Updated DB defaults to include {{balance}} for: {updated}")
        else:
            print("No auto-updates needed for existing DB row.")
