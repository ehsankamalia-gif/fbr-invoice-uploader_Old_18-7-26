# Debug Session: api-autostart-failure
- **Status**: [OPEN]
- **Issue**: API server does not start automatically after Windows sign-in even though the Startup shortcut exists.
- **Debug Server**: http://127.0.0.1:7777/event
- **Log File**: .dbg/trae-debug-log-api-autostart-failure.ndjson

## Reproduction Steps
1. Sign in to Windows with auto-start enabled.
2. Wait for the normal startup window to pass.
3. Check whether `http://127.0.0.1:8000/docs` is reachable.
4. Review launcher logs and debug evidence for the startup chain.

## Hypotheses & Verification
| ID | Hypothesis | Likelihood | Effort | Evidence |
|----|------------|------------|--------|----------|
| A | Windows Startup launches the shortcut, but the hidden launcher never invokes PowerShell successfully. | Medium | Low | Pending |
| B | The PowerShell launcher runs, but Laragon/MySQL/Apache are not ready when FastAPI startup is attempted. | High | Low | Pending |
| C | The launcher starts FastAPI, but the process exits immediately during startup and never reaches a healthy `/docs` endpoint. | Medium | Medium | Pending |
| D | The startup sequence is running twice or colliding with another instance, causing the managed launcher to exit early. | Low | Low | Pending |
| E | Windows Startup timing or background restrictions are delaying or suppressing the hidden startup path beyond our current assumptions. | Medium | Medium | Pending |

## Log Evidence
- Pending

## Verification Conclusion
- Pending
