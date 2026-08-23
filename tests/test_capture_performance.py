import time
import pytest
from app.services.form_capture_service import form_capture_service
from app.services.captured_form_processor import CapturedFormProcessor

class TestCapturePerformance:
    def test_capture_processing_speed(self):
        # Create a simple test data structure
        test_data = {
            "pages": {
                "https://test.url/form": {
                    "last_updated": time.time(),
                    "fields": {
                        "#txt_chassis_no": {"value": "123456789012345", "timestamp": time.time()},
                        "#txt_engine_no": {"value": "9876543210", "timestamp": time.time()},
                        "#txt_color": {"value": "Red", "timestamp": time.time()},
                        "#txt_model": {"value": "CD70", "timestamp": time.time()},
                        "#txt_full_name": {"value": "JOHN DOE", "timestamp": time.time()},
                        "#txt_father_name": {"value": "JANE DOE", "timestamp": time.time()},
                        "#txt_address": {"value": "123 MAIN ST", "timestamp": time.time()},
                        "#txt_cell_no": {"value": "1234567890", "timestamp": time.time()},
                        "#txt_cnic": {"value": "12345-6789012-3", "timestamp": time.time()}
                    }
                }
            }
        }
        
        # Test processing time
        start_time = time.time()
        processor = CapturedFormProcessor({
            "field_mapping": {
                "#txt_chassis_no": "chassis_number",
                "#txt_engine_no": "engine_number",
                "#txt_color": "color",
                "#txt_model": "model_name",
                "#txt_full_name": "buyer_name",
                "#txt_father_name": "buyer_father_name",
                "#txt_address": "buyer_address",
                "#txt_cell_no": "buyer_phone",
                "#txt_cnic": "buyer_cnic"
            }
        })
        result = processor.process_submission(test_data)
        end_time = time.time()
        
        print(f"Processing time: {end_time - start_time:.2f} seconds")
        assert result == True
        assert end_time - start_time < 0.5  # Should process in less than 0.5 seconds
        
    def test_capture_service_initialization_speed(self):
        start_time = time.time()
        service = form_capture_service
        end_time = time.time()
        
        print(f"Initialization time: {end_time - start_time:.2f} seconds")
        assert end_time - start_time < 0.1  # Should initialize in less than 0.1 seconds

if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main(["-v", __file__])
