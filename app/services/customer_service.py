from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Customer, CustomerType
from typing import List, Optional

class CustomerService:
    def _get_db(self) -> Session:
        return SessionLocal()

    def check_duplicate_cnic(self, cnic: str, exclude_id: int = None) -> bool:
        if not cnic:
            return False
        db = self._get_db()
        try:
            query = db.query(Customer).filter(Customer.cnic == cnic)
            if exclude_id:
                query = query.filter(Customer.id != exclude_id)
            return query.first() is not None
        finally:
            db.close()

    def create_customer(self, cnic: str, name: str, father_name: str, phone: str, address: str, ntn: str = None, business_name: str = None, customer_type: str = CustomerType.INDIVIDUAL) -> Customer:
        """Create a new customer."""
        if self.check_duplicate_cnic(cnic):
            raise ValueError(f"CNIC '{cnic}' already exists.")

        db = self._get_db()
        try:
            customer = Customer(
                cnic=cnic,
                name=(name or "").upper(),
                father_name=(father_name or "").upper(),
                business_name=(business_name or "").upper() if business_name else None,
                phone=phone,
                address=(address or "").upper(),
                ntn=ntn,
                type=customer_type
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)
            return customer
        except Exception as e:
            db.rollback()
            if "UNIQUE constraint failed" in str(e) or "Duplicate entry" in str(e):
                if "cnic" in str(e).lower():
                    raise ValueError(f"CNIC '{cnic}' already exists.")
            raise e
        finally:
            db.close()

    def get_customer_by_cnic(self, cnic: str) -> Optional[Customer]:
        """Get a customer by CNIC."""
        db = self._get_db()
        try:
            return db.query(Customer).filter(Customer.cnic == cnic, Customer.is_deleted == False).first()
        finally:
            db.close()

    def get_customer_by_id(self, customer_id: int) -> Optional[Customer]:
        """Get a customer by ID."""
        db = self._get_db()
        try:
            return db.query(Customer).filter(Customer.id == customer_id, Customer.is_deleted == False).first()
        finally:
            db.close()

    def get_all_customers(self) -> List[Customer]:
        """Get all customers."""
        db = self._get_db()
        try:
            return db.query(Customer).filter(Customer.is_deleted == False).order_by(Customer.id.desc()).all()
        finally:
            db.close()

    def search_customers(self, query: str) -> List[Customer]:
        """Search customers by name, cnic, or phone."""
        search = f"%{query}%"
        db = self._get_db()
        try:
            return db.query(Customer).filter(
                Customer.is_deleted == False,
                (Customer.name.ilike(search)) |
                (Customer.cnic.ilike(search)) |
                (Customer.phone.ilike(search)) |
                (Customer.business_name.ilike(search))
            ).order_by(Customer.id.desc()).limit(50).all()
        finally:
            db.close()

    def update_customer(self, customer_id: int, cnic: str, name: str, father_name: str, phone: str, address: str, ntn: str = None, business_name: str = None, customer_type: str = CustomerType.INDIVIDUAL) -> Optional[Customer]:
        """Update an existing customer."""
        if self.check_duplicate_cnic(cnic, exclude_id=customer_id):
            raise ValueError(f"CNIC '{cnic}' already exists.")

        db = self._get_db()
        try:
            customer = db.query(Customer).filter(Customer.id == customer_id, Customer.is_deleted == False).first()
            if customer:
                customer.cnic = cnic
                customer.name = (name or "").upper()
                customer.father_name = (father_name or "").upper()
                customer.business_name = (business_name or "").upper() if business_name else None
                customer.phone = phone
                customer.address = (address or "").upper()
                customer.ntn = ntn
                customer.type = customer_type
                db.commit()
                db.refresh(customer)
                return customer
            return None
        except Exception as e:
            db.rollback()
            if "UNIQUE constraint failed" in str(e) or "Duplicate entry" in str(e):
                if "cnic" in str(e).lower():
                    raise ValueError(f"CNIC '{cnic}' already exists.")
            raise e
        finally:
            db.close()

    def delete_customer(self, customer_id: int) -> bool:
        """Delete a customer by ID (Soft Delete)."""
        db = self._get_db()
        try:
            customer = db.query(Customer).filter(Customer.id == customer_id, Customer.is_deleted == False).first()
            if customer:
                customer.is_deleted = True
                db.commit()
                return True
            return False
        except Exception:
            db.rollback()
            return False
        finally:
            db.close()

    def delete_customers(self, customer_ids: List[int]) -> tuple[bool, str]:
        """Delete multiple customers by IDs (Soft Delete)."""
        if not customer_ids:
            return False, "No customers specified."
            
        db = self._get_db()
        try:
            # Soft delete: update is_deleted = True
            result = db.query(Customer).filter(
                Customer.id.in_(customer_ids)
            ).update({Customer.is_deleted: True}, synchronize_session=False)
            
            db.commit()
            return True, f"Successfully deleted {result} customer(s)."
        except Exception as e:
            db.rollback()
            return False, f"Error deleting customers: {str(e)}"
        finally:
            db.close()

    def close(self):
        # Deprecated since we use per-call sessions
        pass

customer_service = CustomerService()
