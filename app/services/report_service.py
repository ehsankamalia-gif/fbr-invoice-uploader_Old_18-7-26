from datetime import datetime
from typing import List, Optional

from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

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

        if flt.period == "Today" and not start_date and not end_date:
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
        elif flt.period == "This Month" and not start_date and not end_date:
            import calendar

            start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            last_day = calendar.monthrange(now.year, now.month)[1]
            end_date = now.replace(day=last_day, hour=23, minute=59, second=59, microsecond=999999)

        if start_date:
            query = query.filter(Invoice.datetime >= start_date)
        if end_date:
            query = query.filter(Invoice.datetime <= end_date)

        search_text = flt.search_text.strip()
        if search_text:
            search = f"%{search_text}%"
            query = query.outerjoin(Invoice.items).outerjoin(InvoiceItem.motorcycle).filter(
                or_(
                    Invoice.invoice_number.ilike(search),
                    Customer.name.ilike(search),
                    Customer.cnic.ilike(search),
                    Motorcycle.chassis_number.ilike(search),
                    Motorcycle.engine_number.ilike(search),
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


report_service = ReportService()

