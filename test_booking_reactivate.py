
from app.db.session import SessionLocal, init_db
from app.db.models import AdvanceBooking
from app.services.advance_booking_service import advance_booking_service

def run_test():
    init_db()
    db = SessionLocal()
    try:
        # Test 1: Find an active booking or create one for test
        test_booking = advance_booking_service.create_booking(
            db=db,
            customer_name="Test Customer",
            motorcycle_model="Test Model",
            color="Red",
            total_price=100000,
            advance_paid=30000
        )
        print(f"Created test booking {test_booking.booking_number} with advance_remaining {test_booking.advance_remaining}")

        # Now cancel it with full refund
        cancelled_booking = advance_booking_service.cancel_booking(
            db=db,
            booking_number=test_booking.booking_number,
            refund_amount=30000
        )
        print(f"Canceled booking, advance_remaining {cancelled_booking.advance_remaining}")
        
        # Reactivate it
        reactivated = advance_booking_service.reactivate_booking(
            db=db,
            booking_number=test_booking.booking_number
        )
        print(f"Reactivated booking, advance_remaining {reactivated.advance_remaining}, status {reactivated.status}")
        
        # Check summary
        summary = advance_booking_service.get_summary(db)
        print("Summary after reactivation:")
        print(f"outstanding_advance: {summary['outstanding_advance']}")
        
    finally:
        db.close()

if __name__ == "__main__":
    run_test()

