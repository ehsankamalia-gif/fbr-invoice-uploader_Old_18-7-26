
#!/usr/bin/env python3
"""Quick start script for DMS Automation"""
import time
from dms_automator import DMSAutomator


def quick_fill(frame_number: str, engine_number: str):
    """Quickly fill frame and engine numbers"""
    automator = DMSAutomator()

    try:
        print("Starting DMS Automator...")
        automator.start()
        time.sleep(2)

        print("Opening login page...")
        automator.login()
        time.sleep(3)

        print(f"Filling: Frame={frame_number}, Engine={engine_number}")
        result = automator.fill_vehicle_details(frame_number, engine_number)
        print(f"Result: {result}")

        print("\nAutomation complete! Press Ctrl+C to exit or close the browser.")
        while True:
            time.sleep(1)

    except KeyboardInterrupt:
        print("\nStopping...")
        automator.stop()


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3:
        frame = sys.argv[1]
        engine = sys.argv[2]
        quick_fill(frame, engine)
    else:
        print("Usage: python quick_start.py <frame_number> <engine_number>")
        print("\nOr run 'python main.py' for interactive mode")
