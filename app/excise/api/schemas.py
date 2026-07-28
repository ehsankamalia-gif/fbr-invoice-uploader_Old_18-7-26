
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


class ExciseRecordBase(BaseModel):
    record_number: str
    chassis_number: str
    engine_number: str
    motorcycle_model: Optional[str] = None
    color: Optional[str] = None
    year_of_manufacture: Optional[int] = None
    customer_name: str
    customer_cnic: Optional[str] = None
    customer_father_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_address: Optional[str] = None
    registration_number: Optional[str] = None
    tax_amount: Optional[float] = None
    fine_amount: float = 0.0
    total_amount: Optional[float] = None
    status: str = "PENDING"
    notes: Optional[str] = None
    attachments: Optional[List] = None


class ExciseRecordCreate(ExciseRecordBase):
    pass


class ExciseRecordUpdate(BaseModel):
    record_number: Optional[str] = None
    chassis_number: Optional[str] = None
    engine_number: Optional[str] = None
    motorcycle_model: Optional[str] = None
    color: Optional[str] = None
    year_of_manufacture: Optional[int] = None
    customer_name: Optional[str] = None
    customer_cnic: Optional[str] = None
    customer_father_name: Optional[str] = None
    customer_phone: Optional[str] = None
    customer_address: Optional[str] = None
    registration_number: Optional[str] = None
    tax_amount: Optional[float] = None
    fine_amount: Optional[float] = None
    total_amount: Optional[float] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    attachments: Optional[List] = None


class ExciseRecordResponse(ExciseRecordBase):
    id: int
    created_at: datetime
    updated_at: datetime
    is_deleted: bool

    model_config = {
        "from_attributes": True
    }
