import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from reporting.server import (
    start_reporting_server,
    get_last_startup_error,
    get_server_thread_exception,
)

print("=== Test 1: Successful startup ===")
ok, msg = start_reporting_server()
print(f"Result: ok={ok}, msg={msg}")
print(f"Last stored error: {get_last_startup_error()}")
print(f"Server thread exception: {get_server_thread_exception()}")

assert ok is True, f"Expected ok=True, got {ok}"
assert get_last_startup_error() is None
print("PASS\n")

print("=== Test 2: Already running case ===")
ok2, msg2 = start_reporting_server()
print(f"Result: ok={ok2}, msg={msg2}")
assert ok2 is True
print("PASS\n")

print("All tests PASSED!")
