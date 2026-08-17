
import unittest
from unittest.mock import MagicMock, patch
from datetime import datetime, timedelta
from app.services.sequential_upload_service import SequentialUploadService
from app.db.models import Invoice
import time


class TestSequentialUploadService(unittest.TestCase):
    """Unit tests for SequentialUploadService"""
    
    def setUp(self):
        """Set up test environment before each test."""
        self.service = SequentialUploadService()
        self.mock_invoice = MagicMock(spec=Invoice)
        self.mock_invoice.id = 1
        self.mock_invoice.invoice_number = "TEST-INV-001"
        self.mock_invoice.sync_status = "PENDING"
        self.mock_invoice.upload_attempts = 0
        self.mock_invoice.max_upload_attempts = 5
        self.mock_invoice.next_upload_attempt = None
        self.mock_invoice.is_processing = False
        self.mock_invoice.datetime = datetime.utcnow()
        self.mock_invoice.status_updated_at = datetime.utcnow()
    
    def test_service_initialization(self):
        """Test that service initializes correctly."""
        self.assertFalse(self.service.is_running())
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_get_next_invoice_to_process_no_invoices(self, mock_session_local):
        """Test getting next invoice to process when queue is empty."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_order = mock_filter.order_by.return_value
        mock_order.first.return_value = None
        
        result = self.service._get_next_invoice_to_process(mock_db)
        self.assertIsNone(result)
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_get_next_invoice_to_process_with_invoices(self, mock_session_local):
        """Test getting next invoice to process with valid invoices in queue."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_order = mock_filter.order_by.return_value
        mock_order.first.return_value = self.mock_invoice
        
        result = self.service._get_next_invoice_to_process(mock_db)
        self.assertEqual(result, self.mock_invoice)
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_queue_invoice_for_upload(self, mock_session_local):
        """Test queuing an invoice for upload."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        mock_db.query.return_value.get.return_value = self.mock_invoice
        
        self.service.queue_invoice_for_upload(1)
        
        self.assertEqual(self.mock_invoice.sync_status, "PENDING")
        self.assertEqual(self.mock_invoice.upload_attempts, 0)
        self.assertIsNone(self.mock_invoice.next_upload_attempt)
        self.assertFalse(self.mock_invoice.is_processing)
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_cancel_upload(self, mock_session_local):
        """Test canceling an invoice upload."""
        self.mock_invoice.sync_status = "PENDING"
        
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        mock_db.query.return_value.get.return_value = self.mock_invoice
        
        self.service.cancel_upload(1)
        
        self.assertEqual(self.mock_invoice.sync_status, "FAILED")
        self.assertFalse(self.mock_invoice.is_processing)
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_get_queue_status_empty(self, mock_session_local):
        """Test getting queue status when queue is empty."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        # Configure counts to return 0
        mock_db.query.return_value.filter.return_value.count.side_effect = [0, 0, 0, 0]
        # Configure queries to return empty lists
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        mock_db.query.return_value.filter.return_value.first.return_value = None
        
        status = self.service.get_queue_status()
        
        self.assertEqual(status["pending"], 0)
        self.assertEqual(status["processing"], 0)
        self.assertEqual(status["failed"], 0)
        self.assertEqual(status["synced"], 0)
        self.assertIsNone(status["current"])
        self.assertEqual(len(status["upcoming"]), 0)
    
    def test_handle_failure_with_backoff(self):
        """Test that failure handling with exponential backoff works."""
        initial_attempts = 1
        self.mock_invoice.upload_attempts = initial_attempts
        
        self.service._handle_failure(self.mock_invoice)
        
        self.assertEqual(self.mock_invoice.upload_attempts, initial_attempts + 1)
        self.assertIsNotNone(self.mock_invoice.next_upload_attempt)
        self.assertFalse(self.mock_invoice.is_processing)
        
        # Verify backoff delay is correct (exponential: 2^(attempt) minutes)
        expected_delay = 2 ** (initial_attempts + 1) * 60
        actual_delay = (self.mock_invoice.next_upload_attempt - datetime.utcnow()).total_seconds()
        self.assertGreaterEqual(actual_delay, expected_delay - 1)  # Allow 1 sec tolerance
        self.assertLess(actual_delay, expected_delay + 1)
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    @patch("app.services.sequential_upload_service.invoice_service")
    def test_process_success(self, mock_invoice_service, mock_session_local):
        """Test processing a single invoice successfully."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        # Configure mock to find our test invoice
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_order = mock_filter.order_by.return_value
        mock_order.first.return_value = self.mock_invoice
        
        # Configure invoice_service.sync_invoice to mark as synced
        self.mock_invoice.sync_status = "SYNCED"
        
        with patch.object(self.service, '_get_next_invoice_to_process', return_value=self.mock_invoice):
            processed = self.service._process_next_invoice()
            
            self.assertTrue(processed)
            mock_invoice_service.sync_invoice.assert_called_once()
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    @patch("app.services.sequential_upload_service.invoice_service")
    def test_process_failure(self, mock_invoice_service, mock_session_local):
        """Test processing a single invoice that fails."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        # Configure mock to find our test invoice
        mock_query = mock_db.query.return_value
        mock_filter = mock_query.filter.return_value
        mock_order = mock_filter.order_by.return_value
        mock_order.first.return_value = self.mock_invoice
        
        # Configure sync_invoice to raise exception
        error_message = "Connection timeout"
        mock_invoice_service.sync_invoice.side_effect = Exception(error_message)
        
        with patch.object(self.service, '_get_next_invoice_to_process', return_value=self.mock_invoice):
            processed = self.service._process_next_invoice()
            
            self.assertTrue(processed)
            self.assertGreater(self.mock_invoice.upload_attempts, 0)
            self.assertIsNotNone(self.mock_invoice.next_upload_attempt)
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_reset_failed_uploads(self, mock_session_local):
        """Test resetting all failed uploads to pending state."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        failed_invoice1 = MagicMock(spec=Invoice)
        failed_invoice1.sync_status = "FAILED"
        failed_invoice1.upload_attempts = 3
        
        failed_invoice2 = MagicMock(spec=Invoice)
        failed_invoice2.sync_status = "FAILED"
        failed_invoice2.upload_attempts = 2
        
        mock_db.query.return_value.filter.return_value.all.return_value = [failed_invoice1, failed_invoice2]
        
        self.service.reset_failed_uploads()
        
        self.assertEqual(failed_invoice1.sync_status, "PENDING")
        self.assertEqual(failed_invoice1.upload_attempts, 0)
        self.assertIsNone(failed_invoice1.next_upload_attempt)
        
        self.assertEqual(failed_invoice2.sync_status, "PENDING")
        self.assertEqual(failed_invoice2.upload_attempts, 0)
        self.assertIsNone(failed_invoice2.next_upload_attempt)
    
    def test_service_start_stop(self):
        """Test that service can be started and stopped."""
        self.assertFalse(self.service.is_running())
        
        # Start service (should be fast since it's a daemon thread)
        self.service.start()
        time.sleep(0.1)
        self.assertTrue(self.service.is_running())
        
        # Stop service
        self.service.stop()
        time.sleep(0.1)
        self.assertFalse(self.service.is_running())
    
    @patch("app.services.sequential_upload_service.SessionLocal")
    def test_get_upload_history(self, mock_session_local):
        """Test getting recent upload history."""
        mock_db = MagicMock()
        mock_session_local.return_value = mock_db
        
        # Setup mock history data
        mock_invoice1 = MagicMock(spec=Invoice)
        mock_invoice1.invoice_number = "HIST-001"
        mock_invoice1.sync_status = "SYNCED"
        mock_invoice1.upload_attempts = 1
        mock_invoice1.status_updated_at = datetime.utcnow()
        mock_invoice1.fbr_response_message = "Success"
        
        mock_invoice2 = MagicMock(spec=Invoice)
        mock_invoice2.invoice_number = "HIST-002"
        mock_invoice2.sync_status = "FAILED"
        mock_invoice2.upload_attempts = 3
        mock_invoice2.status_updated_at = datetime.utcnow() - timedelta(hours=1)
        mock_invoice2.fbr_response_message = "Failed to connect"
        
        mock_db.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_invoice1,
            mock_invoice2
        ]
        
        history = self.service.get_queue_history()
        
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["invoice_number"], "HIST-001")
        self.assertEqual(history[0]["status"], "SYNCED")
        self.assertEqual(history[0]["attempts"], 1)
        
        self.assertEqual(history[1]["invoice_number"], "HIST-002")
        self.assertEqual(history[1]["status"], "FAILED")
        self.assertEqual(history[1]["attempts"], 3)


class TestIntegrationWithSyncService(unittest.TestCase):
    """Integration tests to verify existing features work with new service."""
    
    @patch("app.services.sync_service.sequential_upload_service")
    def test_sync_service_delegates_to_sequential(self, mock_sequential_service):
        """Test that SyncService delegates to SequentialUploadService."""
        from app.services.sync_service import sync_service
        
        # Start service
        sync_service.start()
        mock_sequential_service.start.assert_called_once()
        
        # Stop service
        sync_service.stop()
        mock_sequential_service.stop.assert_called_once()
        
        # Reset mock
        mock_sequential_service.reset_mock()
        
        # Test trigger sync now
        sync_service.trigger_sync_now()
        mock_sequential_service.start.assert_called_once()
    
    @patch("app.services.sync_service.sequential_upload_service")
    def test_sync_service_queue_methods(self, mock_sequential_service):
        """Test that SyncService queue methods delegate correctly."""
        from app.services.sync_service import sync_service
        
        # Test queue invoice
        sync_service.queue_invoice_for_upload(123)
        mock_sequential_service.queue_invoice_for_upload.assert_called_once_with(123)
        
        # Test cancel upload
        sync_service.cancel_upload(456)
        mock_sequential_service.cancel_upload.assert_called_once_with(456)
        
        # Test reset failed
        sync_service.reset_failed_uploads()
        mock_sequential_service.reset_failed_uploads.assert_called_once()
        
        # Test getting status
        mock_sequential_service.get_queue_status.return_value = {"pending": 0, "processing": 0, "failed": 0, "synced": 0}
        status = sync_service.get_upload_queue_status()
        mock_sequential_service.get_queue_status.assert_called_once()
        self.assertEqual(status, {"pending": 0, "processing": 0, "failed": 0, "synced": 0})


if __name__ == "__main__":
    unittest.main()
