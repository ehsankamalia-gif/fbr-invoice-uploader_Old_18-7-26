
import sys
import os
from sqlalchemy import create_engine, text
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from app.core.config import get_database_url

def run_emergency_migration():
    db_url = get_database_url()
    print(f"Connecting to database: {db_url}")
    
    if "mysql" not in db_url:
        print("Not a MySQL database. Skipping.")
        return

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # List of columns to check and add
            columns = [
                ("whatsapp_enabled", "BOOLEAN DEFAULT 0"),
                ("whatsapp_web_enabled", "BOOLEAN DEFAULT 0"),
                ("whatsapp_gateway_ip", "VARCHAR(100)"),
                ("whatsapp_gateway_port", "VARCHAR(10) DEFAULT '8080'"),
                ("whatsapp_use_https", "BOOLEAN DEFAULT 0"),
                ("whatsapp_instance_id", "VARCHAR(100)"),
                ("whatsapp_api_key", "VARCHAR(100)"),
                ("whatsapp_username", "VARCHAR(100)"),
                ("whatsapp_password", "VARCHAR(100)"),
                ("gateway_username", "VARCHAR(100)"),
                ("gateway_password", "VARCHAR(100)")
            ]
            
            for col_name, col_def in columns:
                try:
                    # Check if column exists
                    conn.execute(text(f"SELECT {col_name} FROM sms_configurations LIMIT 1"))
                    print(f"Column '{col_name}' already exists.")
                except Exception:
                    # Add column
                    print(f"Adding column '{col_name}'...")
                    conn.execute(text(f"ALTER TABLE sms_configurations ADD COLUMN {col_name} {col_def}"))
                    print(f"Column '{col_name}' added successfully.")
            
            conn.commit()
            print("\nEmergency migration completed successfully.")
            
    except Exception as e:
        print(f"\nCRITICAL ERROR during migration: {e}")

if __name__ == "__main__":
    run_emergency_migration()
