"""Bulk import/export of parts + stock via Excel (.xlsx) or CSV.

Export writes every part (active and inactive) with its current stock
and full master-data fields, in a layout designed to be edited and
re-imported as-is - the exported file doubles as the import template.

Import matches rows to existing parts by Part No (case-insensitive): a
match updates that part's master fields, and if the row's Current
Stock differs from today's ledger balance, records ONE stock_service
adjustment to close the gap (stock is never written directly here -
see spare_parts/__init__.py). No match creates a new part, with its
opening stock recorded as a ledger entry the same way.

Categories/brands named in a row are matched by name (case-insensitive)
and auto-created if they don't exist yet - the same inline "+"
convenience already in the Part dialog, just applied in bulk here.

Every row is attempted independently: one bad row (bad number, missing
Part No, a stock-decrease that would go negative, etc.) is recorded as
an error in the returned ImportResult and the session is rolled back
to a clean state before the next row - it never aborts the rest of the
file. A row that errors AFTER its part was already created/updated
(e.g. the stock adjustment step fails) still keeps that part - only
the failed step is rolled back, matching how the Parts page itself
treats "save the part" and "adjust its stock" as two separate actions.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font
from sqlalchemy.orm import Session

from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service
from spare_parts.logging_config import get_logger

logger = get_logger(__name__)

COLUMNS = [
    "Part No", "Name", "Category", "Brand", "Unit", "Pack Size",
    "Barcode", "Rack Location", "Compatible Models", "Cost Price",
    "Retail Price", "Wholesale Price", "Min Wholesale Qty",
    "Reorder Level", "Current Stock", "Notes", "Active",
]

_CANONICAL_BY_NORMALIZED = {c.strip().lower(): c for c in COLUMNS}


def _normalize_header(text) -> str:
    return str(text or "").strip().lower()


def _cell_is_blank(value) -> bool:
    return value is None or str(value).strip() == ""


# --- Export ------------------------------------------------------------

def export_rows(db: Session) -> list[dict]:
    """One dict per part (active and inactive), keyed by the COLUMNS
    header names, sorted by Part No. Relationship access (category/
    brand name) is safe here since it happens while the caller's
    session is still open."""
    parts = parts_service.search_parts(db, active_only=False)
    stock_by_id = stock_service.get_current_stock_bulk(db, [p.id for p in parts])
    rows = []
    for part in sorted(parts, key=lambda p: p.part_no):
        rows.append({
            "Part No": part.part_no,
            "Name": part.name,
            "Category": part.category.name if part.category else "",
            "Brand": part.brand.name if part.brand else "",
            "Unit": part.unit or "",
            "Pack Size": part.pack_size or 1,
            "Barcode": part.barcode or "",
            "Rack Location": part.rack_location or "",
            "Compatible Models": part.compatible_models or "",
            "Cost Price": float(part.cost_price or 0),
            "Retail Price": float(part.retail_price or 0),
            "Wholesale Price": float(part.wholesale_price or 0),
            "Min Wholesale Qty": part.min_wholesale_qty or 1,
            "Reorder Level": part.reorder_level or 0,
            "Current Stock": stock_by_id.get(part.id, 0),
            "Notes": part.notes or "",
            "Active": "Yes" if part.is_active else "No",
        })
    return rows


def write_csv(path: str, rows: list[dict]) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def write_xlsx(path: str, rows: list[dict]) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Parts & Stock"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in rows:
        ws.append([row.get(c, "") for c in COLUMNS])
    for col_idx, header in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max(12, min(40, len(header) + 4))
    wb.save(path)


# --- Sample/template file ------------------------------------------------

SAMPLE_INSTRUCTIONS = [
    "How to fill this in:",
    "- Part No and Name are the only required columns - every other column may be left blank.",
    "- Part No must be unique. Importing a Part No that already exists UPDATES that part"
    " instead of creating a duplicate.",
    "- Category and Brand are matched by name and created automatically if they don't exist yet.",
    "- Current Stock: leave blank to leave that part's stock untouched. Enter a number to set"
    " stock to exactly that amount - the difference from today's stock is recorded as a"
    " 'Stock Import' adjustment, never by editing stock directly.",
    "- Active: Yes or No (defaults to Yes if left blank).",
    "- Pack Size and Min Wholesale Qty are whole numbers (default to 1 if left blank).",
    "- Prices are plain numbers, no currency symbols or commas.",
    "- Delete these two example rows (or just overwrite them) before importing your own data.",
]


def sample_rows() -> list[dict]:
    """A couple of illustrative example rows - one with every column
    filled in, one showing that only Part No and Name are actually
    required - for the 'Download Sample File' button. Not read from the
    database, so this needs no db session."""
    return [
        {
            "Part No": "HD-1001", "Name": "Brake Pad Set", "Category": "Brakes",
            "Brand": "Honda", "Unit": "set", "Pack Size": 1, "Barcode": "123456789012",
            "Rack Location": "A1-03", "Compatible Models": "Honda Civic 2016-2020",
            "Cost Price": 450, "Retail Price": 650, "Wholesale Price": 550,
            "Min Wholesale Qty": 5, "Reorder Level": 10, "Current Stock": 100,
            "Notes": "Example row - edit or delete before importing", "Active": "Yes",
        },
        {
            "Part No": "HD-1002", "Name": "Clutch Plate", "Category": "", "Brand": "",
            "Unit": "", "Pack Size": "", "Barcode": "", "Rack Location": "",
            "Compatible Models": "", "Cost Price": "", "Retail Price": "", "Wholesale Price": "",
            "Min Wholesale Qty": "", "Reorder Level": "", "Current Stock": "",
            "Notes": "Example row - only Part No and Name are required, everything else can be blank",
            "Active": "",
        },
    ]


def write_sample_csv(path: str) -> None:
    write_csv(path, sample_rows())


def write_sample_xlsx(path: str) -> None:
    wb = Workbook()
    ws = wb.active
    ws.title = "Parts & Stock"
    ws.append(COLUMNS)
    for cell in ws[1]:
        cell.font = Font(bold=True)
    for row in sample_rows():
        ws.append([row.get(c, "") for c in COLUMNS])
    for col_idx, header in enumerate(COLUMNS, start=1):
        ws.column_dimensions[ws.cell(row=1, column=col_idx).column_letter].width = max(12, min(40, len(header) + 4))

    instructions_ws = wb.create_sheet("Instructions")
    for row_idx, line in enumerate(SAMPLE_INSTRUCTIONS, start=1):
        cell = instructions_ws.cell(row=row_idx, column=1, value=line)
        if row_idx == 1:
            cell.font = Font(bold=True)
    instructions_ws.column_dimensions["A"].width = 100
    wb.save(path)


# --- Import: file parsing -----------------------------------------------

def _rows_from_grid(grid: list[list]) -> list[dict]:
    """Maps a raw 2D grid (first row = headers) to a list of dicts keyed
    by canonical COLUMNS names. Header matching is case/whitespace
    -insensitive but otherwise exact, so a file re-exported from this
    same feature always matches - unmatched columns are simply ignored,
    and an unmatched blank/trailing row is skipped entirely."""
    if not grid:
        return []
    header_row = grid[0]
    header_map: dict[int, str] = {}
    for idx, cell in enumerate(header_row):
        canonical = _CANONICAL_BY_NORMALIZED.get(_normalize_header(cell))
        if canonical:
            header_map[idx] = canonical

    if "Part No" not in header_map.values() or "Name" not in header_map.values():
        raise SparePartsValidationError(
            "This file is missing the required 'Part No' and/or 'Name' column "
            "headers. Use 'Export to Excel/CSV' first to get a template with "
            "the correct headers."
        )

    rows = []
    for raw_row in grid[1:]:
        if all(_cell_is_blank(c) for c in raw_row):
            continue
        record = {canonical: (raw_row[idx] if idx < len(raw_row) else "") for idx, canonical in header_map.items()}
        rows.append(record)
    return rows


def read_csv(path: str) -> list[dict]:
    with open(path, "r", newline="", encoding="utf-8-sig") as f:
        grid = list(csv.reader(f))
    return _rows_from_grid(grid)


def read_xlsx(path: str) -> list[dict]:
    wb = load_workbook(path, data_only=True, read_only=True)
    try:
        ws = wb.active
        grid = [list(row) for row in ws.iter_rows(values_only=True)]
    finally:
        wb.close()
    return _rows_from_grid(grid)


# --- Import: row processing ---------------------------------------------

@dataclass
class ImportRowError:
    row_number: int  # 1-based, counting the header as row 1 (matches Excel's own row numbers)
    part_no: str
    message: str


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    stock_adjusted: int = 0
    errors: list[ImportRowError] = field(default_factory=list)

    @property
    def total_ok(self) -> int:
        return self.created + self.updated


def _parse_decimal(value) -> Decimal:
    if _cell_is_blank(value):
        return Decimal("0")
    try:
        return Decimal(str(value).strip())
    except InvalidOperation:
        raise SparePartsValidationError(f"'{value}' is not a valid number.")


def _parse_int(value, default: int) -> int:
    if _cell_is_blank(value):
        return default
    try:
        return int(Decimal(str(value).strip()))
    except InvalidOperation:
        raise SparePartsValidationError(f"'{value}' is not a valid whole number.")


def _parse_active(value) -> bool:
    text = _normalize_header(value)
    if text in ("no", "n", "false", "0", "inactive"):
        return False
    return True  # blank or anything else defaults to active


def import_rows(db: Session, rows: list[dict]) -> ImportResult:
    result = ImportResult()
    category_by_name = {c.name.strip().lower(): c for c in parts_service.list_categories(db)}
    brand_by_name = {b.name.strip().lower(): b for b in parts_service.list_brands(db)}

    for i, row in enumerate(rows):
        row_number = i + 2  # header occupies row 1
        part_no = str(row.get("Part No") or "").strip()
        name = str(row.get("Name") or "").strip()
        try:
            if not part_no or not name:
                raise SparePartsValidationError("Part No and Name are both required.")

            category_id = None
            category_name = str(row.get("Category") or "").strip()
            if category_name:
                key = category_name.lower()
                category = category_by_name.get(key)
                if not category:
                    category = parts_service.create_category(db, category_name)
                    category_by_name[key] = category
                category_id = category.id

            brand_id = None
            brand_name = str(row.get("Brand") or "").strip()
            if brand_name:
                key = brand_name.lower()
                brand = brand_by_name.get(key)
                if not brand:
                    brand = parts_service.create_brand(db, brand_name)
                    brand_by_name[key] = brand
                brand_id = brand.id

            fields = dict(
                name=name,
                category_id=category_id,
                brand_id=brand_id,
                unit=str(row.get("Unit") or "pcs").strip() or "pcs",
                pack_size=_parse_int(row.get("Pack Size"), 1) or 1,
                barcode=str(row.get("Barcode") or "").strip(),
                rack_location=str(row.get("Rack Location") or "").strip(),
                compatible_models=str(row.get("Compatible Models") or "").strip(),
                cost_price=_parse_decimal(row.get("Cost Price")),
                retail_price=_parse_decimal(row.get("Retail Price")),
                wholesale_price=_parse_decimal(row.get("Wholesale Price")),
                min_wholesale_qty=_parse_int(row.get("Min Wholesale Qty"), 1) or 1,
                reorder_level=_parse_int(row.get("Reorder Level"), 0),
                notes=str(row.get("Notes") or "").strip(),
            )
            is_active = _parse_active(row.get("Active"))

            existing = parts_service.get_part_by_no(db, part_no)
            if existing:
                part = parts_service.update_part(db, existing.id, part_no=part_no, **fields)
                if bool(part.is_active) != is_active:
                    parts_service.set_part_active(db, part.id, is_active)
                result.updated += 1
            else:
                part = parts_service.create_part(db, part_no=part_no, **fields)
                if not is_active:
                    parts_service.set_part_active(db, part.id, False)
                result.created += 1

            stock_cell = row.get("Current Stock")
            if not _cell_is_blank(stock_cell):
                target_stock = _parse_int(stock_cell, 0)
                current_stock = stock_service.get_current_stock(db, part.id)
                diff = target_stock - current_stock
                if diff > 0:
                    stock_service.create_adjustment(
                        db, part_id=part.id, direction="IN", qty=diff, reason="Stock Import",
                    )
                    result.stock_adjusted += 1
                elif diff < 0:
                    stock_service.create_adjustment(
                        db, part_id=part.id, direction="OUT", qty=abs(diff), reason="Stock Import",
                    )
                    result.stock_adjusted += 1
        except SparePartsValidationError as e:
            db.rollback()
            result.errors.append(ImportRowError(row_number, part_no or f"(row {row_number})", str(e)))
        except Exception as e:
            db.rollback()
            logger.error(f"Unexpected error importing row {row_number}: {e}", exc_info=True)
            result.errors.append(
                ImportRowError(row_number, part_no or f"(row {row_number})", f"Unexpected error: {e}")
            )

    return result
