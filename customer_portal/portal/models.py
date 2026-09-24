from django.db import models
from django.contrib.auth.models import User


# Codename/label pairs for the fine-grained access a Staff account can be
# granted by an Admin. Registered as real Django permissions (see
# StaffAccess below) so they work with the standard `user.has_perm(...)`
# / `{% if perms.portal.xxx %}` machinery.
STAFF_MODULES = [
    ('view_dashboard', 'View admin dashboard'),
    ('view_customers', 'View customers'),
    ('view_customer_summary', 'View customer summary'),
    ('view_sales', 'View credit sales'),
    ('view_payments', 'View payments'),
    ('view_inventory', 'View inventory'),
    ('view_transactions', 'View transaction history'),
    ('view_portal_accounts', 'View customer portal accounts'),
    ('manage_portal_accounts', 'Create/reset/block customer portal accounts'),
    ('view_old_credit_ledger', 'View old running credit ledger'),
    ('view_finance_credit_ledger', 'View advance separate finance ledger'),
    ('view_combined_ledger', 'View combined credit ledger'),
    ('view_spare_ledger', 'View spare parts ledger'),
    ('export_data', 'Export sales/payments to CSV'),
    ('manage_customers', 'Add/edit customer records'),
    ('manage_product_models', 'Add/edit/delete product models'),
    ('manage_inventory', 'Add/edit/delete motorcycles'),
    ('manage_finance_sales', 'Add/edit/delete finance credit sales'),
    ('manage_finance_installments', 'Add/edit/delete finance installments'),
    ('manage_finance_ledger', 'Add/edit/delete finance ledger entries'),
    ('view_invoices', 'View submitted sales invoices'),
    ('create_invoices', 'Create new sales invoices and upload them to FBR'),
]


class StaffAccess(models.Model):
    """Not a real table - exists only to register the STAFF_MODULES permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = STAFF_MODULES

    def __str__(self):
        return 'Staff Access Permissions'


class UserProfile(models.Model):
    """Role for a django.contrib.auth.User in the customer portal's staff/admin area."""

    ADMIN = 'ADMIN'
    STAFF = 'STAFF'
    ROLE_CHOICES = [
        (ADMIN, 'Admin'),
        (STAFF, 'Staff'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default=STAFF)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'portal_user_profile'

    def __str__(self):
        return f"{self.user.username} ({self.get_role_display()})"


class Customer(models.Model):
    INDIVIDUAL = 'INDIVIDUAL'
    DEALER = 'DEALER'
    TYPE_CHOICES = [
        (INDIVIDUAL, 'Individual'),
        (DEALER, 'Dealer'),
    ]

    id = models.IntegerField(primary_key=True)
    cnic = models.CharField(max_length=20, null=False, unique=True)
    name = models.CharField(max_length=100)
    father_name = models.CharField(max_length=100, null=True)
    business_name = models.CharField(max_length=100, null=True)
    normalized_business_name = models.CharField(max_length=100, null=True, unique=True)
    ntn = models.CharField(max_length=20, null=True)
    phone = models.CharField(max_length=20, null=True)
    address = models.CharField(max_length=255, null=True)
    type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=INDIVIDUAL)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'customers'
        managed = False

    def __str__(self):
        return self.name


class ProductModel(models.Model):
    id = models.IntegerField(primary_key=True)
    model_name = models.CharField(max_length=50, unique=True)
    make = models.CharField(max_length=50, default='Honda')
    engine_capacity = models.CharField(max_length=20, null=True)
    pct_code = models.CharField(max_length=20, null=True)
    item_code = models.CharField(max_length=50, null=True)

    class Meta:
        db_table = 'product_models'
        managed = False

    def __str__(self):
        return self.model_name


class Motorcycle(models.Model):
    IN_STOCK = 'IN_STOCK'
    SOLD = 'SOLD'
    STATUS_CHOICES = [
        (IN_STOCK, 'In Stock'),
        (SOLD, 'Sold'),
    ]

    id = models.IntegerField(primary_key=True)
    product_model = models.ForeignKey(ProductModel, on_delete=models.DO_NOTHING, db_column='product_model_id')
    vin = models.CharField(max_length=50, null=True, unique=True)
    chassis_number = models.CharField(max_length=50, unique=True)
    engine_number = models.CharField(max_length=50, unique=True)
    year = models.IntegerField()
    color = models.CharField(max_length=30, null=True)
    cost_price = models.FloatField()
    sale_price = models.FloatField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=IN_STOCK)
    purchase_date = models.DateTimeField()

    class Meta:
        db_table = 'motorcycles'
        managed = False

    def __str__(self):
        return f"{self.chassis_number} - {self.product_model.model_name}"


class Price(models.Model):
    id = models.IntegerField(primary_key=True)
    product_model = models.ForeignKey(ProductModel, on_delete=models.DO_NOTHING, db_column='product_model_id')
    base_price = models.FloatField()
    tax_amount = models.FloatField()
    levy_amount = models.FloatField()
    total_price = models.FloatField()
    optional_features = models.JSONField(null=True, blank=True)
    effective_date = models.DateTimeField(null=True)
    expiration_date = models.DateTimeField(null=True)
    currency = models.CharField(max_length=10, default='Rs')

    class Meta:
        db_table = 'prices'
        managed = False

    def __str__(self):
        return f"{self.product_model.model_name} - {self.base_price}"


class Invoice(models.Model):
    """Mirrors the desktop app's SQLAlchemy Invoice model (app/db/models.py) -
    same shared `invoices` table. Only the columns the old (non-Digital-
    Invoicing) upload flow actually uses are declared here; the table also
    has several unused columns left over from an abandoned Digital
    Invoicing attempt (invoice_type, scenario_id, seller_province, etc.) -
    the desktop app never populates them either, so they're intentionally
    left out here too and simply stay NULL, matching existing rows."""

    PENDING = 'PENDING'
    SYNCED = 'SYNCED'
    FAILED = 'FAILED'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (SYNCED, 'Synced'),
        (FAILED, 'Failed'),
    ]

    id = models.IntegerField(primary_key=True)
    invoice_number = models.CharField(max_length=50, unique=True)
    pos_id = models.CharField(max_length=20)
    usin = models.CharField(max_length=50)
    datetime = models.DateTimeField(null=True)
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='customer_id', null=True)
    total_sale_value = models.FloatField()
    total_tax_charged = models.FloatField()
    total_further_tax = models.FloatField(default=0.0)
    total_quantity = models.FloatField()
    total_amount = models.FloatField()
    discount = models.FloatField(default=0.0)
    payment_mode = models.CharField(max_length=20, default='Cash')
    fbr_invoice_number = models.CharField(max_length=50, null=True, blank=True)
    is_fiscalized = models.BooleanField(default=False)
    sync_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PENDING)
    fbr_response_code = models.CharField(max_length=10, null=True, blank=True)
    fbr_response_message = models.CharField(max_length=255, null=True, blank=True)
    fbr_full_response = models.JSONField(null=True, blank=True)
    status_updated_at = models.DateTimeField(null=True)
    upload_attempts = models.IntegerField(default=0)
    max_upload_attempts = models.IntegerField(default=5)
    upload_priority = models.IntegerField(default=0)
    is_processing = models.BooleanField(default=False)

    class Meta:
        db_table = 'invoices'
        managed = False

    def __str__(self):
        return self.invoice_number


class InvoiceItem(models.Model):
    id = models.IntegerField(primary_key=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, db_column='invoice_id', related_name='items')
    motorcycle = models.ForeignKey(Motorcycle, on_delete=models.DO_NOTHING, db_column='motorcycle_id', null=True)
    item_code = models.CharField(max_length=50)
    item_name = models.CharField(max_length=100)
    pct_code = models.CharField(max_length=20, null=True, blank=True)
    quantity = models.FloatField()
    tax_rate = models.FloatField()
    sale_value = models.FloatField()
    tax_charged = models.FloatField()
    further_tax = models.FloatField(default=0.0)
    total_amount = models.FloatField()
    discount = models.FloatField(default=0.0)

    class Meta:
        db_table = 'invoice_items'
        managed = False

    def __str__(self):
        return f"{self.item_name} ({self.invoice.invoice_number})"


class FBRConfiguration(models.Model):
    """Read-only from the customer portal - the active FBR environment
    (base URL, POS ID, USIN, auth token, tax rules) is configured and
    switched exclusively from the desktop app's Settings screen. The portal
    only ever reads whichever row currently has is_active=True."""

    id = models.IntegerField(primary_key=True)
    environment = models.CharField(max_length=20, unique=True)
    is_active = models.BooleanField(default=False)
    api_base_url = models.CharField(max_length=255)
    pos_id = models.CharField(max_length=50, null=True, blank=True)
    usin = models.CharField(max_length=50, null=True, blank=True)
    auth_token = models.CharField(max_length=500, null=True, blank=True)
    secret_key = models.CharField(max_length=255, null=True, blank=True)
    tax_rate = models.FloatField(default=18.0)
    invoice_type = models.CharField(max_length=20, default='Standard')
    discount = models.FloatField(default=0.0)
    pos_fee = models.FloatField(default=1.0)
    pct_code = models.CharField(max_length=20, default='8711.2010')
    item_code = models.CharField(max_length=50, null=True, blank=True)
    item_name = models.CharField(max_length=100, null=True, blank=True)
    business_name = models.CharField(max_length=100, null=True, blank=True, default='Ehsan Trader')

    class Meta:
        db_table = 'fbr_configurations'
        managed = False

    def __str__(self):
        return self.environment


class FinanceCreditSale(models.Model):
    ACTIVE = 'ACTIVE'
    CLOSED = 'CLOSED'
    OVERDUE = 'OVERDUE'
    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (CLOSED, 'Closed'),
        (OVERDUE, 'Overdue'),
    ]

    id = models.IntegerField(primary_key=True)
    sale_id = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='customer_id')
    customer_name = models.CharField(max_length=100)
    chassis_no = models.CharField(max_length=50)
    engine_no = models.CharField(max_length=50, null=True)
    model = models.CharField(max_length=50, null=True)
    cash_price = models.FloatField(default=0.0)
    credit_price = models.FloatField(default=0.0)
    down_payment = models.FloatField(default=0.0)
    down_payment_method = models.CharField(max_length=50, default='Cash')
    duration_months = models.IntegerField(default=0)
    duration_days = models.IntegerField(default=0)
    installment_amount = models.FloatField(default=0.0)
    sale_date = models.DateTimeField()
    due_date = models.DateTimeField(null=True)
    remaining_balance = models.FloatField(default=0.0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    credit_type = models.CharField(max_length=50, default='Advanced Separate Finance')
    notes = models.CharField(max_length=500, null=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'finance_credit_sales'
        managed = False

    def __str__(self):
        return f"{self.sale_id} - {self.customer_name}"


class FinanceInstallment(models.Model):
    PENDING = 'PENDING'
    PAID = 'PAID'
    PARTIAL = 'PARTIAL'
    STATUS_CHOICES = [
        (PENDING, 'Pending'),
        (PAID, 'Paid'),
        (PARTIAL, 'Partial'),
    ]

    id = models.IntegerField(primary_key=True)
    payment_id = models.CharField(max_length=50, unique=True)
    sale = models.ForeignKey(FinanceCreditSale, on_delete=models.DO_NOTHING, db_column='sale_id')
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='customer_id')
    paid_amount = models.FloatField()
    payment_date = models.DateTimeField()
    payment_method = models.CharField(max_length=50, default='Cash')
    reference_no = models.CharField(max_length=50, null=True)
    notes = models.CharField(max_length=500, null=True)
    loan_id = models.IntegerField(null=True)
    installment_no = models.IntegerField(null=True)
    due_date = models.DateTimeField(null=True)
    principal_due = models.FloatField(default=0.0)
    interest_due = models.FloatField(default=0.0)
    fees_due = models.FloatField(default=0.0)
    total_due = models.FloatField(default=0.0)
    late_fee_accrued = models.FloatField(default=0.0)
    late_fee_last_calculated_at = models.DateTimeField(null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=PAID)
    paid_principal = models.FloatField(default=0.0)
    paid_interest = models.FloatField(default=0.0)
    paid_fees = models.FloatField(default=0.0)
    paid_total = models.FloatField(default=0.0)
    paid_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'finance_installments'
        managed = False
        ordering = ['-payment_date']

    def __str__(self):
        return f"{self.payment_id} - {self.paid_amount}"


class FinanceLedger(models.Model):
    id = models.IntegerField(primary_key=True)
    ledger_id = models.CharField(max_length=50, unique=True)
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='customer_id')
    sale = models.ForeignKey(FinanceCreditSale, on_delete=models.DO_NOTHING, db_column='sale_id', null=True)
    entry_type = models.CharField(max_length=20)
    description = models.CharField(max_length=500, null=True)
    debit = models.FloatField(default=0.0)
    credit = models.FloatField(default=0.0)
    balance = models.FloatField(default=0.0)
    entry_date = models.DateTimeField()
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'finance_ledger'
        managed = False
        ordering = ['-entry_date']

    def __str__(self):
        return f"{self.ledger_id} - {self.entry_type}"


class CustomerPortalAuth(models.Model):
    customer = models.OneToOneField(Customer, on_delete=models.CASCADE, db_column='customer_id')
    phone_number = models.CharField(max_length=20, unique=True)
    password_hash = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'customer_portal_auth'
        managed = True

    def __str__(self):
        return f"{self.customer.name} - {self.phone_number}"


class CreditSale(models.Model):
    ACTIVE = 'ACTIVE'
    CLOSED = 'CLOSED'
    OVERDUE = 'OVERDUE'
    STATUS_CHOICES = [
        (ACTIVE, 'Active'),
        (CLOSED, 'Closed'),
        (OVERDUE, 'Overdue'),
    ]

    id = models.IntegerField(primary_key=True)
    sale_date = models.DateTimeField()
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='buyer_id')
    buyer_type = models.CharField(max_length=20)
    duration_months = models.IntegerField(default=0)
    duration_days = models.IntegerField(default=0)

    total_cash_price = models.FloatField(default=0.0)
    total_credit_price = models.FloatField(default=0.0)
    advance_payment = models.FloatField(default=0.0)
    advance_payment_mode = models.CharField(max_length=50, default='Cash')
    remaining_amount = models.FloatField(default=0.0)

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=ACTIVE)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'credit_sales'
        managed = False

    def __str__(self):
        return f"Credit Sale {self.id} - {self.customer.name}"


class CreditSaleItem(models.Model):
    id = models.IntegerField(primary_key=True)
    sale = models.ForeignKey(CreditSale, on_delete=models.DO_NOTHING, db_column='sale_id')
    chassis_number = models.CharField(max_length=50, unique=True)
    model = models.CharField(max_length=50, null=True)
    color = models.CharField(max_length=30, null=True)
    cash_price = models.FloatField()
    credit_price = models.FloatField()

    class Meta:
        db_table = 'credit_sale_items'
        managed = False

    def __str__(self):
        return f"{self.model} - {self.chassis_number}"


class CreditPayment(models.Model):
    id = models.IntegerField(primary_key=True)
    payment_date = models.DateTimeField()
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='buyer_id')
    amount = models.FloatField()
    penalty_amount = models.FloatField(default=0.0)
    discount_amount = models.FloatField(default=0.0)
    net_amount = models.FloatField()
    payment_mode = models.CharField(max_length=50, default='Cash')
    invoice_reference = models.CharField(max_length=50, null=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'credit_payments'
        managed = False

    def __str__(self):
        return f"{self.id} - {self.customer.name}"


class BuyerLedger(models.Model):
    id = models.IntegerField(primary_key=True)
    date = models.DateTimeField()
    customer = models.ForeignKey(Customer, on_delete=models.DO_NOTHING, db_column='buyer_id')
    chassis_number = models.CharField(max_length=50, null=True)
    description = models.CharField(max_length=255, null=True)
    debit = models.FloatField(default=0.0)
    credit = models.FloatField(default=0.0)
    balance = models.FloatField(default=0.0)
    reference_id = models.IntegerField(null=True)
    reference_type = models.CharField(max_length=20, null=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'buyer_ledger'
        managed = False

    def __str__(self):
        return f"{self.id} - {self.customer.name}"


class SpareLedgerTransaction(models.Model):
    CREDIT = 'CREDIT'
    DEBIT = 'DEBIT'
    TRANS_TYPE_CHOICES = [
        (CREDIT, 'Credit'),
        (DEBIT, 'Debit'),
    ]

    BANK = 'BANK'
    HARD_CASH = 'HARD_CASH'
    CASH_TYPE_CHOICES = [
        (BANK, 'Bank'),
        (HARD_CASH, 'Cash'),
    ]

    id = models.IntegerField(primary_key=True)
    timestamp = models.DateTimeField()
    trans_type = models.CharField(max_length=10, choices=TRANS_TYPE_CHOICES)
    amount = models.FloatField()
    reference_number = models.CharField(max_length=50, null=True)
    description = models.CharField(max_length=255, null=True)
    cash_type = models.CharField(max_length=20, choices=CASH_TYPE_CHOICES, default=HARD_CASH)
    created_by_user_id = models.IntegerField(null=True)
    month_key = models.CharField(max_length=7, null=True)

    class Meta:
        db_table = 'spare_ledger_transactions'
        managed = False
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.id} - {self.trans_type} - {self.amount}"


class SpareLedgerMonthlyClose(models.Model):
    CLOSED = 'CLOSED'
    STATUS_CHOICES = [
        (CLOSED, 'Closed'),
    ]

    id = models.IntegerField(primary_key=True)
    month_key = models.CharField(max_length=7, unique=True)
    closed_at = models.DateTimeField()
    opening_balance = models.FloatField(default=0.0)
    total_credits = models.FloatField(default=0.0)
    total_debits = models.FloatField(default=0.0)
    closing_balance = models.FloatField(default=0.0)
    carried_forward = models.FloatField(default=0.0)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=CLOSED)

    class Meta:
        db_table = 'spare_ledger_monthly_close'
        managed = False
        ordering = ['-month_key']

    def __str__(self):
        return f"{self.month_key} - {self.closing_balance}"


class CapturedData(models.Model):
    id = models.IntegerField(primary_key=True)
    name = models.CharField(max_length=100, null=True)
    father = models.CharField(max_length=100, null=True)
    cnic = models.CharField(max_length=20, null=True)
    cell = models.CharField(max_length=20, null=True)
    chassis_number = models.CharField(max_length=50, null=True)
    engine_number = models.CharField(max_length=50, null=True)
    model = models.CharField(max_length=50, null=True)
    color = models.CharField(max_length=30, null=True)
    address = models.CharField(max_length=255, null=True)
    is_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'captured_data'
        managed = False

    def __str__(self):
        return f"{self.name} - {self.chassis_number}"
