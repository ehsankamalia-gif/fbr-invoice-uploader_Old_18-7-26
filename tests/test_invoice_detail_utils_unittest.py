import unittest
from types import SimpleNamespace

from reporting.invoice_detail_utils import invoice_to_detail_dict


class TestInvoiceDetailUtils(unittest.TestCase):
    def test_invoice_to_detail_dict_basic(self) -> None:
        product_model = SimpleNamespace(model_name="CD70")
        motorcycle = SimpleNamespace(
            chassis_number="HB665591",
            engine_number="EN123",
            color="RED",
            product_model=product_model,
        )
        item = SimpleNamespace(
            item_code="M001",
            item_name="MOTORCYCLE",
            pct_code="8711",
            quantity=1,
            sale_value=144400.0,
            tax_charged=14000.0,
            further_tax=1500.0,
            total_amount=159900.0,
            discount=0.0,
            motorcycle=motorcycle,
        )
        customer = SimpleNamespace(
            name="FAKHAR IQBAL",
            father_name="SIKANDAR",
            cnic="12345-1234567-1",
            ntn="",
            phone="03112536333",
            address="ADDRESS",
            type="DEALER",
            business_name="",
        )
        invoice = SimpleNamespace(
            invoice_number="EHS-0001",
            datetime=SimpleNamespace(isoformat=lambda sep=" ": "2026-04-11 17:56:47"),
            pos_id="1",
            payment_mode="Cash",
            sync_status="PENDING",
            is_fiscalized=False,
            fbr_invoice_number=None,
            customer=customer,
            items=[item],
            total_sale_value=144400.0,
            total_tax_charged=14000.0,
            total_further_tax=1500.0,
            total_amount=159900.0,
        )

        out = invoice_to_detail_dict(invoice)
        self.assertEqual(out["invoice_number"], "EHS-0001")
        self.assertEqual(out["customer"]["name"], "FAKHAR IQBAL")
        self.assertEqual(len(out["items"]), 1)
        self.assertEqual(out["items"][0]["model"], "CD70")
        self.assertEqual(out["items"][0]["chassis_number"], "HB665591")
        self.assertEqual(out["totals"]["total"], 159900.0)

    def test_invoice_to_detail_dict_handles_missing_customer_and_items(self) -> None:
        invoice = SimpleNamespace(invoice_number="X", datetime=None, customer=None, items=[])
        out = invoice_to_detail_dict(invoice)
        self.assertEqual(out["invoice_number"], "X")
        self.assertEqual(out["customer"]["name"], "")
        self.assertEqual(out["items"], [])


if __name__ == "__main__":
    unittest.main()
