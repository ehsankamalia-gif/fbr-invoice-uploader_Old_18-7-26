"""SQLAlchemy models for the Spare Parts module.

Phase 1: categories, brands, parts.
Phase 2: suppliers, stock ledger, purchases, purchase items, settings.
Phase 3: customers, sales, sale items, sale returns, purchase returns.
Phase 4: payments (customer receipts / supplier disbursements).

Every table is sp_-prefixed and relates only to other sp_ tables - see
spare_parts/__init__.py.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from spare_parts.db.base import SpareBase


class SpCategory(SpareBase):
    """A part category, optionally nested under another sp_categories row."""

    __tablename__ = "sp_categories"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("sp_categories.id"), nullable=True)

    parent = relationship("SpCategory", remote_side=[id], backref="children")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpCategory id={self.id} name={self.name!r}>"


class SpBrand(SpareBase):
    """A part brand/manufacturer."""

    __tablename__ = "sp_brands"

    id = Column(Integer, primary_key=True)
    name = Column(String(100), nullable=False, unique=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpBrand id={self.id} name={self.name!r}>"


class SpPart(SpareBase):
    """A stock-keeping unit. Current stock is never stored here directly -
    it is always derived by summing sp_stock_ledger for this part (see
    spare_parts/__init__.py: "Stock is never edited directly")."""

    __tablename__ = "sp_parts"

    id = Column(Integer, primary_key=True)
    part_no = Column(String(50), nullable=False, unique=True, index=True)
    name = Column(String(150), nullable=False, index=True)
    category_id = Column(Integer, ForeignKey("sp_categories.id"), nullable=True)
    brand_id = Column(Integer, ForeignKey("sp_brands.id"), nullable=True)
    compatible_models = Column(Text, nullable=True)
    unit = Column(String(20), nullable=False, default="pcs")
    pack_size = Column(Integer, nullable=False, default=1)
    barcode = Column(String(64), nullable=True, index=True)
    rack_location = Column(String(50), nullable=True)

    # Money as Decimal (SQLAlchemy Numeric <-> Python decimal.Decimal) to
    # avoid float rounding errors - see spare_parts/__init__.py and the
    # Phase 1 summary for why Decimal was chosen over integer-paisa.
    cost_price = Column(Numeric(12, 2), nullable=False, default=0)
    retail_price = Column(Numeric(12, 2), nullable=False, default=0)
    wholesale_price = Column(Numeric(12, 2), nullable=False, default=0)

    min_wholesale_qty = Column(Integer, nullable=False, default=1)
    reorder_level = Column(Integer, nullable=False, default=0)
    # Quantity to SUGGEST ordering once stock drops to/below reorder_level
    # (reorder_level is the threshold, this is the suggested order size).
    # NULL falls back to reorder_level - see reports_service.get_reorder_suggestions.
    reorder_qty = Column(Integer, nullable=True)
    # Days of warranty this part carries when sold (0/NULL = no warranty).
    # Snapshotted per sale line at sale time - see SpSaleItem.warranty_expires_at.
    warranty_days = Column(Integer, nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    category = relationship("SpCategory")
    brand = relationship("SpBrand")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpPart id={self.id} part_no={self.part_no!r} name={self.name!r}>"


class SpSupplier(SpareBase):
    """A parts supplier. Entirely separate from app.db.models.Supplier -
    this module keeps its own supplier records (see spare_parts/__init__.py)."""

    __tablename__ = "sp_suppliers"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False, index=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    opening_balance = Column(Numeric(12, 2), nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpSupplier id={self.id} name={self.name!r}>"


class SpStockLedger(SpareBase):
    """Every stock movement for a part. This is the single source of
    truth for stock - sp_parts has no stock column at all. Each row's
    `balance` is the running total immediately after this movement,
    computed by spare_parts.services.stock_service (never written to
    directly by any other code - see spare_parts/__init__.py)."""

    __tablename__ = "sp_stock_ledger"

    id = Column(Integer, primary_key=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)
    qty_in = Column(Integer, nullable=False, default=0)
    qty_out = Column(Integer, nullable=False, default=0)
    balance = Column(Integer, nullable=False)

    # "PURCHASE", "PURCHASE_CANCEL", "OPENING", and from later phases
    # "SALE", "SALE_RETURN", "PURCHASE_RETURN", "ADJUSTMENT".
    reference_type = Column(String(30), nullable=False, index=True)
    reference_id = Column(Integer, nullable=True)
    note = Column(String(255), nullable=True)

    entry_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<SpStockLedger id={self.id} part_id={self.part_id} "
            f"in={self.qty_in} out={self.qty_out} balance={self.balance} "
            f"ref={self.reference_type}:{self.reference_id}>"
        )


class SpPurchase(SpareBase):
    """A purchase invoice header. Items live in sp_purchase_items."""

    __tablename__ = "sp_purchases"

    id = Column(Integer, primary_key=True)
    purchase_no = Column(String(30), nullable=False, unique=True, index=True)
    supplier_id = Column(Integer, ForeignKey("sp_suppliers.id"), nullable=False)
    purchase_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    paid = Column(Numeric(12, 2), nullable=False, default=0)
    due = Column(Numeric(12, 2), nullable=False, default=0)

    # "POSTED" (normal, affects stock) or "CANCELLED" (stock reversed,
    # see spare_parts.services.purchase_service.cancel_purchase). There is
    # no in-place edit of a saved purchase - cancel and re-enter instead,
    # which keeps the stock-ledger trail honest and simple to reason about.
    status = Column(String(20), nullable=False, default="POSTED")
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    supplier = relationship("SpSupplier")
    items = relationship(
        "SpPurchaseItem", back_populates="purchase", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpPurchase id={self.id} no={self.purchase_no!r} status={self.status}>"


class SpPurchaseItem(SpareBase):
    __tablename__ = "sp_purchase_items"

    id = Column(Integer, primary_key=True)
    purchase_id = Column(Integer, ForeignKey("sp_purchases.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    qty = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    line_total = Column(Numeric(12, 2), nullable=False)

    purchase = relationship("SpPurchase", back_populates="items")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpPurchaseItem id={self.id} part_id={self.part_id} qty={self.qty}>"


class SpSettings(SpareBase):
    """Single-row module settings table. Row id is always 1 - see
    spare_parts.services.settings_service.get_settings(), which creates
    it on first use. Later phases add more columns via their own
    migrations (e.g. wholesale/retail invoice-number prefixes in Phase 3)."""

    __tablename__ = "sp_settings"

    id = Column(Integer, primary_key=True)
    allow_negative_stock = Column(Boolean, nullable=False, default=False)
    default_tax_percent = Column(Numeric(5, 2), nullable=False, default=0)
    purchase_no_prefix = Column(String(10), nullable=False, default="PO-")
    # Phase 3: separate invoice-number series per sale type.
    wholesale_no_prefix = Column(String(10), nullable=False, default="WS-")
    retail_no_prefix = Column(String(10), nullable=False, default="RT-")
    # Which FBR environment is currently selected in the Settings page -
    # the actual per-environment API/security values live on
    # SpFbrEnvironment below (one row per environment), not here, so
    # switching this has real values to switch TO. Entirely separate
    # from app.db.models.FBRConfiguration, never read by app.api.fbr_client
    # or anything that builds an FBR upload payload - see
    # spare_parts/__init__.py independence rules.
    fbr_environment = Column(String(20), nullable=False, default="SANDBOX")
    # Unused - the receipt header now reads the company name live from
    # the main app's own Company setting instead (see
    # ui/sale_card_widget.py's _get_main_app_company_name), per an
    # explicit, narrow exception to rule #2 in spare_parts/__init__.py.
    # Column kept rather than dropped, per this module's append-only
    # migration philosophy (spare_parts/db/migrations.py).
    company_name = Column(String(150), nullable=True)
    # "A4" (standard printer) / "THERMAL_80MM" / "THERMAL_58MM" - picks
    # which receipt layout print_sale_receipt builds and the printer
    # page width it requests. See ui/sale_card_widget.py.
    receipt_paper_format = Column(String(20), nullable=False, default="A4")
    stock_take_no_prefix = Column(String(10), nullable=False, default="ST-")
    quotation_no_prefix = Column(String(10), nullable=False, default="QT-")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpSettings allow_negative_stock={self.allow_negative_stock}>"


class SpFbrEnvironment(SpareBase):
    """This module's OWN FBR API/security settings, one row per
    environment (SANDBOX/PRODUCTION) - mirrors the main app's
    FBRConfiguration table shape/behavior (switching Environment in the
    UI swaps to THAT row's own values), but is entirely separate storage.
    Never read by app.api.fbr_client or anything that builds an FBR
    upload payload - these are inert, nothing in this module calls FBR
    with them. Superseded sp_settings.fbr_api_base_url/fbr_pos_id/
    fbr_usin/fbr_auth_token/fbr_secret_key (added in migration v8),
    which are left in place but unused rather than dropped."""

    __tablename__ = "sp_fbr_environments"

    id = Column(Integer, primary_key=True)
    environment = Column(String(20), nullable=False, unique=True)
    api_base_url = Column(String(255), nullable=True)
    pos_id = Column(String(50), nullable=True)
    usin = Column(String(50), nullable=True)
    auth_token = Column(String(500), nullable=True)
    secret_key = Column(String(255), nullable=True)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpFbrEnvironment environment={self.environment!r}>"


class SpCustomer(SpareBase):
    """A customer of record for this module. Entirely separate from
    app.db.models.Customer - this module keeps its own customer records
    (see spare_parts/__init__.py)."""

    __tablename__ = "sp_customers"

    id = Column(Integer, primary_key=True)
    name = Column(String(150), nullable=False, index=True)
    # "RETAIL" or "WHOLESALE" - drives default sale_type when this
    # customer is selected on a new sale (see sales_service.create_sale).
    type = Column(String(20), nullable=False, default="RETAIL")
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    cnic_ntn = Column(String(30), nullable=True)
    # Informational only - captured for business record-keeping. Not
    # currently consumed by fbr_payload_service.py's POS-style payload,
    # which has no buyerRegistrationType-equivalent field.
    is_fbr_registered = Column(Boolean, nullable=False, default=False)
    credit_limit = Column(Numeric(12, 2), nullable=False, default=0)
    opening_balance = Column(Numeric(12, 2), nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpCustomer id={self.id} name={self.name!r} type={self.type}>"


class SpSale(SpareBase):
    """A sale invoice header (retail counter sale or wholesale invoice).
    Items live in sp_sale_items."""

    __tablename__ = "sp_sales"

    id = Column(Integer, primary_key=True)
    sale_no = Column(String(30), nullable=False, unique=True, index=True)
    # "RETAIL" or "WHOLESALE" - decides which number series (sale_no
    # prefix) and which of the part's two prices this sale used by
    # default (see spare_parts.services.sales_service).
    sale_type = Column(String(20), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("sp_customers.id"), nullable=True)
    # The name the cashier typed into the Customer field at the counter
    # without selecting/creating a registered SpCustomer - kept so a
    # walk-in sale's receipt/sales list can still show a name instead of
    # just "Walk-in". Only meaningful when customer_id is NULL.
    walk_in_customer_name = Column(String(150), nullable=True)
    sale_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    tax_percent = Column(Numeric(5, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    paid = Column(Numeric(12, 2), nullable=False, default=0)
    due = Column(Numeric(12, 2), nullable=False, default=0)
    payment_method = Column(String(30), nullable=False, default="Cash")

    # "POSTED" or "CANCELLED" - same cancel-and-reenter policy as
    # sp_purchases, see spare_parts.services.sales_service.cancel_sale.
    status = Column(String(20), nullable=False, default="POSTED")
    notes = Column(Text, nullable=True)

    # Live FBR POS-integration submission tracking (this module's OWN
    # submission, via spare_parts.services.fbr_submission_service - never
    # linked to the main app's invoice FBR upload). Only the LATEST
    # attempt is kept (overwritten on resubmit), not a full history.
    # "NOT_SUBMITTED" / "SUBMITTED" / "FAILED".
    fbr_submission_status = Column(String(20), nullable=False, default="NOT_SUBMITTED")
    fbr_invoice_number = Column(String(100), nullable=True)
    fbr_submitted_at = Column(DateTime, nullable=True)
    fbr_last_error = Column(Text, nullable=True)
    fbr_last_response = Column(Text, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    customer = relationship("SpCustomer")
    items = relationship("SpSaleItem", back_populates="sale", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpSale id={self.id} no={self.sale_no!r} type={self.sale_type} status={self.status}>"


class SpSaleItem(SpareBase):
    """One line of a sale. `qty` is always in base units (pack sales are
    expanded: qty = packs_sold * part.pack_size) - sold_as/pack_qty are
    kept only for display/audit of how the line was actually entered."""

    __tablename__ = "sp_sale_items"

    id = Column(Integer, primary_key=True)
    sale_id = Column(Integer, ForeignKey("sp_sales.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    qty = Column(Integer, nullable=False)
    sold_as = Column(String(10), nullable=False, default="UNIT")  # "UNIT" or "PACK"
    pack_qty = Column(Integer, nullable=True)  # packs entered, if sold_as == "PACK"
    unit_price = Column(Numeric(12, 2), nullable=False)  # price per base unit
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    line_total = Column(Numeric(12, 2), nullable=False)
    # The part's cost_price AT THE TIME OF SALE (per base unit) - a
    # snapshot, since cost_price drifts over time as new stock is
    # purchased. NULL on rows saved before this column existed; see
    # reports_service.get_profit_report for the fallback used there.
    cost_price = Column(Numeric(12, 2), nullable=True)
    # sale_date + part.warranty_days AT THE TIME OF SALE, if the part
    # carried a warranty - NULL if the part had none, or predates this
    # column. See reports_service.search_warranty.
    warranty_expires_at = Column(DateTime, nullable=True)

    sale = relationship("SpSale", back_populates="items")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpSaleItem id={self.id} part_id={self.part_id} qty={self.qty}>"


class SpSaleReturn(SpareBase):
    """A return against a previously POSTED sale. Always increases stock
    (the goods physically come back)."""

    __tablename__ = "sp_sale_returns"

    id = Column(Integer, primary_key=True)
    return_no = Column(String(30), nullable=False, unique=True, index=True)
    sale_id = Column(Integer, ForeignKey("sp_sales.id"), nullable=False, index=True)
    return_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="POSTED")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    sale = relationship("SpSale")
    items = relationship(
        "SpSaleReturnItem", back_populates="sale_return", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpSaleReturn id={self.id} no={self.return_no!r}>"


class SpSaleReturnItem(SpareBase):
    __tablename__ = "sp_sale_return_items"

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("sp_sale_returns.id"), nullable=False, index=True)
    sale_item_id = Column(Integer, ForeignKey("sp_sale_items.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    qty = Column(Integer, nullable=False)
    unit_price = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    sale_return = relationship("SpSaleReturn", back_populates="items")
    sale_item = relationship("SpSaleItem")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpSaleReturnItem id={self.id} part_id={self.part_id} qty={self.qty}>"


class SpPurchaseReturn(SpareBase):
    """A return against a previously POSTED purchase (goods sent back to
    the supplier). Always decreases stock."""

    __tablename__ = "sp_purchase_returns"

    id = Column(Integer, primary_key=True)
    return_no = Column(String(30), nullable=False, unique=True, index=True)
    purchase_id = Column(Integer, ForeignKey("sp_purchases.id"), nullable=False, index=True)
    return_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)
    notes = Column(Text, nullable=True)
    status = Column(String(20), nullable=False, default="POSTED")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    purchase = relationship("SpPurchase")
    items = relationship(
        "SpPurchaseReturnItem", back_populates="purchase_return", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpPurchaseReturn id={self.id} no={self.return_no!r}>"


class SpPurchaseReturnItem(SpareBase):
    __tablename__ = "sp_purchase_return_items"

    id = Column(Integer, primary_key=True)
    return_id = Column(Integer, ForeignKey("sp_purchase_returns.id"), nullable=False, index=True)
    purchase_item_id = Column(Integer, ForeignKey("sp_purchase_items.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    qty = Column(Integer, nullable=False)
    unit_cost = Column(Numeric(12, 2), nullable=False)
    line_total = Column(Numeric(12, 2), nullable=False)

    purchase_return = relationship("SpPurchaseReturn", back_populates="items")
    purchase_item = relationship("SpPurchaseItem")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpPurchaseReturnItem id={self.id} part_id={self.part_id} qty={self.qty}>"


class SpPayment(SpareBase):
    """A standalone payment against a customer's or supplier's general
    account balance (not tied to one specific sale/purchase - see
    spare_parts.services.ledger_service for why: each sale/purchase's own
    paid/due fields stay an immutable record of what was collected AT THE
    TIME of that transaction, while later payments just reduce the running
    account balance, exactly like a real ledger/statement of account).

    direction "IN" = received from a customer (customer_id set, reduces
    what they owe). direction "OUT" = paid to a supplier (supplier_id
    set, reduces what we owe them)."""

    __tablename__ = "sp_payments"

    id = Column(Integer, primary_key=True)
    payment_no = Column(String(30), nullable=False, unique=True, index=True)
    direction = Column(String(10), nullable=False, index=True)  # "IN" or "OUT"
    customer_id = Column(Integer, ForeignKey("sp_customers.id"), nullable=True)
    supplier_id = Column(Integer, ForeignKey("sp_suppliers.id"), nullable=True)
    amount = Column(Numeric(12, 2), nullable=False)
    payment_method = Column(String(30), nullable=False, default="Cash")
    payment_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    notes = Column(Text, nullable=True)

    # "POSTED" or "CANCELLED" - same pattern as sales/purchases. A
    # cancelled payment is simply excluded from outstanding-balance and
    # ledger calculations, there is nothing to reverse (no stock effect).
    status = Column(String(20), nullable=False, default="POSTED")
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    customer = relationship("SpCustomer")
    supplier = relationship("SpSupplier")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpPayment id={self.id} no={self.payment_no!r} direction={self.direction} amount={self.amount}>"


class SpHeldSale(SpareBase):
    """A held/draft POS card: everything a sale-in-progress needs to be
    reconstructed later, but not yet a real sale - no stock ledger entry
    exists for it (see spare_parts/__init__.py: stock is only reduced
    when a sale is actually finalized via sales_service.create_sale).
    Used by the multi-card POS screen's Hold/Resume feature."""

    __tablename__ = "sp_held_sales"

    id = Column(Integer, primary_key=True)
    hold_no = Column(String(30), nullable=False, unique=True, index=True)
    reference = Column(String(150), nullable=True)  # customer name/phone/free note
    card_label = Column(String(50), nullable=True)  # the tab's display name, if renamed
    sale_type = Column(String(20), nullable=False)
    customer_id = Column(Integer, ForeignKey("sp_customers.id"), nullable=True)

    discount = Column(Numeric(12, 2), nullable=False, default=0)
    tax_percent = Column(Numeric(5, 2), nullable=False, default=0)
    paid = Column(Numeric(12, 2), nullable=False, default=0)
    payment_method = Column(String(30), nullable=False, default="Cash")
    notes = Column(Text, nullable=True)

    held_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)

    customer = relationship("SpCustomer")
    items = relationship("SpHeldSaleItem", back_populates="held_sale", cascade="all, delete-orphan")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpHeldSale id={self.id} no={self.hold_no!r}>"


class SpHeldSaleItem(SpareBase):
    __tablename__ = "sp_held_sale_items"

    id = Column(Integer, primary_key=True)
    held_sale_id = Column(Integer, ForeignKey("sp_held_sales.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    qty = Column(Integer, nullable=False)
    sold_as = Column(String(10), nullable=False, default="UNIT")
    pack_qty = Column(Integer, nullable=True)
    # "RETAIL" or "WHOLESALE" - which price this specific line used, kept
    # independently per line so a mixed card's exact mix survives Hold ->
    # Resume instead of collapsing to the draft's one overall sale_type
    # (see spare_parts.ui.sale_card_widget.SaleCardWidget.load_from_held_sale).
    price_type = Column(String(20), nullable=False, default="RETAIL")
    unit_price = Column(Numeric(12, 2), nullable=False)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    line_total = Column(Numeric(12, 2), nullable=False)

    held_sale = relationship("SpHeldSale", back_populates="items")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpHeldSaleItem id={self.id} part_id={self.part_id} qty={self.qty}>"


class SpStockTake(SpareBase):
    """A physical stock count session: freeze a system_qty snapshot per
    part when the count starts, enter counted_qty per line while DRAFT,
    then post once (stock_take_service.post_stock_take) - which is the
    only thing that actually writes adjustments to sp_stock_ledger, same
    "never write stock directly" rule as everything else in this module.
    No in-place edit once POSTED, same cancel-and-reenter convention as
    Purchases/Sales."""

    __tablename__ = "sp_stock_takes"

    id = Column(Integer, primary_key=True)
    take_no = Column(String(30), nullable=False, unique=True, index=True)
    take_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    status = Column(String(20), nullable=False, default="DRAFT")  # "DRAFT" or "POSTED"
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    items = relationship(
        "SpStockTakeItem", back_populates="stock_take", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpStockTake id={self.id} no={self.take_no!r} status={self.status}>"


class SpStockTakeItem(SpareBase):
    __tablename__ = "sp_stock_take_items"

    id = Column(Integer, primary_key=True)
    stock_take_id = Column(Integer, ForeignKey("sp_stock_takes.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    # The stock balance at the moment this count STARTED (snapshot, not
    # live) - the diff posted is always counted_qty - system_qty,
    # regardless of movements that happen elsewhere while this stays
    # DRAFT. See stock_take_service.post_stock_take for the live-drift
    # warning shown at post time.
    system_qty = Column(Integer, nullable=False)
    counted_qty = Column(Integer, nullable=True)  # NULL = not counted yet

    stock_take = relationship("SpStockTake", back_populates="items")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return (
            f"<SpStockTakeItem id={self.id} part_id={self.part_id} "
            f"system={self.system_qty} counted={self.counted_qty}>"
        )


class SpQuotation(SpareBase):
    """A pre-sale price quote - deliberately NOT a stock hold (no
    sp_stock_ledger effect, no reservation against other open POS cards)
    and NOT in-place editable once CONVERTED/CANCELLED. Converting into a
    real sale goes through the existing, unmodified sales_service.create_sale
    (quotations_service.convert_to_sale), honoring the quoted unit_price
    as-is rather than repricing to current part prices."""

    __tablename__ = "sp_quotations"

    id = Column(Integer, primary_key=True)
    quote_no = Column(String(30), nullable=False, unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("sp_customers.id"), nullable=True)
    # Same rationale as sp_sales.walk_in_customer_name - a quotation can
    # be for a walk-in too, and the typed name should survive even
    # without a registered SpCustomer.
    walk_in_customer_name = Column(String(150), nullable=True)
    sale_type = Column(String(20), nullable=False, default="RETAIL")  # "RETAIL" or "WHOLESALE"
    quote_date = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    valid_until = Column(DateTime, nullable=True)

    subtotal = Column(Numeric(12, 2), nullable=False, default=0)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    tax_percent = Column(Numeric(5, 2), nullable=False, default=0)
    tax_amount = Column(Numeric(12, 2), nullable=False, default=0)
    total = Column(Numeric(12, 2), nullable=False, default=0)

    # "DRAFT" / "CONVERTED" / "CANCELLED" / "EXPIRED"
    status = Column(String(20), nullable=False, default="DRAFT")
    converted_sale_id = Column(Integer, ForeignKey("sp_sales.id"), nullable=True)
    notes = Column(Text, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    customer = relationship("SpCustomer")
    converted_sale = relationship("SpSale")
    items = relationship(
        "SpQuotationItem", back_populates="quotation", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpQuotation id={self.id} no={self.quote_no!r} status={self.status}>"


class SpQuotationItem(SpareBase):
    """Same shape as SpSaleItem minus cost_price - a quotation never
    affects profit/COGS reporting until (and unless) it's converted,
    at which point the resulting SpSaleItem gets its own cost_price
    snapshot the normal way."""

    __tablename__ = "sp_quotation_items"

    id = Column(Integer, primary_key=True)
    quotation_id = Column(Integer, ForeignKey("sp_quotations.id"), nullable=False, index=True)
    part_id = Column(Integer, ForeignKey("sp_parts.id"), nullable=False, index=True)

    qty = Column(Integer, nullable=False)
    sold_as = Column(String(10), nullable=False, default="UNIT")
    pack_qty = Column(Integer, nullable=True)
    unit_price = Column(Numeric(12, 2), nullable=False)
    discount = Column(Numeric(12, 2), nullable=False, default=0)
    line_total = Column(Numeric(12, 2), nullable=False)

    quotation = relationship("SpQuotation", back_populates="items")
    part = relationship("SpPart")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SpQuotationItem id={self.id} part_id={self.part_id} qty={self.qty}>"
