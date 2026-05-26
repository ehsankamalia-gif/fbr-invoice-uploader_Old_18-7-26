
import os
import sys
from dotenv import load_dotenv
import pymysql

load_dotenv()

db_server = os.getenv("DB_SERVER", "localhost")
db_user = os.getenv("DB_USER", "root")
db_password = os.getenv("DB_PASSWORD", "")
db_port = int(os.getenv("DB_PORT", "3306"))
db_name = os.getenv("DB_NAME", "fbr_invoice_uploader")

print("Connecting to MySQL database...")
print(f"Host: {db_server}:{db_port}")
print(f"Database: {db_name}")
print("-" * 60)

try:
    connection = pymysql.connect(
        host=db_server,
        user=db_user,
        password=db_password,
        port=db_port,
        database=db_name,
        cursorclass=pymysql.cursors.DictCursor
    )
    
    with connection.cursor() as cursor:
        # Check if table exists
        cursor.execute("SHOW TABLES LIKE 'customer_portal_auth'")
        result = cursor.fetchone()
        
        if result:
            print("Dropping existing customer_portal_auth table...")
            cursor.execute("DROP TABLE IF EXISTS customer_portal_auth")
            connection.commit()
            print("[OK] Table dropped successfully!")
        else:
            print("Table doesn't exist - nothing to drop.")
    
    connection.close()
    print("\nNow you can run 'python manage.py migrate' to create the table with the correct schema!")
    
except Exception as e:
    print(f"[ERROR] Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
