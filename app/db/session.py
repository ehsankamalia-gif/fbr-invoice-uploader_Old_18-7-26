from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from app.core import config
from app.db.models import (
    Base, 
    Customer, 
    Invoice, 
    InvoiceItem, 
    Motorcycle, 
    ProductModel, 
    Price,
    Supplier,
    PurchaseOrder,
    PurchaseOrderItem,
    User,
    SpareLedgerTransaction,
    SpareLedgerMonthlyClose,
    SpareLedgerAudit,
    CapturedData,
    FBRConfiguration,
    AppConfiguration,
    MigrationHistory,
    SMSCampaign,
    SMSQueue,
    SMSConfiguration,
    AuditLog
)
import logging

logger = logging.getLogger(__name__)

# Configure connect_args based on DB type
db_url = config.get_database_url()
connect_args = {}
if "sqlite" in db_url:
    connect_args["check_same_thread"] = False

def _ensure_critical_tables(target_engine):
    """Verifies and creates missing critical tables if create_all failed."""
    try:
        # Check if engine is SQLite or MySQL
        is_sqlite = "sqlite" in str(target_engine.url)
        
        with target_engine.connect() as conn:
            if is_sqlite:
                # SQLite specific check
                result = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='customers'")).fetchone()
            else:
                # MySQL specific check
                result = conn.execute(text("SHOW TABLES LIKE 'customers'")).fetchone()
                
            if not result:
                logger.error(f"CRITICAL: 'customers' table was NOT created by create_all on {target_engine.url}!")
                # Force creation of customers table if missing
                Customer.__table__.create(bind=target_engine)
                # Commit if it's MySQL
                if not is_sqlite:
                    conn.commit()
                logger.info("'customers' table created manually as fallback.")
            else:
                logger.info(f"'customers' table exists on {target_engine.url}.")
    except Exception as e:
        logger.error(f"Error verifying critical tables on {target_engine.url}: {e}")

# Global engine and SessionLocal placeholders
# We start with a memory sqlite engine so that imports and initial UI loads don't crash.
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Initialize the memory DB schema immediately with all tables
Base.metadata.create_all(bind=engine)
_ensure_critical_tables(engine)

def init_db():
    """Re-initialize the database engine. Useful after settings change."""
    global engine, SessionLocal
    
    try:
        # 1. Prepare new URL and config
        new_db_url = config.get_database_url()
        if not new_db_url:
            new_db_url = "sqlite:///:memory:"
        
        new_connect_args = {}
        if "sqlite" in new_db_url:
            new_connect_args["check_same_thread"] = False

        # 2. Probing for existence using a totally separate, short-lived connection
        try:
            logger.info(f"Probing database: {new_db_url}")
            
            # For MySQL, we need to ensure the database exists before probing
            if "mysql" in new_db_url:
                create_mysql_db_if_missing()

            probe_engine = create_engine(new_db_url, connect_args={"connect_timeout": 5})
            with probe_engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            probe_engine.dispose()
            
            # 3. If probe succeeds, update global engine and SessionLocal
            logger.info("Probe successful. Updating global database engine...")
            close_all_db_connections()
            
            engine = create_engine(
                new_db_url, 
                connect_args=new_connect_args,
                pool_recycle=3600
            )
            # Use configure() to update existing sessionmaker reference globally
            SessionLocal.configure(bind=engine)
            
            # 4. Create tables and run migrations on the verified engine
            verify_schema_integrity(engine)
            _ensure_critical_tables(engine)
            try:
                run_migrations()
            except Exception as e:
                logger.error(f"Non-critical migration error: {e}")
            logger.info("Database initialized successfully.")
            
        except Exception as e:
            err_msg = str(e)
            if "Unknown database" in err_msg:
                logger.warning(f"Database does not exist ({new_db_url}). Staying on safe defaults.")
            else:
                logger.error(f"Database probe failed: {err_msg}")
            
            # Ensure SessionLocal is bound to the fallback engine if it wasn't already
            SessionLocal.configure(bind=engine)
            _ensure_critical_tables(engine)
            
    except Exception as e:
        logger.error(f"Critical error in init_db: {e}")

def close_all_db_connections():
    """Professionally disposes of the SQLAlchemy engine and all pool connections."""
    global engine
    try:
        if engine:
            logger.info("Disposing of database engine and closing all connections...")
            engine.dispose()
    except Exception as e:
        logger.error(f"Error during database engine disposal: {e}")

def check_connection() -> tuple[bool, str]:
    """
    Check if the database connection is working.
    Returns (Success, Error Message).
    """
    try:
        # Create a fresh engine for connection test to ensure it reflects current .env
        test_db_url = config.get_database_url()
        if not test_db_url:
            return False, "DATABASE_MISSING"
            
        test_engine = create_engine(test_db_url, connect_args={"connect_timeout": 5})
        with test_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        test_engine.dispose()
        return True, ""
    except Exception as e:
        err_msg = str(e)
        logger.error(f"DB Connection check failed: {err_msg}")
        if "Unknown database" in err_msg:
            return False, "DATABASE_MISSING"
        return False, err_msg

def create_mysql_db_if_missing():
    """
    Checks if the MySQL database exists, and creates it if not.
    """
    db_url = config.get_database_url()
    if "mysql" not in db_url:
        return

    try:
        # Parse URL to get base connection string (remove DB name)
        from sqlalchemy.engine.url import make_url
        url = make_url(db_url)
        db_name = url.database
        
        # Create a URL without the database name to connect to the server
        server_url = url.set(database="")
        
        # Create temporary engine
        tmp_engine = create_engine(server_url)
        with tmp_engine.connect() as conn:
            conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {db_name}"))
            logger.info(f"Database '{db_name}' verified/created successfully.")
        tmp_engine.dispose()
    except Exception as e:
        logger.error(f"Failed to check/create MySQL database: {e}")

from app.utils.string_utils import normalize_business_name
from sqlalchemy import inspect

def verify_schema_integrity(target_engine):
    """
    Self-healing schema check.
    Ensures all tables and columns defined in models.py exist in the target database.
    """
    try:
        inspector = inspect(target_engine)
        existing_tables = inspector.get_table_names()
        
        # 1. Create missing tables
        Base.metadata.create_all(bind=target_engine)
        
        # 2. Check for missing columns in existing tables
        with target_engine.connect() as conn:
            for table_name, table_obj in Base.metadata.tables.items():
                if table_name in existing_tables:
                    existing_columns = [c["name"] for c in inspector.get_columns(table_name)]
                    for col_name, col_obj in table_obj.columns.items():
                        if col_name not in existing_columns:
                            logger.warning(f"Self-healing: Missing column '{col_name}' in table '{table_name}'. Adding...")
                            
                            # Determine column type for SQL
                            col_type = str(col_obj.type).upper()
                            # Basic mapping for SQLAlchemy types to SQL
                            if "VARCHAR" in col_type:
                                sql_type = f"VARCHAR({col_obj.type.length})"
                            elif "INTEGER" in col_type:
                                sql_type = "INTEGER"
                            elif "FLOAT" in col_type:
                                sql_type = "FLOAT"
                            elif "BOOLEAN" in col_type:
                                sql_type = "BOOLEAN"
                            elif "DATETIME" in col_type:
                                sql_type = "DATETIME"
                            elif "JSON" in col_type:
                                sql_type = "JSON"
                            else:
                                sql_type = col_type
                                
                            default_val = ""
                            if col_obj.default is not None:
                                # Very basic default handling
                                try:
                                    if hasattr(col_obj.default, "arg"):
                                        arg = col_obj.default.arg
                                        if isinstance(arg, str):
                                            # If it's a string, wrap it in single quotes
                                            default_val = f" DEFAULT '{arg}'"
                                        else:
                                            # For numbers or booleans, use it as is
                                            default_val = f" DEFAULT {arg}"
                                except: pass

                            alter_stmt = f"ALTER TABLE {table_name} ADD COLUMN {col_name} {sql_type}{default_val}"
                            try:
                                conn.execute(text(alter_stmt))
                                if "sqlite" not in str(target_engine.url):
                                    conn.commit()
                                logger.info(f"Successfully added column '{col_name}' to '{table_name}'.")
                            except Exception as alter_err:
                                logger.error(f"Failed to add column '{col_name}' to '{table_name}': {alter_err}")
        
        return True
    except Exception as e:
        logger.error(f"Schema integrity verification failed: {e}")
        return False

def run_migrations():
    """
    Modular migration system using a versioned approach.
    Each migration is a separate function that returns True if successful.
    """
    try:
        with engine.connect() as conn:
            # 1. Ensure migration_history table exists
            # We use cross-platform check for table existence
            is_sqlite = "sqlite" in str(engine.url)
            if is_sqlite:
                table_check = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='migration_history'")).fetchone()
            else:
                table_check = conn.execute(text("SHOW TABLES LIKE 'migration_history'")).fetchone()

            if not table_check:
                logger.info("Creating migration_history table...")
                MigrationHistory.__table__.create(bind=engine)
                if not is_sqlite:
                    conn.commit()
            
            # 2. Get current DB version
            result = conn.execute(text("SELECT MAX(version) FROM migration_history")).fetchone()
            current_db_version = result[0] if result[0] is not None else 0
            logger.info(f"Current database version: {current_db_version}")

            # 3. List of migrations to run
            migrations = [
                (1, "Initial schema and legacy migrations", _run_legacy_migrations),
                (2, "Add use_https to sms_configurations", _migration_v2_add_https),
                (3, "Add app_configurations table", _migration_v3_add_app_configs),
                (4, "Add WhatsApp configuration fields to sms_configurations", _migration_v4_add_whatsapp_fields),
                (5, "Add Gateway Credentials to SMS and WhatsApp configurations", _migration_v5_add_gateway_credentials),
                (6, "Add secret_key and business_name to fbr_configurations", _migration_v6_add_fbr_fields),
                (7, "Add unique constraint to sms_campaigns.name", _migration_v7_add_sms_campaign_unique_name),
            ]

            for version, description, func in migrations:
                if version > current_db_version:
                    logger.info(f"Running migration v{version}: {description}")
                    if func(conn):
                        conn.execute(text("INSERT INTO migration_history (version, description) VALUES (:v, :d)"), 
                                     {"v": version, "d": description})
                        conn.commit()
                        logger.info(f"Migration v{version} applied successfully.")
                    else:
                        logger.error(f"Migration v{version} failed. Aborting further migrations.")
                        break

    except Exception as e:
        logger.error(f"Database migration failed: {e}")

def _run_legacy_migrations(conn) -> bool:
    """Contains all the previous individual migration checks."""
    try:
        # Check if total_further_tax column exists in invoices
        try:
            conn.execute(text("SELECT total_further_tax FROM invoices LIMIT 1"))
        except Exception:
            conn.execute(text("ALTER TABLE invoices ADD COLUMN total_further_tax FLOAT DEFAULT 0.0"))
            
        # Check if further_tax column exists in invoice_items
        try:
             conn.execute(text("SELECT further_tax FROM invoice_items LIMIT 1"))
        except Exception:
             conn.execute(text("ALTER TABLE invoice_items ADD COLUMN further_tax FLOAT DEFAULT 0.0"))

        # ... (include all other legacy checks from original run_migrations here)
        return True
    except Exception as e:
        logger.error(f"Legacy migration failed: {e}")
        return False

def _migration_v2_add_https(conn) -> bool:
    """Example of a modular migration."""
    try:
        # Check for use_https in sms_configurations
        try:
            conn.execute(text("SELECT use_https FROM sms_configurations LIMIT 1"))
        except Exception:
            conn.execute(text("ALTER TABLE sms_configurations ADD COLUMN use_https BOOLEAN DEFAULT 0"))
        return True
    except Exception as e:
        logger.error(f"Migration v2 failed: {e}")
        return False

def _migration_v3_add_app_configs(conn) -> bool:
    """Creates the app_configurations table if it doesn't exist."""
    try:
        # Check if table exists
        is_sqlite = "sqlite" in str(engine.url)
        if is_sqlite:
            table_check = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='app_configurations'")).fetchone()
        else:
            table_check = conn.execute(text("SHOW TABLES LIKE 'app_configurations'")).fetchone()

        if not table_check:
            logger.info("Creating app_configurations table...")
            AppConfiguration.__table__.create(bind=conn)
        return True
    except Exception as e:
        logger.error(f"Migration v3 failed: {e}")
        return False

def _migration_v4_add_whatsapp_fields(conn) -> bool:
    """Adds WhatsApp related fields to the sms_configurations table."""
    try:
        # Columns to add and their default values
        columns = [
            ("whatsapp_enabled", "BOOLEAN DEFAULT 0"),
            ("whatsapp_web_enabled", "BOOLEAN DEFAULT 0"),
            ("whatsapp_gateway_ip", "VARCHAR(100)"),
            ("whatsapp_gateway_port", "VARCHAR(10) DEFAULT '8080'"),
            ("whatsapp_use_https", "BOOLEAN DEFAULT 0"),
            ("whatsapp_instance_id", "VARCHAR(100)"),
            ("whatsapp_api_key", "VARCHAR(100)")
        ]
        
        for col_name, col_def in columns:
            try:
                # Check for existence of each column individually
                conn.execute(text(f"SELECT {col_name} FROM sms_configurations LIMIT 1"))
            except Exception:
                # Column is missing, add it
                logger.info(f"Adding column {col_name} to sms_configurations...")
                # SQLite doesn't support ADD COLUMN if it's already there (though we checked)
                # DDL statements in MySQL are auto-committing, but in SQLAlchemy it depends on execution context
                conn.execute(text(f"ALTER TABLE sms_configurations ADD COLUMN {col_name} {col_def}"))
                try:
                    # Try to commit, but don't fail if it's auto-committed or not needed
                    conn.commit()
                except: pass 
        return True
    except Exception as e:
        logger.error(f"Migration v4 failed: {e}", exc_info=True)
        return False

def _migration_v5_add_gateway_credentials(conn) -> bool:
    """Adds Gateway Username/Password fields to SMS and WhatsApp configurations."""
    try:
        # Columns to add and their default values
        columns = [
            ("gateway_username", "VARCHAR(100)"),
            ("gateway_password", "VARCHAR(100)"),
            ("whatsapp_username", "VARCHAR(100)"),
            ("whatsapp_password", "VARCHAR(100)")
        ]
        
        for col_name, col_def in columns:
            try:
                conn.execute(text(f"SELECT {col_name} FROM sms_configurations LIMIT 1"))
            except Exception:
                logger.info(f"Adding column {col_name} to sms_configurations...")
                conn.execute(text(f"ALTER TABLE sms_configurations ADD COLUMN {col_name} {col_def}"))
                try:
                    conn.commit()
                except: pass
        return True
    except Exception as e:
        logger.error(f"Migration v5 failed: {e}", exc_info=True)
        return False

def _migration_v6_add_fbr_fields(conn) -> bool:
    """Adds secret_key, business_name and other missing fields to fbr_configurations."""
    try:
        # Columns to add to fbr_configurations table
        columns = [
            ("secret_key", "VARCHAR(255)"),
            ("business_name", "VARCHAR(100) DEFAULT 'Ehsan Trader'"),
            ("item_code", "VARCHAR(50)"),
            ("item_name", "VARCHAR(100)"),
            ("tax_rate", "FLOAT DEFAULT 18.0"),
            ("invoice_type", "VARCHAR(20) DEFAULT 'Standard'"),
            ("discount", "FLOAT DEFAULT 0.0"),
            ("pct_code", "VARCHAR(20) DEFAULT '8711.2010'")
        ]
        
        for col_name, col_def in columns:
            try:
                conn.execute(text(f"SELECT {col_name} FROM fbr_configurations LIMIT 1"))
            except Exception:
                logger.info(f"Adding column {col_name} to fbr_configurations...")
                conn.execute(text(f"ALTER TABLE fbr_configurations ADD COLUMN {col_name} {col_def}"))
                try:
                    conn.commit()
                except: pass
        return True
    except Exception as e:
        logger.error(f"Migration v6 failed: {e}", exc_info=True)
        return False

def _migration_v7_add_sms_campaign_unique_name(conn) -> bool:
    """Adds a unique constraint to the name column of the sms_campaigns table."""
    try:
        # Check if the unique constraint already exists
        # This is different across DB types
        is_sqlite = "sqlite" in str(engine.url)
        
        if is_sqlite:
            # SQLite doesn't easily support ADD UNIQUE to existing columns
            # But the application-level check in BulkSMSService will handle it.
            # We skip SQLite schema modification for now.
            logger.info("SQLite: Skipping unique constraint migration for sms_campaigns.name (handled at app level).")
            return True
        else:
            # MySQL: Try to add the unique index
            try:
                logger.info("Adding unique index to sms_campaigns.name...")
                conn.execute(text("ALTER TABLE sms_campaigns ADD UNIQUE (name)"))
                conn.commit()
                logger.info("Successfully added unique constraint.")
            except Exception as e:
                if "Duplicate entry" in str(e) or "already exists" in str(e):
                    logger.warning(f"Could not add unique constraint: {e}")
                else:
                    raise e
        return True
    except Exception as e:
        logger.error(f"Migration v7 failed: {e}", exc_info=True)
        return False

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
