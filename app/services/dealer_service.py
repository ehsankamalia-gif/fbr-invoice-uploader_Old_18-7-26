from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.db.session import SessionLocal
from app.db.models import Customer, CustomerType
from typing import List, Optional
import logging

from app.utils.string_utils import normalize_business_name

logger = logging.getLogger(__name__)

class DealerService:
    def __init__(self):
        self.db: Session = SessionLocal()

    def check_duplicate_dealer(self, business_name: str, cnic: str, exclude_id: int = None) -> Optional[str]:
        """
        Check if a dealer with the same business name OR CNIC already exists.
        Returns the error message if duplicate found, None otherwise.
        """
        # Check Business Name
        if business_name:
            norm_name = normalize_business_name(business_name)
            query = self.db.query(Customer).filter(
                Customer.normalized_business_name == norm_name,
                Customer.type == CustomerType.DEALER
            )
            
            if exclude_id:
                query = query.filter(Customer.id != exclude_id)
                
            if query.first():
                logger.warning(f"Duplicate dealer attempt detected: Business='{business_name}'")
                return f"Business Name '{business_name}' already exists."

        # Check CNIC
        if cnic:
            query = self.db.query(Customer).filter(
                Customer.cnic == cnic
            )
            if exclude_id:
                query = query.filter(Customer.id != exclude_id)
                
            if query.first():
                logger.warning(f"Duplicate dealer attempt detected: CNIC='{cnic}'")
                return f"CNIC '{cnic}' already exists."
            
        return None

    def create_dealer(self, cnic: str, name: str, father_name: str, business_name: str, phone: str, address: str) -> Customer:
        """Create a new dealer (Customer with type DEALER)."""
        # Validation
        error_msg = self.check_duplicate_dealer(business_name, cnic)
        if error_msg:
            raise ValueError(error_msg)

        try:
            norm_name = normalize_business_name(business_name)
            dealer = Customer(
                cnic=cnic,
                name=(name or "").upper(),
                father_name=(father_name or "").upper(),
                business_name=(business_name or "").upper(),
                normalized_business_name=norm_name,
                phone=phone,
                address=(address or "").upper(),
                type=CustomerType.DEALER
            )
            self.db.add(dealer)
            self.db.commit()
            self.db.refresh(dealer)
            return dealer
        except Exception as e:
            self.db.rollback()
            if "UNIQUE constraint failed" in str(e) or "Duplicate entry" in str(e):
                 if "normalized_business_name" in str(e):
                      raise ValueError(f"Business Name '{business_name}' is too similar to an existing one.")
                 if "cnic" in str(e).lower():
                      raise ValueError(f"CNIC '{cnic}' already exists.")
            raise e

    def get_dealer_by_business_name(self, business_name: str) -> Optional[Customer]:
        """Get a dealer by business name (case insensitive)."""
        return self.db.query(Customer).filter(
            Customer.business_name.ilike(business_name),
            Customer.type == CustomerType.DEALER,
            Customer.is_deleted == False
        ).first()

    def search_dealers_by_business_name(self, query: str, limit: int = 5) -> List[Customer]:
        """Search dealers by business name (partial match)."""
        if not query:
            return []
        return self.db.query(Customer).filter(
            Customer.business_name.ilike(f"{query}%"),
            Customer.type == CustomerType.DEALER,
            Customer.is_deleted == False
        ).limit(limit).all()

    def get_dealer_by_id(self, dealer_id: int) -> Optional[Customer]:
        """Get a dealer by ID."""
        return self.db.query(Customer).filter(
            Customer.id == dealer_id,
            Customer.type == CustomerType.DEALER
        ).first()

    def get_all_dealers(self) -> List[Customer]:
        """Get all dealers."""
        return self.db.query(Customer).filter(
            Customer.type == CustomerType.DEALER,
            Customer.is_deleted == False
        ).all()

    def update_dealer(self, dealer_id: int, cnic: str, name: str, father_name: str, business_name: str, phone: str, address: str) -> Optional[Customer]:
        """Update an existing dealer."""
        # Validation
        error_msg = self.check_duplicate_dealer(business_name, cnic, exclude_id=dealer_id)
        if error_msg:
            raise ValueError(error_msg)

        dealer = self.db.query(Customer).filter(
            Customer.id == dealer_id,
            Customer.type == CustomerType.DEALER
        ).first()
        if dealer:
            try:
                dealer.cnic = cnic
                dealer.name = (name or "").upper()
                dealer.father_name = (father_name or "").upper()
                dealer.business_name = (business_name or "").upper()
                dealer.normalized_business_name = normalize_business_name(business_name)
                dealer.phone = phone
                dealer.address = (address or "").upper()
                self.db.commit()
                self.db.refresh(dealer)
                return dealer
            except Exception as e:
                self.db.rollback()
                if "UNIQUE constraint failed" in str(e) or "Duplicate entry" in str(e):
                    if "normalized_business_name" in str(e):
                        raise ValueError(f"Business Name '{business_name}' is too similar to an existing one.")
                    if "cnic" in str(e).lower():
                        raise ValueError(f"CNIC '{cnic}' already exists.")
                raise e
        return None

    def delete_dealer(self, dealer_id: int):
        """Delete a dealer by ID."""
        dealer = self.db.query(Customer).filter(
            Customer.id == dealer_id,
            Customer.type == CustomerType.DEALER
        ).first()
        if dealer:
            self.db.delete(dealer)
            self.db.commit()
            return True
        return False

    def close(self):
        self.db.close()

dealer_service = DealerService()
