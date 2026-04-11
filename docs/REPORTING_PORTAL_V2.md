# Reporting Portal v2

## Overview
The Reporting Portal v2 is a web-based reporting system running locally at `http://localhost:9000/` and started automatically by the desktop application. It replaces the legacy in-app reporting screens and provides:

- Interactive dashboards with live refresh
- Dynamic filtering (date range + FBR sync status)
- Drag-and-drop template builder
- Multi-format exports (PDF, Excel, CSV, PowerPoint)
- Scheduled report generation with optional email distribution
- Audit logging for reporting actions
- Optional access token gate and role enforcement (admin/manager for configuration actions)

## URLs
- Dashboard: `http://localhost:9000/dashboard`
- Template Builder: `http://localhost:9000/builder`
- Schedules: `http://localhost:9000/schedules`

Backward compatibility:
- Legacy CSV export: `http://localhost:9000/invoices.csv`
- Root URL redirects to dashboard: `http://localhost:9000/`

## Data Sources
The portal reads reporting data directly from the existing database through SQLAlchemy models:
- `Invoice`
- `InvoiceItem`

Reporting metadata is stored in new tables:
- `report_templates`
- `report_schedules`
- `report_runs`

## Metrics
The built-in metrics available to templates:
- `total_invoices`
- `total_amount`
- `avg_invoice_amount`
- `daily_sales` (time series)
- `status_breakdown` (distribution)
- `invoices` (recent rows, capped for performance)

## Template Builder
Templates define an ordered list of widgets:
```json
{
  "version": 1,
  "widgets": [
    { "type": "kpi", "metric": "total_invoices", "title": "Total Invoices" },
    { "type": "chart", "metric": "daily_sales", "title": "Daily Sales" }
  ]
}
```

Widget types:
- `kpi`: renders a KPI card
- `chart`: renders a Plotly chart (line for `daily_sales`, pie for `status_breakdown`)
- `table`: renders an invoices table

## Exports
Export routes:
- `/export/csv`
- `/export/xlsx`
- `/export/pdf`
- `/export/pptx`

Each export supports:
- `template_id` (required)
- `from_date` (optional, `YYYY-MM-DD`)
- `to_date` (optional, `YYYY-MM-DD`)
- `status` (optional: `ALL`, `PENDING`, `SUCCESS`, `FAILED`)

## Scheduling
Schedules are interval-based (minutes). When enabled, the server generates a report at the interval and can email it to recipients.

Stored fields:
- template, interval, format, recipients
- last run time
- run status + file path

Generated files are stored under:
- `exports/reports/`

## Email Distribution
Email sending is optional and controlled by environment variables:
- `REPORTING_SMTP_HOST`
- `REPORTING_SMTP_PORT` (default 587)
- `REPORTING_SMTP_USER`
- `REPORTING_SMTP_PASSWORD`
- `REPORTING_SMTP_FROM`
- `REPORTING_SMTP_TLS` (`1` or `0`, default `1`)

If SMTP variables are not configured, schedules still run and generate files but do not send emails.

## Security & RBAC
The portal supports an optional access token gate:
- `REPORTING_ACCESS_TOKEN`

If set, requests must include:
- Header `X-API-Key: <token>`

Role enforcement:
- Header `X-User-Role: admin|manager|sales`
- Admin/manager required for template write and schedule APIs.

## Audit Logging
Reporting actions create entries in `audit_logs`:
- Template create/update
- Schedule create/update
- Export actions (including legacy export)

## Operations
Disable scheduler thread (useful for tests):
- `REPORTING_DISABLE_SCHEDULER=1`

## Troubleshooting
- If the portal does not open, verify the desktop app started the local server on port 9000.
- If exports fail, ensure dependencies are installed:
  - `reportlab` (PDF)
  - `python-pptx` (PowerPoint)
  - `openpyxl` (Excel)

