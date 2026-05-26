
from django.db import models


class Customer(models.Model):
    INDIVIDUAL = 'INDIVIDUAL'
    DEALER = 'DEALER'
    TYPE_CHOICES = [
        (INDIVIDUAL, 'Individual'),
        (DEALER, 'Dealer'),
    ]
    
    id = models.IntegerField(primary_key=True)
    cnic = models.CharField(max_length=20, null=True, unique=True)
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
