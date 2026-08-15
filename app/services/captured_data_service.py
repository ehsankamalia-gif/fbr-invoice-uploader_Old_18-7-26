from sqlalchemy.orm import Session
from sqlalchemy import or_, desc
from app.db.session import SessionLocal
from app.db.models import CapturedData
from typing import List, Optional, Tuple, Dict, Any
import math

import logging

# Configure logger
logger = logging.getLogger(__name__)

class CapturedDataService:
    def __init__(self):
        self.db: Session = SessionLocal()

    def delete_by_chassis(self, db: Session, chassis_number: str) -> bool:
        """
        Delete a record from captured_data by chassis number.
        Uses the provided database session for transaction integrity.
        """
        try:
            if not chassis_number:
                return False

            record = db.query(CapturedData).filter(CapturedData.chassis_number == chassis_number).first()
            
            if record:
                db.delete(record)
                # Commit the transaction to make the delete permanent
                db.commit()
                logger.info(f"AUDIT: Automatically deleted captured_data record for chassis {chassis_number} after FBR upload.")
                return True
            else:
                logger.info(f"AUDIT: No captured_data record found for chassis {chassis_number} during cleanup.")
                return False
                
        except Exception as e:
            logger.error(f"Error deleting captured data for chassis {chassis_number}: {e}")
            # Rollback the transaction if there's an error
            db.rollback()
            # Do not raise exception to avoid rolling back the main invoice transaction
            # just because cleanup failed? 
            # User said: "transaction management to ensure data integrity"
            # If we fail to delete "captured data", does it violate integrity?
            # Usually "integrity" here means "don't delete if FBR failed" (handled by placement)
            # and "don't leave orphan if FBR succeeded" (handled by delete).
            # If delete fails, we might want to warn but maybe not fail the invoice.
            # However, since we are passed 'db' which is part of the main transaction,
            # if we suppress the error here, the transaction continues. 
            # If we raise, the whole invoice rolls back. 
            # Given "Captured Data" is likely a staging table, it's better to NOT fail the invoice
            # if this cleanup fails, but definitely log it.
            return False

    def get_captured_data(
        self, 
        page: int = 1, 
        per_page: int = 20, 
        search_query: str = None
    ) -> Dict[str, Any]:
        """
        Retrieve paginated captured data with optional search.
        
        Args:
            page (int): Current page number (1-based).
            per_page (int): Number of records per page.
            search_query (str): Search term for filtering.
            
        Returns:
            Dict containing 'data', 'total_records', 'total_pages', 'current_page'.
        """
        # Ensure we are reading fresh data from the database
        # Commit ensures the current transaction (if any) is closed and next query starts a new one
        self.db.commit()

        query = self.db.query(CapturedData).filter(CapturedData.is_deleted == False)

        if search_query:
            search = f"%{search_query}%"
            query = query.filter(
                or_(
                    CapturedData.name.ilike(search),
                    CapturedData.father.ilike(search),
                    CapturedData.cnic.ilike(search),
                    CapturedData.cell.ilike(search),
                    CapturedData.chassis_number.ilike(search),
                    CapturedData.engine_number.ilike(search),
                    CapturedData.model.ilike(search)
                )
            )

        # Get total count before pagination
        total_records = query.count()
        total_pages = math.ceil(total_records / per_page) if total_records > 0 else 1

        # Apply pagination
        offset = (page - 1) * per_page
        data = query.order_by(desc(CapturedData.created_at)).offset(offset).limit(per_page).all()

        return {
            "data": data,
            "total_records": total_records,
            "total_pages": total_pages,
            "current_page": page,
            "per_page": per_page
        }

    def delete_records(self, record_ids: List[int], soft_delete: bool = True) -> Tuple[bool, str]:
        """
        Delete captured data records.
        
        Args:
            record_ids: List of IDs to delete
            soft_delete: If True, mark as deleted instead of removing from DB
            
        Returns:
            Tuple[bool, str]: (Success status, Message)
        """
        logger.info(f"delete_records called with IDs={record_ids}, soft_delete={soft_delete}")
        if not record_ids:
            return False, "No records specified for deletion."
            
        try:
            if soft_delete:
                # Soft Delete
                # Verify CapturedData has is_deleted attribute
                if not hasattr(CapturedData, 'is_deleted'):
                    logger.error("CapturedData model missing is_deleted attribute")
                    return False, "Database model missing deletion support. Restart application."

                result = self.db.query(CapturedData).filter(
                    CapturedData.id.in_(record_ids)
                ).update(
                    {CapturedData.is_deleted: True}, 
                    synchronize_session=False
                )
                
                self.db.commit()
                msg = f"Successfully soft deleted {result} record(s)."
                logger.info(f"AUDIT: {msg} IDs: {record_ids}")
                return True, msg
            else:
                # Hard Delete (Admin only usually)
                result = self.db.query(CapturedData).filter(
                    CapturedData.id.in_(record_ids)
                ).delete(synchronize_session=False)
                
                self.db.commit()
                msg = f"Successfully permanently deleted {result} record(s)."
                logger.info(f"AUDIT: {msg} IDs: {record_ids}")
                return True, msg
                
        except Exception as e:
            self.db.rollback()
            err_msg = f"Error deleting records: {str(e)}"
            logger.error(err_msg, exc_info=True)
            return False, err_msg

    def close(self):
        self.db.close()

captured_data_service = CapturedDataService()
