import time
import unittest

from reporting.lookup_utils import (
    format_cnic,
    is_valid_cnic,
    is_valid_name,
    is_valid_phone,
    normalize_phone,
    validate_lookup_inputs,
)


class TestLookupUtils(unittest.TestCase):
    def test_phone_normalization_and_validation(self) -> None:
        self.assertEqual(normalize_phone("03-001234567"), "03001234567")
        self.assertTrue(is_valid_phone("03001234567"))
        self.assertFalse(is_valid_phone("04001234567"))
        self.assertFalse(is_valid_phone("0300123456"))

    def test_cnic_formatting_and_validation(self) -> None:
        self.assertEqual(format_cnic("1234512345671"), "12345-1234567-1")
        self.assertEqual(format_cnic("12345-1234567-1"), "12345-1234567-1")
        self.assertTrue(is_valid_cnic("12345-1234567-1"))
        self.assertFalse(is_valid_cnic("12345-1234567"))

    def test_name_validation(self) -> None:
        self.assertTrue(is_valid_name(""))
        self.assertFalse(is_valid_name("A"))
        self.assertTrue(is_valid_name("Ali"))

    def test_validate_lookup_inputs_combinations(self) -> None:
        p, c, n = validate_lookup_inputs("03001234567", "12345-1234567-1", "Ali")
        self.assertEqual(p, "03001234567")
        self.assertEqual(c, "1234512345671")
        self.assertEqual(n, "Ali")

        p, c, n = validate_lookup_inputs("", "", "")
        self.assertEqual(p, "")
        self.assertEqual(c, "")
        self.assertEqual(n, "")

        with self.assertRaises(ValueError):
            validate_lookup_inputs("0300", "", "")

        with self.assertRaises(ValueError):
            validate_lookup_inputs("", "12345-1234567", "")

        with self.assertRaises(ValueError):
            validate_lookup_inputs("", "", "A")

    def test_performance_validation_large_inputs(self) -> None:
        start = time.monotonic()
        for _ in range(50000):
            validate_lookup_inputs("03001234567", "12345-1234567-1", "Ali")
        elapsed = time.monotonic() - start
        self.assertLess(elapsed, 2.5)


if __name__ == "__main__":
    unittest.main()
