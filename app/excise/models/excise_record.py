
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, JSON, Index, Enum
from sqlalchemy.orm import relationship, declarative_base
import datetime as dt
import enum

try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None


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


# Create our own independent Base class for excise module (to keep it separate)
ExciseBase = declarative_base()


class ExciseRecordStatus(str, enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class ExciseRecord(ExciseBase):
    __tablename__ = "excise_records"
    
    id = Column(Integer, primary_key=True, index=True)
    record_number = Column(String(50), unique=True, index=True, nullable=False)
    
    # Vehicle details
    chassis_number = Column(String(50), unique=True, index=True, nullable=False)
    engine_number = Column(String(50), unique=True, index=True, nullable=False)
    motorcycle_model = Column(String(50), nullable=True)
    color = Column(String(30), nullable=True)
    year_of_manufacture = Column(Integer, nullable=True)
    
    # Customer details
    customer_name = Column(String(100), nullable=False)
    customer_cnic = Column(String(20), index=True, nullable=True)
    customer_father_name = Column(String(100), nullable=True)
    customer_phone = Column(String(20), nullable=True)
    customer_address = Column(String(255), nullable=True)
    
    # Excise details
    registration_number = Column(String(50), nullable=True, index=True)
    tax_amount = Column(Float, nullable=True)
    fine_amount = Column(Float, default=0.0)
    total_amount = Column(Float, nullable=True)
    
    status = Column(String(20), default=ExciseRecordStatus.PENDING, index=True)
    notes = Column(String(500), nullable=True)
    
    created_at = Column(DateTime, default=pk_now)
    updated_at = Column(DateTime, default=pk_now, onupdate=pk_now)
    is_deleted = Column(Boolean, default=False, index=True)
    
    # For attachments
    attachments = Column(JSON, nullable=True)  # Store list of file paths or URLs
