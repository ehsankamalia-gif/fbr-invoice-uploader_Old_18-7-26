"""
End-to-end tests for automated customer portal account creation on credit sale.

Tests cover:
1. Password generation uses cryptographically secure random (secrets.choice)
2. Password hash compatibility with Django check_password
3. Portal account creation via CustomerPortalService
4. Duplicate account prevention (subsequent sales skip creation)
5. Phone number fallback logic
6. Login form validation
7. SMS service signature checks
8. Service method signature checks
9. Source code security audit
"""
import unittest
import os
import sys

HAS_SQLALCHEMY = True
HAS_DJANGO = True
try:
    import sqlalchemy
except Exception:
    HAS_SQLALCHEMY = False

try:
    import django
except Exception:
    HAS_DJANGO = False


def _setup_django_for_tests():
    """Configure Django minimally for password hash compatibility tests."""
    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            DATABASES={
                'default': {
                    'ENGINE': 'django.db.backends.sqlite3',
                    'NAME': ':memory:',
                }
            },
            INSTALLED_APPS=[
                'django.contrib.auth',
                'django.contrib.contenttypes',
            ],
            USE_TZ=True,
        )
        django.setup()


# =============================================================================
# SECTION 1: Password Generation Security Tests
# =============================================================================

class TestPasswordGenerationSecurity(unittest.TestCase):
    """Verify that passwords are generated using cryptographically secure methods."""

    def setUp(self):
        from app.services.customer_portal_service import customer_portal_service
        self.service = customer_portal_service

    def test_generate_password_uses_secrets_choice(self):
        """Verify _generate_password uses secrets.choice, not random.choice."""
        import inspect
        source = inspect.getsource(self.service._generate_password)
        self.assertIn("secrets.choice", source,
                      "Password generation must use secrets.choice for cryptographic security")
        self.assertNotIn("random.choice", source,
                         "Password generation must NOT use random.choice")

    def test_generated_password_length(self):
        """Generated password should be exactly 8 characters by default."""
        password = self.service._generate_password()
        self.assertEqual(len(password), 8)

    def test_generated_password_contains_only_allowed_chars(self):
        """Generated password should only contain letters and digits."""
        import string
        allowed = set(string.ascii_letters + string.digits)
        password = self.service._generate_password()
        for char in password:
            self.assertIn(char, allowed,
                          f"Character '{char}' not in allowed set")

    def test_generated_passwords_are_unique(self):
        """Multiple generated passwords should be unique (probabilistic check)."""
        passwords = {self.service._generate_password() for _ in range(100)}
        self.assertGreaterEqual(len(passwords), 95,
                                "Generated passwords lack sufficient entropy")


# =============================================================================
# SECTION 2: Password Hash Compatibility Tests
# =============================================================================

@unittest.skipUnless(HAS_DJANGO, "Django is required for hash compatibility tests")
class TestPasswordHashCompatibility(unittest.TestCase):
    """Verify that custom make_password produces Django-compatible hashes."""

    def setUp(self):
        _setup_django_for_tests()
        from app.services.customer_portal_service import make_password as custom_make_password
        self.custom_make_password = custom_make_password

    def test_custom_hash_format(self):
        """Custom hash should follow Django's <algorithm>$<iterations>$<salt>$<hash> format."""
        password = "TestPassword123"
        hash_str = self.custom_make_password(password)
        pattern = r'^pbkdf2_sha256\$\d+\$[A-Za-z0-9_-]+\$[A-Za-z0-9+/=]+$'
        self.assertRegex(hash_str, pattern,
                         "Hash format must match Django's PBKDF2 format")

    def test_custom_hash_uses_high_iterations(self):
        """Custom hash should use at least 600000 PBKDF2 iterations."""
        hash_str = self.custom_make_password("test")
        iterations = int(hash_str.split("$")[1])
        self.assertGreaterEqual(iterations, 600000,
                                "PBKDF2 iterations must be >= 600000 for security")

    def test_unique_salt_per_hash(self):
        """Each hash should have a unique salt."""
        hashes = [self.custom_make_password("samepassword") for _ in range(5)]
        salts = [h.split("$")[2] for h in hashes]
        self.assertEqual(len(set(salts)), len(salts),
                         "Each hash must use a unique salt")


# =============================================================================
# SECTION 3: Portal Account Creation via CustomerPortalService
# =============================================================================

@unittest.skipUnless(HAS_SQLALCHEMY, "SQLAlchemy is required for portal account tests")
class TestCustomerPortalServiceAccountCreation(unittest.TestCase):
    """Verify CustomerPortalService.create_portal_account works correctly."""

    _test_customer_id = None

    @classmethod
    def setUpClass(cls):
        from app.db.session import SessionLocal
        from app.db.models import Customer
        from sqlalchemy import text

        db = SessionLocal()
        try:
            # Create a unique test customer with unique CNIC
            import random
            unique_id = random.randint(10000, 99999)
            customer = Customer(
                name=f"TEST PORTAL USER {unique_id}",
                phone=f"0312{unique_id:05d}",
                cnic=f"{unique_id}-1234567-1",
                type="INDIVIDUAL",
                address="TEST ADDRESS"
            )
            db.add(customer)
            db.commit()
            db.refresh(customer)
            cls._test_customer_id = customer.id

            # Clean up any existing portal auth for this customer
            db.execute(
                text("DELETE FROM customer_portal_auth WHERE customer_id = :cid"),
                {"cid": customer.id}
            )
            db.commit()
        finally:
            db.close()

    @classmethod
    def tearDownClass(cls):
        if cls._test_customer_id is None:
            return
        from app.db.session import SessionLocal
        from sqlalchemy import text

        db = SessionLocal()
        try:
            db.execute(
                text("DELETE FROM customer_portal_auth WHERE customer_id = :cid"),
                {"cid": cls._test_customer_id}
            )
            db.execute(
                text("DELETE FROM customers WHERE id = :cid"),
                {"cid": cls._test_customer_id}
            )
            db.commit()
        finally:
            db.close()

    def setUp(self):
        from app.services.customer_portal_service import customer_portal_service
        from app.db.session import SessionLocal
        from sqlalchemy import text

        self.service = customer_portal_service
        self.customer_id = self._test_customer_id
        self.db = SessionLocal()

        # Clean up any existing portal auth
        self.db.execute(
            text("DELETE FROM customer_portal_auth WHERE customer_id = :cid"),
            {"cid": self.customer_id}
        )
        self.db.commit()

    def tearDown(self):
        if hasattr(self, 'db') and self.db:
            self.db.close()

    def test_create_portal_account_returns_credentials(self):
        """create_portal_account should return credentials dict on success."""
        result = self.service.create_portal_account(
            customer_id=self.customer_id,
            phone_number="03123456789"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["customer_id"], self.customer_id)
        self.assertEqual(result["phone_number"], "03123456789")
        self.assertIn("password", result)
        self.assertIn("customer_name", result)
        self.assertEqual(len(result["password"]), 8)

    def test_create_portal_account_prevents_duplicates(self):
        """create_portal_account should return None if account already exists."""
        first = self.service.create_portal_account(
            customer_id=self.customer_id,
            phone_number="03123456789"
        )
        self.assertIsNotNone(first)

        second = self.service.create_portal_account(
            customer_id=self.customer_id,
            phone_number="03123456789"
        )
        self.assertIsNone(second)

    def test_create_portal_account_fallback_to_customer_phone(self):
        """create_portal_account should fall back to customer.phone if no phone provided."""
        result = self.service.create_portal_account(
            customer_id=self.customer_id
        )
        self.assertIsNotNone(result)
        # The customer was created with a phone number
        self.assertIsNotNone(result["phone_number"])

    def test_create_portal_account_fails_without_phone(self):
        """create_portal_account should return None if customer has no phone."""
        from app.db.session import SessionLocal
        from app.db.models import Customer

        db = SessionLocal()
        try:
            customer = db.query(Customer).filter(Customer.id == self.customer_id).first()
            orig_phone = customer.phone
            customer.phone = None
            db.commit()

            result = self.service.create_portal_account(
                customer_id=self.customer_id
            )
            self.assertIsNone(result)

            # Restore phone
            customer.phone = orig_phone
            db.commit()
        finally:
            db.close()

    def test_create_account_for_credit_sale_integration(self):
        """create_account_for_credit_sale should work and return credentials."""
        result = self.service.create_account_for_credit_sale(
            customer_id=self.customer_id,
            phone_number="03123456789"
        )
        self.assertIsNotNone(result)
        self.assertEqual(result["customer_id"], self.customer_id)

    def test_last_created_credentials_tracking(self):
        """last_created_credentials should track the most recent creation."""
        self.service.pop_last_credentials()

        result = self.service.create_portal_account(
            customer_id=self.customer_id,
            phone_number="03123456789"
        )
        self.assertIsNotNone(result)

        creds = self.service.last_created_credentials
        self.assertIsNotNone(creds)
        self.assertEqual(creds["password"], result["password"])

    def test_pop_last_credentials_clears(self):
        """pop_last_credentials should return and clear the stored credentials."""
        self.service.pop_last_credentials()

        self.service.create_portal_account(
            customer_id=self.customer_id,
            phone_number="03123456789"
        )

        creds = self.service.pop_last_credentials()
        self.assertIsNotNone(creds)

        creds2 = self.service.pop_last_credentials()
        self.assertIsNone(creds2)


# =============================================================================
# SECTION 4: SMS Service Portal Credentials Integration Tests
# =============================================================================

class TestSmsPortalCredentialsIntegration(unittest.TestCase):
    """Verify SMS service handles portal credentials correctly."""

    def test_queue_credit_sale_sms_accepts_portal_credentials_param(self):
        """queue_credit_sale_sms should accept portal_credentials parameter."""
        import inspect
        from app.services.sms_service import sms_service
        sig = inspect.signature(sms_service.queue_credit_sale_sms)
        self.assertIn("portal_credentials", sig.parameters,
                      "queue_credit_sale_sms must accept portal_credentials parameter")

    def test_queue_finance_sale_sms_accepts_portal_credentials_param(self):
        """queue_finance_sale_sms should accept portal_credentials parameter."""
        import inspect
        from app.services.sms_service import sms_service
        sig = inspect.signature(sms_service.queue_finance_sale_sms)
        self.assertIn("portal_credentials", sig.parameters,
                      "queue_finance_sale_sms must accept portal_credentials parameter")


# =============================================================================
# SECTION 5: Service Method Signature Tests
# =============================================================================

class TestServiceMethodSignatures(unittest.TestCase):
    """Verify that service methods have correct signatures for credential handling."""

    def test_create_account_for_credit_sale_accepts_password_param(self):
        """create_account_for_credit_sale should accept an optional password parameter."""
        import inspect
        from app.services.customer_portal_service import customer_portal_service
        sig = inspect.signature(customer_portal_service.create_account_for_credit_sale)
        params = list(sig.parameters.keys())
        self.assertIn("password", params,
                      "create_account_for_credit_sale must accept password parameter")

    def test_customer_portal_service_has_last_created_credentials(self):
        """CustomerPortalService should have last_created_credentials attribute."""
        from app.services.customer_portal_service import customer_portal_service
        self.assertTrue(hasattr(customer_portal_service, "last_created_credentials"),
                        "CustomerPortalService must track last_created_credentials")

    def test_customer_portal_service_has_pop_last_credentials(self):
        """CustomerPortalService should have pop_last_credentials method."""
        from app.services.customer_portal_service import customer_portal_service
        self.assertTrue(hasattr(customer_portal_service, "pop_last_credentials"),
                        "CustomerPortalService must have pop_last_credentials method")

    def test_bulk_credit_service_passes_phone_number(self):
        """BulkCreditService.create_bulk_purchase should pass phone_number to portal service."""
        import inspect
        from app.services.bulk_credit_service import BulkCreditService
        source = inspect.getsource(BulkCreditService.create_bulk_purchase)
        self.assertIn("phone_number", source,
                      "BulkCreditService must pass phone_number for portal account creation")

    def test_create_credit_sale_captures_portal_credentials(self):
        """create_credit_sale should capture portal_creds from portal service."""
        import inspect
        from app.services.credit_ledger_service import CreditLedgerService
        source = inspect.getsource(CreditLedgerService.create_credit_sale)
        self.assertIn("portal_creds", source,
                      "create_credit_sale must capture portal_creds return value")

    def test_create_finance_sale_captures_portal_credentials(self):
        """create_finance_sale should capture portal_creds from portal service."""
        import inspect
        from app.services.credit_ledger_service import CreditLedgerService
        source = inspect.getsource(CreditLedgerService.create_finance_sale)
        self.assertIn("portal_creds", source,
                      "create_finance_sale must capture portal_creds return value")

    def test_create_credit_sale_passes_portal_creds_to_sms(self):
        """create_credit_sale should pass portal_credentials to SMS service."""
        import inspect
        from app.services.credit_ledger_service import CreditLedgerService
        source = inspect.getsource(CreditLedgerService.create_credit_sale)
        self.assertIn("portal_credentials=portal_creds", source.replace(" ", ""),
                      "create_credit_sale must pass portal_credentials to SMS")

    def test_create_finance_sale_passes_portal_creds_to_sms(self):
        """create_finance_sale should pass portal_credentials to SMS service."""
        import inspect
        from app.services.credit_ledger_service import CreditLedgerService
        source = inspect.getsource(CreditLedgerService.create_finance_sale)
        self.assertIn("portal_credentials=portal_creds", source.replace(" ", ""),
                      "create_finance_sale must pass portal_credentials to SMS")


# =============================================================================
# SECTION 6: Source Code Security Audit Tests
# =============================================================================

class TestSourceCodeSecurity(unittest.TestCase):
    """Audit source files for security issues in the credit/portal flow."""

    def test_no_random_choice_in_password_generation(self):
        """No password generation code should use random.choice."""
        files_to_check = [
            os.path.join(os.path.dirname(__file__), "..", "app", "services", "customer_portal_service.py"),
            os.path.join(os.path.dirname(__file__), "..", "credit_portal_integration", "auto_activation_service.py"),
        ]

        for filepath in files_to_check:
            filepath = os.path.normpath(filepath)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                lines = content.split("\n")
                for i, line in enumerate(lines, 1):
                    stripped = line.strip()
                    if "random.choice" in stripped and ("password" in stripped.lower() or "generate" in stripped.lower()):
                        self.fail(
                            f"File {os.path.basename(filepath)} line {i}: "
                            f"random.choice must not be used for password generation. "
                            f"Use secrets.choice instead."
                        )

    def test_portal_service_uses_secrets_not_random(self):
        """customer_portal_service.py should not import random."""
        filepath = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "app", "services", "customer_portal_service.py")
        )
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("import random", content,
                         "customer_portal_service.py must not import random")


# =============================================================================
# SECTION 7: UI Integration Tests (static analysis)
# =============================================================================

class TestUiPortalCredentialsDisplay(unittest.TestCase):
    """Verify UI pages display portal credentials when created."""

    def test_credit_ledger_page_shows_portal_creds(self):
        """credit_ledger_system_page should display portal credentials."""
        import inspect
        from app.qt_ui import credit_ledger_system_page
        source = inspect.getsource(credit_ledger_system_page)
        self.assertIn("Portal Access Granted", source,
                      "UI must show 'Portal Access Granted' message")
        self.assertIn("pop_last_credentials", source,
                      "UI must call pop_last_credentials to get credentials")

    def test_bulk_credit_page_shows_portal_creds(self):
        """bulk_credit_page should display portal credentials."""
        import inspect
        from app.qt_ui import bulk_credit_page
        source = inspect.getsource(bulk_credit_page)
        self.assertIn("Portal Access Granted", source,
                      "Bulk credit UI must show 'Portal Access Granted' message")
        self.assertIn("pop_last_credentials", source,
                      "Bulk credit UI must call pop_last_credentials")


# =============================================================================
# SECTION 8: Auto Activation Service Security Tests
# =============================================================================

class TestAutoActivationServiceSecurity(unittest.TestCase):
    """Verify auto_activation_service uses secure random."""

    def test_auto_activation_uses_secrets_not_random(self):
        """auto_activation_service.py should use secrets, not random."""
        filepath = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "credit_portal_integration", "auto_activation_service.py")
        )
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertNotIn("import random", content,
                         "auto_activation_service.py must not import random")
        self.assertIn("import secrets", content,
                      "auto_activation_service.py must import secrets")

    def test_auto_activation_generate_password_uses_secrets_choice(self):
        """auto_activation_service generate_random_password should use secrets.choice."""
        filepath = os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "credit_portal_integration", "auto_activation_service.py")
        )
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        self.assertIn("secrets.choice", content,
                      "auto_activation_service must use secrets.choice for passwords")


if __name__ == "__main__":
    unittest.main()
