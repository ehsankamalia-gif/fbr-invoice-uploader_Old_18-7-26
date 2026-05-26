
from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import Customer, FinanceCreditSale, CreditSale
from typing import Optional, Dict, Any
import random
import string
from django.contrib.auth.hashers import make_password
from app.core.logger import logger
import datetime as dt


class CustomerPortalService:
    def _get_db(self) -> Session:
        return SessionLocal()

    def _generate_password(self, length: int = 8) -> str:
        """Generate a random password with letters and digits."""
        characters = string.ascii_letters + string.digits
        return ''.join(random.choice(characters) for _ in range(length))

    def create_portal_account(
        self,
        customer_id: int,
        phone_number: Optional[str] = None,
        password: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create a customer portal account if it doesn't already exist.
        
        Args:
            customer_id: ID of the customer
            phone_number: Phone number to use (if not provided, uses customer's phone)
            password: Password to use (if not provided, generates random)
            
        Returns:
            Dictionary with account details if created, None if account already exists
        """
        db = self._get_db()
        try:
            # First check if customer exists
            customer = db.query(Customer).filter(Customer.id == customer_id).first()
            if not customer:
                logger.error(f"Customer with ID {customer_id} not found")
                return None

            # Check if portal account already exists
            # We'll use raw SQL to check since portal models are in Django app
            from sqlalchemy import text
            result = db.execute(
                text("SELECT id FROM customer_portal_auth WHERE customer_id = :customer_id"),
                {"customer_id": customer_id}
            ).fetchone()
            
            if result:
                logger.info(f"Portal account already exists for customer {customer_id}")
                return None

            # Determine phone number
            use_phone = phone_number or customer.phone
            if not use_phone:
                logger.error(f"No phone number available for customer {customer_id}")
                return None

            # Generate password if not provided
            use_password = password or self._generate_password()
            
            # Hash the password using Django's make_password
            password_hash = make_password(use_password)

            # Create the portal account using raw SQL (let DB handle auto-increment id)
            now = dt.datetime.now()
            db.execute(
                text("""
                    INSERT INTO customer_portal_auth 
                    (customer_id, phone_number, password_hash, is_active, created_at, updated_at)
                    VALUES (:customer_id, :phone_number, :password_hash, 1, :created_at, :updated_at)
                """),
                {
                    "customer_id": customer_id,
                    "phone_number": use_phone,
                    "password_hash": password_hash,
                    "created_at": now,
                    "updated_at": now
                }
            )
            db.commit()

            logger.info(f"Created portal account for customer {customer_id} (phone: {use_phone})")
            
            return {
                "customer_id": customer_id,
                "customer_name": customer.name,
                "phone_number": use_phone,
                "password": use_password,
                "created_at": now
            }

        except Exception as e:
            db.rollback()
            logger.error(f"Error creating portal account: {e}", exc_info=True)
            return None
        finally:
            db.close()

    def create_account_for_credit_sale(
        self,
        customer_id: int,
        phone_number: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Create portal account when a credit sale is created (only once per customer).
        
        This should be called whenever a new credit sale (old or advanced) is created.
        """
        return self.create_portal_account(customer_id, phone_number)


customer_portal_service = CustomerPortalService()
