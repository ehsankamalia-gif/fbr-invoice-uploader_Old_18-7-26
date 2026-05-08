import re
import datetime as dt
from typing import Tuple, Optional

def add_months(sourcedate: dt.date, months: int) -> dt.date:
    """
    Safely adds months to a date, handling end-of-month cases.
    Example: Jan 31 + 1 month = Feb 28 (or 29)
    """
    month = sourcedate.month - 1 + months
    year = sourcedate.year + month // 12
    month = month % 12 + 1
    day = min(sourcedate.day, [31,
        29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
        31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month-1])
    return dt.date(year, month, day)

def parse_duration_string(duration_str: str) -> Tuple[int, int]:
    """
    Parses a finance-style duration string (Months,Days) into (months, days).
    Supports:
    - "1,15" -> (1, 15)
    - "2,0"  -> (2, 0)
    - "0,20" -> (0, 20)
    - "2"    -> (2, 0) (Auto-convert single number to months)
    """
    duration_str = duration_str.strip()
    if not duration_str:
        return 0, 0

    try:
        if ',' in duration_str:
            parts = duration_str.split(',')
            if len(parts) != 2:
                raise ValueError("Invalid format. Use 'Months,Days' (e.g., 1,15)")
            
            m_str, d_str = parts[0].strip(), parts[1].strip()
            months = int(m_str) if m_str else 0
            days = int(d_str) if d_str else 0
        else:
            # Single number input defaults to months
            months = int(duration_str)
            days = 0
            
        if months < 0 or days < 0:
            raise ValueError("Duration cannot be negative.")
            
        return months, days
    except ValueError as e:
        if "invalid literal for int()" in str(e):
            raise ValueError("Please enter only numbers and a single comma.")
        raise e

def format_duration(months: int, days: int) -> str:
    """Formats months and days into a human-readable string."""
    parts = []
    if months > 0:
        parts.append(f"{months} month{'s' if months != 1 else ''}")
    if days > 0:
        parts.append(f"{days} day{'s' if days != 1 else ''}")
    
    if not parts:
        return "0 days"
    return " ".join(parts)

def calculate_total_days(months: int, days: int) -> int:
    """Calculates total days assuming 30 days per month for simplicity in finance."""
    return (months * 30) + days
