from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Index, Enum
from sqlalchemy.orm import relationship, declarative_base
import datetime as dt
import enum

Base = declarative_base()

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
    created_at = Column(DateTime, default=dt.datetime.utcnow, index=True)

    customer_name = Column(String(100), nullable=False)
    motorcycle_model = Column(String(50), nullable=False)
    color = Column(String(30), nullable=False)

    total_price = Column(Float, nullable=False)
    advance_paid = Column(Float, nullable=False)
    balance_amount = Column(Float, nullable=False)

    status = Column(String(20), default="ACTIVE", index=True)

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

