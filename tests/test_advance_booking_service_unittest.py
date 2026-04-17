import datetime as dt
import unittest

HAS_SQLALCHEMY = True
try:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
except Exception:
    HAS_SQLALCHEMY = False

if HAS_SQLALCHEMY:
    from app.db.models import Base
    from app.services.advance_booking_service import AdvanceBookingService


@unittest.skipUnless(HAS_SQLALCHEMY, "sqlalchemy is required for advance booking tests")
class TestAdvanceBookingService(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.engine = create_engine("sqlite:///:memory:")
        cls.TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=cls.engine)
        Base.metadata.create_all(bind=cls.engine)

    def setUp(self) -> None:
        self.svc = AdvanceBookingService()

    def _db(self):
        connection = self.engine.connect()
        transaction = connection.begin()
        session = self.TestingSessionLocal(bind=connection)
        return connection, transaction, session

    def test_create_booking_generates_number_and_balance(self):
        connection, transaction, db = self._db()
        try:
            booking = self.svc.create_booking(
                db=db,
                customer_name="Javed Ali",
                motorcycle_model="CD 70",
                color="Red",
                total_price=150000,
                advance_paid=50000,
            )
            self.assertIsNotNone(booking.id)
            self.assertEqual(booking.balance_amount, 100000)
            self.assertEqual(booking.customer_name, "JAVED ALI")
            self.assertEqual(booking.motorcycle_model, "CD 70")
            self.assertEqual(booking.color, "RED")
            self.assertEqual(booking.booking_number, "CD70-1")
            self.assertEqual(getattr(booking, "model_code", ""), "CD70")
            self.assertEqual(getattr(booking, "model_seq", 0), 1)

            booking2 = self.svc.create_booking(
                db=db,
                customer_name="X",
                motorcycle_model="CD 70",
                color="Black",
                total_price=150000,
                advance_paid=1000,
            )
            self.assertEqual(booking2.booking_number, "CD70-2")
        finally:
            db.close()
            transaction.rollback()
            connection.close()

    def test_create_booking_rejects_invalid_amounts(self):
        connection, transaction, db = self._db()
        try:
            with self.assertRaises(ValueError):
                self.svc.create_booking(
                    db=db,
                    customer_name="A",
                    motorcycle_model="M",
                    color="C",
                    total_price=0,
                    advance_paid=0,
                )

            with self.assertRaises(ValueError):
                self.svc.create_booking(
                    db=db,
                    customer_name="A",
                    motorcycle_model="M",
                    color="C",
                    total_price=100,
                    advance_paid=200,
                )
        finally:
            db.close()
            transaction.rollback()
            connection.close()

    def test_mark_delivered_updates_status_and_summary(self):
        connection, transaction, db = self._db()
        try:
            booking = self.svc.create_booking(
                db=db,
                customer_name="A",
                motorcycle_model="CD70",
                color="RED",
                total_price=100,
                advance_paid=10,
            )
            self.assertEqual(booking.status, "ACTIVE")

            delivered = self.svc.mark_delivered(db, booking.booking_number, delivery_paid=90)
            self.assertEqual(delivered.status, "DELIVERED")
            self.assertIsNotNone(delivered.delivered_at)
            self.assertEqual(getattr(delivered, "advance_remaining", None), 0.0)
            self.assertEqual(getattr(delivered, "advance_applied", None), 10.0)
            self.assertEqual(getattr(delivered, "delivery_paid", None), 90.0)
            self.assertEqual(getattr(delivered, "balance_amount", None), 0.0)

            summary = self.svc.get_summary(db)
            self.assertEqual(summary["delivered_count"], 1)
            self.assertEqual(summary["active_count"], 0)
            self.assertEqual(summary["outstanding_advance"], 0.0)
            self.assertEqual(summary["outstanding_balance"], 0.0)

            counts = self.svc.get_active_counts_by_model(db, limit=10)
            self.assertEqual(counts, [])
        finally:
            db.close()
            transaction.rollback()
            connection.close()

    def test_counts_by_model_active_only(self):
        connection, transaction, db = self._db()
        try:
            self.svc.create_booking(
                db=db,
                customer_name="A",
                motorcycle_model="CD70",
                color="RED",
                total_price=100,
                advance_paid=10,
            )
            self.svc.create_booking(
                db=db,
                customer_name="B",
                motorcycle_model="CD70",
                color="BLACK",
                total_price=100,
                advance_paid=20,
            )
            self.svc.create_booking(
                db=db,
                customer_name="C",
                motorcycle_model="CG125",
                color="RED",
                total_price=100,
                advance_paid=30,
            )
            counts = dict(self.svc.get_active_counts_by_model(db, limit=10))
            self.assertEqual(counts.get("CD70"), 2)
            self.assertEqual(counts.get("CG125"), 1)
        finally:
            db.close()
            transaction.rollback()
            connection.close()


if __name__ == "__main__":
    unittest.main()

