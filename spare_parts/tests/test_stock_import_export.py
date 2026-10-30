"""Unit tests for spare_parts.services.stock_import_export.

Uses the same isolated in-memory SQLite fixture as test_parts_service.py.
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401 - registers tables on SpareBase.metadata
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service, stock_import_export as sie


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


# --- Export --------------------------------------------------------------

def test_export_rows_includes_all_fields_and_current_stock(db_session):
    cat = parts_service.create_category(db_session, "Engine Parts")
    brand = parts_service.create_brand(db_session, "Honda")
    part = parts_service.create_part(
        db_session, part_no="hd-1", name="Brake Pad", category_id=cat.id, brand_id=brand.id,
        unit="box", pack_size=5, cost_price="10.50", retail_price="20", wholesale_price="15",
    )
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=30, reason="Opening")

    rows = sie.export_rows(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row["Part No"] == "HD-1"
    assert row["Name"] == "Brake Pad"
    assert row["Category"] == "Engine Parts"
    assert row["Brand"] == "Honda"
    assert row["Unit"] == "box"
    assert row["Pack Size"] == 5
    assert row["Cost Price"] == 10.5
    assert row["Current Stock"] == 30
    assert row["Active"] == "Yes"


def test_export_rows_includes_inactive_parts(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    parts_service.set_part_active(db_session, part.id, False)
    rows = sie.export_rows(db_session)
    assert len(rows) == 1
    assert rows[0]["Active"] == "No"


def test_write_and_read_csv_round_trip(db_session, tmp_path):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", unit="pcs")
    rows = sie.export_rows(db_session)
    path = tmp_path / "export.csv"
    sie.write_csv(str(path), rows)

    read_back = sie.read_csv(str(path))
    assert len(read_back) == 1
    assert read_back[0]["Part No"] == "HD-1"
    assert read_back[0]["Name"] == "Brake Pad"


def test_write_and_read_xlsx_round_trip(db_session, tmp_path):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", unit="pcs")
    rows = sie.export_rows(db_session)
    path = tmp_path / "export.xlsx"
    sie.write_xlsx(str(path), rows)

    read_back = sie.read_xlsx(str(path))
    assert len(read_back) == 1
    assert read_back[0]["Part No"] == "HD-1"
    assert read_back[0]["Name"] == "Brake Pad"


# --- Sample/template file -------------------------------------------------

def test_sample_rows_has_required_columns_filled():
    rows = sie.sample_rows()
    assert len(rows) >= 1
    for row in rows:
        assert row["Part No"]
        assert row["Name"]


def test_sample_csv_is_importable_without_needing_the_db(db_session, tmp_path):
    path = tmp_path / "sample.csv"
    sie.write_sample_csv(str(path))
    rows = sie.read_csv(str(path))
    result = sie.import_rows(db_session, rows)
    assert result.created == len(sie.sample_rows())
    assert result.errors == []


def test_sample_xlsx_has_an_instructions_sheet_the_importer_ignores(db_session, tmp_path):
    path = tmp_path / "sample.xlsx"
    sie.write_sample_xlsx(str(path))

    from openpyxl import load_workbook
    wb = load_workbook(str(path))
    assert "Instructions" in wb.sheetnames
    wb.close()

    # read_xlsx only reads the active/first sheet - the instructions
    # sheet must never be mistaken for data rows.
    rows = sie.read_xlsx(str(path))
    assert len(rows) == len(sie.sample_rows())
    result = sie.import_rows(db_session, rows)
    assert result.created == len(sie.sample_rows())
    assert result.errors == []


# --- Import: header validation -------------------------------------------

def test_rows_from_grid_requires_part_no_and_name_headers():
    with pytest.raises(SparePartsValidationError):
        sie._rows_from_grid([["Name", "Category"], ["Brake Pad", "Engine"]])


def test_rows_from_grid_skips_fully_blank_rows():
    grid = [["Part No", "Name"], ["HD-1", "Brake Pad"], ["", ""], [None, None]]
    rows = sie._rows_from_grid(grid)
    assert len(rows) == 1


def test_rows_from_grid_header_matching_is_case_and_space_insensitive():
    grid = [[" part no ", " NAME "], ["HD-1", "Brake Pad"]]
    rows = sie._rows_from_grid(grid)
    assert rows[0]["Part No"] == "HD-1"
    assert rows[0]["Name"] == "Brake Pad"


# --- Import: creating new parts -------------------------------------------

def test_import_creates_new_part_with_opening_stock(db_session):
    rows = [{
        "Part No": "HD-1", "Name": "Brake Pad", "Category": "Engine Parts",
        "Brand": "Honda", "Unit": "box", "Current Stock": "25",
        "Cost Price": "10", "Retail Price": "20", "Wholesale Price": "15",
    }]
    result = sie.import_rows(db_session, rows)
    assert result.created == 1
    assert result.updated == 0
    assert result.stock_adjusted == 1
    assert result.errors == []

    part = parts_service.get_part_by_no(db_session, "HD-1")
    assert part is not None
    assert part.category.name == "Engine Parts"
    assert part.brand.name == "Honda"
    assert stock_service.get_current_stock(db_session, part.id) == 25


def test_import_reuses_existing_category_and_brand_across_rows(db_session):
    rows = [
        {"Part No": "HD-1", "Name": "Brake Pad", "Category": "Engine Parts", "Brand": "Honda"},
        {"Part No": "HD-2", "Name": "Clutch Plate", "Category": "Engine Parts", "Brand": "Honda"},
    ]
    sie.import_rows(db_session, rows)
    assert len(parts_service.list_categories(db_session)) == 1
    assert len(parts_service.list_brands(db_session)) == 1


def test_import_new_part_without_stock_column_has_zero_stock(db_session):
    rows = [{"Part No": "HD-1", "Name": "Brake Pad"}]
    result = sie.import_rows(db_session, rows)
    assert result.created == 1
    assert result.stock_adjusted == 0
    part = parts_service.get_part_by_no(db_session, "HD-1")
    assert stock_service.get_current_stock(db_session, part.id) == 0


def test_import_inactive_column_deactivates_new_part(db_session):
    rows = [{"Part No": "HD-1", "Name": "Brake Pad", "Active": "No"}]
    sie.import_rows(db_session, rows)
    part = parts_service.get_part_by_no(db_session, "HD-1")
    assert part.is_active is False


# --- Import: updating existing parts --------------------------------------

def test_import_updates_existing_part_fields(db_session):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", unit="pcs")
    rows = [{"Part No": "hd-1", "Name": "Brake Pad V2", "Unit": "box"}]
    result = sie.import_rows(db_session, rows)
    assert result.updated == 1
    assert result.created == 0

    part = parts_service.get_part_by_no(db_session, "HD-1")
    assert part.name == "Brake Pad V2"
    assert part.unit == "box"


def test_import_increases_stock_to_match_target(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=10, reason="Opening")
    rows = [{"Part No": "HD-1", "Name": "Brake Pad", "Current Stock": "40"}]
    result = sie.import_rows(db_session, rows)
    assert result.stock_adjusted == 1
    assert stock_service.get_current_stock(db_session, part.id) == 40


def test_import_decreases_stock_to_match_target(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=40, reason="Opening")
    rows = [{"Part No": "HD-1", "Name": "Brake Pad", "Current Stock": "10"}]
    result = sie.import_rows(db_session, rows)
    assert result.stock_adjusted == 1
    assert stock_service.get_current_stock(db_session, part.id) == 10


def test_import_matching_stock_value_does_not_adjust(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=15, reason="Opening")
    rows = [{"Part No": "HD-1", "Name": "Brake Pad", "Current Stock": "15"}]
    result = sie.import_rows(db_session, rows)
    assert result.stock_adjusted == 0


def test_import_toggles_existing_part_to_inactive(db_session):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    rows = [{"Part No": "HD-1", "Name": "Brake Pad", "Active": "No"}]
    sie.import_rows(db_session, rows)
    part = parts_service.get_part_by_no(db_session, "HD-1")
    assert part.is_active is False


# --- Import: error handling, one bad row doesn't abort the batch ---------

def test_import_missing_part_no_or_name_records_row_error(db_session):
    rows = [
        {"Part No": "", "Name": "Brake Pad"},
        {"Part No": "HD-2", "Name": ""},
        {"Part No": "HD-3", "Name": "Clutch Plate"},
    ]
    result = sie.import_rows(db_session, rows)
    assert result.created == 1
    assert len(result.errors) == 2
    assert result.errors[0].row_number == 2
    assert result.errors[1].row_number == 3


def test_import_invalid_price_records_row_error_without_aborting_batch(db_session):
    rows = [
        {"Part No": "HD-1", "Name": "Brake Pad", "Cost Price": "not-a-number"},
        {"Part No": "HD-2", "Name": "Clutch Plate", "Cost Price": "12.50"},
    ]
    result = sie.import_rows(db_session, rows)
    assert result.created == 1
    assert len(result.errors) == 1
    assert result.errors[0].part_no == "HD-1"
    assert parts_service.get_part_by_no(db_session, "HD-2") is not None
    assert parts_service.get_part_by_no(db_session, "HD-1") is None


def test_import_stock_decrease_below_zero_is_recorded_as_row_error(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    stock_service.create_adjustment(db_session, part_id=part.id, direction="IN", qty=5, reason="Opening")
    rows = [{"Part No": "HD-1", "Name": "Brake Pad", "Current Stock": "-5"}]
    result = sie.import_rows(db_session, rows)
    assert len(result.errors) == 1
    # The part's own fields were still updated/committed before the stock
    # step failed - only the stock adjustment itself was rolled back.
    assert result.updated == 1
    assert stock_service.get_current_stock(db_session, part.id) == 5


def test_import_continues_after_db_level_error(db_session):
    """A row error after a service call's own db.commit() (not just a
    validation error raised before any write) must still roll back
    cleanly enough that the NEXT row succeeds - this is what the
    db.rollback() in the except branch guards against."""
    rows = [
        {"Part No": "HD-1", "Name": "Brake Pad", "Current Stock": "-100"},
        {"Part No": "HD-2", "Name": "Clutch Plate", "Current Stock": "10"},
    ]
    result = sie.import_rows(db_session, rows)
    assert len(result.errors) == 1
    assert result.errors[0].part_no == "HD-1"
    assert parts_service.get_part_by_no(db_session, "HD-2") is not None
    assert stock_service.get_current_stock(
        db_session, parts_service.get_part_by_no(db_session, "HD-2").id
    ) == 10
