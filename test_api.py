#!/usr/bin/env python
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from app.services.form_capture_service import FormCaptureService

def test_form_capture_api():
    service = FormCaptureService()
    
    print("Testing FormCaptureService API...")
    print("Version:", getattr(service, '__version__', 'Unknown'))
    print("Is running?", service.is_running)
    
    # Start a capture session
    print("\nStarting capture session...")
    try:
        service.start_capture_session(url="https://example.com")
        time.sleep(2) # Wait for browser thread to start
        
        print("Session started")
        print("Is running?", service.is_running)
        
        # Check if browser objects are created
        print("\nBrowser context:", service.browser)
        print("Playwright instance:", service.playwright)
        print("Context:", service.context)
        print("Page:", service.page)
        
        if service.is_running and service.page:
            # Try to execute script in browser thread
            print("\nExecuting script in browser thread...")
            result = service.execute_task(lambda page: page.evaluate("typeof window"))
            print("Page evaluate result (window):", result)
            
            # Check injection script presence
            functions_to_check = [
                "typeof handleSubmit",
                "typeof capture", 
                "typeof debouncedCapture",
                "typeof grabText"
            ]
            
            for func in functions_to_check:
                try:
                    res = service.execute_task(lambda page: page.evaluate(func))
                    print(f"  {func} = {res}")
                except Exception as e:
                    print(f"  {func} = Error: {e}")
                    
            # Check window.py_capture
            print("\nChecking window.py_capture...")
            try:
                res = service.execute_task(lambda page: page.evaluate("typeof window.py_capture"))
                print(f"  window.py_capture type: {res}")
                
                if res == "function":
                    print("  ✓ window.py_capture exposed as function")
                    
                    # Try calling it
                    try:
                        data = {
                            'type': 'api_test',
                            'source': 'api_test',
                            'url': page.url,
                            'timestamp': 1234567890,
                            'forced_capture': {'test_key': 'test_value'}
                        }
                        res = service.execute_task(lambda page: page.evaluate(
                            "window.py_capture(arguments[0])", data
                        ))
                        print("  ✓ window.py_capture call returned:", res)
                    except Exception as e:
                        print(f"  ✗ window.py_capture call failed: {e}")
                        
            except Exception as e:
                print(f"  Checking window.py_capture failed: {e}")
                
    except Exception as e:
        print(f"Error starting session: {e}")
        import traceback
        print(traceback.format_exc())
        
    # Stop session
    print("\nStopping capture session...")
    try:
        service.stop_capture_session()
        print("Session stopped")
    except Exception as e:
        print(f"Error stopping session: {e}")

if __name__ == "__main__":
    test_form_capture_api()
