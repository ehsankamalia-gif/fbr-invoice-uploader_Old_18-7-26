from sqlalchemy.orm import Session
from app.db.session import SessionLocal
from app.db.models import CreditBook, Customer, Motorcycle, Price, CapturedData
from typing import List, Optional, Dict, Any
import datetime as dt
from app.core.logger import logger

class CreditBookService:
    def _get_db(self) -> Session:
        return SessionLocal()

    def create_entry(self, data: Dict[str, Any]) -> CreditBook:
        """Create a new credit book entry."""
        db = self._get_db()
        try:
            # Convert date string if necessary (though PyQt should provide QDate/QDateTime)
            if isinstance(data.get('date'), str):
                data['date'] = dt.datetime.fromisoformat(data['date'])
            
            entry = CreditBook(**data)
            db.add(entry)
            db.commit()
            db.refresh(entry)
            logger.info(f"Credit book entry created for customer: {entry.customer_name}")
            return entry
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating credit book entry: {e}", exc_info=True)
            raise e
        finally:
            db.close()

    def get_all_entries(self) -> List[CreditBook]:
        """Get all credit book entries."""
        db = self._get_db()
        try:
            return db.query(CreditBook).order_by(CreditBook.date.desc()).all()
        finally:
            db.close()

    def search_suggestions(self, query: str) -> List[str]:
        """Search for customer and dealer names for auto-suggestion."""
        if not query or len(query) < 1:
            return []
            
        db = self._get_db()
        try:
            # Search in customers table (names)
            customer_names = db.query(Customer.name).filter(
                Customer.name.ilike(f"%{query}%"),
                Customer.is_deleted == False
            ).limit(20).all()
            
            # Search in customers table (business names / dealers)
            dealer_names = db.query(Customer.business_name).filter(
                Customer.business_name.ilike(f"%{query}%"),
                Customer.is_deleted == False
            ).limit(20).all()
            
            suggestions = set()
            for name in customer_names:
                if name[0]: suggestions.add(name[0].upper())
            for name in dealer_names:
                if name[0]: suggestions.add(name[0].upper())
                
            return sorted(list(suggestions))
        finally:
            db.close()

    def search_chassis_suggestions(self, query: str) -> List[str]:
        """Search for chassis numbers for auto-suggestion."""
        if not query or len(query) < 1:
            return []
            
        db = self._get_db()
        try:
            chassis_list = db.query(Motorcycle.chassis_number).filter(
                Motorcycle.chassis_number.ilike(f"%{query}%")
            ).limit(20).all()
            
            return [c[0].upper() for c in chassis_list if c[0]]
        finally:
            db.close()

    def get_chassis_details(self, chassis_no: str) -> Optional[Dict[str, Any]]:
        """Get motorcycle details for a given chassis number with price from Price table."""
        db = self._get_db()
        try:
            # Join Motorcycle with Price to get the current active price
            motorcycle = db.query(Motorcycle).filter(
                Motorcycle.chassis_number == chassis_no
            ).first()
            
            if motorcycle:
                # Fetch active price from Price table
                from app.db.models import Price
                active_price = db.query(Price).filter(
                    Price.product_model_id == motorcycle.product_model_id,
                    Price.expiration_date.is_(None)
                ).first()

                return {
                    "model": motorcycle.model,
                    "color": motorcycle.color,
                    "price": active_price.total_price if active_price else motorcycle.sale_price,
                    "engine_no": motorcycle.engine_number
                }
            
            # If not found in Motorcycle, try CapturedData as fallback
            captured = db.query(CapturedData).filter(
                CapturedData.chassis_number == chassis_no
            ).first()
            
            if captured:
                return {
                    "model": captured.model,
                    "color": captured.color,
                    "price": 0.0, # Price not usually in captured data
                    "engine_no": captured.engine_number
                }
                
            return None
        finally:
            db.close()

credit_book_service = CreditBookService()
