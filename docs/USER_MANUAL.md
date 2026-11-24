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

### Converting a Dealer to a Customer (and back)
Use this when a dealer should from now on be treated as an ordinary customer.

**Dealer → Customer**
1. Open **Dealers**, select the dealer.
2. Click **Convert to Customer** (or right-click the row and choose it).
3. Read the confirmation and click **Convert to Customer**.

**Customer → Dealer**
1. Open **Customers**, select the customer.
2. Click **Convert to Dealer**. If the record has no business name you will be asked for one.

What happens:
- The record is **not duplicated**: it keeps the same name, CNIC/NTN and contact details and simply moves to the other list.
- **Invoices already uploaded never change.** An invoice keeps the type (dealer or customer) it had when it was created, in every report and lookup.
- Only invoices created **after** the conversion are treated as the new type.
- Every conversion is recorded (who, when, from/to) in the conversion history.
- The Customers list has a **Type** column: *Dealer*, *Customer*, or *Customer (converted)* for former dealers.

Where to see the result:
- **Reporting → Lookup** has a **Party Type** column per invoice, so a converted party's full history shows its older dealer invoices and newer customer invoices side by side.
- The **Reporting dashboard** has a *Dealer vs Customer Invoices* chart that counts each invoice by its own type.

Notes:
- A converted party cannot be turned back into a dealer by simply selecting "dealer" on the invoice form; use **Convert to Dealer**.
- Take a database backup before updating the application the first time: the update adds the columns this feature needs.

## Troubleshooting
See `TROUBLESHOOTING.md` for common issues.
