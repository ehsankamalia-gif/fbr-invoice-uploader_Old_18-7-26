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
                motorcycle_model="CD70",
                color="Red",
                total_price=150000,
                advance_paid=50000,
            )
            self.assertIsNotNone(booking.id)
            self.assertEqual(booking.balance_amount, 100000)
            self.assertEqual(booking.customer_name, "JAVED ALI")
            self.assertEqual(booking.motorcycle_model, "CD70")
            self.assertEqual(booking.color, "RED")

            prefix = dt.datetime.utcnow().strftime("AB%Y%m")
            self.assertTrue(booking.booking_number.startswith(prefix + "-"))
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


if __name__ == "__main__":
    unittest.main()

