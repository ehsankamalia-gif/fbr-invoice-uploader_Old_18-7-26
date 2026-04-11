import os
import json
import time
import threading
import smtplib
from email.message import EmailMessage
from datetime import datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from sqlalchemy import desc, func
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.db.models import Invoice, ReportTemplate, ReportSchedule, ReportRun, AuditLog
from app.services.invoice_service import invoice_service


def get_db() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _reporting_root_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "exports" / "reports"


def _get_role(role_header: Optional[str]) -> str:
    role = (role_header or "").strip().lower()
    return role or "sales"


def _require_auth(
    api_key: Optional[str],
    role: str,
    required_roles: Optional[List[str]] = None,
) -> None:
    configured_key = (os.getenv("REPORTING_ACCESS_TOKEN") or "").strip()
    if configured_key and (api_key or "").strip() != configured_key:
        raise HTTPException(status_code=401, detail="Unauthorized")
    if required_roles and role not in [r.lower() for r in required_roles]:
        raise HTTPException(status_code=403, detail="Forbidden")


def _audit(
    db: Session,
    *,
    action: str,
    resource_type: str,
    resource_id: int,
    details: Dict[str, Any],
    request: Optional[Request] = None,
) -> None:
    ip = None
    if request:
        ip = request.client.host if request.client else None
    db.add(
        AuditLog(
            user_id=None,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip,
        )
    )
    db.commit()


app = FastAPI(title="FBR Reporting Portal v2")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_retry_lock = threading.Lock()
_last_retry_at: Dict[str, float] = {}


DEFAULT_TEMPLATE = {
    "version": 1,
    "widgets": [
        {"type": "kpi", "metric": "total_invoices", "title": "Total Invoices"},
        {"type": "kpi", "metric": "total_amount", "title": "Total Amount"},
        {"type": "kpi", "metric": "avg_invoice_amount", "title": "Avg Invoice"},
        {"type": "chart", "metric": "daily_sales", "title": "Daily Sales"},
        {"type": "chart", "metric": "status_breakdown", "title": "Status Breakdown"},
        {"type": "table", "metric": "invoices", "title": "Invoices"},
    ],
}


def _parse_dates(from_date: Optional[str], to_date: Optional[str]) -> Tuple[Optional[datetime], Optional[datetime]]:
    start_dt = None
    end_dt = None
    if from_date:
        try:
            start_dt = datetime.strptime(from_date, "%Y-%m-%d")
        except ValueError:
            start_dt = None
    if to_date:
        try:
            end_dt = datetime.strptime(to_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)
        except ValueError:
            end_dt = None
    return start_dt, end_dt


def _invoice_query(db: Session, start_dt: Optional[datetime], end_dt: Optional[datetime], status: str) -> Any:
    q = db.query(Invoice)
    if start_dt:
        q = q.filter(Invoice.datetime >= start_dt)
    if end_dt:
        q = q.filter(Invoice.datetime <= end_dt)
    st = (status or "ALL").upper()
    if st != "ALL":
        q = q.filter(Invoice.sync_status == st)
    return q


def _compute_metrics(db: Session, start_dt: Optional[datetime], end_dt: Optional[datetime], status: str) -> Dict[str, Any]:
    q = _invoice_query(db, start_dt, end_dt, status)
    total_invoices = q.count()
    total_amount = q.with_entities(func.coalesce(func.sum(Invoice.total_amount), 0.0)).scalar() or 0.0
    avg_invoice_amount = float(total_amount) / float(total_invoices) if total_invoices else 0.0

    daily_rows = (
        q.with_entities(func.date(Invoice.datetime), func.coalesce(func.sum(Invoice.total_amount), 0.0))
        .group_by(func.date(Invoice.datetime))
        .order_by(func.date(Invoice.datetime))
        .all()
    )
    daily_sales = [{"date": str(d), "amount": float(a or 0.0)} for d, a in daily_rows]

    status_rows = (
        q.with_entities(Invoice.sync_status, func.count(Invoice.id))
        .group_by(Invoice.sync_status)
        .order_by(Invoice.sync_status)
        .all()
    )
    status_breakdown = [{"status": str(s or ""), "count": int(c or 0)} for s, c in status_rows]

    invoices = (
        q.order_by(desc(Invoice.datetime))
        .limit(200)
        .all()
    )
    invoice_rows = []
    for inv in invoices:
        invoice_rows.append(
            {
                "invoice_number": inv.invoice_number,
                "datetime": inv.datetime.isoformat(sep=" ") if inv.datetime else "",
                "pos_id": inv.pos_id or "",
                "payment_mode": inv.payment_mode or "",
                "total_amount": float(inv.total_amount or 0),
                "sync_status": inv.sync_status,
            }
        )

    return {
        "total_invoices": int(total_invoices),
        "total_amount": float(total_amount),
        "avg_invoice_amount": float(avg_invoice_amount),
        "daily_sales": daily_sales,
        "status_breakdown": status_breakdown,
        "invoices": invoice_rows,
    }


def _load_or_create_default_template(db: Session) -> ReportTemplate:
    tmpl = db.query(ReportTemplate).filter(ReportTemplate.name == "Default Dashboard").first()
    if tmpl:
        return tmpl
    tmpl = ReportTemplate(name="Default Dashboard", description="Default reporting dashboard", definition=DEFAULT_TEMPLATE, is_active=True)
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    return tmpl


def _render_dashboard_html() -> str:
    return """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>Reporting Portal</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
      <script src="https://cdn.jsdelivr.net/npm/plotly.js-dist@2.32.0/plotly.min.js"></script>
      <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js"></script>
    </head>
    <body class="bg-light">
      <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container-fluid">
          <span class="navbar-brand">Reporting Portal</span>
          <div class="d-flex gap-2">
            <a class="btn btn-outline-light btn-sm" href="/builder">Template Builder</a>
            <a class="btn btn-outline-light btn-sm" href="/schedules">Schedules</a>
          </div>
        </div>
      </nav>
      <main class="container-fluid py-3">
        <div class="row g-3">
          <div class="col-12">
            <div class="card">
              <div class="card-body">
                <div class="row g-2 align-items-end">
                  <div class="col-12 col-md-3">
                    <label class="form-label">Template</label>
                    <select class="form-select" id="templateSelect"></select>
                  </div>
                  <div class="col-6 col-md-2">
                    <label class="form-label">From</label>
                    <input class="form-control" type="date" id="fromDate"/>
                  </div>
                  <div class="col-6 col-md-2">
                    <label class="form-label">To</label>
                    <input class="form-control" type="date" id="toDate"/>
                  </div>
                  <div class="col-12 col-md-2">
                    <label class="form-label">Status</label>
                    <select class="form-select" id="status">
                      <option value="ALL">All</option>
                      <option value="PENDING">Pending</option>
                      <option value="SUCCESS">Success</option>
                      <option value="FAILED">Failed</option>
                    </select>
                  </div>
                  <div class="col-12 col-md-3 d-flex gap-2">
                    <button class="btn btn-primary flex-grow-1" id="applyBtn">Apply</button>
                    <button class="btn btn-outline-secondary" id="autoBtn">Auto</button>
                  </div>
                </div>
                <div class="mt-3 d-flex flex-wrap gap-2">
                  <button class="btn btn-outline-primary btn-sm" id="exportCsv">CSV</button>
                  <button class="btn btn-outline-primary btn-sm" id="exportXlsx">Excel</button>
                  <button class="btn btn-outline-primary btn-sm" id="exportPdf">PDF</button>
                  <button class="btn btn-outline-primary btn-sm" id="exportPptx">PowerPoint</button>
                </div>
              </div>
            </div>
          </div>
          <div class="col-12">
            <div id="widgets" class="row g-3"></div>
          </div>
        </div>
      </main>
      <script>
        const state = { auto: true, timer: null, templateId: null, role: 'sales', token: '' };
        function qs() {
          const p = new URLSearchParams(window.location.search);
          return {
            from_date: p.get('from_date') || '',
            to_date: p.get('to_date') || '',
            status: p.get('status') || 'ALL',
            template_id: p.get('template_id') || ''
          };
        }
        function headers() {
          const h = { 'Content-Type': 'application/json' };
          if (state.role) h['X-User-Role'] = state.role;
          if (state.token) h['X-API-Key'] = state.token;
          return h;
        }
        async function loadTemplates() {
          const res = await fetch('/api/templates', { headers: headers() });
          const data = await res.json();
          const sel = document.getElementById('templateSelect');
          sel.innerHTML = '';
          data.items.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            sel.appendChild(opt);
          });
          const q = qs();
          if (q.template_id) sel.value = q.template_id;
          state.templateId = sel.value;
        }
        function renderKpi(title, value) {
          const col = document.createElement('div');
          col.className = 'col-12 col-md-3';
          col.innerHTML = `<div class="card"><div class="card-body"><div class="text-muted small">${title}</div><div class="fs-4 fw-bold">${value}</div></div></div>`;
          return col;
        }
        function renderTable(title, rows) {
          const col = document.createElement('div');
          col.className = 'col-12';
          const head = `<thead><tr><th>Invoice</th><th>Date</th><th>POS</th><th>Mode</th><th>Total</th><th>Status</th><th style="width: 110px;">Action</th></tr></thead>`;
          const body = rows.map(r => {
            const inv = r.invoice_number;
            const statusTd = `<td data-status-for="${inv}">${r.sync_status}</td>`;
            const canRetry = (r.sync_status || '').toUpperCase() === 'PENDING';
            const btn = canRetry
              ? `<button type="button" class="btn btn-sm btn-outline-primary retry-btn" data-invoice="${inv}">Retry</button>`
              : `<span class="text-muted small">—</span>`;
            return `<tr data-invoice-row="${inv}"><td>${inv}</td><td>${r.datetime}</td><td>${r.pos_id}</td><td>${r.payment_mode}</td><td>${r.total_amount.toFixed(2)}</td>${statusTd}<td>${btn}</td></tr>`;
          }).join('');
          col.innerHTML = `<div class="card"><div class="card-header fw-bold">${title}</div><div class="card-body p-0"><div class="table-responsive"><table class="table table-sm mb-0">${head}<tbody>${body}</tbody></table></div></div></div>`;
          return col;
        }
        function renderChart(title, dailySales) {
          const col = document.createElement('div');
          col.className = 'col-12';
          const id = 'chart_' + Math.random().toString(36).slice(2);
          col.innerHTML = `<div class="card"><div class="card-header fw-bold">${title}</div><div class="card-body"><div id="${id}" style="height: 320px;"></div></div></div>`;
          setTimeout(() => {
            if (Array.isArray(dailySales) && dailySales.length && dailySales[0].date !== undefined) {
              const x = dailySales.map(d => d.date);
              const y = dailySales.map(d => d.amount);
              Plotly.newPlot(id, [{ x, y, type: 'scatter', mode: 'lines+markers' }], { margin: { t: 10, r: 10, l: 40, b: 40 } }, { displayModeBar: false, responsive: true });
              return;
            }
            if (Array.isArray(dailySales) && dailySales.length && dailySales[0].status !== undefined) {
              const labels = dailySales.map(d => d.status || 'UNKNOWN');
              const values = dailySales.map(d => d.count || 0);
              Plotly.newPlot(id, [{ labels, values, type: 'pie' }], { margin: { t: 10, r: 10, l: 10, b: 10 } }, { displayModeBar: false, responsive: true });
              return;
            }
            Plotly.newPlot(id, [], { margin: { t: 10, r: 10, l: 10, b: 10 } }, { displayModeBar: false, responsive: true });
          }, 0);
          return col;
        }
        async function loadDashboard() {
          const sel = document.getElementById('templateSelect');
          state.templateId = sel.value;
          const from_date = document.getElementById('fromDate').value;
          const to_date = document.getElementById('toDate').value;
          const status = document.getElementById('status').value;
          const url = `/api/dashboard?template_id=${encodeURIComponent(state.templateId)}&from_date=${encodeURIComponent(from_date)}&to_date=${encodeURIComponent(to_date)}&status=${encodeURIComponent(status)}`;
          const res = await fetch(url, { headers: headers() });
          const data = await res.json();
          const w = document.getElementById('widgets');
          w.innerHTML = '';
          data.widgets.forEach(widget => {
            if (widget.type === 'kpi') w.appendChild(renderKpi(widget.title, widget.value));
            if (widget.type === 'chart') w.appendChild(renderChart(widget.title, widget.value));
            if (widget.type === 'table') w.appendChild(renderTable(widget.title, widget.value));
          });
        }
        function toast(message, kind) {
          const id = 'toast_' + Math.random().toString(36).slice(2);
          const bg = kind === 'success' ? 'text-bg-success' : (kind === 'error' ? 'text-bg-danger' : 'text-bg-secondary');
          const el = document.createElement('div');
          el.innerHTML = `
            <div class="toast-container position-fixed bottom-0 end-0 p-3">
              <div id="${id}" class="toast align-items-center ${bg} border-0" role="alert" aria-live="assertive" aria-atomic="true">
                <div class="d-flex">
                  <div class="toast-body">${message}</div>
                  <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
                </div>
              </div>
            </div>`;
          document.body.appendChild(el);
          const toastEl = document.getElementById(id);
          const t = new bootstrap.Toast(toastEl, { delay: 4500 });
          t.show();
          toastEl.addEventListener('hidden.bs.toast', () => el.remove());
        }
        async function retryInvoice(invoiceNumber, buttonEl) {
          if (!invoiceNumber || !buttonEl) return;
          const now = Date.now();
          const last = parseInt(buttonEl.getAttribute('data-last-click') || '0', 10);
          if (now - last < 15000) {
            toast('Please wait before retrying again.', 'info');
            return;
          }
          buttonEl.setAttribute('data-last-click', String(now));
          const originalHtml = buttonEl.innerHTML;
          buttonEl.disabled = true;
          buttonEl.innerHTML = `<span class="spinner-border spinner-border-sm me-1" role="status" aria-hidden="true"></span>Retrying`;
          const statusCell = document.querySelector(`td[data-status-for="${invoiceNumber}"]`);
          if (statusCell) statusCell.textContent = 'RETRYING';
          try {
            const res = await fetch(`/api/invoices/${encodeURIComponent(invoiceNumber)}/retry`, { method: 'POST', headers: headers() });
            const data = await res.json();
            if (!res.ok) {
              const msg = data && (data.detail || data.message) ? (data.detail || data.message) : 'Retry failed.';
              toast(msg, 'error');
              if (statusCell) statusCell.textContent = 'PENDING';
              buttonEl.disabled = false;
              buttonEl.innerHTML = originalHtml;
              return;
            }
            const newStatus = (data && data.sync_status) ? data.sync_status : 'PENDING';
            if (statusCell) statusCell.textContent = newStatus;
            if (newStatus.toUpperCase() === 'SYNCED') {
              toast(`Invoice ${invoiceNumber} uploaded successfully.`, 'success');
              buttonEl.outerHTML = `<span class="text-muted small">—</span>`;
            } else if (newStatus.toUpperCase() === 'FAILED') {
              toast(data && data.message ? data.message : `Invoice ${invoiceNumber} failed.`, 'error');
              buttonEl.disabled = false;
              buttonEl.innerHTML = originalHtml;
            } else {
              toast(data && data.message ? data.message : `Invoice ${invoiceNumber} is still pending.`, 'info');
              buttonEl.disabled = false;
              buttonEl.innerHTML = originalHtml;
            }
          } catch (e) {
            toast(`Network error: ${e}`, 'error');
            if (statusCell) statusCell.textContent = 'PENDING';
            buttonEl.disabled = false;
            buttonEl.innerHTML = originalHtml;
          }
        }
        function setAuto(on) {
          state.auto = on;
          const btn = document.getElementById('autoBtn');
          btn.textContent = on ? 'Auto' : 'Manual';
          if (state.timer) clearInterval(state.timer);
          if (on) state.timer = setInterval(loadDashboard, 15000);
        }
        function exportFmt(fmt) {
          const from_date = document.getElementById('fromDate').value;
          const to_date = document.getElementById('toDate').value;
          const status = document.getElementById('status').value;
          const url = `/export/${fmt}?template_id=${encodeURIComponent(state.templateId)}&from_date=${encodeURIComponent(from_date)}&to_date=${encodeURIComponent(to_date)}&status=${encodeURIComponent(status)}`;
          window.location.href = url;
        }
        async function init() {
          const q = qs();
          document.getElementById('fromDate').value = q.from_date;
          document.getElementById('toDate').value = q.to_date;
          document.getElementById('status').value = q.status;
          await loadTemplates();
          document.getElementById('applyBtn').addEventListener('click', loadDashboard);
          document.getElementById('autoBtn').addEventListener('click', () => setAuto(!state.auto));
          document.getElementById('templateSelect').addEventListener('change', loadDashboard);
          document.getElementById('exportCsv').addEventListener('click', () => exportFmt('csv'));
          document.getElementById('exportXlsx').addEventListener('click', () => exportFmt('xlsx'));
          document.getElementById('exportPdf').addEventListener('click', () => exportFmt('pdf'));
          document.getElementById('exportPptx').addEventListener('click', () => exportFmt('pptx'));
          document.addEventListener('click', (ev) => {
            const t = ev.target;
            if (!t || !t.classList) return;
            if (t.classList.contains('retry-btn')) {
              ev.preventDefault();
              retryInvoice(t.getAttribute('data-invoice'), t);
            }
          });
          setAuto(true);
          await loadDashboard();
        }
        init();
      </script>
    </body>
    </html>
    """


def _render_builder_html() -> str:
    return """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>Template Builder</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
      <script src="https://cdn.jsdelivr.net/npm/sortablejs@1.15.2/Sortable.min.js"></script>
    </head>
    <body class="bg-light">
      <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container-fluid">
          <a class="navbar-brand" href="/dashboard">Reporting Portal</a>
        </div>
      </nav>
      <main class="container py-3">
        <div class="row g-3">
          <div class="col-12 col-lg-4">
            <div class="card">
              <div class="card-header fw-bold">Templates</div>
              <div class="card-body">
                <div class="mb-2">
                  <label class="form-label">Select</label>
                  <select class="form-select" id="templateSelect"></select>
                </div>
                <div class="mb-2">
                  <label class="form-label">Name</label>
                  <input class="form-control" id="name"/>
                </div>
                <div class="mb-2">
                  <label class="form-label">Description</label>
                  <input class="form-control" id="description"/>
                </div>
                <div class="d-flex gap-2">
                  <button class="btn btn-primary" id="saveBtn">Save</button>
                  <button class="btn btn-outline-secondary" id="newBtn">New</button>
                </div>
              </div>
            </div>
            <div class="card mt-3">
              <div class="card-header fw-bold">Available Widgets</div>
              <div class="card-body">
                <div class="list-group" id="palette">
                  <div class="list-group-item" data-type="kpi" data-metric="total_invoices" data-title="Total Invoices">KPI: Total Invoices</div>
                  <div class="list-group-item" data-type="kpi" data-metric="total_amount" data-title="Total Amount">KPI: Total Amount</div>
                  <div class="list-group-item" data-type="kpi" data-metric="avg_invoice_amount" data-title="Avg Invoice">KPI: Avg Invoice</div>
                  <div class="list-group-item" data-type="chart" data-metric="daily_sales" data-title="Daily Sales">Chart: Daily Sales</div>
                  <div class="list-group-item" data-type="chart" data-metric="status_breakdown" data-title="Status Breakdown">Chart: Status Breakdown</div>
                  <div class="list-group-item" data-type="table" data-metric="invoices" data-title="Invoices">Table: Invoices</div>
                </div>
                <div class="text-muted small mt-2">Drag widgets into the layout.</div>
              </div>
            </div>
          </div>
          <div class="col-12 col-lg-8">
            <div class="card">
              <div class="card-header fw-bold">Layout</div>
              <div class="card-body">
                <div class="list-group" id="layout"></div>
              </div>
            </div>
          </div>
        </div>
      </main>
      <script>
        const state = { templateId: null, token: '', role: 'admin' };
        function headers() {
          const h = { 'Content-Type': 'application/json', 'X-User-Role': state.role };
          if (state.token) h['X-API-Key'] = state.token;
          return h;
        }
        function layoutItem(widget) {
          const el = document.createElement('div');
          el.className = 'list-group-item d-flex justify-content-between align-items-center';
          el.dataset.type = widget.type;
          el.dataset.metric = widget.metric;
          el.dataset.title = widget.title;
          el.innerHTML = `<div><div class="fw-bold">${widget.title}</div><div class="text-muted small">${widget.type} / ${widget.metric}</div></div><button class="btn btn-sm btn-outline-danger">Remove</button>`;
          el.querySelector('button').addEventListener('click', () => el.remove());
          return el;
        }
        function readLayout() {
          const items = [];
          document.querySelectorAll('#layout .list-group-item').forEach(el => {
            items.push({ type: el.dataset.type, metric: el.dataset.metric, title: el.dataset.title });
          });
          return items;
        }
        async function loadTemplates() {
          const res = await fetch('/api/templates', { headers: headers() });
          const data = await res.json();
          const sel = document.getElementById('templateSelect');
          sel.innerHTML = '';
          data.items.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            sel.appendChild(opt);
          });
          state.templateId = sel.value;
          await loadTemplate();
        }
        async function loadTemplate() {
          const id = document.getElementById('templateSelect').value;
          state.templateId = id;
          const res = await fetch(`/api/templates/${id}`, { headers: headers() });
          const t = await res.json();
          document.getElementById('name').value = t.name;
          document.getElementById('description').value = t.description || '';
          const layout = document.getElementById('layout');
          layout.innerHTML = '';
          (t.definition.widgets || []).forEach(w => layout.appendChild(layoutItem(w)));
        }
        async function saveTemplate() {
          const id = state.templateId;
          const payload = {
            name: document.getElementById('name').value.trim(),
            description: document.getElementById('description').value.trim(),
            definition: { version: 1, widgets: readLayout() }
          };
          if (!payload.name) return;
          const res = await fetch(`/api/templates/${id}`, { method: 'PUT', headers: headers(), body: JSON.stringify(payload) });
          if (!res.ok) return;
          await loadTemplates();
        }
        async function newTemplate() {
          const payload = { name: `Template ${Date.now()}`, description: '', definition: { version: 1, widgets: [] } };
          const res = await fetch('/api/templates', { method: 'POST', headers: headers(), body: JSON.stringify(payload) });
          if (!res.ok) return;
          await loadTemplates();
        }
        new Sortable(document.getElementById('palette'), { group: { name: 'shared', pull: 'clone', put: false }, sort: false });
        new Sortable(document.getElementById('layout'), { group: { name: 'shared', pull: true, put: true }, animation: 150,
          onAdd: (evt) => {
            const el = evt.item;
            const widget = { type: el.dataset.type, metric: el.dataset.metric, title: el.dataset.title };
            evt.item.replaceWith(layoutItem(widget));
          }
        });
        document.getElementById('templateSelect').addEventListener('change', loadTemplate);
        document.getElementById('saveBtn').addEventListener('click', saveTemplate);
        document.getElementById('newBtn').addEventListener('click', newTemplate);
        loadTemplates();
      </script>
    </body>
    </html>
    """


def _render_schedules_html() -> str:
    return """
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width, initial-scale=1"/>
      <title>Report Schedules</title>
      <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet"/>
    </head>
    <body class="bg-light">
      <nav class="navbar navbar-expand-lg navbar-dark bg-primary">
        <div class="container-fluid">
          <a class="navbar-brand" href="/dashboard">Reporting Portal</a>
        </div>
      </nav>
      <main class="container py-3">
        <div class="card">
          <div class="card-header fw-bold">Scheduled Reports</div>
          <div class="card-body">
            <div class="row g-2 align-items-end">
              <div class="col-12 col-md-4">
                <label class="form-label">Template</label>
                <select class="form-select" id="templateSelect"></select>
              </div>
              <div class="col-6 col-md-2">
                <label class="form-label">Interval (min)</label>
                <input class="form-control" type="number" id="interval" value="60"/>
              </div>
              <div class="col-6 col-md-2">
                <label class="form-label">Format</label>
                <select class="form-select" id="format">
                  <option value="pdf">PDF</option>
                  <option value="xlsx">Excel</option>
                  <option value="csv">CSV</option>
                  <option value="pptx">PowerPoint</option>
                </select>
              </div>
              <div class="col-12 col-md-4">
                <label class="form-label">Recipients (comma)</label>
                <input class="form-control" id="recipients" placeholder="a@b.com,c@d.com"/>
              </div>
              <div class="col-12">
                <button class="btn btn-primary" id="createBtn">Create Schedule</button>
              </div>
            </div>
            <hr/>
            <div class="table-responsive">
              <table class="table table-sm" id="tbl">
                <thead><tr><th>ID</th><th>Template</th><th>Interval</th><th>Format</th><th>Enabled</th><th>Last Run</th><th></th></tr></thead>
                <tbody></tbody>
              </table>
            </div>
          </div>
        </div>
      </main>
      <script>
        const state = { role: 'admin', token: '' };
        function headers() {
          const h = { 'Content-Type': 'application/json', 'X-User-Role': state.role };
          if (state.token) h['X-API-Key'] = state.token;
          return h;
        }
        async function loadTemplates() {
          const res = await fetch('/api/templates', { headers: headers() });
          const data = await res.json();
          const sel = document.getElementById('templateSelect');
          sel.innerHTML = '';
          data.items.forEach(t => {
            const opt = document.createElement('option');
            opt.value = t.id;
            opt.textContent = t.name;
            sel.appendChild(opt);
          });
        }
        async function loadSchedules() {
          const res = await fetch('/api/schedules', { headers: headers() });
          const data = await res.json();
          const body = document.querySelector('#tbl tbody');
          body.innerHTML = '';
          data.items.forEach(s => {
            const tr = document.createElement('tr');
            tr.innerHTML = `<td>${s.id}</td><td>${s.template_name}</td><td>${s.interval_minutes}</td><td>${s.export_format}</td><td>${s.enabled}</td><td>${s.last_run_at || ''}</td>
              <td><button class="btn btn-sm btn-outline-secondary">Toggle</button></td>`;
            tr.querySelector('button').addEventListener('click', async () => {
              await fetch(`/api/schedules/${s.id}`, { method:'PUT', headers: headers(), body: JSON.stringify({ enabled: !s.enabled }) });
              await loadSchedules();
            });
            body.appendChild(tr);
          });
        }
        async function createSchedule() {
          const payload = {
            template_id: parseInt(document.getElementById('templateSelect').value, 10),
            interval_minutes: parseInt(document.getElementById('interval').value, 10),
            export_format: document.getElementById('format').value,
            recipients: document.getElementById('recipients').value.split(',').map(x => x.trim()).filter(Boolean),
            enabled: true
          };
          await fetch('/api/schedules', { method:'POST', headers: headers(), body: JSON.stringify(payload) });
          await loadSchedules();
        }
        document.getElementById('createBtn').addEventListener('click', createSchedule);
        loadTemplates().then(loadSchedules);
      </script>
    </body>
    </html>
    """


@app.on_event("startup")
def _startup() -> None:
    if (os.getenv("REPORTING_DISABLE_SCHEDULER") or "").strip() == "1":
        return

    root = _reporting_root_dir()
    root.mkdir(parents=True, exist_ok=True)

    def loop() -> None:
        while True:
            try:
                _run_due_schedules()
            except Exception:
                pass
            time.sleep(30)

    threading.Thread(target=loop, daemon=True, name="ReportingScheduler").start()


def _run_due_schedules() -> None:
    db = SessionLocal()
    try:
        _load_or_create_default_template(db)
        schedules = db.query(ReportSchedule).filter(ReportSchedule.enabled.is_(True)).all()
        now = datetime.utcnow()
        for sch in schedules:
            last = sch.last_run_at
            interval = int(sch.interval_minutes or 60)
            due = (not last) or ((now - last).total_seconds() >= interval * 60)
            if not due:
                continue
            sch.last_run_at = now
            db.add(sch)
            db.commit()
            _execute_schedule(db, sch)
    finally:
        db.close()


def _smtp_config() -> Dict[str, Any]:
    return {
        "host": os.getenv("REPORTING_SMTP_HOST", ""),
        "port": int(os.getenv("REPORTING_SMTP_PORT", "587") or "587"),
        "user": os.getenv("REPORTING_SMTP_USER", ""),
        "password": os.getenv("REPORTING_SMTP_PASSWORD", ""),
        "from": os.getenv("REPORTING_SMTP_FROM", ""),
        "use_tls": (os.getenv("REPORTING_SMTP_TLS", "1") or "1") == "1",
    }


def _send_email(to_list: List[str], subject: str, body: str, attachment_name: str, attachment_bytes: bytes) -> None:
    cfg = _smtp_config()
    if not cfg["host"] or not cfg["from"] or not to_list:
        return

    msg = EmailMessage()
    msg["From"] = cfg["from"]
    msg["To"] = ", ".join(to_list)
    msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(attachment_bytes, maintype="application", subtype="octet-stream", filename=attachment_name)

    if cfg["use_tls"]:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            s.starttls()
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
    else:
        with smtplib.SMTP(cfg["host"], cfg["port"]) as s:
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)


def _execute_schedule(db: Session, sch: ReportSchedule) -> None:
    run = ReportRun(schedule_id=sch.id, status="STARTED")
    db.add(run)
    db.commit()
    db.refresh(run)

    try:
        tmpl = db.query(ReportTemplate).filter(ReportTemplate.id == sch.template_id).first()
        if not tmpl:
            raise RuntimeError("Template not found")

        metrics = _compute_metrics(db, None, None, "ALL")
        file_bytes, name, media_type = _export_bytes(tmpl, metrics, sch.export_format)

        root = _reporting_root_dir()
        root.mkdir(parents=True, exist_ok=True)
        file_path = root / f"schedule_{sch.id}_run_{run.id}_{name}"
        file_path.write_bytes(file_bytes)

        run.status = "SUCCESS"
        run.finished_at = datetime.utcnow()
        run.file_path = str(file_path)
        db.add(run)
        db.commit()

        recipients = sch.recipients or []
        if isinstance(recipients, list) and recipients:
            _send_email(
                [str(x) for x in recipients],
                subject=f"Scheduled Report: {tmpl.name}",
                body=f"Scheduled report generated at {datetime.utcnow().isoformat(sep=' ')}",
                attachment_name=name,
                attachment_bytes=file_bytes,
            )

    except Exception as e:
        run.status = "FAILED"
        run.finished_at = datetime.utcnow()
        run.error_message = str(e)
        db.add(run)
        db.commit()


def _export_csv(metrics: Dict[str, Any]) -> bytes:
    buffer = StringIO()
    buffer.write("invoice_number,datetime,pos_id,payment_mode,total_amount,sync_status\n")
    for r in metrics.get("invoices", []):
        buffer.write(
            f"{r['invoice_number']},{r['datetime']},{r['pos_id']},{r['payment_mode']},{float(r['total_amount']):.2f},{r['sync_status']}\n"
        )
    return buffer.getvalue().encode("utf-8")


def _export_xlsx(metrics: Dict[str, Any]) -> bytes:
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.title = "Invoices"
    ws.append(["Invoice #", "DateTime", "POS ID", "Payment Mode", "Total Amount", "Sync Status"])
    for r in metrics.get("invoices", []):
        ws.append([r["invoice_number"], r["datetime"], r["pos_id"], r["payment_mode"], float(r["total_amount"]), r["sync_status"]])
    bio = BytesIO()
    wb.save(bio)
    return bio.getvalue()


def _export_pdf(template: ReportTemplate, metrics: Dict[str, Any]) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    bio = BytesIO()
    c = canvas.Canvas(bio, pagesize=A4)
    width, height = A4
    y = height - 40
    c.setFont("Helvetica-Bold", 14)
    c.drawString(40, y, f"Report: {template.name}")
    y -= 24
    c.setFont("Helvetica", 10)
    c.drawString(40, y, f"Generated: {datetime.utcnow().isoformat(sep=' ')}")
    y -= 24
    c.setFont("Helvetica", 11)
    c.drawString(40, y, f"Total Invoices: {metrics.get('total_invoices', 0)}")
    y -= 18
    c.drawString(40, y, f"Total Amount: {float(metrics.get('total_amount', 0.0)):.2f}")
    y -= 30
    c.setFont("Helvetica-Bold", 11)
    c.drawString(40, y, "Recent Invoices")
    y -= 18
    c.setFont("Helvetica", 9)
    for r in metrics.get("invoices", [])[:25]:
        c.drawString(40, y, f"{r['invoice_number']} | {r['datetime']} | {r['total_amount']:.2f} | {r['sync_status']}")
        y -= 12
        if y < 60:
            c.showPage()
            y = height - 40
            c.setFont("Helvetica", 9)
    c.showPage()
    c.save()
    return bio.getvalue()


def _export_pptx(template: ReportTemplate, metrics: Dict[str, Any]) -> bytes:
    from pptx import Presentation
    from pptx.util import Inches

    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    title_shape = slide.shapes.title
    if title_shape:
        title_shape.text = f"{template.name}"
    tx = slide.shapes.add_textbox(Inches(0.8), Inches(1.6), Inches(8.5), Inches(2.0))
    tf = tx.text_frame
    tf.text = f"Generated: {datetime.utcnow().isoformat(sep=' ')}"
    p = tf.add_paragraph()
    p.text = f"Total Invoices: {metrics.get('total_invoices', 0)}"
    p = tf.add_paragraph()
    p.text = f"Total Amount: {float(metrics.get('total_amount', 0.0)):.2f}"

    slide2 = prs.slides.add_slide(prs.slide_layouts[5])
    title2 = slide2.shapes.title
    if title2:
        title2.text = "Recent Invoices"
    box = slide2.shapes.add_textbox(Inches(0.8), Inches(1.4), Inches(8.5), Inches(5.0))
    tf2 = box.text_frame
    tf2.word_wrap = True
    for r in metrics.get("invoices", [])[:15]:
        p = tf2.add_paragraph()
        p.text = f"{r['invoice_number']} | {r['datetime']} | {r['total_amount']:.2f} | {r['sync_status']}"

    bio = BytesIO()
    prs.save(bio)
    return bio.getvalue()


def _export_bytes(template: ReportTemplate, metrics: Dict[str, Any], fmt: str) -> Tuple[bytes, str, str]:
    fmt = (fmt or "").lower()
    if fmt == "csv":
        return _export_csv(metrics), "report.csv", "text/csv"
    if fmt == "xlsx":
        return _export_xlsx(metrics), "report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if fmt == "pptx":
        return _export_pptx(template, metrics), "report.pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"
    return _export_pdf(template, metrics), "report.pdf", "application/pdf"


@app.get("/", response_class=HTMLResponse)
def root() -> RedirectResponse:
    return RedirectResponse(url="/dashboard")


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard() -> str:
    return _render_dashboard_html()

@app.get("/favicon.ico")
def favicon() -> StreamingResponse:
    return StreamingResponse(BytesIO(b""), media_type="image/x-icon")


@app.get("/builder", response_class=HTMLResponse)
def builder() -> str:
    return _render_builder_html()


@app.get("/schedules", response_class=HTMLResponse)
def schedules_page() -> str:
    return _render_schedules_html()


@app.get("/api/templates")
def list_templates(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role)
    items = db.query(ReportTemplate).order_by(ReportTemplate.name.asc()).all()
    return JSONResponse({"items": [{"id": t.id, "name": t.name, "description": t.description, "is_active": t.is_active} for t in items]})


@app.get("/api/templates/{template_id}")
def get_template(
    template_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role)
    tmpl = db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Not found")
    return JSONResponse({"id": tmpl.id, "name": tmpl.name, "description": tmpl.description, "definition": tmpl.definition})


@app.post("/api/templates")
def create_template(
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role, required_roles=["admin", "manager"])
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    definition = payload.get("definition") or {"version": 1, "widgets": []}
    tmpl = ReportTemplate(name=name, description=payload.get("description"), definition=definition, is_active=True, created_by_role=role)
    db.add(tmpl)
    db.commit()
    db.refresh(tmpl)
    _audit(db, action="CREATE", resource_type="REPORT_TEMPLATE", resource_id=tmpl.id, details={"name": tmpl.name}, request=request)
    return JSONResponse({"id": tmpl.id})


@app.put("/api/templates/{template_id}")
def update_template(
    template_id: int,
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role, required_roles=["admin", "manager"])
    tmpl = db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()
    if not tmpl:
        raise HTTPException(status_code=404, detail="Not found")
    name = (payload.get("name") or tmpl.name).strip()
    tmpl.name = name
    tmpl.description = payload.get("description")
    tmpl.definition = payload.get("definition") or tmpl.definition
    db.add(tmpl)
    db.commit()
    _audit(db, action="UPDATE", resource_type="REPORT_TEMPLATE", resource_id=tmpl.id, details={"name": tmpl.name}, request=request)
    return JSONResponse({"ok": True})


@app.get("/api/dashboard")
def api_dashboard(
    template_id: int,
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role)
    tmpl = db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()
    if not tmpl:
        tmpl = _load_or_create_default_template(db)
    start_dt, end_dt = _parse_dates(from_date, to_date)
    metrics = _compute_metrics(db, start_dt, end_dt, status or "ALL")

    widgets = []
    for w in (tmpl.definition or {}).get("widgets", []):
        metric = w.get("metric")
        widgets.append({"type": w.get("type"), "metric": metric, "title": w.get("title"), "value": metrics.get(metric)})
    return JSONResponse({"template": {"id": tmpl.id, "name": tmpl.name}, "widgets": widgets})


@app.post("/api/invoices/{invoice_number}/retry")
def retry_invoice_upload(
    invoice_number: str,
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role)
    inv_num = (invoice_number or "").strip()
    if not inv_num:
        raise HTTPException(status_code=400, detail="invoice_number required")

    with _retry_lock:
        now = time.time()
        last = _last_retry_at.get(inv_num, 0.0)
        if now - last < 30.0:
            raise HTTPException(status_code=429, detail="Too many retry attempts. Please wait and try again.")
        _last_retry_at[inv_num] = now

    inv = db.query(Invoice).filter(Invoice.invoice_number == inv_num).first()
    if not inv:
        raise HTTPException(status_code=404, detail="Invoice not found")
    if (inv.sync_status or "").upper() != "PENDING":
        return JSONResponse(
            {
                "invoice_number": inv.invoice_number,
                "sync_status": inv.sync_status,
                "message": "Retry not available for this status.",
            }
        )

    inv.fbr_response_message = "Manual retry requested."
    db.add(inv)
    db.commit()
    db.refresh(inv)

    try:
        invoice_service.sync_invoice(db, inv)
        db.commit()
        db.refresh(inv)
    except Exception as e:
        db.rollback()
        inv = db.query(Invoice).filter(Invoice.invoice_number == inv_num).first()
        status = inv.sync_status if inv else "PENDING"
        msg = str(e)
        return JSONResponse(
            {
                "invoice_number": inv_num,
                "sync_status": status,
                "message": msg,
            },
            status_code=200,
        )

    _audit(
        db,
        action="RETRY_SYNC",
        resource_type="INVOICE",
        resource_id=int(inv.id),
        details={"invoice_number": inv.invoice_number, "sync_status": inv.sync_status, "triggered_by": role},
        request=request,
    )

    return JSONResponse(
        {
            "invoice_number": inv.invoice_number,
            "sync_status": inv.sync_status,
            "message": inv.fbr_response_message or "",
        }
    )


@app.get("/export/{fmt}")
def export_report(
    fmt: str,
    template_id: int,
    request: Request,
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> StreamingResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role)
    tmpl = db.query(ReportTemplate).filter(ReportTemplate.id == template_id).first()
    if not tmpl:
        tmpl = _load_or_create_default_template(db)
    start_dt, end_dt = _parse_dates(from_date, to_date)
    metrics = _compute_metrics(db, start_dt, end_dt, status or "ALL")
    content, filename, media_type = _export_bytes(tmpl, metrics, fmt)
    _audit(db, action="EXPORT", resource_type="REPORT_TEMPLATE", resource_id=tmpl.id, details={"fmt": fmt, "filename": filename}, request=request)
    return StreamingResponse(BytesIO(content), media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})


@app.get("/invoices.csv")
def invoices_csv_legacy(
    request: Request,
    db: Session = Depends(get_db),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    status: Optional[str] = Query("ALL"),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> StreamingResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role)
    tmpl = _load_or_create_default_template(db)
    start_dt, end_dt = _parse_dates(from_date, to_date)
    metrics = _compute_metrics(db, start_dt, end_dt, status or "ALL")
    content = _export_csv(metrics)
    _audit(db, action="EXPORT", resource_type="REPORT_TEMPLATE", resource_id=tmpl.id, details={"fmt": "csv", "legacy": True}, request=request)
    return StreamingResponse(BytesIO(content), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=invoices.csv"})


@app.get("/api/schedules")
def list_schedules(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role, required_roles=["admin", "manager"])
    schedules = db.query(ReportSchedule).order_by(ReportSchedule.id.desc()).all()
    items = []
    for s in schedules:
        tmpl = db.query(ReportTemplate).filter(ReportTemplate.id == s.template_id).first()
        items.append(
            {
                "id": s.id,
                "template_id": s.template_id,
                "template_name": tmpl.name if tmpl else "",
                "enabled": bool(s.enabled),
                "interval_minutes": int(s.interval_minutes or 60),
                "export_format": s.export_format,
                "recipients": s.recipients or [],
                "last_run_at": s.last_run_at.isoformat(sep=" ") if s.last_run_at else None,
            }
        )
    return JSONResponse({"items": items})


@app.post("/api/schedules")
def create_schedule(
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role, required_roles=["admin", "manager"])
    template_id = int(payload.get("template_id") or 0)
    interval = int(payload.get("interval_minutes") or 60)
    export_format = (payload.get("export_format") or "pdf").lower()
    recipients = payload.get("recipients") or []
    schedule = ReportSchedule(
        template_id=template_id,
        interval_minutes=interval,
        export_format=export_format,
        recipients=recipients,
        enabled=bool(payload.get("enabled", True)),
        created_by_role=role,
    )
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    _audit(db, action="CREATE", resource_type="REPORT_SCHEDULE", resource_id=schedule.id, details={"template_id": template_id}, request=request)
    return JSONResponse({"id": schedule.id})


@app.put("/api/schedules/{schedule_id}")
def update_schedule(
    schedule_id: int,
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key"),
    x_user_role: Optional[str] = Header(default=None, alias="X-User-Role"),
) -> JSONResponse:
    role = _get_role(x_user_role)
    _require_auth(x_api_key, role, required_roles=["admin", "manager"])
    sch = db.query(ReportSchedule).filter(ReportSchedule.id == schedule_id).first()
    if not sch:
        raise HTTPException(status_code=404, detail="Not found")
    if "enabled" in payload:
        sch.enabled = bool(payload.get("enabled"))
    if "interval_minutes" in payload:
        sch.interval_minutes = int(payload.get("interval_minutes") or sch.interval_minutes or 60)
    if "export_format" in payload:
        sch.export_format = (payload.get("export_format") or sch.export_format).lower()
    if "recipients" in payload:
        sch.recipients = payload.get("recipients")
    db.add(sch)
    db.commit()
    _audit(db, action="UPDATE", resource_type="REPORT_SCHEDULE", resource_id=sch.id, details={"enabled": sch.enabled}, request=request)
    return JSONResponse({"ok": True})
