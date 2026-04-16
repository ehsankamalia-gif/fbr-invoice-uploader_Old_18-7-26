import unittest

HAS_SQLALCHEMY = True
try:
    import sqlalchemy
except Exception:
    HAS_SQLALCHEMY = False

if HAS_SQLALCHEMY:
    from app.db.session import SessionLocal
    from app.db.models import Customer
    from app.services.customer_service import customer_service


@unittest.skipUnless(HAS_SQLALCHEMY, "sqlalchemy is required for customer_service tests")
class TestCustomerService(unittest.TestCase):
    def setUp(self) -> None:
        db = SessionLocal()
        try:
            db.query(Customer).delete()
            db.commit()
        finally:
            db.close()

    def test_create_customer_uppercases_text_fields(self) -> None:
        created = customer_service.create_customer(
            cnic="33302-1234567-1",
            name="Fakhar Iqbal",
            father_name="Sikandar",
            phone="03112536333",
            address="Noor Shah St No 1 Kamalia",
            ntn="",
            business_name="",
        )

        db = SessionLocal()
        try:
            saved = db.query(Customer).filter(Customer.id == created.id).first()
            self.assertIsNotNone(saved)
            assert saved is not None
            self.assertEqual(saved.name, "FAKHAR IQBAL")
            self.assertEqual(saved.father_name, "SIKANDAR")
            self.assertEqual(saved.address, "NOOR SHAH ST NO 1 KAMALIA")
        finally:
            db.close()

    def test_create_customer_duplicate_cnic_blocked(self) -> None:
        customer_service.create_customer(
            cnic="33302-1234567-1",
            name="A",
            father_name="B",
            phone="03111111111",
            address="X",
        )

        with self.assertRaises(ValueError):
            customer_service.create_customer(
                cnic="33302-1234567-1",
                name="C",
                father_name="D",
                phone="03222222222",
                address="Y",
            )


if __name__ == "__main__":
    unittest.main()
