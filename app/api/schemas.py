from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime as dt


class MotorcycleResponse(BaseModel):
    id: int
    chassis_number: str
    engine_number: str
    color: Optional[str] = None
    model: Optional[str] = None
    year: int
    status: str

    model_config = {
        "from_attributes": True
    }


class InvoiceWithDetailsResponse(BaseModel):
    id: int
    invoice_number: str
    fbr_invoice_number: Optional[str] = None
    is_fiscalized: bool
    datetime: dt

    model_config = {
        "from_attributes": True
    }

class InvoiceItemCreate(BaseModel):
    item_code: str
    item_name: str
    pct_code: Optional[str] = Field(default=None)
    quantity: float
    tax_rate: float
    sale_value: float
    tax_charged: float # Explicitly passed
    further_tax: float = 0.0 # Added Further Tax
    discount: float = 0.0
    chassis_number: Optional[str] = Field(default=None)
    engine_number: Optional[str] = Field(default=None)
    model_name: Optional[str] = Field(default=None)
    color: Optional[str] = Field(default=None)

class InvoiceCreate(BaseModel):
    invoice_number: str
    datetime: dt = Field(default_factory=dt.utcnow)
    buyer_name: Optional[str] = Field(default=None)
    buyer_father_name: Optional[str] = Field(default=None)
    buyer_ntn: Optional[str] = Field(default=None)
    buyer_cnic: Optional[str] = Field(default=None)
    buyer_phone: Optional[str] = Field(default=None)
    buyer_address: Optional[str] = Field(default=None)
    buyer_type: Optional[str] = Field(default="INDIVIDUAL") # Added for dealer support
    payment_mode: str = "Cash"
    discount: float = 0.0
    items: List[InvoiceItemCreate]

class InvoiceResponse(InvoiceCreate):
    id: int
    pos_id: str
    usin: str
    total_sale_value: float
    total_tax_charged: float
    total_further_tax: float = 0.0
    total_quantity: float
    total_amount: float
    fbr_invoice_number: Optional[str] = None
    is_fiscalized: bool
    sync_status: str

    model_config = {
        "from_attributes": True
    }

class PriceBase(BaseModel):
    model: str
    base_price: float
    tax_amount: float
    levy_amount: float
    total_price: float
    optional_features: Optional[dict] = None
    currency: str = "Rs"

class PriceCreate(PriceBase):
    pass

class PriceResponse(PriceBase):
    id: int
    effective_date: dt
    expiration_date: Optional[dt] = None

    model_config = {
        "from_attributes": True
    }


class MotorcycleSaleInfoResponse(BaseModel):
    id: int
    invoice_number: str
    fbr_invoice_number: Optional[str] = None
    is_fiscalized: bool
    invoice_datetime: dt
    customer_name: Optional[str] = None
    customer_father_name: Optional[str] = None
    customer_cnic: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_address: Optional[str] = None
    chassis_number: Optional[str] = None
    engine_number: Optional[str] = None
    motorcycle_color: Optional[str] = None
    motorcycle_model: Optional[str] = None
    motorcycle_year: Optional[int] = None
    total_amount: float
    payment_mode: str

    model_config = {
        "from_attributes": True
    }
