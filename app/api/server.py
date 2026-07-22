from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from typing import List, Optional
from datetime import datetime
from sqlalchemy.orm import Session, joinedload
import os
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.db.session import SessionLocal, init_db
from app.services.price_service import price_service
from app.api.schemas import PriceResponse, PriceCreate, MotorcycleResponse, InvoiceWithDetailsResponse, MotorcycleSaleInfoResponse
from app.db.models import Motorcycle, Invoice, Price, ProductModel, InvoiceItem, Customer

# Initialize database when server starts
init_db()

app = FastAPI(title="FBR Invoice Uploader API", version="1.0.0")

# Mount static files
static_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static")
if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/demo", include_in_schema=False)
async def read_demo():
    return FileResponse(os.path.join(static_dir, "index.html"))

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

@app.get("/prices/active", response_model=List[PriceResponse])
def get_active_prices(db: Session = Depends(get_db)):
    """
    Get all currently active prices.
    """
    try:
        prices = price_service.get_all_active_prices(db)
        return prices
    except Exception as e:
        logger.exception("Error getting active prices")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/prices/{model}/active", response_model=PriceResponse)
def get_active_price_for_model(model: str, db: Session = Depends(get_db)):
    """
    Get active price for a specific model.
    """
    try:
        price = price_service.get_active_price(model, db)
        if not price:
            raise HTTPException(status_code=404, detail=f"No active price found for model {model}")
        return price
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting active price for model {model}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/prices/{model}/history", response_model=List[PriceResponse])
def get_price_history(
    model: str, 
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    Get price history for a specific model (including expired ones).
    """
    try:
        prices = db.query(Price).options(joinedload(Price.product_model)).join(ProductModel).filter(ProductModel.model_name == model).order_by(Price.effective_date.desc()).limit(limit).all()
        if not prices:
             raise HTTPException(status_code=404, detail=f"No price history found for model {model}")
        return prices
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting price history for model {model}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")

@app.post("/prices", response_model=PriceResponse)
def create_price(price: PriceCreate, db: Session = Depends(get_db)):
    """
    Create a new price version for a model. Expires the previous active price.
    """
    try:
        new_price = price_service.add_price(
            model=price.model,
            base_price=price.base_price,
            tax=price.tax_amount,
            levy=price.levy_amount,
            total=price.total_price,
            optional_features=price.optional_features,
            db=db
        )
        return new_price
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.get("/invoices/check-chassis/{chassis_number}")
def check_chassis_duplication(chassis_number: str, db: Session = Depends(get_db)):
    """
    Check if a chassis number has already been used in a posted invoice.
    """
    from app.services.invoice_service import InvoiceService
    service = InvoiceService()
    is_duplicate = service.is_chassis_used_in_posted_invoice(db, chassis_number)
    
    if is_duplicate:
        return {
            "exists": True, 
            "message": f"Invoice with chassis number {chassis_number} has already been posted"
        }
    return {"exists": False, "message": "Chassis number is available"}


# --- Motorcycle Endpoints ---
@app.get("/motorcycles", response_model=List[MotorcycleResponse])
def get_all_motorcycles(db: Session = Depends(get_db), status: Optional[str] = None):
    """
    Get all motorcycles, optionally filtered by status (IN_STOCK, etc.)
    """
    try:
        query = db.query(Motorcycle).options(joinedload(Motorcycle.product_model))
        if status:
            query = query.filter(Motorcycle.status == status)
        return query.all()
    except Exception as e:
        logger.exception("Error getting motorcycles")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/motorcycles/chassis/{chassis_number}", response_model=MotorcycleResponse)
def get_motorcycle_by_chassis(chassis_number: str, db: Session = Depends(get_db)):
    """
    Get motorcycle details by chassis number
    """
    try:
        motorcycle = db.query(Motorcycle).options(joinedload(Motorcycle.product_model)).filter(Motorcycle.chassis_number == chassis_number).first()
        if not motorcycle:
            raise HTTPException(status_code=404, detail=f"Motorcycle with chassis number {chassis_number} not found")
        return motorcycle
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting motorcycle by chassis {chassis_number}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/motorcycles/engine/{engine_number}", response_model=MotorcycleResponse)
def get_motorcycle_by_engine(engine_number: str, db: Session = Depends(get_db)):
    """
    Get motorcycle details by engine number
    """
    try:
        motorcycle = db.query(Motorcycle).options(joinedload(Motorcycle.product_model)).filter(Motorcycle.engine_number == engine_number).first()
        if not motorcycle:
            raise HTTPException(status_code=404, detail=f"Motorcycle with engine number {engine_number} not found")
        return motorcycle
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting motorcycle by engine {engine_number}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# --- Invoice Endpoints ---
@app.get("/invoices", response_model=List[InvoiceWithDetailsResponse])
def get_all_invoices(db: Session = Depends(get_db), is_fiscalized: Optional[bool] = None):
    """
    Get all invoices, optionally filtered by fiscalization status
    """
    try:
        query = db.query(Invoice)
        if is_fiscalized is not None:
            query = query.filter(Invoice.is_fiscalized == is_fiscalized)
        return query.all()
    except Exception as e:
        logger.exception("Error getting invoices")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/invoices/fbr/{fbr_invoice_number}", response_model=InvoiceWithDetailsResponse)
def get_invoice_by_fbr_number(fbr_invoice_number: str, db: Session = Depends(get_db)):
    """
    Get invoice details by FBR invoice number
    """
    try:
        invoice = db.query(Invoice).filter(Invoice.fbr_invoice_number == fbr_invoice_number).first()
        if not invoice:
            raise HTTPException(status_code=404, detail=f"Invoice with FBR number {fbr_invoice_number} not found")
        return invoice
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting invoice by FBR number {fbr_invoice_number}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/invoices/{invoice_number}", response_model=InvoiceWithDetailsResponse)
def get_invoice_by_number(invoice_number: str, db: Session = Depends(get_db)):
    """
    Get invoice details by local invoice number
    """
    try:
        invoice = db.query(Invoice).filter(Invoice.invoice_number == invoice_number).first()
        if not invoice:
            raise HTTPException(status_code=404, detail=f"Invoice with number {invoice_number} not found")
        return invoice
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"Error getting invoice by number {invoice_number}")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# --- Motorcycle Sale Info Endpoints ---
def build_motorcycle_sale_info(invoice: Invoice, invoice_item: Optional[InvoiceItem] = None, motorcycle: Optional[Motorcycle] = None, customer: Optional[Customer] = None):
    """Helper to build the MotorcycleSaleInfoResponse from database objects"""
    return MotorcycleSaleInfoResponse(
        id=invoice.id,
        invoice_number=invoice.invoice_number,
        fbr_invoice_number=invoice.fbr_invoice_number,
        is_fiscalized=invoice.is_fiscalized,
        invoice_datetime=invoice.datetime,
        customer_name=customer.name if customer else None,
        customer_father_name=customer.father_name if customer else None,
        customer_cnic=customer.cnic if customer else None,
        customer_phone=customer.phone if customer else None,
        customer_address=customer.address if customer else None,
        chassis_number=motorcycle.chassis_number if motorcycle else None,
        engine_number=motorcycle.engine_number if motorcycle else None,
        motorcycle_color=motorcycle.color if motorcycle else None,
        motorcycle_model=motorcycle.model if motorcycle else None,
        motorcycle_year=motorcycle.year if motorcycle else None,
        total_amount=invoice.total_amount,
        payment_mode=invoice.payment_mode
    )


@app.get("/motorcycle-sales/search", response_model=List[MotorcycleSaleInfoResponse])
def search_motorcycle_sales(
    chassis_number: Optional[str] = Query(None),
    engine_number: Optional[str] = Query(None),
    invoice_number: Optional[str] = Query(None),
    fbr_invoice_number: Optional[str] = Query(None),
    db: Session = Depends(get_db)
):
    """
    Search motorcycle sales by chassis number, engine number, invoice number, or FBR invoice number.
    """
    try:
        from sqlalchemy.orm import contains_eager
        
        # Start with invoice query
        query = db.query(Invoice)
        
        # Always eager load customer
        query = query.options(joinedload(Invoice.customer))
        
        # Apply filters
        if invoice_number:
            query = query.filter(Invoice.invoice_number == invoice_number)
        if fbr_invoice_number:
            query = query.filter(Invoice.fbr_invoice_number == fbr_invoice_number)
        
        # If filtering by motorcycle fields, join and eager load items + motorcycle
        if chassis_number or engine_number:
            query = query.join(Invoice.items).join(InvoiceItem.motorcycle)
            query = query.options(
                contains_eager(Invoice.items).contains_eager(InvoiceItem.motorcycle).contains_eager(Motorcycle.product_model)
            )
            if chassis_number:
                query = query.filter(Motorcycle.chassis_number == chassis_number)
            if engine_number:
                query = query.filter(Motorcycle.engine_number == engine_number)
        else:
            # Just eager load items and motorcycle
            query = query.options(
                joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle).joinedload(Motorcycle.product_model)
            )
        
        # Execute query
        invoices = query.all()
        
        # Build response
        results = []
        for invoice in invoices:
            customer = invoice.customer
            for item in invoice.items:
                motorcycle = item.motorcycle
                results.append(build_motorcycle_sale_info(invoice, item, motorcycle, customer))
        
        return results
    except Exception as e:
        logger.exception("Error searching motorcycle sales")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@app.get("/motorcycle-sales", response_model=List[MotorcycleSaleInfoResponse])
def get_all_motorcycle_sales(db: Session = Depends(get_db)):
    """
    Get all motorcycle sales.
    """
    try:
        invoices = db.query(Invoice).options(
            joinedload(Invoice.customer),
            joinedload(Invoice.items).joinedload(InvoiceItem.motorcycle).joinedload(Motorcycle.product_model)
        ).all()
        
        results = []
        for invoice in invoices:
            customer = invoice.customer
            for item in invoice.items:
                motorcycle = item.motorcycle
                results.append(build_motorcycle_sale_info(invoice, item, motorcycle, customer))
        
        return results
    except Exception as e:
        logger.exception("Error getting all motorcycle sales")
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
