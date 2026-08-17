# FBR Invoice Uploader for Honda Dealerships

A comprehensive software solution for Honda motorcycle dealerships to securely upload sales invoice data to the Federal Board of Revenue (FBR) system.

## Features
- **FBR Integration**: Seamless integration with FBR's official API.
- **Fiscalization**: Automatic generation of fiscalized invoices.
- **Sequential Upload**: Strict order processing with exponential backoff for failed uploads.
- **Offline Support**: Store data locally and sync when online.
- **Security**: Data encryption and secure authentication.
- **Audit Trail**: Comprehensive logging of all transactions.

## Setup
1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
2. Configure environment:
   Copy `.env.example` to `.env` and fill in your FBR credentials.
3. Run the application:
   ```bash
   python -m app.main
   ```

## Architecture
- **app/core**: Core functionality (config, logging, security).
- **app/api**: FBR API client and schemas.
- **app/db**: Database models and session management.
- **app/services**: Business logic (Invoice validation, sync, sequential processing).
- **app/ui**: Desktop User Interface.
