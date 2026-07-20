@echo off
title FBR Invoice Uploader API Server
echo Starting FastAPI Server...
echo.
echo API will be available at:
echo   - API Documentation: http://localhost:8000/docs
echo   - API Endpoints: http://localhost:8000
echo.
echo Press Ctrl+C to stop the server
echo.

call venv\Scripts\activate.bat
python -m uvicorn app.api.server:app --host 0.0.0.0 --port 8000 --reload
