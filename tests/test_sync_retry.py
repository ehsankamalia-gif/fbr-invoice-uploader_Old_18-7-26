
import unittest
from unittest.mock import MagicMock, patch
from app.services.sync_service import SyncService
from app.db.models import Invoice


class TestSyncRetry(unittest.TestCase):
    def setUp(self):
        self.sync_service = SyncService()
        self.sync_service._stop_event = MagicMock()
        self.sync_service._stop_event.is_set.return_value = False

    @patch("app.services.sync_service.sequential_upload_service")
    def test_sync_service_starts_sequential_service(self, mock_sequential):
        """Test that SyncService starts sequential upload service."""
        self.sync_service.start()
        mock_sequential.start.assert_called_once()

    @patch("app.services.sync_service.sequential_upload_service")
    def test_sync_service_stops_sequential_service(self, mock_sequential):
        """Test that SyncService stops sequential upload service."""
        self.sync_service.stop()
        mock_sequential.stop.assert_called_once()

    @patch("app.services.sync_service.sequential_upload_service")
    def test_trigger_sync_now_delegates_to_sequential(self, mock_sequential):
        """Test that trigger_sync_now delegates to sequential service."""
        self.sync_service.trigger_sync_now()
        mock_sequential.start.assert_called_once()

    @patch("app.services.sync_service.sequential_upload_service")
    def test_queue_invoice_delegation(self, mock_sequential):
        """Test that queue_invoice_for_upload delegates to sequential service."""
        self.sync_service.queue_invoice_for_upload(123)
        mock_sequential.queue_invoice_for_upload.assert_called_once_with(123)

    @patch("app.services.sync_service.sequential_upload_service")
    def test_cancel_upload_delegation(self, mock_sequential):
        """Test that cancel_upload delegates to sequential service."""
        self.sync_service.cancel_upload(123)
        mock_sequential.cancel_upload.assert_called_once_with(123)

    @patch("app.services.sync_service.sequential_upload_service")
    def test_reset_failed_delegation(self, mock_sequential):
        """Test that reset_failed_uploads delegates to sequential service."""
        self.sync_service.reset_failed_uploads()
        mock_sequential.reset_failed_uploads.assert_called_once()

    @patch("app.services.sync_service.sequential_upload_service")
    def test_get_upload_queue_status_delegation(self, mock_sequential):
        """Test that get_upload_queue_status delegates to sequential service."""
        mock_status = {"pending": 5, "processing": 1, "failed": 2, "synced": 10}
        mock_sequential.get_queue_status.return_value = mock_status
        status = self.sync_service.get_upload_queue_status()
        mock_sequential.get_queue_status.assert_called_once()
        self.assertEqual(status, mock_status)

    @patch("app.services.sync_service.sequential_upload_service")
    def test_is_sequential_service_running(self, mock_sequential):
        """Test that is_sequential_service_running works correctly."""
        mock_sequential.is_running.return_value = True
        self.assertTrue(self.sync_service.is_sequential_service_running())
        mock_sequential.is_running.return_value = False
        self.assertFalse(self.sync_service.is_sequential_service_running())


if __name__ == "__main__":
    unittest.main()
