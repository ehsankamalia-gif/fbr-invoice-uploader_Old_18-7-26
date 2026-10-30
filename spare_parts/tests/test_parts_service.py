"""Unit tests for spare_parts.services.parts_service.

Uses an isolated in-memory SQLite database (its own engine/session, not
the shared app database) so tests never touch real data and run fast.
This is independent of, but consistent with, the module's own choice to
use the app's live connection at runtime (spare_parts/db/base.py) - test
isolation is standard practice and does not change that runtime choice.

Run with: pytest spare_parts/tests/test_parts_service.py -v
"""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401 - registers tables on SpareBase.metadata
from spare_parts.services import parts_service
from spare_parts.services.parts_service import SparePartsValidationError


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


# --- Parts -------------------------------------------------------------

def test_create_part_success(db_session):
    part = parts_service.create_part(db_session, part_no="hd-1", name="Brake Pad")
    assert part.id is not None
    assert part.part_no == "HD-1"  # normalized to uppercase
    assert part.is_active is True
    assert part.pack_size == 1
    assert part.unit == "pcs"


def test_create_part_duplicate_part_no_rejected(db_session):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    with pytest.raises(SparePartsValidationError):
        parts_service.create_part(db_session, part_no="hd-1", name="Another Brake Pad")


def test_create_part_requires_name(db_session):
    with pytest.raises(SparePartsValidationError):
        parts_service.create_part(db_session, part_no="HD-2", name="")


def test_create_part_requires_part_no(db_session):
    with pytest.raises(SparePartsValidationError):
        parts_service.create_part(db_session, part_no="   ", name="Brake Pad")


def test_update_part_part_no_clash_rejected(db_session):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    p2 = parts_service.create_part(db_session, part_no="HD-2", name="Clutch Plate")
    with pytest.raises(SparePartsValidationError):
        parts_service.update_part(db_session, p2.id, part_no="HD-1")


def test_update_part_allows_keeping_own_part_no(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    updated = parts_service.update_part(db_session, part.id, part_no="HD-1", name="Brake Pad V2")
    assert updated.name == "Brake Pad V2"


def test_update_part_fields_and_money_precision(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", cost_price=10)
    updated = parts_service.update_part(db_session, part.id, cost_price="12.50")
    assert str(updated.cost_price) == "12.50"


def test_set_part_active_toggle(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    assert part.is_active is True
    parts_service.set_part_active(db_session, part.id, False)
    db_session.refresh(part)
    assert part.is_active is False
    parts_service.set_part_active(db_session, part.id, True)
    db_session.refresh(part)
    assert part.is_active is True


def test_search_parts_by_name_and_part_no(db_session):
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    parts_service.create_part(db_session, part_no="HD-2", name="Clutch Plate")
    results = parts_service.search_parts(db_session, query="brake")
    assert len(results) == 1
    assert results[0].part_no == "HD-1"

    results = parts_service.search_parts(db_session, query="hd-2")
    assert len(results) == 1
    assert results[0].name == "Clutch Plate"


def test_search_parts_active_only_default(db_session):
    part = parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad")
    parts_service.set_part_active(db_session, part.id, False)
    assert parts_service.search_parts(db_session) == []
    assert len(parts_service.search_parts(db_session, active_only=False)) == 1


def test_search_parts_filters_by_category_and_brand(db_session):
    cat = parts_service.create_category(db_session, "Brakes")
    brand = parts_service.create_brand(db_session, "Honda")
    parts_service.create_part(
        db_session, part_no="HD-1", name="Brake Pad",
        category_id=cat.id, brand_id=brand.id,
    )
    parts_service.create_part(db_session, part_no="HD-2", name="Clutch Plate")

    assert len(parts_service.search_parts(db_session, category_id=cat.id)) == 1
    assert len(parts_service.search_parts(db_session, brand_id=brand.id)) == 1
    assert len(parts_service.search_parts(db_session)) == 2


# --- Categories & brands -------------------------------------------------

def test_category_hierarchy(db_session):
    parent = parts_service.create_category(db_session, "Engine Parts")
    child = parts_service.create_category(db_session, "Pistons", parent_id=parent.id)
    assert child.parent_id == parent.id


def test_create_category_requires_name(db_session):
    with pytest.raises(SparePartsValidationError):
        parts_service.create_category(db_session, "  ")


def test_create_brand_is_idempotent_by_name(db_session):
    b1 = parts_service.create_brand(db_session, "Honda")
    b2 = parts_service.create_brand(db_session, "Honda")
    assert b1.id == b2.id


def test_create_brand_requires_name(db_session):
    with pytest.raises(SparePartsValidationError):
        parts_service.create_brand(db_session, "")


def test_update_category_rename_and_reparent(db_session):
    parent = parts_service.create_category(db_session, "Engine Parts")
    other_parent = parts_service.create_category(db_session, "Body Parts")
    child = parts_service.create_category(db_session, "Pistons", parent_id=parent.id)

    updated = parts_service.update_category(db_session, child.id, name="Pistons V2")
    assert updated.name == "Pistons V2"
    assert updated.parent_id == parent.id  # untouched since parent_id was not passed

    updated = parts_service.update_category(db_session, child.id, parent_id=other_parent.id)
    assert updated.parent_id == other_parent.id

    updated = parts_service.update_category(db_session, child.id, parent_id=None)
    assert updated.parent_id is None


def test_update_category_rejects_self_as_parent(db_session):
    cat = parts_service.create_category(db_session, "Engine Parts")
    with pytest.raises(SparePartsValidationError):
        parts_service.update_category(db_session, cat.id, parent_id=cat.id)


def test_update_category_rejects_descendant_cycle(db_session):
    grandparent = parts_service.create_category(db_session, "Engine Parts")
    parent = parts_service.create_category(db_session, "Pistons", parent_id=grandparent.id)
    child = parts_service.create_category(db_session, "Rings", parent_id=parent.id)

    with pytest.raises(SparePartsValidationError):
        parts_service.update_category(db_session, grandparent.id, parent_id=child.id)


def test_update_category_requires_name_when_provided(db_session):
    cat = parts_service.create_category(db_session, "Engine Parts")
    with pytest.raises(SparePartsValidationError):
        parts_service.update_category(db_session, cat.id, name="   ")


def test_get_valid_parent_choices_excludes_self_and_descendants(db_session):
    grandparent = parts_service.create_category(db_session, "Engine Parts")
    parent = parts_service.create_category(db_session, "Pistons", parent_id=grandparent.id)
    child = parts_service.create_category(db_session, "Rings", parent_id=parent.id)
    unrelated = parts_service.create_category(db_session, "Body Parts")

    choices = parts_service.get_valid_parent_choices(db_session, parent.id)
    choice_ids = {c.id for c in choices}
    assert parent.id not in choice_ids
    assert child.id not in choice_ids
    assert grandparent.id in choice_ids
    assert unrelated.id in choice_ids


def test_get_valid_parent_choices_for_new_category_includes_all(db_session):
    cat = parts_service.create_category(db_session, "Engine Parts")
    choices = parts_service.get_valid_parent_choices(db_session, None)
    assert cat.id in {c.id for c in choices}


def test_delete_category_blocked_when_part_references_it(db_session):
    cat = parts_service.create_category(db_session, "Engine Parts")
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", category_id=cat.id)
    with pytest.raises(SparePartsValidationError):
        parts_service.delete_category(db_session, cat.id)


def test_delete_category_blocked_when_has_children(db_session):
    parent = parts_service.create_category(db_session, "Engine Parts")
    parts_service.create_category(db_session, "Pistons", parent_id=parent.id)
    with pytest.raises(SparePartsValidationError):
        parts_service.delete_category(db_session, parent.id)


def test_delete_category_succeeds_when_unused(db_session):
    cat = parts_service.create_category(db_session, "Engine Parts")
    parts_service.delete_category(db_session, cat.id)
    assert parts_service.get_category(db_session, cat.id) is None


def test_update_brand_renames_and_rejects_duplicate(db_session):
    b1 = parts_service.create_brand(db_session, "Honda")
    b2 = parts_service.create_brand(db_session, "Toyota")

    updated = parts_service.update_brand(db_session, b1.id, name="Honda Motors")
    assert updated.name == "Honda Motors"

    with pytest.raises(SparePartsValidationError):
        parts_service.update_brand(db_session, b2.id, name="Honda Motors")


def test_update_brand_requires_name(db_session):
    b1 = parts_service.create_brand(db_session, "Honda")
    with pytest.raises(SparePartsValidationError):
        parts_service.update_brand(db_session, b1.id, name="   ")


def test_delete_brand_blocked_when_part_references_it(db_session):
    brand = parts_service.create_brand(db_session, "Honda")
    parts_service.create_part(db_session, part_no="HD-1", name="Brake Pad", brand_id=brand.id)
    with pytest.raises(SparePartsValidationError):
        parts_service.delete_brand(db_session, brand.id)


def test_delete_brand_succeeds_when_unused(db_session):
    brand = parts_service.create_brand(db_session, "Honda")
    parts_service.delete_brand(db_session, brand.id)
    assert parts_service.get_brand(db_session, brand.id) is None


# --- bulk_update_prices -----------------------------------------------

def test_bulk_update_prices_percent_increase(db_session):
    from decimal import Decimal
    part = parts_service.create_part(db_session, part_no="BP-1", name="Part", retail_price=100)
    results = parts_service.bulk_update_prices(db_session, field="retail_price", mode="PERCENT", value=10)
    assert len(results) == 1
    assert results[0]["old_price"] == Decimal("100")
    assert results[0]["new_price"] == Decimal("110.00")
    db_session.refresh(part)
    assert part.retail_price == Decimal("110.00")


def test_bulk_update_prices_fixed_decrease(db_session):
    from decimal import Decimal
    parts_service.create_part(db_session, part_no="BP-2", name="Part", retail_price=100)
    results = parts_service.bulk_update_prices(db_session, field="retail_price", mode="FIXED", value=-30)
    assert results[0]["new_price"] == Decimal("70.00")


def test_bulk_update_prices_never_goes_below_zero(db_session):
    from decimal import Decimal
    parts_service.create_part(db_session, part_no="BP-3", name="Part", retail_price=10)
    results = parts_service.bulk_update_prices(db_session, field="retail_price", mode="FIXED", value=-100)
    assert results[0]["new_price"] == Decimal("0.00")


def test_bulk_update_prices_filters_by_category(db_session):
    cat_a = parts_service.create_category(db_session, "Brakes")
    cat_b = parts_service.create_category(db_session, "Electrical")
    parts_service.create_part(db_session, part_no="BP-4", name="In A", category_id=cat_a.id, retail_price=100)
    parts_service.create_part(db_session, part_no="BP-5", name="In B", category_id=cat_b.id, retail_price=100)

    results = parts_service.bulk_update_prices(
        db_session, category_id=cat_a.id, field="retail_price", mode="PERCENT", value=10,
    )
    assert len(results) == 1
    assert results[0]["part"].part_no == "BP-4"


def test_bulk_update_prices_excludes_inactive_parts(db_session):
    part = parts_service.create_part(db_session, part_no="BP-6", name="Inactive", retail_price=100)
    parts_service.set_part_active(db_session, part.id, False)
    results = parts_service.bulk_update_prices(db_session, field="retail_price", mode="PERCENT", value=10)
    assert results == []


def test_bulk_update_prices_rejects_unknown_field(db_session):
    parts_service.create_part(db_session, part_no="BP-7", name="Part", retail_price=100)
    with pytest.raises(SparePartsValidationError):
        parts_service.bulk_update_prices(db_session, field="bogus_field", mode="PERCENT", value=10)


def test_bulk_update_prices_rejects_unknown_mode(db_session):
    parts_service.create_part(db_session, part_no="BP-8", name="Part", retail_price=100)
    with pytest.raises(SparePartsValidationError):
        parts_service.bulk_update_prices(db_session, field="retail_price", mode="BOGUS", value=10)
