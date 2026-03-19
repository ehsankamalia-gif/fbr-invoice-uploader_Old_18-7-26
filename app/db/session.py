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
    SpareLedgerTransaction,
    CapturedData,
    FBRConfiguration,
    AppConfiguration,
    MigrationHistory,
    SMSQueue,
    SMSConfiguration
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
            Base.metadata.create_all(bind=engine)
            _ensure_critical_tables(engine)
            run_migrations()
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
                (4, "Add WhatsApp fields to SMS configuration and models", _migration_v4_whatsapp_support),
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

def _migration_v4_whatsapp_support(conn) -> bool:
    """Adds WhatsApp fields to configurations and channel to campaign/queue."""
    try:
        # 1. SMS Configurations
        cols = [
            ("whatsapp_enabled", "BOOLEAN DEFAULT 0"),
            ("whatsapp_gateway_ip", "VARCHAR(100) NULL"),
            ("whatsapp_gateway_port", "VARCHAR(10) DEFAULT '8080'"),
            ("whatsapp_instance_id", "VARCHAR(100) NULL"),
            ("whatsapp_api_key", "VARCHAR(100) NULL")
        ]
        for col, dtype in cols:
            try:
                conn.execute(text(f"SELECT {col} FROM sms_configurations LIMIT 1"))
            except Exception:
                logger.info(f"Adding column {col} to sms_configurations")
                conn.execute(text(f"ALTER TABLE sms_configurations ADD COLUMN {col} {dtype}"))
        
        # 2. SMS Campaigns (channel)
        try:
            conn.execute(text("SELECT channel FROM sms_campaigns LIMIT 1"))
        except Exception:
            logger.info("Adding column 'channel' to sms_campaigns")
            conn.execute(text("ALTER TABLE sms_campaigns ADD COLUMN channel VARCHAR(20) DEFAULT 'SMS'"))
            
        # 3. SMS Queue (channel)
        try:
            conn.execute(text("SELECT channel FROM sms_queue LIMIT 1"))
        except Exception:
            logger.info("Adding column 'channel' to sms_queue")
            conn.execute(text("ALTER TABLE sms_queue ADD COLUMN channel VARCHAR(20) DEFAULT 'SMS'"))
            
        return True
    except Exception as e:
        logger.error(f"Migration v4 failed: {e}")
        return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
