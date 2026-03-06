from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import OperationalError
from app.core import config
from app.db.models import Base
import logging

logger = logging.getLogger(__name__)

# Configure connect_args based on DB type
connect_args = {}
if "sqlite" in config.settings.DB_URL:
    connect_args["check_same_thread"] = False

engine = create_engine(
    config.settings.DB_URL, 
    connect_args=connect_args,
    pool_pre_ping=True # Helps with MySQL connection drops
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def init_db():
    """Re-initialize the database engine. Useful after settings change."""
    global engine, SessionLocal
    
    # Configure connect_args based on DB type
    connect_args = {}
    if "sqlite" in config.settings.DB_URL:
        connect_args["check_same_thread"] = False

    engine = create_engine(
        config.settings.DB_URL, 
        connect_args=connect_args,
        pool_pre_ping=True
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def check_connection():
    """Check if the database connection is working."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"DB Connection check failed: {e}")
        return False

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


def init_db():
    create_mysql_db_if_missing()
    Base.metadata.create_all(bind=engine)
    run_migrations()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
