
import os
import pandas as pd
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.core.logger import logger
from app.db.models import (
    ExciseRecord,
    ExciseRecordStatus,
    pk_now,
)


class ExciseService:
    def create_excise_record(
        self,
        db: Session,
        record_number: str,
        chassis_number: str,
        engine_number: str,
        customer_name: str,
        motorcycle_model: Optional[str] = None,
        maker_make: Optional[str] = None,
        color: Optional[str] = None,
        year_of_manufacture: Optional[int] = None,
        customer_cnic: Optional[str] = None,
        customer_father_name: Optional[str] = None,
        customer_phone: Optional[str] = None,
        customer_address: Optional[str] = None,
        registration_number: Optional[str] = None,
        tax_amount: Optional[float] = None,
        fine_amount: float = 0.0,
        total_amount: Optional[float] = None,
        amount: Optional[float] = None,
        income: Optional[float] = None,
        profit: Optional[float] = None,
        income2: Optional[float] = None,
        expenditure: Optional[float] = None,
        tcs_receiving_date: Optional[datetime] = None,
        excise_submitting_date: Optional[datetime] = None,
        dealer_address: Optional[str] = None,
        issue_authority: Optional[str] = None,
        receiver: Optional[str] = None,
        file_card: Optional[str] = None,
        modified_pc: Optional[str] = None,
        remarks: Optional[str] = None,
        notes: Optional[str] = None,
        attachments: Optional[List] = None,
    ) -> ExciseRecord:
        """Create a new excise record"""
        record = ExciseRecord(
            record_number=record_number,
            chassis_number=chassis_number.upper().strip(),
            engine_number=engine_number.upper().strip(),
            motorcycle_model=motorcycle_model,
            maker_make=maker_make,
            color=color,
            year_of_manufacture=year_of_manufacture,
            customer_name=customer_name,
            customer_cnic=customer_cnic,
            customer_father_name=customer_father_name,
            customer_phone=customer_phone,
            customer_address=customer_address,
            registration_number=registration_number,
            tax_amount=tax_amount,
            fine_amount=fine_amount,
            total_amount=total_amount,
            amount=amount,
            income=income,
            profit=profit,
            income2=income2,
            expenditure=expenditure,
            tcs_receiving_date=tcs_receiving_date,
            excise_submitting_date=excise_submitting_date,
            dealer_address=dealer_address,
            issue_authority=issue_authority,
            receiver=receiver,
            file_card=file_card,
            modified_pc=modified_pc,
            remarks=remarks,
            status=ExciseRecordStatus.PENDING,
            notes=notes,
            attachments=attachments,
        )
        
        db.add(record)
        db.commit()
        db.refresh(record)
        logger.info(f"Created excise record: {record_number}")
        return record

    def get_excise_record_by_id(self, db: Session, record_id: int) -> Optional[ExciseRecord]:
        """Get an excise record by ID"""
        return db.query(ExciseRecord).filter(
            ExciseRecord.id == record_id,
            ExciseRecord.is_deleted == False,
        ).first()

    def get_excise_record_by_chassis(self, db: Session, chassis_number: str) -> Optional[ExciseRecord]:
        """Get an excise record by chassis number"""
        return db.query(ExciseRecord).filter(
            ExciseRecord.chassis_number == chassis_number.upper().strip(),
            ExciseRecord.is_deleted == False,
        ).first()

    def get_all_excise_records(self, db: Session, skip: int = 0, limit: int = 100) -> List[ExciseRecord]:
        """Get all excise records (paginated)"""
        return db.query(ExciseRecord).filter(
            ExciseRecord.is_deleted == False
        ).order_by(ExciseRecord.created_at.desc()).offset(skip).limit(limit).all()

    def update_excise_record(
        self,
        db: Session,
        record_id: int,
        **kwargs,
    ) -> Optional[ExciseRecord]:
        """Update an excise record"""
        record = self.get_excise_record_by_id(db, record_id)
        if not record:
            logger.error(f"Excise record not found: {record_id}")
            return None
        
        for key, value in kwargs.items():
            if hasattr(record, key):
                if key in ["chassis_number", "engine_number"] and value:
                    value = value.upper().strip()
                setattr(record, key, value)
        
        db.commit()
        db.refresh(record)
        logger.info(f"Updated excise record: {record.record_number}")
        return record

    def delete_excise_record(self, db: Session, record_id: int) -> bool:
        """Soft delete an excise record"""
        record = self.get_excise_record_by_id(db, record_id)
        if not record:
            return False
        
        record.is_deleted = True
        db.commit()
        logger.info(f"Deleted excise record: {record.record_number}")
        return True

    def _parse_date(self, date_value) -> Optional[datetime]:
        """Helper to parse Excel date values"""
        if pd.isna(date_value):
            return None
        if isinstance(date_value, datetime):
            return date_value
        try:
            return pd.to_datetime(date_value).to_pydatetime()
        except Exception:
            return None

    def _parse_float(self, value) -> Optional[float]:
        """Helper to parse float values"""
        if pd.isna(value):
            return None
        try:
            return float(value)
        except (ValueError, TypeError):
            return None

    def import_from_excel(self, db: Session, file_path: str) -> Dict[str, Any]:
        """Import excise records from Excel file"""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Excel file not found: {file_path}")
        
        logger.info(f"Starting Excel import from: {file_path}")
        
        try:
            # Read Excel file
            df = pd.read_excel(file_path)
            
            # Normalize column names (lowercase, strip spaces)
            df.columns = [str(col).strip().upper().replace(" ", "_") for col in df.columns]
            
            # Mapping of Excel columns (normalized) to model fields
            column_mapping = {
                "S#": "record_number",
                "DATE": "date",
                "NAME": "customer_name",
                "FATHER": "customer_father_name",
                "ID_CARD": "customer_cnic",
                "CELL": "customer_phone",
                "COLOR": "color",
                "MODEL": "motorcycle_model",
                "ADDRESS": "customer_address",
                "RECEIVE": "receive",
                "REGISTRATION_NUMBER": "registration_number",
                "MAKER/MAKE": "maker_make",
                "MAKER_MAKE": "maker_make",
                "CHASSIS_NUMBER": "chassis_number",
                "ENGINE#": "engine_number",
                "ENGINE_#": "engine_number",
                "AMOUNT": "amount",
                "INCOME": "income",
                "PROFIT": "profit",
                "INCOME2": "income2",
                "EXPENDENTUR": "expenditure",
                "FILE_CARD": "file_card",
                "TCS_RECEIVING_DATE": "tcs_receiving_date",
                "EXCISE_SUBMITTEING_DATE": "excise_submitting_date",
                "DEALER_ADDRESS": "dealer_address",
                "REMARKS": "remarks",
                "ISSUE_AUTHORITY": "issue_authority",
                "RECIEVER": "receiver",
                "MODIFIED_TIME": "modified_time",
                "MODIFIED_PC": "modified_pc",
            }
            
            imported_count = 0
            skipped_count = 0
            errors = []
            
            for index, row in df.iterrows():
                try:
                    # Prepare data
                    record_data = {}
                    for excel_col, model_field in column_mapping.items():
                        if excel_col in df.columns:
                            record_data[model_field] = row[excel_col]
                    
                    # Validate required fields
                    record_number = record_data.get("record_number") or f"EXC-{datetime.now().strftime('%Y%m%d%H%M%S')}-{index+1}"
                    chassis_number = record_data.get("chassis_number")
                    engine_number = record_data.get("engine_number")
                    customer_name = record_data.get("customer_name")
                    
                    if not chassis_number or not engine_number or not customer_name:
                        skipped_count += 1
                        errors.append(f"Row {index+1}: Missing required fields (Chassis, Engine, or Name)")
                        continue
                    
                    # Check if record already exists
                    existing = self.get_excise_record_by_chassis(db, chassis_number)
                    if existing:
                        skipped_count += 1
                        errors.append(f"Row {index+1}: Chassis {chassis_number} already exists")
                        continue
                    
                    # Parse date fields
                    tcs_receiving_date = self._parse_date(record_data.get("tcs_receiving_date"))
                    excise_submitting_date = self._parse_date(record_data.get("excise_submitting_date"))
                    modified_time = self._parse_date(record_data.get("modified_time"))
                    
                    # Parse numeric fields
                    amount = self._parse_float(record_data.get("amount"))
                    income = self._parse_float(record_data.get("income"))
                    profit = self._parse_float(record_data.get("profit"))
                    income2 = self._parse_float(record_data.get("income2"))
                    expenditure = self._parse_float(record_data.get("expenditure"))
                    
                    # Create record
                    self.create_excise_record(
                        db=db,
                        record_number=record_number,
                        chassis_number=chassis_number,
                        engine_number=engine_number,
                        customer_name=customer_name,
                        motorcycle_model=record_data.get("motorcycle_model"),
                        maker_make=record_data.get("maker_make"),
                        color=record_data.get("color"),
                        customer_cnic=record_data.get("customer_cnic"),
                        customer_father_name=record_data.get("customer_father_name"),
                        customer_phone=record_data.get("customer_phone"),
                        customer_address=record_data.get("customer_address"),
                        registration_number=record_data.get("registration_number"),
                        amount=amount,
                        income=income,
                        profit=profit,
                        income2=income2,
                        expenditure=expenditure,
                        tcs_receiving_date=tcs_receiving_date,
                        excise_submitting_date=excise_submitting_date,
                        dealer_address=record_data.get("dealer_address"),
                        issue_authority=record_data.get("issue_authority"),
                        receiver=record_data.get("receiver"),
                        file_card=record_data.get("file_card"),
                        modified_pc=record_data.get("modified_pc"),
                        remarks=record_data.get("remarks"),
                    )
                    
                    imported_count += 1
                    
                except Exception as e:
                    logger.error(f"Error importing row {index+1}: {str(e)}", exc_info=True)
                    skipped_count += 1
                    errors.append(f"Row {index+1}: {str(e)}")
            
            logger.info(f"Excel import completed: Imported {imported_count}, Skipped {skipped_count}")
            
            return {
                "success": True,
                "imported_count": imported_count,
                "skipped_count": skipped_count,
                "errors": errors,
            }
            
        except Exception as e:
            logger.error(f"Error reading Excel file: {str(e)}", exc_info=True)
            raise


# Singleton instance
excise_service = ExciseService()
