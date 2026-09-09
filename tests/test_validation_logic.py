
import pytest
from playwright.sync_api import sync_playwright
from unittest.mock import patch
import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

with patch('app.services.captured_form_processor.CapturedFormProcessor'):
    from app.services.form_capture_service import FormCaptureService

def test_validation_rejects_invalid_data():
    """
    Verifies that the injection script rejects invalid data (e.g. 'Submit' as color)
    and adheres to the validation schema.
    """
    service = FormCaptureService()
    service.config = {
        "debounce_ms": 100,
        "include_selectors": ["#txt_engine_no", "#txt_model", "#txt_color"], 
        "exclude_selectors": [],
        "submit_selector": "#submit_btn",
        "login_config": {}
    }
    
    script = service._get_injection_script()
    
    # HTML with BAD values
    html_content = """
    <html>
        <body>
            <div id="form-container">
                <!-- Engine Number: Too short -->
                <div class="row">
                    <label>Engine Number</label>
                    <span class="value">12</span>
                </div>
                
                <!-- Model: Contains 'Submit' -->
                <table>
                    <tr>
                        <td>Vehicle Model:</td>
                        <td>Please Submit</td>
                    </tr>
                </table>
                
                <!-- Color: Is 'Save' -->
                <p>Vehicle Color: Save</p>
                
                <input type="hidden" id="txt_engine_no" value="">
                <!-- Marks this as a customer-profile page. The injector only
                     force-captures on submit when this field is present, so
                     unrelated portal pages no longer create captured records. -->
                <input type="hidden" id="txt_chassis_no" value="CH-TEST-1234">
            </div>
            
            <button id="submit_btn">Submit</button>
        </body>
    </html>
    """
    
    captured_events = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        # Capture console logs to see validation warnings
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))

        def py_capture(data):
            if data.get("type") == "form_submission":
                captured_events.append(data)
            
        page.expose_function("py_capture", py_capture)
        page.set_content(html_content)
        page.evaluate(script)
        
        # Trigger submit
        page.click("#submit_btn")
        
        page.wait_for_timeout(2000)
        browser.close()
        
    assert len(captured_events) > 0
    submission = captured_events[-1]["forced_capture"]
    
    print(f"Captured Submission: {submission}")
    
    # Assertions: Fields should be MISSING because they were rejected
    # Engine number '12' is < 4 chars -> rejected
    assert "#txt_engine_no" not in submission or submission["#txt_engine_no"] == "", "Invalid engine number should be rejected"
    
    # Model 'Please Submit' contains 'Submit' -> rejected
    assert "#txt_model" not in submission or submission["#txt_model"] == "", "Invalid model should be rejected"
    
    # Color 'Save' -> rejected
    assert "#txt_color" not in submission or submission["#txt_color"] == "", "Invalid color should be rejected"

def test_validation_accepts_valid_data():
    """
    Verifies that valid data is still accepted.
    """
    service = FormCaptureService()
    service.config = {
        "debounce_ms": 100,
        "include_selectors": ["#txt_engine_no", "#txt_model", "#txt_color"], 
        "exclude_selectors": [],
        "submit_selector": "#submit_btn",
        "login_config": {}
    }
    
    script = service._get_injection_script()
    
    html_content = """
    <html>
        <body>
            <div id="form-container">
                <p>Engine Number: ENG-9999</p>
                <p>Vehicle Model: Toyota Corolla</p>
                <p>Vehicle Color: White</p>
                <input type="hidden" id="txt_engine_no" value="">
                <!-- Marks this as a customer-profile page. The injector only
                     force-captures on submit when this field is present, so
                     unrelated portal pages no longer create captured records. -->
                <input type="hidden" id="txt_chassis_no" value="CH-TEST-1234">
            </div>
            <button id="submit_btn">Submit</button>
        </body>
    </html>
    """
    
    captured_events = []
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: print(f"BROWSER LOG: {msg.text}"))
        
        def py_capture(data):
            if data.get("type") == "form_submission":
                captured_events.append(data)
            
        page.expose_function("py_capture", py_capture)
        page.set_content(html_content)
        page.evaluate(script)
        page.click("#submit_btn")
        page.wait_for_timeout(2000)
        browser.close()
        
    submission = captured_events[-1]["forced_capture"]
    assert submission.get("#txt_engine_no") == "ENG-9999"
    assert submission.get("#txt_model") == "Toyota Corolla"
    assert submission.get("#txt_color") == "White"
