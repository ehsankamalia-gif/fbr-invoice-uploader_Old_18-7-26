
from app.db.session import SessionLocal
from app.db.models import Invoice
from datetime import datetime, date, time

with open('stats_output.txt', 'w') as f:
    db = SessionLocal()
    today = date.today()
    start_of_day = datetime.combine(today, time.min)

    f.write('=== Invoices created today ===\n')
    total = db.query(Invoice).filter(Invoice.datetime >= start_of_day).count()
    f.write(f'Total: {total}\n')

    synced = db.query(Invoice).filter(
        Invoice.datetime >= start_of_day,
        Invoice.fbr_invoice_number != None
    ).count()
    f.write(f'Synced: {synced}\n')

    pending = total - synced
    f.write(f'Pending: {pending}\n')

    f.write('\n=== All invoices (for reference) ===\n')
    all_total = db.query(Invoice).count()
    f.write(f'Total: {all_total}\n')
    all_synced = db.query(Invoice).filter(Invoice.fbr_invoice_number != None).count()
    f.write(f'Synced: {all_synced}\n')
    all_pending = all_total - all_synced
    f.write(f'Pending: {all_pending}\n')

    db.close()

print('Statistics written to stats_output.txt')
