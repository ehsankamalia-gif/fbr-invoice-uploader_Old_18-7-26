import unittest

from app.utils.string_utils import to_uppercase_preserving, InvoiceFormState


class TestInvoicePreserveFeatures(unittest.TestCase):
    def test_to_uppercase_preserving_keeps_numbers_spaces_symbols(self) -> None:
        self.assertEqual(
            to_uppercase_preserving("House #12, st. 5-A (near park)"),
            "HOUSE #12, ST. 5-A (NEAR PARK)",
        )

    def test_to_uppercase_preserving_empty(self) -> None:
        self.assertEqual(to_uppercase_preserving(""), "")
        self.assertEqual(to_uppercase_preserving(None), "")

    def test_after_submit_preserves_customer_info_when_enabled(self) -> None:
        state = InvoiceFormState(
            preserve_info=True,
            buyer_cnic="12345-1234567-1",
            buyer_name="ALI",
            buyer_address="HOUSE #12",
            model="CD70",
            chassis="ABC",
            amount_excl=144400.0,
        )
        cleared = state.after_submit()
        self.assertTrue(cleared.preserve_info)
        self.assertEqual(cleared.buyer_cnic, "12345-1234567-1")
        self.assertEqual(cleared.buyer_name, "ALI")
        self.assertEqual(cleared.buyer_address, "HOUSE #12")
        self.assertEqual(cleared.model, "")
        self.assertEqual(cleared.chassis, "")
        self.assertEqual(cleared.amount_excl, 0.0)

    def test_after_submit_clears_all_when_preserve_disabled(self) -> None:
        state = InvoiceFormState(
            preserve_info=False,
            buyer_cnic="12345-1234567-1",
            buyer_name="ALI",
            model="CD70",
            chassis="ABC",
            amount_excl=144400.0,
        )
        cleared = state.after_submit()
        self.assertFalse(cleared.preserve_info)
        self.assertEqual(cleared.buyer_cnic, "")
        self.assertEqual(cleared.buyer_name, "")
        self.assertEqual(cleared.model, "")
        self.assertEqual(cleared.chassis, "")
        self.assertEqual(cleared.amount_excl, 0.0)

    def test_after_reset_always_clears_everything(self) -> None:
        state = InvoiceFormState(
            preserve_info=True,
            buyer_cnic="12345-1234567-1",
            buyer_name="ALI",
            buyer_address="HOUSE #12",
            model="CD70",
        )
        cleared = state.after_reset()
        self.assertFalse(cleared.preserve_info)
        self.assertEqual(cleared.buyer_cnic, "")
        self.assertEqual(cleared.buyer_name, "")
        self.assertEqual(cleared.buyer_address, "")
        self.assertEqual(cleared.model, "")


if __name__ == "__main__":
    unittest.main()
