"""Dealer -> Customer conversion: old invoices frozen, new ones snapshotted,
reports split correctly, and a failed conversion rolls back completely."""
import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.schemas import InvoiceCreate, InvoiceItemCreate
from app.db import session as db_session_module
from app.db.models import Base, Customer, Invoice, PartyTypeHistory
from app.services import party_conversion_service as pcs
from app.services.invoice_service import InvoiceService
from app.services.settings_service import settings_service


@pytest.fixture
def SF():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def _add_invoice(db, number, customer_id, party_type, total=1000.0):
    db.add(Invoice(
        invoice_number=number, pos_id="1", usin=number,
        customer_id=customer_id, invoice_party_type=party_type,
        total_sale_value=total, total_tax_charged=0.0,
        total_quantity=1.0, total_amount=total,
    ))


@pytest.fixture
def dealer(SF):
    db = SF()
    c = Customer(
        cnic="11111-1111111-1", name="DEALER ONE", business_name="ABC MOTORS",
        normalized_business_name="abcmotors", ntn="1234567-8", phone="0300", type="DEALER",
    )
    db.add(c)
    db.flush()
    _add_invoice(db, "U-0001", c.id, "DEALER", 1000.0)
    _add_invoice(db, "U-0002", c.id, "DEALER", 2500.0)
    db.commit()
    cid = c.id
    db.close()
    return cid


def _invoices(SF, cid):
    db = SF()
    try:
        return {
            i.invoice_number: (i.invoice_party_type, i.total_amount)
            for i in db.query(Invoice).filter(Invoice.customer_id == cid)
        }
    finally:
        db.close()


def _new_invoice(number, buyer_type="INDIVIDUAL"):
    return InvoiceCreate(
        invoice_number=number,
        buyer_cnic="11111-1111111-1",
        buyer_name="DEALER ONE",
        buyer_type=buyer_type,
        items=[InvoiceItemCreate(
            item_code="X", item_name="Bike", quantity=1, tax_rate=18,
            sale_value=100.0, tax_charged=18.0, pct_code="8711.2010",
        )],
    )


@pytest.fixture
def patched_invoice_env(monkeypatch):
    monkeypatch.setattr(settings_service, "get_active_settings", lambda: {"pos_id": "1"})
    monkeypatch.setattr(InvoiceService, "sync_invoice", lambda self, db, inv: None)


# (a) old invoices are unchanged ------------------------------------------------
def test_old_invoices_unchanged_after_conversion(SF, dealer):
    before = _invoices(SF, dealer)
    result = pcs.convert_dealer_to_customer(dealer, "tester", session_factory=SF)
    assert result["old_type"] == "DEALER" and result["new_type"] == "INDIVIDUAL"

    assert _invoices(SF, dealer) == before  # same party type + totals

    db = SF()
    c = db.query(Customer).get(dealer)
    assert c.type == "INDIVIDUAL"
    assert c.converted_to_customer_at is not None
    # same record: identity and details untouched, no duplicate created
    assert (c.name, c.cnic, c.ntn, c.phone, c.business_name) == (
        "DEALER ONE", "11111-1111111-1", "1234567-8", "0300", "ABC MOTORS")
    assert db.query(Customer).count() == 1
    h = db.query(PartyTypeHistory).one()
    assert (h.party_id, h.old_type, h.new_type, h.changed_by) == (dealer, "DEALER", "INDIVIDUAL", "tester")
    db.close()


# (b) new invoices are customer invoices ---------------------------------------
def test_new_invoice_after_conversion_is_customer(SF, dealer, patched_invoice_env):
    pcs.convert_dealer_to_customer(dealer, "tester", session_factory=SF)
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003"))
    db.close()
    inv = _invoices(SF, dealer)
    assert inv["U-0003"][0] == "INDIVIDUAL"
    assert inv["U-0001"][0] == "DEALER" and inv["U-0002"][0] == "DEALER"


def test_stale_dealer_flag_cannot_repromote_converted_party(SF, dealer, patched_invoice_env):
    pcs.convert_dealer_to_customer(dealer, "tester", session_factory=SF)
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003", buyer_type="DEALER"))
    db.close()
    db = SF()
    assert db.query(Customer).get(dealer).type == "INDIVIDUAL"
    db.close()
    assert _invoices(SF, dealer)["U-0003"][0] == "INDIVIDUAL"


def test_invoice_before_conversion_is_dealer(SF, dealer, patched_invoice_env):
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003", buyer_type="DEALER"))
    db.close()
    assert _invoices(SF, dealer)["U-0003"][0] == "DEALER"


# (c) reports show both correctly -----------------------------------------------
def test_reports_group_by_invoice_snapshot(SF, dealer, patched_invoice_env):
    pcs.convert_dealer_to_customer(dealer, "tester", session_factory=SF)
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003"))
    db.close()

    db = SF()
    party = func.coalesce(Invoice.invoice_party_type, Customer.type)
    rows = dict(
        db.query(party, func.count(Invoice.id))
        .join(Customer, Invoice.customer_id == Customer.id)
        .group_by(party).all()
    )
    db.close()
    # Customer.type is now INDIVIDUAL for all three - grouping by the party's
    # current type would wrongly report 3 customer invoices.
    assert rows == {"DEALER": 2, "INDIVIDUAL": 1}


def test_lookup_endpoint_reports_party_type_per_invoice(SF, dealer, patched_invoice_env, monkeypatch):
    import json
    import reporting.main as rm
    from app.services.auth_session import auth_session

    pcs.convert_dealer_to_customer(dealer, "tester", session_factory=SF)
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003"))
    db.close()

    monkeypatch.setattr(auth_session, "is_logged_in", lambda: True)
    monkeypatch.setattr(auth_session, "is_admin", lambda: True)
    db = SF()
    try:
        resp = rm.lookup_search(
            db=db, phone="", cnic="1111111111111", name="", chassis="", engine="",
            sort_by="date", sort_dir="desc", page=1, page_size=100,
            x_api_key=None, x_user_role=None,
        )
    finally:
        db.close()
    by_inv = {i["invoice_number"]: i["party_type"] for i in json.loads(resp.body)["items"]}
    assert by_inv == {"U-0001": "Dealer", "U-0002": "Dealer", "U-0003": "Customer"}


# (d) failed conversion rolls back fully ----------------------------------------
def test_failed_conversion_rolls_back_everything(SF, dealer, monkeypatch):
    class _Boom:
        def __init__(self, **kw):
            raise RuntimeError("history insert failed")

    monkeypatch.setattr(pcs, "PartyTypeHistory", _Boom)
    with pytest.raises(RuntimeError):
        pcs.convert_dealer_to_customer(dealer, "tester", session_factory=SF)

    db = SF()
    c = db.query(Customer).get(dealer)
    assert c.type == "DEALER" and c.converted_to_customer_at is None
    assert db.query(PartyTypeHistory).count() == 0
    db.close()
    assert all(t == "DEALER" for t, _ in _invoices(SF, dealer).values())


def test_failure_at_commit_rolls_back(SF, dealer, monkeypatch):
    real_factory = SF

    def factory():
        s = real_factory()
        orig = s.commit

        def bad_commit():
            raise RuntimeError("commit failed")

        s.commit = bad_commit
        return s

    with pytest.raises(RuntimeError):
        pcs.convert_dealer_to_customer(dealer, "tester", session_factory=factory)
    db = SF()
    assert db.query(Customer).get(dealer).type == "DEALER"
    assert db.query(PartyTypeHistory).count() == 0
    db.close()


# Edge cases ----------------------------------------------------------------------
def test_already_customer_is_rejected(SF, dealer):
    pcs.convert_dealer_to_customer(dealer, "t", session_factory=SF)
    with pytest.raises(pcs.PartyConversionError):
        pcs.convert_dealer_to_customer(dealer, "t", session_factory=SF)
    db = SF()
    assert db.query(PartyTypeHistory).count() == 1  # no second history row
    db.close()


def test_unknown_party_is_rejected(SF):
    with pytest.raises(pcs.PartyConversionError):
        pcs.convert_dealer_to_customer(9999, "t", session_factory=SF)


def test_customer_back_to_dealer_leaves_past_invoices_alone(SF, dealer, patched_invoice_env):
    pcs.convert_dealer_to_customer(dealer, "t", session_factory=SF)
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003"))
    db.close()
    pcs.convert_customer_to_dealer(dealer, "t", session_factory=SF)
    inv = _invoices(SF, dealer)
    assert inv["U-0001"][0] == "DEALER" and inv["U-0003"][0] == "INDIVIDUAL"
    db = SF()
    assert db.query(Customer).get(dealer).type == "DEALER"
    assert db.query(Customer).get(dealer).converted_to_customer_at is None
    assert db.query(PartyTypeHistory).count() == 2
    db.close()


# One-time migration --------------------------------------------------------------
def test_migration_backfills_existing_invoices_from_current_type(SF, dealer):
    db = SF()
    ind = Customer(cnic="22222-2222222-2", name="IND", type="INDIVIDUAL")
    db.add(ind)
    db.flush()
    _add_invoice(db, "U-0100", ind.id, None)
    db.query(Invoice).filter(Invoice.customer_id == dealer).update({Invoice.invoice_party_type: None})
    db.commit()
    bind = db.get_bind()
    db.close()

    with bind.connect() as conn:
        assert db_session_module._migration_v25_party_conversion(conn) is True

    inv = _invoices(SF, dealer)
    assert {t for t, _ in inv.values()} == {"DEALER"}
    db = SF()
    assert db.query(Invoice).filter(Invoice.invoice_number == "U-0100").one().invoice_party_type == "INDIVIDUAL"
    db.close()


# Customer -> Dealer with a business name ---------------------------------------
def _plain_customer(SF, cnic="33333-3333333-3", business_name=None):
    db = SF()
    c = Customer(cnic=cnic, name="PLAIN", type="INDIVIDUAL", business_name=business_name)
    db.add(c)
    db.commit()
    cid = c.id
    db.close()
    return cid


def test_customer_to_dealer_sets_business_name(SF):
    cid = _plain_customer(SF)
    with pytest.raises(pcs.PartyConversionError):  # no business name anywhere
        pcs.convert_customer_to_dealer(cid, "t", session_factory=SF)
    pcs.convert_customer_to_dealer(cid, "t", session_factory=SF, business_name="Xyz Motors")
    db = SF()
    c = db.query(Customer).get(cid)
    assert c.type == "DEALER" and c.business_name == "XYZ MOTORS" and c.normalized_business_name
    db.close()


def test_customer_to_dealer_rejects_duplicate_business_name(SF, dealer):
    cid = _plain_customer(SF)
    with pytest.raises(pcs.PartyConversionError):
        pcs.convert_customer_to_dealer(cid, "t", session_factory=SF, business_name="ABC Motors")
    db = SF()
    assert db.query(Customer).get(cid).type == "INDIVIDUAL"
    assert db.query(PartyTypeHistory).count() == 0
    db.close()


# Dashboard: dealer vs customer split ---------------------------------------------
def test_dashboard_metrics_split_by_invoice_snapshot(SF, dealer, patched_invoice_env):
    import reporting.main as rm
    pcs.convert_dealer_to_customer(dealer, "t", session_factory=SF)
    db = SF()
    InvoiceService().create_invoice(db, _new_invoice("U-0003"))
    db.close()

    db = SF()
    metrics = rm._compute_metrics(db, None, None, "ALL")
    db.close()
    split = {r["party_type"]: (r["count"], r["amount"]) for r in metrics["party_breakdown"]}
    assert split["Dealer"] == (2, 3500.0)      # old invoices stay Dealer
    assert split["Customer"][0] == 1           # only the post-conversion one
    assert metrics["total_invoices"] == 3


def test_default_dashboard_template_gets_party_widget_once(SF):
    import reporting.main as rm
    from app.db.models import ReportTemplate
    db = SF()
    old = {"version": 1, "widgets": [
        {"type": "chart", "metric": "status_breakdown", "title": "Status Breakdown"},
        {"type": "table", "metric": "invoices", "title": "Invoices"}]}
    d = ReportTemplate(name="Default Dashboard", definition=old, is_active=True)
    custom = ReportTemplate(name="My Custom", definition=dict(old), is_active=True)
    db.add_all([d, custom])
    db.commit()
    for _ in range(2):  # idempotent
        rm._ensure_template_has_widgets(db, d)
        rm._ensure_template_has_widgets(db, custom)
    metrics = [w["metric"] for w in d.definition["widgets"]]
    assert metrics == ["status_breakdown", "party_breakdown", "invoices"]
    assert [w["metric"] for w in custom.definition["widgets"]] == ["status_breakdown", "invoices"]
    db.close()
