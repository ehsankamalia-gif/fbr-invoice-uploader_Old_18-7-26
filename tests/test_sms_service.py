import unittest
from unittest.mock import MagicMock, patch
from app.services.sms_service import SMSService
import time

class TestSMSService(unittest.TestCase):
    def setUp(self):
        self.sms_service = SMSService()
        self.ip = "192.168.1.10"
        self.port = "8080"
        self.phone = "03001234567"
        self.msg = "Test message"

    @patch('app.services.sms_service.socket.socket')
    @patch('app.services.sms_service.requests.Session')
    def test_official_library_success(self, mock_session_class, mock_socket):
        """Test that the official library is tried first and succeeds."""
        # Mock successful socket connection
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance

        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # Mock successful response
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = '{"status": "success"}'
        mock_session.post.return_value = mock_resp
        
        # Reset the service to use the mocked session class
        self.sms_service = SMSService()
        
        success, msg = self.sms_service.send_sms_via_wifi(
            self.ip, self.port, self.phone, self.msg, 
            username="test_user", password="test_password"
        )
        
        self.assertTrue(success)
        self.assertIn("Success", msg)
        mock_session.post.assert_called()

    @patch('app.services.sms_service.socket.socket')
    def test_connection_failure_fast(self, mock_socket):
        """Test that the service fails fast if the socket connection fails."""
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 111 # Connection refused
        mock_socket.return_value = mock_sock_instance
        
        success, msg = self.sms_service.send_sms_via_wifi(
            self.ip, self.port, self.phone, self.msg
        )
        
        self.assertFalse(success)
        self.assertIn("Unreachable", msg)
        mock_sock_instance.connect_ex.assert_called_once()

    @patch('app.services.sms_service.socket.socket')
    @patch('app.services.sms_service.requests.Session')
    def test_discovery_fallback_success(self, mock_session_class, mock_socket):
        """Test that discovery fallback works if official library fails."""
        # Mock successful socket connection
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance

        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # 1. First call (/message) fails
        # 2. Second call (/sms) succeeds
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 404
        
        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.text = '{"status": "success", "message": "sent"}'
        
        mock_session.post.side_effect = [mock_resp_fail, mock_resp_success]

        self.sms_service = SMSService()
        success, msg = self.sms_service.send_sms_via_wifi(
            self.ip, self.port, self.phone, self.msg,
            username=None, password=None
        )
        
        self.assertTrue(success)
        self.assertIn("Success (/sms)", msg)

    @patch('app.services.sms_service.socket.socket')
    def test_global_timeout(self, mock_socket):
        """Test that the global timeout correctly stops a long discovery process."""
        # Mock successful socket connection
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance

        start_time = time.time()
        # Set a very short total timeout
        success, msg = self.sms_service.send_sms_via_wifi(
            self.ip, self.port, self.phone, self.msg,
            total_timeout=0.01
        )
        
        self.assertFalse(success)
        self.assertIn("Total time limit", msg)

    @patch('app.services.sms_service.socket.socket')
    @patch('app.services.sms_service.requests.Session')
    def test_false_positive_prevention(self, mock_session_class, mock_socket):
        """Test that generic 200 OK responses without success keywords are ignored."""
        # Mock successful socket connection
        mock_sock_instance = MagicMock()
        mock_sock_instance.connect_ex.return_value = 0
        mock_socket.return_value = mock_sock_instance

        mock_session = MagicMock()
        mock_session_class.return_value = mock_session
        
        # All endpoints return 200 but generic HTML content
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.text = "<html>Welcome to my server</html>"
        mock_session.post.return_value = mock_resp
        
        self.sms_service = SMSService()
        success, msg = self.sms_service.send_sms_via_wifi(
            self.ip, self.port, self.phone, self.msg
        )
        
        self.assertFalse(success)
        self.assertTrue("All prioritized endpoints failed" in msg or "RetryError" in msg)

if __name__ == '__main__':
    unittest.main()
