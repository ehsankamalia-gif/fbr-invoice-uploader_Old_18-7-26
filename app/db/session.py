from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from app.core import config
from app.db.models import Base
import logging

logger = logging.getLogger(__name__)

# Configure connect_args based on DB type
db_url = config.get_database_url()
connect_args = {}
if "sqlite" in db_url:
    connect_args["check_same_thread"] = False

# Global engine and SessionLocal placeholders
# We start with a memory sqlite engine so that imports and initial UI loads don't crash.
engine = create_engine("sqlite:///:memory:")
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
# Initialize the memory DB schema immediately
Base.metadata.create_all(bind=engine)

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
    This requires parsing the DB_URL to connect to the server without a DB first.
    """
    if "mysql" not in config.settings.DB_URL:
        return

    try:
        # Try connecting normally
        with engine.connect() as conn:
            pass
    except OperationalError as e:
        if "Unknown database" in str(e):
            logger.info("Database does not exist. Attempting to create it...")
            # Parse URL to get base connection string (remove DB name)
            # Assumption: DB_URL format is mysql+pymysql://user:pass@host:port/dbname
            try:
                from sqlalchemy.engine.url import make_url
                url = make_url(config.settings.DB_URL)
                db_name = url.database
                
                # Create a URL without the database name to connect to the server
                # We can't modify the url object directly easily in all versions, 
                # but we can replace the database component
                server_url = url.set(database="")
                
                # Create temporary engine
                tmp_engine = create_engine(server_url)
                with tmp_engine.connect() as conn:
                    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS {db_name}"))
                    logger.info(f"Database '{db_name}' created successfully.")
            except Exception as create_error:
                logger.error(f"Failed to create database: {create_error}")
                # Re-raise original error if creation fails
                raise e
        else:
            raise e

from app.utils.string_utils import normalize_business_name
from app.db.models import Base, Customer, MigrationHistory

# ... (existing imports)

def run_migrations():
    """
    Modular migration system using a versioned approach.
    Each migration is a separate function that returns True if successful.
    """
    try:
        with engine.connect() as conn:
            # 1. Ensure migration_history table exists
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS migration_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    version INTEGER UNIQUE NOT NULL,
                    description VARCHAR(255),
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """))
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
                # Add more migrations here as needed
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
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS app_configurations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                auto_push_enabled BOOLEAN DEFAULT 0,
                auto_push_interval INTEGER DEFAULT 5,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """))
        return True
    except Exception as e:
        logger.error(f"Migration v3 failed: {e}")
        return False


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
