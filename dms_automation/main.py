
#!/usr/bin/env python3
import sys
import time
from dms_automator import DMSAutomator


def main():
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
        print("Login page opened. Please complete login manually if needed.")

        print("\n" + "=" * 60)
        print("Automation is running in the background!")
        print("You can now use your PC for other tasks.")
        print("=" * 60)

        while True:
            print("\nOptions:")
            print("1. Fill Vehicle Details (Frame & Engine Number)")
            print("2. Navigate to URL")
            print("3. Exit")

            choice = input("\nEnter your choice (1-3): ").strip()

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
                url = input("Enter URL to navigate to: ").strip()
                if url:
                    automator.navigate_to(url)
                    print(f"Navigated to {url}")

            elif choice == "3":
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
