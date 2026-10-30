"""Unit tests for spare_parts.services.stock_take_service."""
from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from spare_parts.db.base import SpareBase
from spare_parts.db import models  # noqa: F401
from spare_parts.errors import SparePartsValidationError
from spare_parts.services import parts_service, stock_service, stock_take_service


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SpareBase.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def part(db_session):
    p = parts_service.create_part(db_session, part_no="ST-1", name="Counted Part")
    stock_service.add_ledger_entry(db_session, part_id=p.id, qty_in=50, reference_type="OPENING")
    db_session.commit()
    return p


def test_create_stock_take_snapshots_system_qty(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    assert take.status == "DRAFT"
    assert len(take.items) == 1
    assert take.items[0].part_id == part.id
    assert take.items[0].system_qty == 50
    assert take.items[0].counted_qty is None


def test_create_stock_take_rejects_empty_filter(db_session):
    with pytest.raises(SparePartsValidationError):
        stock_take_service.create_stock_take(db_session, query="no-such-part")


def test_create_stock_take_filters_by_category(db_session):
    cat_a = parts_service.create_category(db_session, "A")
    cat_b = parts_service.create_category(db_session, "B")
    p1 = parts_service.create_part(db_session, part_no="ST-CAT-1", name="In A", category_id=cat_a.id)
    parts_service.create_part(db_session, part_no="ST-CAT-2", name="In B", category_id=cat_b.id)
    stock_service.add_ledger_entry(db_session, part_id=p1.id, qty_in=5, reference_type="OPENING")
    db_session.commit()

    take = stock_take_service.create_stock_take(db_session, category_id=cat_a.id)
    assert len(take.items) == 1
    assert take.items[0].part_id == p1.id


def test_update_counted_qty_only_while_draft(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    stock_take_service.update_counted_qty(db_session, item.id, 45)
    db_session.refresh(item)
    assert item.counted_qty == 45

    stock_take_service.post_stock_take(db_session, take.id)
    with pytest.raises(SparePartsValidationError):
        stock_take_service.update_counted_qty(db_session, item.id, 40)


def test_post_stock_take_creates_correct_adjustment(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    stock_take_service.update_counted_qty(db_session, item.id, 45)  # 50 -> 45, OUT 5

    result = stock_take_service.post_stock_take(db_session, take.id)
    assert result["adjusted_count"] == 1
    assert result["drift_warnings"] == []
    assert result["stock_take"].status == "POSTED"
    assert stock_service.get_current_stock(db_session, part.id) == 45

    ledger_entries = stock_service.get_ledger_entries(db_session, part.id)
    stock_take_entry = [e for e in ledger_entries if e.reference_type == "STOCK_TAKE"][0]
    assert stock_take_entry.qty_out == 5
    assert stock_take_entry.reference_id == take.id


def test_post_stock_take_increases_stock_when_counted_higher(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    stock_take_service.update_counted_qty(db_session, item.id, 60)  # 50 -> 60, IN 10

    stock_take_service.post_stock_take(db_session, take.id)
    assert stock_service.get_current_stock(db_session, part.id) == 60


def test_post_stock_take_skips_lines_with_no_variance(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    stock_take_service.update_counted_qty(db_session, item.id, 50)  # unchanged

    result = stock_take_service.post_stock_take(db_session, take.id)
    assert result["adjusted_count"] == 0
    assert stock_service.get_current_stock(db_session, part.id) == 50


def test_post_stock_take_requires_at_least_one_counted_line(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    with pytest.raises(SparePartsValidationError):
        stock_take_service.post_stock_take(db_session, take.id)


def test_post_stock_take_warns_on_drift_but_posts_correct_diff(db_session, part):
    """If stock moves (e.g. a sale) while the count is still DRAFT, the
    posted diff must still be counted_qty - system_qty (the snapshot),
    not counted_qty - live_stock, but a drift warning should fire."""
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    assert item.system_qty == 50

    # Simulate a sale happening elsewhere while the count is still DRAFT.
    stock_service.add_ledger_entry(db_session, part_id=part.id, qty_out=10, reference_type="SALE")
    db_session.commit()
    assert stock_service.get_current_stock(db_session, part.id) == 40

    stock_take_service.update_counted_qty(db_session, item.id, 45)  # counted against the ORIGINAL 50

    result = stock_take_service.post_stock_take(db_session, take.id)
    assert len(result["drift_warnings"]) == 1
    assert part.part_no in result["drift_warnings"][0]
    # diff = counted_qty(45) - system_qty(50) = -5, applied on top of the
    # live 40 -> 35, NOT counted_qty(45) directly.
    assert stock_service.get_current_stock(db_session, part.id) == 35


def test_post_stock_take_rejects_non_draft(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    stock_take_service.update_counted_qty(db_session, item.id, 45)
    stock_take_service.post_stock_take(db_session, take.id)
    with pytest.raises(SparePartsValidationError):
        stock_take_service.post_stock_take(db_session, take.id)


def test_cancel_stock_take_only_while_draft(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    stock_take_service.cancel_stock_take(db_session, take.id)
    assert stock_take_service.get_stock_take(db_session, take.id) is None


def test_cancel_stock_take_rejects_posted(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    item = take.items[0]
    stock_take_service.update_counted_qty(db_session, item.id, 45)
    stock_take_service.post_stock_take(db_session, take.id)
    with pytest.raises(SparePartsValidationError):
        stock_take_service.cancel_stock_take(db_session, take.id)


def test_generate_stock_take_no_uses_prefix(db_session, part):
    take = stock_take_service.create_stock_take(db_session)
    assert take.take_no.startswith("ST-")


def test_list_stock_takes_newest_first(db_session, part):
    import datetime as dt
    take1 = stock_take_service.create_stock_take(db_session)
    take1.take_date = dt.datetime(2020, 1, 1)
    db_session.commit()
    take2 = stock_take_service.create_stock_take(db_session)

    rows = stock_take_service.list_stock_takes(db_session)
    assert rows[0].id == take2.id
    assert rows[1].id == take1.id