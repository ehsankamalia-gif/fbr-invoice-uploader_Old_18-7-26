import os
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_, func
from app.db.models import Invoice, InvoiceItem, Motorcycle, Customer

class SalesFilter:
    def __init__(
        self,
        search_text: str = "",
        status: str = "All",
        payment_mode: str = "All",
        period: str = "All Time",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: Optional[int] = None,
    ) -> None:
        self.search_text = search_text
        self.status = status
        self.payment_mode = payment_mode
        self.period = period
        self.start_date = start_date
        self.end_date = end_date
        self.limit = limit

class ReportService:
    def build_sales_query(self, db: Session, flt: SalesFilter):
        query = db.query(Invoice).join(Customer).options(
            joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle)
        ).order_by(Invoice.datetime.desc())

        now = datetime.now()
        start_date = flt.start_date
        end_date = flt.end_date

        if not start_date and not end_date:
            if flt.period == "Today":
                start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            elif flt.period == "Yesterday":
                yesterday = now - timedelta(days=1)
                start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
            elif flt.period == "This Week":
                start_date = (now - timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            elif flt.period == "This Month":
                start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
            elif flt.period == "Last 30 Days":
                start_date = (now - timedelta(days=30)).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        if start_date:
            query = query.filter(Invoice.datetime >= start_date)
        if end_date:
            query = query.filter(Invoice.datetime <= end_date)

        search_text = flt.search_text.strip()
        if search_text:
            search = f"%{search_text}%"
            # Use a subquery or join for item searches to avoid cartesian products in count
            query = query.filter(
                or_(
                    Invoice.invoice_number.ilike(search),
                    Customer.name.ilike(search),
                    Customer.cnic.ilike(search),
                    Invoice.items.any(InvoiceItem.item_code.ilike(search)),
                    Invoice.items.any(InvoiceItem.motorcycle.has(Motorcycle.chassis_number.ilike(search))),
                    Invoice.items.any(InvoiceItem.motorcycle.has(Motorcycle.engine_number.ilike(search)))
                )
            )

        status_filter = flt.status
        if status_filter == "Synced":
            query = query.filter(Invoice.is_fiscalized.is_(True))
        elif status_filter == "Pending":
            query = query.filter(Invoice.is_fiscalized.is_(False), Invoice.sync_status != "FAILED")
        elif status_filter == "Failed":
            query = query.filter(Invoice.sync_status == "FAILED")

        if flt.payment_mode and flt.payment_mode != "All":
            query = query.filter(Invoice.payment_mode == flt.payment_mode)

        if flt.limit:
            query = query.limit(flt.limit)

        return query

    def get_sales(self, db: Session, flt: SalesFilter) -> List[Invoice]:
        query = self.build_sales_query(db, flt)
        return list(query.all())

    def get_sales_summary(self, db: Session, flt: SalesFilter) -> Dict[str, Any]:
        """Calculates summary statistics for the filtered sales."""
        query = self.build_sales_query(db, flt)
        # Remove ordering and eager loading for aggregation
        summary_query = query.order_by(None).options(joinedload(Invoice.items, innerjoin=True))
        
        invoices = summary_query.all()
        
        total_revenue = sum(inv.total_amount for inv in invoices)
        total_tax = sum(inv.total_tax_charged for inv in invoices)
        total_further_tax = sum(getattr(inv, 'total_further_tax', 0) or 0 for inv in invoices)
        count = len(invoices)
        
        # Daily sales for chart
        df_data = []
        for inv in invoices:
            df_data.append({
                'date': inv.datetime.date(),
                'amount': float(inv.total_amount or 0)
            })
        
        daily_sales = {}
        if df_data:
            df = pd.DataFrame(df_data)
            daily = df.groupby('date')['amount'].sum().reset_index()
            daily_sales = {str(row['date']): row['amount'] for _, row in daily.iterrows()}

        return {
            "total_revenue": float(total_revenue),
            "total_tax": float(total_tax),
            "total_further_tax": float(total_further_tax),
            "invoice_count": count,
            "daily_sales": daily_sales
        }

    def export_to_csv(self, db: Session, flt: SalesFilter, file_path: str) -> bool:
        """Exports filtered sales to a CSV file."""
        try:
            invoices = self.get_sales(db, flt)
            data = []
            for inv in invoices:
                chassis = ", ".join([it.motorcycle.chassis_number for it in inv.items if it.motorcycle])
                data.append({
                    "Date": inv.datetime.strftime("%Y-%m-%d %H:%M"),
                    "Invoice #": inv.invoice_number,
                    "Customer": inv.customer.name if inv.customer else "N/A",
                    "CNIC": inv.customer.cnic if inv.customer else "N/A",
                    "Chassis": chassis,
                    "Sale Value": inv.total_sale_value,
                    "Tax": inv.total_tax_charged,
                    "Further Tax": getattr(inv, 'total_further_tax', 0),
                    "Total": inv.total_amount,
                    "Status": "Synced" if inv.is_fiscalized else inv.sync_status
                })
            
            df = pd.DataFrame(data)
            df.to_csv(file_path, index=False)
            return True
        except Exception as e:
            print(f"CSV Export Error: {e}")
            return False

    def export_to_excel(self, db: Session, flt: SalesFilter, file_path: str) -> bool:
        """Exports filtered sales to an Excel file."""
        try:
            invoices = self.get_sales(db, flt)
            data = []
            for inv in invoices:
                chassis = ", ".join([it.motorcycle.chassis_number for it in inv.items if it.motorcycle])
                data.append({
                    "Date": inv.datetime.strftime("%Y-%m-%d %H:%M"),
                    "Invoice #": inv.invoice_number,
                    "Customer": inv.customer.name if inv.customer else "N/A",
                    "CNIC": inv.customer.cnic if inv.customer else "N/A",
                    "Chassis": chassis,
                    "Sale Value": inv.total_sale_value,
                    "Tax": inv.total_tax_charged,
                    "Further Tax": getattr(inv, 'total_further_tax', 0),
                    "Total": inv.total_amount,
                    "Status": "Synced" if inv.is_fiscalized else inv.sync_status
                })
            
            df = pd.DataFrame(data)
            # Use openpyxl engine if available, otherwise fallback
            try:
                df.to_excel(file_path, index=False, engine='openpyxl')
            except ImportError:
                df.to_excel(file_path, index=False)
            return True
        except Exception as e:
            print(f"Excel Export Error: {e}")
            return False

    def export_to_pdf(self, db: Session, flt: SalesFilter, file_path: str) -> bool:
        """Exports filtered sales to a professional PDF report with watermarking."""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.pdfgen import canvas

            invoices = self.get_sales(db, flt)
            summary = self.get_sales_summary(db, flt)
            
            doc = SimpleDocTemplate(file_path, pagesize=landscape(A4))
            elements = []
            styles = getSampleStyleSheet()
            
            # Professional Header
            title_style = ParagraphStyle('TitleStyle', parent=styles['Heading1'], fontSize=18, spaceAfter=10)
            elements.append(Paragraph("Sales Intelligence Report", title_style))
            elements.append(Paragraph(f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')}", styles['Normal']))
            elements.append(Spacer(1, 20))
            
            # Summary Table
            summary_data = [
                ["Total Invoices", "Total Revenue", "Total Tax (Inc. Further)"],
                [str(summary['invoice_count']), f"Rs. {summary['total_revenue']:,.2f}", f"Rs. {summary['total_tax'] + summary['total_further_tax']:,.2f}"]
            ]
            summary_table = Table(summary_data, colWidths=[150, 150, 200])
            summary_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#34495e")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('GRID', (0, 0), (-1, -1), 1, colors.grey)
            ]))
            elements.append(summary_table)
            elements.append(Spacer(1, 30))
            
            # Main Data Table
            data = [["Date", "Invoice #", "Customer", "Chassis", "Value", "Tax", "Total", "Status"]]
            for inv in invoices:
                chassis = ", ".join([it.motorcycle.chassis_number for it in inv.items if it.motorcycle])
                data.append([
                    inv.datetime.strftime("%Y-%m-%d"),
                    inv.invoice_number,
                    (inv.customer.name[:20] + '..') if inv.customer and len(inv.customer.name) > 20 else (inv.customer.name if inv.customer else "N/A"),
                    chassis[:15] + '..' if len(chassis) > 15 else chassis,
                    f"{inv.total_sale_value:,.0f}",
                    f"{inv.total_tax_charged + (getattr(inv, 'total_further_tax', 0) or 0):,.0f}",
                    f"{inv.total_amount:,.0f}",
                    "Synced" if inv.is_fiscalized else "Pending"
                ])
            
            main_table = Table(data, repeatRows=1)
            main_table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#2c3e50")),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 9),
                ('FONTSIZE', (0, 1), (-1, -1), 8),
                ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.whitesmoke, colors.white]),
                ('GRID', (0, 0), (-1, -1), 0.5, colors.grey)
            ]))
            elements.append(main_table)
            
            # Watermark Function
            def add_watermark(canvas, doc):
                canvas.saveState()
                canvas.setFont('Helvetica-Bold', 60)
                canvas.setStrokeColor(colors.lightgrey)
                canvas.setFillBrushAlpha(0.1)
                canvas.translate(doc.pagesize[0]/2, doc.pagesize[1]/2)
                canvas.rotate(45)
                canvas.drawCentredString(0, 0, "CONFIDENTIAL")
                canvas.restoreState()

            doc.build(elements, onFirstPage=add_watermark, onLaterPages=add_watermark)
            return True
        except Exception as e:
            print(f"PDF Export Error: {e}")
            return False

report_service = ReportService()

