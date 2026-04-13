import pathlib
import unittest


class TestLookupPageUnifiedTable(unittest.TestCase):
    def test_lookup_page_contains_unified_table_and_actions(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        content = (repo_root / "reporting" / "main.py").read_text(encoding="utf-8", errors="ignore")

        self.assertIn('id="resultsTable"', content)
        self.assertIn('id="resultsBody"', content)
        self.assertIn('id="pager"', content)
        self.assertIn('id="retryUploadBtn"', content)
        self.assertIn('id="copyInvoiceBtn"', content)
        self.assertIn('id="copyChassisBtn"', content)
        self.assertIn("/api/lookup/search", content)
        self.assertIn('id="invoiceDetailModal"', content)
        self.assertIn("/api/invoices/", content)
        self.assertIn("/details", content)
        self.assertIn("openInvoiceDetails", content)
        self.assertIn("tabindex=\"0\"", content)
        self.assertIn("aria-label=\"View invoice", content)

        self.assertIn("Customer Name", content)
        self.assertIn("Father's Name", content)
        self.assertIn("Mobile Number", content)
        self.assertIn("Invoice Number", content)
        self.assertIn("Bike Model", content)
        self.assertIn("Chassis Number", content)
        self.assertIn("Date", content)

    def test_lookup_page_removed_per_filter_results_containers(self) -> None:
        repo_root = pathlib.Path(__file__).resolve().parents[1]
        content = (repo_root / "reporting" / "main.py").read_text(encoding="utf-8", errors="ignore")

        self.assertNotIn('id="phoneResults"', content)
        self.assertNotIn('id="cnicResults"', content)
        self.assertNotIn('id="nameResults"', content)


if __name__ == "__main__":
    unittest.main()
