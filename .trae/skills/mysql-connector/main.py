import os
import sys
from pathlib import Path

# Add project root to path so we can import from app.core.config
project_root = Path(__file__).resolve().parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import get_database_url
from sqlalchemy import create_engine, text
import json


def execute_query(query, limit=100):
    """Execute a SQL query and return results as a list of dictionaries."""
    try:
        db_url = get_database_url()
        engine = create_engine(db_url)
        with engine.connect() as conn:
            result = conn.execute(text(query))
            
            # Get column names
            columns = result.keys()
            
            # Fetch rows (limited by limit)
            rows = []
            for idx, row in enumerate(result):
                if idx >= limit:
                    break
                rows.append(dict(zip(columns, row)))
                
            return {
                "success": True,
                "columns": list(columns),
                "rows": rows,
                "total_rows": len(rows)
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def list_tables():
    """List all tables in the database."""
    try:
        db_url = get_database_url()
        engine = create_engine(db_url)
        
        # For MySQL: SHOW TABLES;
        if 'mysql' in db_url:
            query = "SHOW TABLES"
        else:
            # Fallback for SQLite
            query = "SELECT name FROM sqlite_master WHERE type='table'"
        result = execute_query(query)
        if result["success"]:
            tables = [row[list(row.keys())[0]] for row in result["rows"]]
            return {
                "success": True,
                "tables": tables
            }
        return result
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "No action not specified"}))
        return
    
    action = sys.argv[1]
    
    if action == "query_database":
        if len(sys.argv) < 3:
            print(json.dumps({"success": False, "error": "Query parameter required"}))
            return
        
        query = sys.argv[2]
        limit = int(sys.argv[3]) if len(sys.argv) >3 else 100
        result = execute_query(query, limit)
        print(json.dumps(result))
    elif action == "list_tables":
        result = list_tables()
        print(json.dumps(result))
    else:
        print(json.dumps({"success": False, "error": f"Unknown action: {action}"}))


if __name__ == "__main__":
    main()