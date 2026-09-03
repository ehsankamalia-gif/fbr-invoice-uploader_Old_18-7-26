import sys
sys.path.insert(0, r'c:\laragon\www\fbr-invoice-uploader_Old_18-7-26')

from app.db.session import SessionLocal
from app.db.models import CapturedData
from datetime import datetime
import logging
logging.basicConfig(level=logging.DEBUG)

db = SessionLocal()
try:
    # Check if DB is MySQL or SQLite
    result = db.execute("SELECT 1")
    print("DB connection OK")
    
    # Check current engine
    from sqlalchemy import inspect
    inspector = inspect(db.bind)
    print(f"Engine URL: {db.bind.url}")
    
    record = CapturedData(
        name='TEST USER',
        father='TEST FATHER',
        cnic='12345-6789012-3',
        cell='03000000000',
        address='TEST ADDRESS',
        chassis_number='TESTCHASSIS001',
        engine_number='TESTENG001',
        color='RED',
        model='CD70',
        created_at=datetime.utcnow()
    )
    db.add(record)
    db.commit()
    print('Save successful!')
    print('Record ID:', record.id)
except Exception as e:
    db.rollback()
    import traceback
    print('Error:', e)
    traceback.print_exc()
finally:
    db.close()
