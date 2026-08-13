"""Add invoice formatting standardization columns to app_configurations table.

TARGETS THE REAL MYSQL DATABASE (not in-memory SQLite):
  - Uses app.core.config.get_database_url() DIRECTLY to create a new engine
  - Does NOT import session.engine (which starts as in-memory SQLite)
  - Idempotent: columns are added only if missing

Columns added:
  - invoice_font_family (VARCHAR 200, default "Arial, sans-serif")
  - invoice_font_field_size_pt (INT, default 11)
  - invoice_font_label_size_pt (INT, default 9)
  - invoice_font_weight_field (INT, default 600)
  - invoice_font_weight_label (INT, default 500)
  - invoice_business_name_size_pt (INT, default 16)
  - invoice_business_name_weight (INT, default 800)
  - invoice_color_label (VARCHAR 20, default "#555555")
  - invoice_mono_font_family (VARCHAR 200, default "Consolas, 'Courier New', monospace")
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import get_database_url  # noqa: E402
from sqlalchemy import create_engine, text, inspect  # noqa: E402


def main():
    db_url = get_database_url()
    print(f"Using database URL (suffix shown): ...{db_url[-60:]}")
    is_sqlite = "sqlite" in db_url.lower()

    # For MySQL, ensure database exists first
    if not is_sqlite and "mysql" in db_url.lower():
        try:
            from sqlalchemy.engine.url import make_url
            url = make_url(db_url)
            db_name = url.database
            server_url = str(url.set(database=""))
            tmp = create_engine(server_url)
            with tmp.connect() as conn:
                conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{db_name}`"))
                try:
                    conn.commit()
                except Exception:
                    pass
            tmp.dispose()
            print(f"MySQL database '{db_name}' verified/created.")
        except Exception as e:
            print(f"WARNING: Could not verify MySQL database existence: {e}")

    engine = create_engine(db_url, pool_recycle=3600)

    with engine.connect() as conn:
        trans = conn.begin()
        try:
            insp = inspect(engine)
            existing_cols = set(c["name"] for c in insp.get_columns("app_configurations"))
            print(f"app_configurations currently has {len(existing_cols)} columns.")

            new_cols = [
                # (col_name, mysql_col_def_with_default, sqlite_compat_def, backfill_default)
                (
                    "invoice_font_family",
                    "VARCHAR(200) DEFAULT 'Arial, sans-serif'",
                    "TEXT",
                    "'Arial, sans-serif'",
                ),
                (
                    "invoice_font_field_size_pt",
                    "INT DEFAULT 11",
                    "INTEGER DEFAULT 11",
                    "11",
                ),
                (
                    "invoice_font_label_size_pt",
                    "INT DEFAULT 9",
                    "INTEGER DEFAULT 9",
                    "9",
                ),
                (
                    "invoice_font_weight_field",
                    "INT DEFAULT 600",
                    "INTEGER DEFAULT 600",
                    "600",
                ),
                (
                    "invoice_font_weight_label",
                    "INT DEFAULT 500",
                    "INTEGER DEFAULT 500",
                    "500",
                ),
                (
                    "invoice_business_name_size_pt",
                    "INT DEFAULT 16",
                    "INTEGER DEFAULT 16",
                    "16",
                ),
                (
                    "invoice_business_name_weight",
                    "INT DEFAULT 800",
                    "INTEGER DEFAULT 800",
                    "800",
                ),
                (
                    "invoice_color_label",
                    "VARCHAR(20) DEFAULT '#555555'",
                    "TEXT",
                    "'#555555'",
                ),
                (
                    "invoice_mono_font_family",
                    "VARCHAR(200) DEFAULT 'Consolas, \\'Courier New\\', monospace'",
                    "TEXT",
                    "'Consolas, \\'Courier New\\', monospace'",
                ),
            ]

            for col_name, mysql_def, sqlite_def, backfill in new_cols:
                if col_name in existing_cols:
                    print(f"[SKIP] {col_name} already exists")
                    continue

                col_def = sqlite_def if is_sqlite else mysql_def
                sql = f"ALTER TABLE app_configurations ADD COLUMN {col_name} {col_def}"
                print(f"[ADD ] {col_name}: {col_def}")
                conn.execute(text(sql))

                # Backfill existing rows if any NULLs (SQLite may not honor DEFAULT for existing rows)
                try:
                    conn.execute(
                        text(f"UPDATE app_configurations SET {col_name} = {backfill} WHERE {col_name} IS NULL")
                    )
                except Exception as e:
                    print(f"       (backfill skipped: {e})")

                if not is_sqlite:
                    try:
                        conn.commit()
                    except Exception:
                        pass

            trans.commit()
            print("\nMigration completed successfully.")

            # Verify
            insp2 = inspect(engine)
            final_cols = set(c["name"] for c in insp2.get_columns("app_configurations"))
            expected = {c[0] for c in new_cols}
            missing = expected - final_cols
            if missing:
                print(f"ERROR: Still missing columns: {sorted(missing)}")
                sys.exit(1)
            print(f"VERIFIED: All {len(expected)} invoice formatting columns present.")
        except Exception as e:
            trans.rollback()
            print(f"MIGRATION FAILED: {e}", file=sys.stderr)
            import traceback
            traceback.print_exc()
            sys.exit(1)
        finally:
            try:
                conn.close()
            except Exception:
                pass
    engine.dispose()


if __name__ == "__main__":
    main()
