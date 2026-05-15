
#!/usr/bin/env python3
import sys
import time
import json
import os
from pathlib import Path
from dms_automator import DMSAutomator


def process_pending_submissions(automator):
    """Process submissions saved from the GUI"""
    data_dir = Path(__file__).parent / "data"
    submissions_file = data_dir / "submissions.json"
    
    if not submissions_file.exists():
        print("\n[!] No pending submissions found from GUI.")
        return

    try:
        with open(submissions_file, 'r') as f:
            submissions = json.load(f)
        
        if not submissions:
            print("\n[!] Submissions list is empty.")
            return

        print(f"\n[+] Found {len(submissions)} pending submissions from GUI.")
        
        for i, sub in enumerate(submissions):
            chassis = sub.get('chassis_number')
            engine = sub.get('engine_number')
            
            print(f"\n[{i+1}/{len(submissions)}] Processing Chassis: {chassis}, Engine: {engine}")
            result = automator.fill_vehicle_details(chassis, engine)
            print(f"    Result: {result}")
            
            # Small delay between submissions
            time.sleep(1)
            
        # Move the file to processed folder
        processed_dir = data_dir / "processed"
        processed_dir.mkdir(exist_ok=True)
        
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        processed_file = processed_dir / f"submissions_{timestamp}.json"
        
        import shutil
        shutil.move(str(submissions_file), str(processed_file))
        print(f"\n[+] All pending submissions processed and moved to {processed_file}")

    except Exception as e:
        print(f"\n[!] Error processing submissions: {e}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="DMS Portal Automation")
    parser.add_argument("--auto", action="store_true", help="Automatically process pending submissions and exit")
    args = parser.parse_args()

    print("=" * 60)
    print("           DMS Portal Automation")
    print("=" * 60)

    automator = DMSAutomator()

    try:
        print("\nStarting DMS Automator in background...")
        automator.start()
        time.sleep(2)

        print("\nAttempting to login to DMS portal...")
        automator.login()
        
        if args.auto:
            print("\n[!] Manual Action Required: Please solve the CAPTCHA and click Login.")
            print("[!] Automation will resume automatically once you are logged in...")
            if automator.wait_for_login(timeout=300):
                print("\n[+] Login successful! Resuming automation...")
                time.sleep(2)
                print("\n[Auto Mode] Processing pending submissions...")
                process_pending_submissions(automator)
            else:
                print("\n[!] Login wait timed out. Please restart and try again.")
            
            print("\n[Auto Mode] Finished. Shutting down...")
            automator.stop()
            return

        print("Login page opened. Please complete login manually if needed.")

        print("\n" + "=" * 60)
        print("Automation is running in the background!")
        print("You can now use your PC for other tasks.")
        print("=" * 60)

        while True:
            print("\nOptions:")
            print("1. Fill Vehicle Details (Manual Entry)")
            print("2. Process Pending Submissions (from GUI)")
            print("3. Navigate to URL")
            print("4. Exit")

            choice = input("\nEnter your choice (1-4): ").strip()

            if choice == "1":
                frame_number = input("Enter Frame Number: ").strip()
                engine_number = input("Enter Engine Number: ").strip()

                if frame_number and engine_number:
                    print(f"\nFilling details - Frame: {frame_number}, Engine: {engine_number}")
                    result = automator.fill_vehicle_details(frame_number, engine_number)
                    print(f"\nResult: {result}")
                else:
                    print("Please enter both frame and engine numbers.")

            elif choice == "2":
                process_pending_submissions(automator)

            elif choice == "3":
                url = input("Enter URL to navigate to: ").strip()
                if url:
                    automator.navigate_to(url)
                    print(f"Navigated to {url}")

            elif choice == "4":
                print("\nShutting down DMS Automator...")
                automator.stop()
                print("Goodbye!")
                break

            else:
                print("Invalid choice. Please try again.")

    except KeyboardInterrupt:
        print("\n\nReceived interrupt signal. Shutting down...")
        automator.stop()
        sys.exit(0)
    except Exception as e:
        print(f"\nError: {e}")
        automator.stop()
        sys.exit(1)


if __name__ == "__main__":
    main()
