from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Index, Enum
from sqlalchemy.orm import relationship, declarative_base
import datetime as dt
import enum
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

Base = declarative_base()

def _get_pk_tz() -> dt.tzinfo:
    if ZoneInfo is not None:
        try:
            return ZoneInfo("Asia/Karachi")
        except Exception:
            pass
    return dt.timezone(dt.timedelta(hours=5))


_PK_TZ = _get_pk_tz()


def pk_now() -> dt.datetime:
    return dt.datetime.now(_PK_TZ).replace(tzinfo=None)


class CustomerType(str, enum.Enum):
    INDIVIDUAL = "INDIVIDUAL"
    DEALER = "DEALER"

class Customer(Base):
    __tablename__ = "customers"
    __table_args__ = (
        Index('uq_business_cnic', 'business_name', 'cnic', unique=True),
    )

    id = Column(Integer, primary_key=True, index=True)
    cnic = Column(String(20), nullable=True, unique=True, index=True) 
    name = Column(String(100), nullable=False)
    father_name = Column(String(100), nullable=True)
    business_name = Column(String(100), nullable=True)
    normalized_business_name = Column(String(100), nullable=True, unique=True, index=True) # Enforce strict uniqueness
    ntn = Column(String(20), nullable=True)
    phone = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    type = Column(String(20), default=CustomerType.INDIVIDUAL)
    is_deleted = Column(Boolean, default=False)
    
    created_at = Column(DateTime, default=dt.datetime.utcnow)
    
    invoices = relationship("Invoice", back_populates="customer")

class ProductModel(Base):
    __tablename__ = "product_models"
    
    id = Column(Integer, primary_key=True, index=True)
    model_name = Column(String(50), unique=True, index=True, nullable=False)
    make = Column(String(50), default="Honda")
    engine_capacity = Column(String(20), nullable=True)
    
    pct_code = Column(String(20), nullable=True)
    item_code = Column(String(50), nullable=True)
    
    motorcycles = relationship("Motorcycle", back_populates="product_model")
    prices = relationship("Price", back_populates="product_model")
    purchase_order_items = relationship("PurchaseOrderItem", back_populates="product_model")

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(Integer, primary_key=True, index=True)
    invoice_number = Column(String(50), unique=True, index=True, nullable=False)
    pos_id = Column(String(20), nullable=False)
    usin = Column(String(50), nullable=False) # Updated to be Unique in context, but FBR allows multiple? USIN is unique POS ID basically.
    datetime = Column(DateTime, default=dt.datetime.utcnow)
    
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=True)
    customer = relationship("Customer", back_populates="invoices")
    
    total_sale_value = Column(Float, nullable=False)
    total_tax_charged = Column(Float, nullable=False)
    total_further_tax = Column(Float, default=0.0)
    total_quantity = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)
    
    payment_mode = Column(String(20), default="Cash")
    
    fbr_invoice_number = Column(String(50), nullable=True)
    is_fiscalized = Column(Boolean, default=False)
    sync_status = Column(String(20), default="PENDING")
    status_updated_at = Column(DateTime, default=dt.datetime.utcnow)
    fbr_response_code = Column(String(10), nullable=True)
    fbr_response_message = Column(String(255), nullable=True)
    fbr_full_response = Column(JSON, nullable=True)
    
    items = relationship("InvoiceItem", back_populates="invoice", cascade="all, delete-orphan")

class InvoiceItem(Base):
    __tablename__ = "invoice_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=False)
    
    motorcycle_id = Column(Integer, ForeignKey("motorcycles.id"), nullable=True)
    motorcycle = relationship("Motorcycle")
    
    item_code = Column(String(50), nullable=False)
    item_name = Column(String(100), nullable=False)
    pct_code = Column(String(20), nullable=True)
    
    quantity = Column(Float, nullable=False)
    tax_rate = Column(Float, nullable=False)
    sale_value = Column(Float, nullable=False)
    tax_charged = Column(Float, nullable=False)
    further_tax = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=False)
    discount = Column(Float, default=0.0)
    
    invoice = relationship("Invoice", back_populates="items")


class AdvanceBooking(Base):
    __tablename__ = "advance_bookings"

    id = Column(Integer, primary_key=True, index=True)
    booking_number = Column(String(50), unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=pk_now, index=True)

    customer_name = Column(String(100), nullable=False)
    customer_phone = Column(String(20), nullable=True)
    motorcycle_model = Column(String(50), nullable=False)
    model_code = Column(String(30), index=True, nullable=True)
    model_seq = Column(Integer, index=True, nullable=True)
    color = Column(String(30), nullable=False)

    total_price = Column(Float, nullable=False)
    advance_paid = Column(Float, nullable=False)
    balance_amount = Column(Float, nullable=False)
    delivery_paid = Column(Float, default=0.0, nullable=False)

    status = Column(String(20), default="ACTIVE", index=True)
    delivered_at = Column(DateTime, nullable=True, index=True)
    advance_remaining = Column(Float, default=0.0, nullable=False)
    advance_applied = Column(Float, default=0.0, nullable=False)


class AdvanceBookingModelCounter(Base):
    __tablename__ = "advance_booking_model_counters"

    id = Column(Integer, primary_key=True, index=True)
    model_code = Column(String(30), unique=True, index=True, nullable=False)
    last_seq = Column(Integer, default=0, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, index=True)


class AdvanceBookingAudit(Base):
    __tablename__ = "advance_booking_audit"

    id = Column(Integer, primary_key=True, index=True)
    booking_number = Column(String(50), index=True, nullable=False)
    action = Column(String(30), index=True, nullable=False)
    amount = Column(Float, nullable=False)
    before_advance_remaining = Column(Float, nullable=False)
    after_advance_remaining = Column(Float, nullable=False)
    before_balance_amount = Column(Float, nullable=True)
    after_balance_amount = Column(Float, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    note = Column(String(255), nullable=True)

class CapturedData(Base):
    __tablename__ = "captured_data"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=True)
    father = Column(String(100), nullable=True)
    cnic = Column(String(20), nullable=True)
    cell = Column(String(20), nullable=True)
    address = Column(String(255), nullable=True)
    
    chassis_number = Column(String(50), unique=True, index=True, nullable=False)
    engine_number = Column(String(50), nullable=True)
    color = Column(String(30), nullable=True)
    model = Column(String(50), nullable=True)
    
    is_deleted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=dt.datetime.utcnow)

class Motorcycle(Base):
    __tablename__ = "motorcycles"

    id = Column(Integer, primary_key=True, index=True)
    
    product_model_id = Column(Integer, ForeignKey("product_models.id"), nullable=False)
    product_model = relationship("ProductModel", back_populates="motorcycles")
    
    vin = Column(String(50), unique=True, index=True, nullable=True)
    chassis_number = Column(String(50), unique=True, index=True, nullable=False)
    engine_number = Column(String(50), unique=True, index=True, nullable=False)
    
    year = Column(Integer, nullable=False)
    color = Column(String(30), nullable=True)
    
    cost_price = Column(Float, nullable=False)
    sale_price = Column(Float, nullable=False)
    
    status = Column(String(20), default="IN_STOCK")
    purchase_date = Column(DateTime, default=dt.datetime.utcnow)
    
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=True)
    supplier = relationship("Supplier", back_populates="motorcycles")

    @property
    def model(self):
        return self.product_model.model_name if self.product_model else None

    @property
    def make(self):
        return self.product_model.make if self.product_model else None

class Price(Base):
    __tablename__ = "prices"

    id = Column(Integer, primary_key=True, index=True)
    
    product_model_id = Column(Integer, ForeignKey("product_models.id"), nullable=False)
    product_model = relationship("ProductModel", back_populates="prices")
    
    base_price = Column(Float, nullable=False)
    tax_amount = Column(Float, nullable=False)
    levy_amount = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    
    optional_features = Column(JSON, nullable=True)
    
    effective_date = Column(DateTime, default=dt.datetime.utcnow, index=True)
    expiration_date = Column(DateTime, nullable=True, index=True)
    currency = Column(String(10), default='Rs')

    __table_args__ = (
        Index('idx_price_model_active', 'product_model_id', 'expiration_date'),
    )

    @property
    def model(self):
        return self.product_model.model_name if self.product_model else None

class Supplier(Base):
    __tablename__ = "suppliers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    contact_person = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    email = Column(String(100), nullable=True)
    address = Column(String(255), nullable=True)
    
    motorcycles = relationship("Motorcycle", back_populates="supplier")

class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"

    id = Column(Integer, primary_key=True, index=True)
    supplier_id = Column(Integer, ForeignKey("suppliers.id"), nullable=False)
    order_date = Column(DateTime, default=dt.datetime.utcnow)
    status = Column(String(20), default="PENDING")
    total_amount = Column(Float, default=0.0)
    
    supplier = relationship("Supplier")
    items = relationship("PurchaseOrderItem", back_populates="order", cascade="all, delete-orphan")

class PurchaseOrderItem(Base):
    __tablename__ = "purchase_order_items"

    id = Column(Integer, primary_key=True, index=True)
    po_id = Column(Integer, ForeignKey("purchase_orders.id"), nullable=False)
    
    product_model_id = Column(Integer, ForeignKey("product_models.id"), nullable=False)
    product_model = relationship("ProductModel", back_populates="purchase_order_items")
    
    color = Column(String(30), nullable=True)
    quantity = Column(Integer, nullable=False)
    unit_price = Column(Float, nullable=False)
    total_price = Column(Float, nullable=False)
    
    order = relationship("PurchaseOrder", back_populates="items")

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), default="sales")
    is_active = Column(Boolean, default=True)

class FBRConfiguration(Base):
    __tablename__ = "fbr_configurations"

    id = Column(Integer, primary_key=True, index=True)
    environment = Column(String(20), unique=True, nullable=False)
    is_active = Column(Boolean, default=False)
    
    api_base_url = Column(String(255), nullable=False)
    pos_id = Column(String(50), nullable=True)
    usin = Column(String(50), nullable=True)
    auth_token = Column(String(500), nullable=True)
    secret_key = Column(String(255), nullable=True) # New field for HMAC signature
    
    tax_rate = Column(Float, default=18.0)
    invoice_type = Column(String(20), default="Standard")
    discount = Column(Float, default=0.0)
    
    pct_code = Column(String(20), default="8711.2010")
    item_code = Column(String(50), nullable=True)
    item_name = Column(String(100), nullable=True)
    business_name = Column(String(100), nullable=True, default="Ehsan Trader")
    
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

class MigrationHistory(Base):
    __tablename__ = "migration_history"

    id = Column(Integer, primary_key=True, index=True)
    version = Column(Integer, nullable=False, unique=True)
    description = Column(String(255), nullable=True)
    applied_at = Column(DateTime, default=dt.datetime.utcnow)

# --- Spare Parts Ledger ---
class LedgerTransactionType(str, enum.Enum):
    CREDIT = "CREDIT"  # Deposit
    DEBIT = "DEBIT"    # Spare part order

class SpareLedgerTransaction(Base):
    __tablename__ = "spare_ledger_transactions"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    trans_type = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    reference_number = Column(String(50), nullable=True)
    description = Column(String(255), nullable=True)
    cash_type = Column(String(20), nullable=True, default="HARD_CASH") # BANK or HARD_CASH
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    month_key = Column(String(7), index=True)  # YYYY-MM of closing cycle (6th..5th)

class SpareLedgerMonthlyClose(Base):
    __tablename__ = "spare_ledger_monthly_close"

    id = Column(Integer, primary_key=True, index=True)
    month_key = Column(String(7), unique=True, nullable=False)  # YYYY-MM representing cycle ending on 5th
    closed_at = Column(DateTime, nullable=False)
    opening_balance = Column(Float, default=0.0)
    total_credits = Column(Float, default=0.0)
    total_debits = Column(Float, default=0.0)
    closing_balance = Column(Float, default=0.0)
    carried_forward = Column(Float, default=0.0)
    status = Column(String(10), default="CLOSED")

class SpareLedgerAudit(Base):
    __tablename__ = "spare_ledger_audit"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False)  # CREATE_TXN, UPDATE_TXN, CLOSE_MONTH, EXPORT
    timestamp = Column(DateTime, default=dt.datetime.utcnow)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    transaction_id = Column(Integer, ForeignKey("spare_ledger_transactions.id"), nullable=True)
    details = Column(JSON, nullable=True)

class CreditBookDirection(str, enum.Enum):
    DEBIT = "DEBIT"
    CREDIT = "CREDIT"

class CreditBookEntryType(str, enum.Enum):
    SALE = "SALE"
    PAYMENT = "PAYMENT"
    ADJUSTMENT = "ADJUSTMENT"
    OPENING = "OPENING"

class CreditBookTransaction(Base):
    __tablename__ = "credit_book_transactions"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    direction = Column(String(10), nullable=False, index=True)
    entry_type = Column(String(20), nullable=False, index=True)
    amount = Column(Float, nullable=False)
    reference_number = Column(String(80), nullable=True, index=True)
    description = Column(String(500), nullable=True)
    related_invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True, index=True)
    finance_application_id = Column(Integer, ForeignKey("finance_applications.id"), nullable=True, index=True)
    finance_loan_id = Column(Integer, ForeignKey("finance_loans.id"), nullable=True, index=True)
    created_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    month_key = Column(String(7), index=True)
    is_void = Column(Boolean, default=False, index=True)
    voided_at = Column(DateTime, nullable=True)
    void_reason = Column(String(255), nullable=True)
    original_transaction_id = Column(Integer, ForeignKey("credit_book_transactions.id"), nullable=True, index=True)

    customer = relationship("Customer")
    invoice = relationship("Invoice")

class CreditBookAudit(Base):
    __tablename__ = "credit_book_audit"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    transaction_id = Column(Integer, ForeignKey("credit_book_transactions.id"), nullable=True, index=True)
    details = Column(JSON, nullable=True)

class FinanceApplicantType(str, enum.Enum):
    CUSTOMER = "CUSTOMER"
    DEALER = "DEALER"

class FinanceApplicationStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    SUBMITTED = "SUBMITTED"
    IN_REVIEW = "IN_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

class FinanceLoanStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"
    DEFAULTED = "DEFAULTED"
    REFINANCED = "REFINANCED"

class FinanceInstallmentStatus(str, enum.Enum):
    DUE = "DUE"
    PARTIAL = "PARTIAL"
    PAID = "PAID"
    LATE = "LATE"
    WAIVED = "WAIVED"

class FinancePaymentStatus(str, enum.Enum):
    POSTED = "POSTED"
    REVERSED = "REVERSED"
    PENDING = "PENDING"

class FinancePaymentMethod(str, enum.Enum):
    CASH = "CASH"
    BANK_TRANSFER = "BANK_TRANSFER"
    CHEQUE = "CHEQUE"
    ONLINE = "ONLINE"
    CARD = "CARD"

class DealerProfile(Base):
    __tablename__ = "dealer_profiles"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, unique=True, index=True)
    is_verified = Column(Boolean, default=False, index=True)
    verified_at = Column(DateTime, nullable=True)
    credit_limit = Column(Float, default=0.0)
    bulk_auto_approve = Column(Boolean, default=False)
    max_active_loans = Column(Integer, default=10)
    risk_tier_override = Column(String(20), nullable=True)
    notes = Column(String(500), nullable=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

    customer = relationship("Customer")

class FinanceApplication(Base):
    __tablename__ = "finance_applications"

    id = Column(Integer, primary_key=True, index=True)
    applicant_type = Column(String(20), nullable=False, default=FinanceApplicantType.CUSTOMER, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    dealer_profile_id = Column(Integer, ForeignKey("dealer_profiles.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default=FinanceApplicationStatus.DRAFT, index=True)

    requested_term_months = Column(Integer, nullable=False)
    down_payment_percent = Column(Float, nullable=False)
    interest_rate_annual = Column(Float, nullable=False)

    cash_total_price = Column(Float, nullable=False, default=0.0)
    requested_total_price = Column(Float, nullable=False, default=0.0)
    requested_down_payment_amount = Column(Float, nullable=False, default=0.0)
    requested_financed_amount = Column(Float, nullable=False, default=0.0)

    monthly_income = Column(Float, nullable=True)
    income_verified = Column(Boolean, default=False)
    income_verification_method = Column(String(50), nullable=True)

    credit_score = Column(Integer, nullable=True, index=True)
    risk_tier = Column(String(20), nullable=True, index=True)
    risk_profile = Column(JSON, nullable=True)

    bureau_provider = Column(String(60), nullable=True)
    bureau_reference = Column(String(120), nullable=True, index=True)
    bureau_score = Column(Integer, nullable=True)

    decision_reason = Column(String(500), nullable=True)
    approved_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    approved_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, index=True)

    customer = relationship("Customer")
    dealer_profile = relationship("DealerProfile")
    items = relationship("FinanceApplicationItem", back_populates="application", cascade="all, delete-orphan")

class FinanceApplicationItem(Base):
    __tablename__ = "finance_application_items"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("finance_applications.id"), nullable=False, index=True)
    motorcycle_id = Column(Integer, ForeignKey("motorcycles.id"), nullable=True, index=True)
    product_model_id = Column(Integer, ForeignKey("product_models.id"), nullable=True, index=True)
    color = Column(String(30), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    cash_unit_price = Column(Float, nullable=False, default=0.0)
    cash_total_price = Column(Float, nullable=False, default=0.0)
    unit_price = Column(Float, nullable=False, default=0.0)
    total_price = Column(Float, nullable=False, default=0.0)

    application = relationship("FinanceApplication", back_populates="items")
    motorcycle = relationship("Motorcycle")
    product_model = relationship("ProductModel")

class FinanceInventoryReservation(Base):
    __tablename__ = "finance_inventory_reservations"

    id = Column(Integer, primary_key=True, index=True)
    application_id = Column(Integer, ForeignKey("finance_applications.id"), nullable=False, index=True)
    motorcycle_id = Column(Integer, ForeignKey("motorcycles.id"), nullable=False, unique=True, index=True)
    reserved_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    released_at = Column(DateTime, nullable=True, index=True)
    status = Column(String(20), nullable=False, default="RESERVED", index=True)

class FinanceLoan(Base):
    __tablename__ = "finance_loans"

    id = Column(Integer, primary_key=True, index=True)
    loan_number = Column(String(40), nullable=False, unique=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    dealer_profile_id = Column(Integer, ForeignKey("dealer_profiles.id"), nullable=True, index=True)
    application_id = Column(Integer, ForeignKey("finance_applications.id"), nullable=True, index=True)
    status = Column(String(20), nullable=False, default=FinanceLoanStatus.ACTIVE, index=True)

    cash_total_price = Column(Float, nullable=False, default=0.0)
    credit_total_price = Column(Float, nullable=False, default=0.0)
    principal_amount = Column(Float, nullable=False, default=0.0)
    down_payment_amount = Column(Float, nullable=False, default=0.0)
    financed_amount = Column(Float, nullable=False, default=0.0)
    interest_rate_annual = Column(Float, nullable=False, default=0.0)
    term_months = Column(Integer, nullable=False, default=12)
    emi_amount = Column(Float, nullable=False, default=0.0)

    total_interest = Column(Float, nullable=False, default=0.0)
    total_payable = Column(Float, nullable=False, default=0.0)
    currency = Column(String(10), nullable=False, default="PKR")

    late_fee_flat = Column(Float, nullable=False, default=0.0)
    late_fee_daily_percent = Column(Float, nullable=False, default=0.0)
    grace_days = Column(Integer, nullable=False, default=0)

    start_date = Column(DateTime, nullable=False, index=True)
    next_due_date = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    closed_at = Column(DateTime, nullable=True)
    closed_reason = Column(String(255), nullable=True)

    customer = relationship("Customer")
    dealer_profile = relationship("DealerProfile")
    application = relationship("FinanceApplication")
    items = relationship("FinanceLoanItem", back_populates="loan", cascade="all, delete-orphan")
    installments = relationship("FinanceInstallment", back_populates="loan", cascade="all, delete-orphan")
    payments = relationship("FinancePayment", back_populates="loan", cascade="all, delete-orphan")

class FinanceLoanItem(Base):
    __tablename__ = "finance_loan_items"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("finance_loans.id"), nullable=False, index=True)
    motorcycle_id = Column(Integer, ForeignKey("motorcycles.id"), nullable=True, index=True)
    product_model_id = Column(Integer, ForeignKey("product_models.id"), nullable=True, index=True)
    color = Column(String(30), nullable=True)
    quantity = Column(Integer, nullable=False, default=1)
    cash_unit_price = Column(Float, nullable=False, default=0.0)
    cash_total_price = Column(Float, nullable=False, default=0.0)
    unit_price = Column(Float, nullable=False, default=0.0)
    total_price = Column(Float, nullable=False, default=0.0)

    loan = relationship("FinanceLoan", back_populates="items")
    motorcycle = relationship("Motorcycle")
    product_model = relationship("ProductModel")

class FinanceInstallment(Base):
    __tablename__ = "finance_installments"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("finance_loans.id"), nullable=False, index=True)
    installment_no = Column(Integer, nullable=False, index=True)
    due_date = Column(DateTime, nullable=False, index=True)

    principal_due = Column(Float, nullable=False, default=0.0)
    interest_due = Column(Float, nullable=False, default=0.0)
    fees_due = Column(Float, nullable=False, default=0.0)
    total_due = Column(Float, nullable=False, default=0.0)
    late_fee_accrued = Column(Float, nullable=False, default=0.0)
    late_fee_last_calculated_at = Column(DateTime, nullable=True, index=True)

    status = Column(String(20), nullable=False, default=FinanceInstallmentStatus.DUE, index=True)
    paid_principal = Column(Float, nullable=False, default=0.0)
    paid_interest = Column(Float, nullable=False, default=0.0)
    paid_fees = Column(Float, nullable=False, default=0.0)
    paid_total = Column(Float, nullable=False, default=0.0)
    paid_at = Column(DateTime, nullable=True, index=True)

    loan = relationship("FinanceLoan", back_populates="installments")

class FinancePayment(Base):
    __tablename__ = "finance_payments"

    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("finance_loans.id"), nullable=False, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    amount = Column(Float, nullable=False)
    method = Column(String(30), nullable=False, default=FinancePaymentMethod.CASH, index=True)
    provider = Column(String(50), nullable=True)
    reference_number = Column(String(100), nullable=True, index=True)
    status = Column(String(20), nullable=False, default=FinancePaymentStatus.POSTED, index=True)
    received_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    payment_metadata = Column("metadata", JSON, nullable=True)

    loan = relationship("FinanceLoan", back_populates="payments")
    allocations = relationship("FinancePaymentAllocation", back_populates="payment", cascade="all, delete-orphan")

class FinancePaymentAllocation(Base):
    __tablename__ = "finance_payment_allocations"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(Integer, ForeignKey("finance_payments.id"), nullable=False, index=True)
    installment_id = Column(Integer, ForeignKey("finance_installments.id"), nullable=False, index=True)
    principal_amount = Column(Float, nullable=False, default=0.0)
    interest_amount = Column(Float, nullable=False, default=0.0)
    fees_amount = Column(Float, nullable=False, default=0.0)
    total_allocated = Column(Float, nullable=False, default=0.0)

    payment = relationship("FinancePayment", back_populates="allocations")
    installment = relationship("FinanceInstallment")

class FinanceRefinance(Base):
    __tablename__ = "finance_refinance"

    id = Column(Integer, primary_key=True, index=True)
    old_loan_id = Column(Integer, ForeignKey("finance_loans.id"), nullable=False, index=True)
    new_loan_id = Column(Integer, ForeignKey("finance_loans.id"), nullable=False, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    reason = Column(String(500), nullable=True)
    fees = Column(Float, nullable=False, default=0.0)

class FinanceCreditBureauInquiry(Base):
    __tablename__ = "finance_credit_bureau_inquiries"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    application_id = Column(Integer, ForeignKey("finance_applications.id"), nullable=True, index=True)
    provider = Column(String(60), nullable=False)
    request_id = Column(String(120), nullable=True, index=True)
    status = Column(String(30), nullable=False, default="PENDING", index=True)
    score = Column(Integer, nullable=True)
    risk_grade = Column(String(20), nullable=True)
    response_summary = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)

class FinancePortalToken(Base):
    __tablename__ = "finance_portal_tokens"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    token = Column(String(64), nullable=False, unique=True, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True, index=True)
    revoked_at = Column(DateTime, nullable=True, index=True)

class FinanceAudit(Base):
    __tablename__ = "finance_audit"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String(60), nullable=False, index=True)
    timestamp = Column(DateTime, default=dt.datetime.utcnow, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    entity_type = Column(String(60), nullable=True, index=True)
    entity_id = Column(Integer, nullable=True, index=True)
    details = Column(JSON, nullable=True)

# --- SMS & WhatsApp Module ---
class SMSStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENDING = "SENDING"
    SENT = "SENT"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    SCHEDULED = "SCHEDULED"

class SMSCampaign(Base):
    __tablename__ = "sms_campaigns"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True)
    template = Column(String(1000), nullable=False)
    channel = Column(String(20), default="SMS") # SMS, WHATSAPP
    total_recipients = Column(Integer, default=0)
    sent_count = Column(Integer, default=0)
    failed_count = Column(Integer, default=0)
    status = Column(String(20), default="PENDING", index=True) # PENDING, RUNNING, COMPLETED, PAUSED
    error_message = Column(String(500), nullable=True)
    
    # Metadata for Excel-based campaigns
    excel_file_path = Column(String(255), nullable=True)
    merge_fields = Column(JSON, nullable=True) # List of column names found in Excel
    
    scheduled_at = Column(DateTime, nullable=True, index=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    started_at = Column(DateTime, nullable=True)
    paused_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    
    messages = relationship("SMSQueue", back_populates="campaign", cascade="all, delete-orphan")

class SMSQueue(Base):
    __tablename__ = "sms_queue"

    id = Column(Integer, primary_key=True, index=True)
    campaign_id = Column(Integer, ForeignKey("sms_campaigns.id"), nullable=True)
    channel = Column(String(20), default="SMS") # SMS, WHATSAPP
    phone_number = Column(String(20), nullable=False, index=True)
    recipient_name = Column(String(100), nullable=True)
    message = Column(String(1000), nullable=False)
    status = Column(String(20), default=SMSStatus.PENDING, index=True)
    
    # Retry Logic Fields
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    next_retry_at = Column(DateTime, nullable=True, index=True)
    retry_history = Column(JSON, nullable=True) # List of {timestamp, error, attempt}
    
    error_message = Column(String(255), nullable=True)
    
    # Reference to invoice if applicable
    invoice_id = Column(Integer, ForeignKey("invoices.id"), nullable=True)
    
    # Analytics data
    is_read = Column(Boolean, default=False)
    read_at = Column(DateTime, nullable=True)
    response_received = Column(Boolean, default=False)
    last_response = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    sent_at = Column(DateTime, nullable=True)
    scheduled_at = Column(DateTime, nullable=True, index=True)
    
    campaign = relationship("SMSCampaign", back_populates="messages")
    invoice = relationship("Invoice")

class SMSConfiguration(Base):
    __tablename__ = "sms_configurations"

    id = Column(Integer, primary_key=True, index=True)
    is_enabled = Column(Boolean, default=False)
    gateway_type = Column(String(20), default="WIFI") # WIFI or CLOUD
    
    # WiFi Gateway Settings (SMS)
    gateway_ip = Column(String(100), nullable=True) 
    gateway_port = Column(String(10), default="8080")
    use_https = Column(Boolean, default=False)
    
    # Cloud/Common Settings
    api_url = Column(String(255), nullable=True) # Cloud Server URL
    cloud_username = Column(String(100), nullable=True)
    cloud_password = Column(String(100), nullable=True)
    gateway_username = Column(String(100), nullable=True) # WiFi Username
    gateway_password = Column(String(100), nullable=True) # WiFi Password
    api_key = Column(String(100), nullable=True)
    delay_seconds = Column(Integer, default=5)
    
    # Templates
    invoice_template = Column(String(500), default="Dear {customer}, your invoice {invoice_no} for Rs. {amount} has been generated. FBR ID: {fbr_id}")
    booking_template = Column(String(500), default="Dear {customer}, your booking for {model} ({color}) is confirmed. Booking #: {booking_no}. Paid: Rs. {paid}. Balance: Rs. {balance}.")
    otp_template = Column(String(500), default="Your verification code is {code}")
    
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)

class AuditLog(Base):
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True) # Optional link to user table if it exists
    action = Column(String(50), nullable=False) # DELETE, RETRY, START, etc.
    resource_type = Column(String(50), nullable=False) # CAMPAIGN, MESSAGE
    resource_id = Column(Integer, nullable=False)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)

class AppConfiguration(Base):
    __tablename__ = "app_configurations"

    id = Column(Integer, primary_key=True, index=True)
    auto_push_enabled = Column(Boolean, default=False)
    auto_push_interval = Column(Integer, default=5) # seconds
    address_shortcodes = Column(JSON, nullable=True)
    urdu_font_enabled = Column(Boolean, default=False)
    urdu_font_family = Column(String(200), default="Jameel Noori Nastaleeq")
    urdu_font_path = Column(String(500), default="")
    urdu_font_size = Column(Integer, default=14)
    ui_font_enabled = Column(Boolean, default=False)
    ui_font_family = Column(String(200), default="")
    ui_font_size = Column(Integer, default=13)
    sidebar_font_size = Column(Integer, default=15)
    sidebar_group_font_size = Column(Integer, default=12)
    sidebar_header_font_size = Column(Integer, default=18)
    sidebar_footer_font_size = Column(Integer, default=15)
    sidebar_exit_font_size = Column(Integer, default=16)
    sidebar_collapsed_font_size = Column(Integer, default=18)
    
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow)


class ReportTemplate(Base):
    __tablename__ = "report_templates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True)
    description = Column(String(500), nullable=True)
    definition = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=True)
    created_by_user_id = Column(Integer, nullable=True)
    created_by_role = Column(String(20), default="admin")
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, index=True)


class ReportSchedule(Base):
    __tablename__ = "report_schedules"

    id = Column(Integer, primary_key=True, index=True)
    template_id = Column(Integer, ForeignKey("report_templates.id"), nullable=False, index=True)
    enabled = Column(Boolean, default=True, index=True)
    interval_minutes = Column(Integer, default=60)
    export_format = Column(String(10), default="pdf")
    recipients = Column(JSON, nullable=True)
    last_run_at = Column(DateTime, nullable=True, index=True)
    created_by_user_id = Column(Integer, nullable=True)
    created_by_role = Column(String(20), default="admin")
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, index=True)

    template = relationship("ReportTemplate")


class ReportRun(Base):
    __tablename__ = "report_runs"

    id = Column(Integer, primary_key=True, index=True)
    schedule_id = Column(Integer, ForeignKey("report_schedules.id"), nullable=False, index=True)
    status = Column(String(20), default="STARTED", index=True)
    started_at = Column(DateTime, default=dt.datetime.utcnow, index=True)
    finished_at = Column(DateTime, nullable=True, index=True)
    file_path = Column(String(500), nullable=True)
    error_message = Column(String(1000), nullable=True)

    schedule = relationship("ReportSchedule")


class PrintTemplateLayout(Base):
    __tablename__ = "print_template_layouts"

    id = Column(Integer, primary_key=True, index=True)
    template_name = Column(String(80), unique=True, index=True, nullable=False)
    positions = Column(JSON, nullable=False)
    updated_at = Column(DateTime, default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, index=True)

