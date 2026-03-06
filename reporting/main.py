from datetime import datetime, timedelta
from io import BytesIO, StringIO
from typing import List, Optional

from fastapi import Depends, FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse, PlainTextResponse
from sqlalchemy.orm import Session
from sqlalchemy import desc, func

from app.db.session import SessionLocal
from app.db.models import Invoice


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app = FastAPI(title="FBR Reporting Portal MVP")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_recent_invoices(
    db: Session,
    limit: int = 100,
    start_dt: Optional[datetime] = None,
    end_dt: Optional[datetime] = None,
    sync_status: Optional[str] = None,
) -> List[Invoice]:
    query = db.query(Invoice)
    if start_dt:
        query = query.filter(Invoice.datetime >= start_dt)
    if end_dt:
        query = query.filter(Invoice.datetime <= end_dt)
    if sync_status and sync_status.upper() != "ALL":
        query = query.filter(Invoice.sync_status == sync_status.upper())
    return query.order_by(desc(Invoice.datetime)).limit(limit).all()


@app.get("/", response_class=HTMLResponse)
def read_root(
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
) -> str:
    default_start = datetime.utcnow() - timedelta(days=30)

    start_dt = None
    end_dt = None
    if from_date:
        try:
            start_dt = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            start_dt = None
    if to_date:
        try:
            end_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(
                seconds=1
            )
        except ValueError:
            end_dt = None

    if not start_dt and not end_dt:
        start_dt = default_start

    base_query = db.query(Invoice)
    if start_dt:
        base_query = base_query.filter(Invoice.datetime >= start_dt)
    if end_dt:
        base_query = base_query.filter(Invoice.datetime <= end_dt)
    if status and status.upper() != "ALL":
        base_query = base_query.filter(Invoice.sync_status == status.upper())

    total_invoices = db.query(Invoice).count()

    filtered_count = base_query.count()
    filtered_total_amount = (
        base_query.with_entities(func.coalesce(func.sum(Invoice.total_amount), 0.0)).scalar()
        or 0.0
    )

    invoices = (
        base_query.order_by(desc(Invoice.datetime))
        .limit(50)
        .all()
    )

    rows_html = ""
    for inv in invoices:
        date_str = inv.datetime.strftime("%Y-%m-%d %H:%M") if inv.datetime else ""
        pos_id = inv.pos_id or ""
        payment_mode = inv.payment_mode or ""
        rows_html += (
            f"<tr>"
            f"<td>{inv.invoice_number}</td>"
            f"<td>{date_str}</td>"
            f"<td>{pos_id}</td>"
            f"<td>{payment_mode}</td>"
            f"<td>{inv.total_amount:.2f}</td>"
            f"<td>{inv.sync_status}</td>"
            f"</tr>"
        )

    window_label_count = filtered_count
    status_value = (status or "ALL").upper()
    from_value = start_dt.strftime("%Y-%m-%d") if start_dt else ""
    to_value = ""
    if end_dt:
        to_value = (end_dt - timedelta(seconds=1)).strftime("%Y-%m-%d")

    html = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <title>FBR Reporting Portal</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                margin: 0;
                padding: 0;
                background-color: #f4f6f8;
            }}
            header {{
                background-color: #1976d2;
                color: white;
                padding: 16px 24px;
                font-size: 20px;
                font-weight: bold;
            }}
            .container {{
                padding: 24px;
            }}
            .kpi-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 16px;
            }}
            .kpi-card {{
                background-color: white;
                border-radius: 8px;
                padding: 16px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                flex: 1 1 220px;
            }}
            .kpi-title {{
                font-size: 14px;
                color: #666;
            }}
            .kpi-value {{
                font-size: 24px;
                font-weight: bold;
                margin-top: 4px;
            }}
            .filters {{
                margin-top: 24px;
                display: flex;
                flex-wrap: wrap;
                gap: 12px;
                align-items: flex-end;
            }}
            .filters label {{
                font-size: 12px;
                color: #555;
                display: block;
                margin-bottom: 4px;
            }}
            .filters input,
            .filters select {{
                padding: 6px 8px;
                border-radius: 4px;
                border: 1px solid #ccc;
                min-width: 150px;
                font-size: 13px;
            }}
            .filters button {{
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 7px 16px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 13px;
            }}
            .filters button:hover {{
                background-color: #145aa3;
            }}
            .summary-grid {{
                display: flex;
                flex-wrap: wrap;
                gap: 16px;
                margin-top: 24px;
            }}
            .summary-card {{
                background-color: white;
                border-radius: 8px;
                padding: 16px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                flex: 1 1 260px;
                font-size: 14px;
            }}
            .summary-card h3 {{
                margin: 0 0 8px 0;
                font-size: 15px;
            }}
            .summary-card table {{
                width: 100%;
                border-collapse: collapse;
            }}
            .summary-card th,
            .summary-card td {{
                padding: 4px 6px;
                border-bottom: 1px solid #eee;
                text-align: left;
                font-size: 13px;
            }}
            .summary-card th {{
                background-color: #fafafa;
            }}
            .table-wrapper {{
                margin-top: 32px;
                background-color: white;
                border-radius: 8px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1);
                padding: 16px;
                overflow-x: auto;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                font-size: 14px;
            }}
            th, td {{
                padding: 8px 10px;
                border-bottom: 1px solid #e0e0e0;
                text-align: left;
            }}
            th {{
                background-color: #fafafa;
                font-weight: 600;
            }}
            tr:hover {{
                background-color: #f5f5f5;
            }}
            .toolbar {{
                margin-top: 16px;
                display: flex;
                justify-content: flex-end;
            }}
            .btn {{
                background-color: #1976d2;
                color: white;
                border: none;
                padding: 8px 14px;
                border-radius: 4px;
                cursor: pointer;
                font-size: 13px;
            }}
            .btn:hover {{
                background-color: #145aa3;
            }}
            @media (max-width: 768px) {{
                .kpi-grid {{
                    flex-direction: column;
                }}
            }}
        </style>
    </head>
    <body>
        <header>FBR Reporting Portal - Dashboard (MVP)</header>
        <div class="container">
            <div class="kpi-grid" id="kpi-grid">
                <div class="kpi-card">
                    <div class="kpi-title">Total Invoices</div>
                    <div class="kpi-value">{total_invoices}</div>
                </div>
                <div class="kpi-card">
                    <div class="kpi-title">Invoices in current filter</div>
                    <div class="kpi-value">{window_label_count}</div>
                </div>
            </div>
            <form class="filters" method="get" action="/">
                <div>
                    <label for="from_date">From date</label>
                    <input type="date" id="from_date" name="from_date" value="{from_value}">
                </div>
                <div>
                    <label for="to_date">To date</label>
                    <input type="date" id="to_date" name="to_date" value="{to_value}">
                </div>
                <div>
                    <label for="status">Sync status</label>
                    <select id="status" name="status">
                        <option value="ALL" {"selected" if status_value == "ALL" else ""}>All</option>
                        <option value="PENDING" {"selected" if status_value == "PENDING" else ""}>Pending</option>
                        <option value="SUCCESS" {"selected" if status_value == "SUCCESS" else ""}>Success</option>
                        <option value="FAILED" {"selected" if status_value == "FAILED" else ""}>Failed</option>
                    </select>
                </div>
                <div>
                    <button type="submit">Apply filters</button>
                </div>
            </form>
            <div class="summary-grid">
                <div class="summary-card">
                    <h3>Amount summary</h3>
                    <table>
                        <tbody>
                            <tr>
                                <th style="width:60%;">Total amount in filter</th>
                                <td>{filtered_total_amount:.2f}</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
            <div class="table-wrapper">
                <div class="toolbar">
                    <a class="btn" href="/invoices.csv?from_date={from_value}&to_date={to_value}&status={status_value}">Download CSV</a>
                </div>
                <table>
                    <thead>
                        <tr>
                            <th>Invoice #</th>
                            <th>Date/Time</th>
                            <th>POS ID</th>
                            <th>Payment Mode</th>
                            <th>Total Amount</th>
                            <th>Sync Status</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows_html}
                    </tbody>
                </table>
            </div>
            <p style="margin-top:24px;color:#555;">
                This is the initial MVP dashboard and invoice snapshot. We will gradually add filters, charts and advanced exports here.
            </p>
        </div>
    </body>
    </html>
    """
    return html


@app.get("/invoices.csv")
def invoices_csv(
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
) -> StreamingResponse:
    start_dt = None
    end_dt = None
    if from_date:
        try:
            start_dt = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            start_dt = None
    if to_date:
        try:
            end_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(
                seconds=1
            )
        except ValueError:
            end_dt = None

    invoices = _get_recent_invoices(
        db,
        limit=1000,
        start_dt=start_dt,
        end_dt=end_dt,
        sync_status=status,
    )

    buffer = StringIO()
    buffer.write("invoice_number,datetime,total_amount,sync_status\n")
    for inv in invoices:
        date_str = inv.datetime.isoformat(sep=" ") if inv.datetime else ""
        buffer.write(
            f"{inv.invoice_number},{date_str},{inv.total_amount:.2f},{inv.sync_status}\n"
        )

    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=invoices.csv"},
    )
