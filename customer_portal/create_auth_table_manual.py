
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
        # First drop table if exists
        print("Dropping customer_portal_auth table if it exists...")
        cursor.execute("DROP TABLE IF EXISTS customer_portal_auth")
        
        # Now create the table
        print("Creating customer_portal_auth table...")
        create_table_sql = """
        CREATE TABLE customer_portal_auth (
            id INT AUTO_INCREMENT PRIMARY KEY,
            customer_id INT NOT NULL,
            phone_number VARCHAR(20) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            is_active BOOLEAN DEFAULT TRUE,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """
        cursor.execute(create_table_sql)
        connection.commit()
        
        print("[OK] customer_portal_auth table created successfully!")
        
        # Verify the table exists
        cursor.execute("SHOW TABLES LIKE 'customer_portal_auth'")
        result = cursor.fetchone()
        if result:
            print("[OK] Verified - table exists in database!")
        
    connection.close()
    print("\nDone! Now you can log in!")
    
except Exception as e:
    print(f"[ERROR] Error: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
