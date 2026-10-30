"""Idempotent, versioned migration runner for the Spare Parts module.

Completely separate from the main app's migration system
(app/db/session.py's run_migrations) - this tracks its own version in its
own sp_schema_migrations table and only ever creates/alters sp_-prefixed
tables. Safe to call on every app startup and safe to re-run manually:
each migration only runs once (gated by the version already recorded),
and migration 1 itself uses CREATE TABLE IF NOT EXISTS semantics via
SQLAlchemy's `checkfirst=True` create_all default.

Can also be run standalone (useful for deployment scripts or to
pre-create the schema without launching the GUI):

    python -m spare_parts.db.migrations
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Connection

from spare_parts.db.base import SpareBase, get_engine
# Imported for its side effect of registering SpCategory/SpBrand/SpPart on
# SpareBase.metadata before create_all() runs below.
from spare_parts.db import models  # noqa: F401
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

MIGRATIONS_TABLE = "sp_schema_migrations"


def _is_sqlite(engine) -> bool:
    return "sqlite" in str(engine.url)


def _ensure_migrations_table(conn: Connection, is_sqlite: bool) -> None:
    if is_sqlite:
        exists = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name=:t"),
            {"t": MIGRATIONS_TABLE},
        ).fetchone()
    else:
        exists = conn.execute(text(f"SHOW TABLES LIKE '{MIGRATIONS_TABLE}'")).fetchone()

    if exists:
        return

    logger.info(f"Creating {MIGRATIONS_TABLE} table...")
    if is_sqlite:
        conn.execute(
            text(
                f"""
                CREATE TABLE {MIGRATIONS_TABLE} (
                    version INTEGER PRIMARY KEY,
                    description VARCHAR(255),
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
    else:
        conn.execute(
            text(
                f"""
                CREATE TABLE {MIGRATIONS_TABLE} (
                    version INT PRIMARY KEY,
                    description VARCHAR(255),
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.commit()


def _migration_v1_initial_schema(conn: Connection, is_sqlite: bool) -> bool:
    """Creates sp_categories, sp_brands, sp_parts (Phase 1)."""
    try:
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v1 failed: {e}", exc_info=True)
        return False


def _migration_v2_suppliers_purchases_ledger(conn: Connection, is_sqlite: bool) -> bool:
    """Creates sp_suppliers, sp_stock_ledger, sp_purchases,
    sp_purchase_items, sp_settings (Phase 2). create_all is safe to call
    again even though v1's tables already exist - it only creates tables
    that are missing."""
    try:
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v2 failed: {e}", exc_info=True)
        return False


def _add_column_if_missing(conn: Connection, is_sqlite: bool, table: str, column: str, ddl_type: str) -> None:
    try:
        conn.execute(text(f"SELECT {column} FROM {table} LIMIT 1"))
        return  # already there
    except Exception:
        pass
    logger.info(f"spare_parts: adding column {column} to {table}...")
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
    if not is_sqlite:
        conn.commit()


def _migration_v3_customers_sales_returns(conn: Connection, is_sqlite: bool) -> bool:
    """Phase 3: sp_customers, sp_sales, sp_sale_items, sp_sale_returns,
    sp_sale_return_items, sp_purchase_returns, sp_purchase_return_items -
    plus two new columns (wholesale_no_prefix, retail_no_prefix) on the
    EXISTING sp_settings table, which create_all() alone cannot add since
    it only creates missing tables, never alters existing ones."""
    try:
        _add_column_if_missing(
            conn, is_sqlite, "sp_settings", "wholesale_no_prefix",
            "VARCHAR(10) DEFAULT 'WS-'",
        )
        _add_column_if_missing(
            conn, is_sqlite, "sp_settings", "retail_no_prefix",
            "VARCHAR(10) DEFAULT 'RT-'",
        )
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v3 failed: {e}", exc_info=True)
        return False


def _migration_v4_payments(conn: Connection, is_sqlite: bool) -> bool:
    """Phase 4: sp_payments (customer receipts / supplier disbursements
    against the running account balance - see spare_parts.db.models.SpPayment
    and spare_parts.services.ledger_service)."""
    try:
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v4 failed: {e}", exc_info=True)
        return False


def _migration_v5_held_sales(conn: Connection, is_sqlite: bool) -> bool:
    """sp_held_sales, sp_held_sale_items - the multi-card POS screen's
    Hold/Resume drafts (see spare_parts.db.models.SpHeldSale and
    spare_parts.services.held_sales_service). No stock-ledger effect,
    see spare_parts/__init__.py."""
    try:
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v5 failed: {e}", exc_info=True)
        return False


def _migration_v6_held_sale_item_price_type(conn: Connection, is_sqlite: bool) -> bool:
    """Adds sp_held_sale_items.price_type (RETAIL/WHOLESALE per line) so
    a mixed card's exact per-line pricing choice survives Hold -> Resume,
    instead of collapsing every line back to the draft's one overall
    sale_type (see spare_parts.ui.sale_card_widget.SaleCardWidget.
    load_from_held_sale)."""
    try:
        _add_column_if_missing(
            conn, is_sqlite, "sp_held_sale_items", "price_type",
            "VARCHAR(20) DEFAULT 'RETAIL'",
        )
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v6 failed: {e}", exc_info=True)
        return False


def _migration_v7_settings_fbr_info(conn: Connection, is_sqlite: bool) -> bool:
    """Adds this module's OWN FBR reference fields (business name, NTN/
    CNIC, STRN) to sp_settings - entirely separate from the main app's
    FBRConfiguration/Company.ntn used for actual invoice submission. See
    the field comments on SpSettings and spare_parts/__init__.py.

    Superseded by v8 below, which replaces this field set with one
    matching the main app's FBR dialog shape instead - these 3 columns
    are left in place (unused, harmless) rather than dropped, since
    column drops aren't part of this module's migration vocabulary and
    this migration has already run against real databases."""
    try:
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_business_name", "VARCHAR(200)")
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_ntn_cnic", "VARCHAR(50)")
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_strn", "VARCHAR(50)")
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v7 failed: {e}", exc_info=True)
        return False


def _migration_v8_settings_fbr_api_fields(conn: Connection, is_sqlite: bool) -> bool:
    """Replaces v7's FBR field set with one matching the main app's FBR
    dialog shape (Environment, API Base URL, POS ID, USIN, Auth Token,
    Secret Key) at the user's request, for a familiar layout - still
    entirely separate storage from app.db.models.FBRConfiguration, never
    read by app.api.fbr_client or any invoice-upload code."""
    try:
        _add_column_if_missing(
            conn, is_sqlite, "sp_settings", "fbr_environment", "VARCHAR(20) DEFAULT 'SANDBOX'",
        )
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_api_base_url", "VARCHAR(255)")
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_pos_id", "VARCHAR(50)")
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_usin", "VARCHAR(50)")
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_auth_token", "VARCHAR(500)")
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "fbr_secret_key", "VARCHAR(255)")
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v8 failed: {e}", exc_info=True)
        return False


def _migration_v9_fbr_environments_table(conn: Connection, is_sqlite: bool) -> bool:
    """Creates sp_fbr_environments (one row per FBR Environment -
    SANDBOX/PRODUCTION), so switching Environment in the Settings page
    actually swaps in THAT environment's own API Base URL/POS ID/USIN/
    Auth Token/Secret Key, mirroring the main app's FBRConfiguration
    per-environment behavior. Supersedes v8's flat sp_settings.
    fbr_api_base_url/fbr_pos_id/fbr_usin/fbr_auth_token/fbr_secret_key
    columns, which only ever held ONE shared set of values regardless of
    the selected environment - those are left in place, unused, rather
    than dropped (this module's migrations only ever add)."""
    try:
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v9 failed: {e}", exc_info=True)
        return False


def _migration_v10_sale_fbr_submission_and_customer_fbr_flag(conn: Connection, is_sqlite: bool) -> bool:
    """Adds live FBR POS-submission tracking to sp_sales (only the
    LATEST attempt is kept, not a full history - see
    spare_parts.services.fbr_submission_service) and an informational
    sp_customers.is_fbr_registered flag. Neither is read by the main
    app's FBR/invoice code - see spare_parts/__init__.py."""
    try:
        _add_column_if_missing(conn, is_sqlite, "sp_sales", "fbr_invoice_number", "VARCHAR(100)")
        _add_column_if_missing(
            conn, is_sqlite, "sp_sales", "fbr_submission_status", "VARCHAR(20) DEFAULT 'NOT_SUBMITTED'",
        )
        _add_column_if_missing(conn, is_sqlite, "sp_sales", "fbr_submitted_at", "DATETIME")
        _add_column_if_missing(conn, is_sqlite, "sp_sales", "fbr_last_error", "TEXT")
        _add_column_if_missing(conn, is_sqlite, "sp_sales", "fbr_last_response", "TEXT")
        _add_column_if_missing(
            conn, is_sqlite, "sp_customers", "is_fbr_registered", "BOOLEAN DEFAULT 0",
        )
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v10 failed: {e}", exc_info=True)
        return False


def _migration_v11_company_name_and_walk_in_customer(conn: Connection, is_sqlite: bool) -> bool:
    """Adds sp_settings.company_name (printed on the receipt header -
    this module cannot read the main app's own Company setting, since
    rule #2 in spare_parts/__init__.py forbids any query against a
    non-sp_ table, so it keeps its own independent copy of the name) and
    sp_sales.walk_in_customer_name (persists whatever the cashier typed
    into the Customer field at the counter without selecting/creating a
    registered SpCustomer - previously only used for the POS card's tab
    label and discarded once the sale was saved, so it never reached the
    printed receipt)."""
    try:
        _add_column_if_missing(conn, is_sqlite, "sp_settings", "company_name", "VARCHAR(150)")
        _add_column_if_missing(conn, is_sqlite, "sp_sales", "walk_in_customer_name", "VARCHAR(150)")
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v11 failed: {e}", exc_info=True)
        return False


def _migration_v12_receipt_paper_format(conn: Connection, is_sqlite: bool) -> bool:
    """Adds sp_settings.receipt_paper_format ('A4' / 'THERMAL_80MM' /
    'THERMAL_58MM') so the printed receipt can use a narrow, thermal-
    printer-style layout instead of the standard A4 one - see
    ui/sale_card_widget.py's print_sale_receipt."""
    try:
        _add_column_if_missing(
            conn, is_sqlite, "sp_settings", "receipt_paper_format", "VARCHAR(20) DEFAULT 'A4'",
        )
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v12 failed: {e}", exc_info=True)
        return False


def _migration_v13_sale_item_cost_price_snapshot(conn: Connection, is_sqlite: bool) -> bool:
    """Adds sp_sale_items.cost_price - the part's cost_price AT THE TIME
    OF SALE, captured going forward by sales_service.create_sale. Needed
    for an accurate profit (Revenue - COGS) report: a part's cost_price
    changes over time as new stock is purchased, so using today's
    cost_price for an old sale would misstate its actual margin. Rows
    saved before this migration have cost_price=NULL -
    reports_service.get_profit_report falls back to the part's current
    cost_price for those (best-effort estimate, flagged in the report)."""
    try:
        _add_column_if_missing(conn, is_sqlite, "sp_sale_items", "cost_price", "DECIMAL(12,2)")
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v13 failed: {e}", exc_info=True)
        return False


def _migration_v14_reorder_qty(conn: Connection, is_sqlite: bool) -> bool:
    """Adds sp_parts.reorder_qty - the quantity to SUGGEST ordering once
    a part drops to/below reorder_level (distinct from reorder_level
    itself, which is the threshold that triggers the suggestion). NULL
    falls back to reorder_level in reports_service.get_reorder_suggestions."""
    try:
        _add_column_if_missing(conn, is_sqlite, "sp_parts", "reorder_qty", "INTEGER")
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v14 failed: {e}", exc_info=True)
        return False


def _migration_v15_warranty_tracking(conn: Connection, is_sqlite: bool) -> bool:
    """Adds sp_parts.warranty_days (how many days of warranty this part
    carries when sold) and sp_sale_items.warranty_expires_at (the
    per-line snapshot: sale_date + warranty_days at the moment it was
    actually sold, captured going forward by sales_service - same
    snapshot principle as v13's cost_price, since warranty_days can
    change later without retroactively altering what was already sold)."""
    try:
        _add_column_if_missing(conn, is_sqlite, "sp_parts", "warranty_days", "INTEGER")
        _add_column_if_missing(conn, is_sqlite, "sp_sale_items", "warranty_expires_at", "DATETIME")
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v15 failed: {e}", exc_info=True)
        return False


def _migration_v16_stock_take(conn: Connection, is_sqlite: bool) -> bool:
    """Creates sp_stock_takes + sp_stock_take_items (a formal physical
    count reconciliation: freeze a system_qty snapshot per part, enter
    counted_qty over time while DRAFT, then post once - see
    spare_parts.services.stock_take_service) + sp_settings.stock_take_no_prefix."""
    try:
        _add_column_if_missing(
            conn, is_sqlite, "sp_settings", "stock_take_no_prefix", "VARCHAR(10) DEFAULT 'ST-'",
        )
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v16 failed: {e}", exc_info=True)
        return False


def _migration_v17_quotations(conn: Connection, is_sqlite: bool) -> bool:
    """Creates sp_quotations + sp_quotation_items (a pre-sale price
    quote, separate from POS Held Sales - no stock reservation, no
    ledger effect until converted into a real sale - see
    spare_parts.services.quotations_service) + sp_settings.quotation_no_prefix."""
    try:
        _add_column_if_missing(
            conn, is_sqlite, "sp_settings", "quotation_no_prefix", "VARCHAR(10) DEFAULT 'QT-'",
        )
        SpareBase.metadata.create_all(bind=get_engine())
        return True
    except Exception as e:
        logger.error(f"Migration v17 failed: {e}", exc_info=True)
        return False


# (version, description, function) - function receives (conn, is_sqlite)
# and returns True on success. Append new tuples here for later phases;
# never edit an already-applied migration's behavior.
MIGRATIONS: list[tuple[int, str, callable]] = [
    (1, "Phase 1: sp_categories, sp_brands, sp_parts", _migration_v1_initial_schema),
    (2, "Phase 2: sp_suppliers, sp_stock_ledger, sp_purchases, sp_purchase_items, sp_settings",
     _migration_v2_suppliers_purchases_ledger),
    (3, "Phase 3: sp_customers, sp_sales, sp_sale_items, sp_sale_returns, "
        "sp_sale_return_items, sp_purchase_returns, sp_purchase_return_items, "
        "+ sp_settings wholesale/retail prefixes",
     _migration_v3_customers_sales_returns),
    (4, "Phase 4: sp_payments", _migration_v4_payments),
    (5, "POS multi-card: sp_held_sales, sp_held_sale_items", _migration_v5_held_sales),
    (6, "sp_held_sale_items.price_type (per-line Retail/Wholesale survives Hold/Resume)",
     _migration_v6_held_sale_item_price_type),
    (7, "sp_settings FBR info (business name, NTN/CNIC, STRN) - module-local, not linked to invoice FBR config",
     _migration_v7_settings_fbr_info),
    (8, "sp_settings FBR API fields (Environment, API Base URL, POS ID, USIN, Auth Token, Secret Key) - "
        "module-local, not linked to invoice FBR config",
     _migration_v8_settings_fbr_api_fields),
    (9, "sp_fbr_environments (one row per SANDBOX/PRODUCTION, so switching Environment swaps the "
        "actual API URL/POS ID/USIN/Auth Token/Secret Key values) - module-local, not linked to invoice FBR config",
     _migration_v9_fbr_environments_table),
    (10, "sp_sales FBR submission tracking (invoice number/status/submitted_at/last_error/last_response) "
         "+ sp_customers.is_fbr_registered flag - module-local, not linked to invoice FBR config",
     _migration_v10_sale_fbr_submission_and_customer_fbr_flag),
    (11, "sp_settings.company_name (receipt header) + sp_sales.walk_in_customer_name "
         "(typed-at-counter customer name for walk-in sales) - module-local, independent copies",
     _migration_v11_company_name_and_walk_in_customer),
    (12, "sp_settings.receipt_paper_format (A4 / THERMAL_80MM / THERMAL_58MM) for thermal printer support",
     _migration_v12_receipt_paper_format),
    (13, "sp_sale_items.cost_price (cost snapshot at time of sale) for the Profit report",
     _migration_v13_sale_item_cost_price_snapshot),
    (14, "sp_parts.reorder_qty for the Reorder/Purchase Suggestions report",
     _migration_v14_reorder_qty),
    (15, "sp_parts.warranty_days + sp_sale_items.warranty_expires_at for Warranty Tracking",
     _migration_v15_warranty_tracking),
    (16, "sp_stock_takes, sp_stock_take_items + sp_settings.stock_take_no_prefix for Stock Take",
     _migration_v16_stock_take),
    (17, "sp_quotations, sp_quotation_items + sp_settings.quotation_no_prefix for Quotations",
     _migration_v17_quotations),
]


def run_migrations() -> None:
    engine = get_engine()
    is_sqlite = _is_sqlite(engine)

    with engine.connect() as conn:
        _ensure_migrations_table(conn, is_sqlite)
        if not is_sqlite:
            conn.commit()

        current_version = conn.execute(
            text(f"SELECT MAX(version) FROM {MIGRATIONS_TABLE}")
        ).scalar() or 0
        logger.info(f"spare_parts schema version: {current_version}")

        for version, description, func in MIGRATIONS:
            if version <= current_version:
                continue
            logger.info(f"Running spare_parts migration v{version}: {description}")
            if func(conn, is_sqlite):
                conn.execute(
                    text(
                        f"INSERT INTO {MIGRATIONS_TABLE} (version, description) "
                        "VALUES (:v, :d)"
                    ),
                    {"v": version, "d": description},
                )
                conn.commit()
                logger.info(f"spare_parts migration v{version} applied.")
            else:
                logger.error(f"spare_parts migration v{version} failed; aborting further migrations.")
                break


if __name__ == "__main__":
    run_migrations()
    print("spare_parts migrations complete.")
