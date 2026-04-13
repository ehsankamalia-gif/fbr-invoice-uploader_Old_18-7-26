# FBR Invoice Uploader - User Manual

## Introduction
This application allows Honda Dealerships to upload sales invoices to FBR's fiscalization system.

## Getting Started

### Installation
1. Ensure Python 3.10+ is installed.
2. Run `pip install -r requirements.txt`.
3. Configure `.env` file with your POS ID and USIN provided by FBR.

### Running the Application
Run the following command in the terminal:
```bash
python -m app.main
```

## Features

### Dashboard
The dashboard provides an overview of your fiscalization status:
- **Total Invoices**: Number of invoices created locally.
- **Synced**: Number of invoices successfully uploaded to FBR.
- **Pending**: Invoices waiting for upload.

### Creating an Invoice
1. Navigate to "New Invoice" tab.
2. Fill in the "Invoice & Customer Information" section.
3. Optional: enable **Preserve invoice and customer information** to keep buyer details for the next invoice after submission.
   - When enabled, buyer fields remain filled after successful submission, while product, pricing, and payment fields are cleared.
   - When disabled, the entire form is cleared after successful submission.
4. Enter product, payment, and chassis/engine details.
5. Click "Submit to FBR".

#### Reset Form
- Clicking **Reset Form** always clears every field in all sections and turns off the preserve option.

#### Address Uppercase
- The Address field automatically converts letters to uppercase while typing (numbers and special characters remain unchanged).

### Syncing
If an upload fails (e.g., no internet), the invoice stays in "Pending" state.
1. Click "Sync Now" on the sidebar.
2. The system will retry uploading all pending invoices.

## Troubleshooting
See `TROUBLESHOOTING.md` for common issues.
