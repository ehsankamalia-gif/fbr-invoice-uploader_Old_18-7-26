"""Global multi-company query filtering.

Registers a single SQLAlchemy `do_orm_execute` event on the Session CLASS
(not a specific engine/SessionLocal instance, so it survives init_db()
re-binding SessionLocal to a new engine at runtime). For every SELECT
against one of the company-scoped models below, it transparently injects
`WHERE company_id = <active company>` via with_loader_criteria - covering
both the legacy `Query` API (`db.query(Model)...`, used exclusively
throughout this codebase) and 2.0-style `session.execute(select(...))`.

This is deliberately a single choke point instead of editing the ~290
existing `.query()` call sites individually - missing even one such edit
would silently leak another company's data. Import `register()` once at
app startup (called from app/db/session.py right after Base/engine are
set up, so it's active before any real query runs).

Escape hatches this does NOT cover (need their own manual company_id
filter): raw `text()` SQL against `customers`, `invoices`, `invoice_items`,
`finance_installments`, and the fully-raw-SQL `customer_portal_auth`
access in app/services/customer_portal_service.py.
"""
import logging

from sqlalchemy import event
from sqlalchemy.orm import Session, with_loader_criteria

from app.db.models import (
    AdvanceBooking, BuyerLedger, CapturedData, CreditPayment, CreditSale,
    CreditSaleItem, Customer, FinanceCreditSale, FinanceInstallment,
    FinanceLedger, Invoice, InvoiceItem, Motorcycle, Price, ProductModel,
    SpareLedgerMonthlyClose, SpareLedgerTransaction,
)

logger = logging.getLogger(__name__)

# Company itself, FBRConfiguration, and every non-business-data table
# (users, app_configurations, report_*, excise_records, etc.) are
# deliberately NOT in this list - FBRConfiguration is looked up directly by
# is_active in settings_service, not by company, and scoping it here would
# create a chicken-and-egg problem resolving the active company itself.
SCOPED_MODELS = (
    Customer, Motorcycle, ProductModel, Price, Invoice, InvoiceItem,
    FinanceCreditSale, FinanceInstallment, FinanceLedger, CreditSale,
    CreditSaleItem, CreditPayment, BuyerLedger, SpareLedgerTransaction,
    SpareLedgerMonthlyClose, CapturedData, AdvanceBooking,
)

_registered = False


def _get_active_company_id():
    # Deferred import: settings_service imports from app.db.session, which
    # would otherwise create a circular import with this module.
    from app.services.settings_service import settings_service
    return settings_service.get_active_company_id()


def _do_orm_execute(execute_state):
    if not execute_state.is_select:
        return
    # Escape hatch for genuinely cross-company reads (none needed yet, but
    # kept as a documented hook rather than something call sites invent
    # their own workaround for): db.execute(stmt, execution_options={"skip_company_filter": True})
    if execute_state.execution_options.get("skip_company_filter"):
        return

    # NOTE: pass a direct boolean expression (model.company_id == company_id),
    # NOT a `lambda cls: cls.company_id == company_id` callable. Empirically
    # verified the callable form gets its closure value baked in and stale-
    # cached by SQLAlchemy's statement compilation cache - the first
    # company_id resolved in the process would silently "stick" for every
    # later query, defeating the whole filter. The direct-expression form
    # builds a fresh, correctly-parameterized criterion on every call.
    company_id = _get_active_company_id()
    for model in SCOPED_MODELS:
        execute_state.statement = execute_state.statement.options(
            with_loader_criteria(model, model.company_id == company_id, include_aliases=True)
        )


def register():
    """Idempotent - safe to call more than once (e.g. if init_db() runs
    again at settings-change time)."""
    global _registered
    if _registered:
        return
    event.listen(Session, "do_orm_execute", _do_orm_execute)
    _registered = True
    logger.info(f"Company-scope query filter registered for {len(SCOPED_MODELS)} models.")
