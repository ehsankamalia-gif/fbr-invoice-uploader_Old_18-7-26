from sqlalchemy.orm import Session, joinedload
from sqlalchemy import and_, desc
from app.db.models import Price, ProductModel
from app.db.session import SessionLocal
from app.services.settings_service import settings_service
from datetime import datetime
import json
import logging
import re
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)

class PriceService:
    def __init__(self):
        self._cache = {}
        self._cache_timestamp = None
        self._CACHE_DURATION = 300  # 5 minutes

    def get_db(self):
        return SessionLocal()

    def get_price_by_id(self, price_id: int, db: Session = None) -> Optional[Price]:
        """Get a price record by its unique ID."""
        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            return db.query(Price).options(joinedload(Price.product_model)).filter(Price.id == price_id).first()
        finally:
            if close_db:
                db.close()

    def get_active_price(self, model_name: str, db: Session = None) -> Optional[Price]:
        """
        Get the currently active price for a specific model.
        Checks cache first.
        """
        # Check cache
        if self._cache_timestamp and (datetime.now() - self._cache_timestamp).seconds < self._CACHE_DURATION:
            if model_name in self._cache:
                return self._cache[model_name]

        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True

        try:
            price = db.query(Price).options(joinedload(Price.product_model)).join(ProductModel).filter(
                ProductModel.model_name == model_name,
                Price.expiration_date.is_(None)
            ).first()
            
            if price:
                self._cache[model_name] = price
            
            return price
        finally:
            if close_db:
                db.close()

    def get_active_prices_for_model(self, model_name: str, db: Session = None) -> List[Price]:
        """Get all active price records for a model (handling multiple variants/colors)."""
        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            return db.query(Price).join(ProductModel).filter(
                ProductModel.model_name == model_name,
                Price.expiration_date.is_(None)
            ).all()
        finally:
            if close_db:
                db.close()

    def get_price_by_model_and_color(self, model_name: str, color: str, db: Session = None) -> Optional[Price]:
        """Find specific price based on model and color."""
        prices = self.get_active_prices_for_model(model_name, db)
        if not prices:
            return None

        target = re.sub(r"[^A-Za-z]", "", (color or "")).lower()
        if not target:
            return prices[0]

        # 1. Try to find exact match where color is in the price's color list
        for p in prices:
            if p.optional_features and isinstance(p.optional_features, dict):
                colors_str = p.optional_features.get("colors") or p.optional_features.get("color") or ""
                candidates = [re.sub(r"[^A-Za-z]", "", c.strip()).lower() for c in str(colors_str).split(",")]
                if target in [c for c in candidates if c]:
                    return p
        
        # 2. If no color-specific match, return the first available price (fallback)
        return prices[0]


    def get_all_active_prices(self, db: Session = None) -> List[Price]:
        """Get all currently active prices."""
        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            prices = db.query(Price).options(joinedload(Price.product_model)).join(ProductModel).filter(Price.expiration_date.is_(None)).all()
            
            # Update cache
            self._cache = {p.product_model.model_name: p for p in prices if p.product_model}
            self._cache_timestamp = datetime.now()
            
            return prices
        finally:
            if close_db:
                db.close()

    def get_price_history(self, model_name: str, db: Session = None) -> List[Price]:
        """Get historical prices for a model."""
        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            return db.query(Price).join(ProductModel).filter(
                ProductModel.model_name == model_name
            ).order_by(desc(Price.effective_date)).all()
        finally:
            if close_db:
                db.close()

    def get_price_at_date(self, model_name: str, target_date: datetime, db: Session = None) -> Optional[Price]:
        """
        Get the price that was active at a specific date.
        """
        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            # Find the price where effective_date <= target_date 
            # AND (expiration_date IS NULL OR expiration_date > target_date)
            return db.query(Price).join(ProductModel).filter(
                ProductModel.model_name == model_name,
                Price.effective_date <= target_date,
                (Price.expiration_date.is_(None)) | (Price.expiration_date > target_date)
            ).order_by(desc(Price.effective_date)).first()
        finally:
            if close_db:
                db.close()

    def add_price(self, model: str, base_price: float, tax: float, levy: float, 
                  total: float, optional_features: Dict = None, db: Session = None) -> Price:
        """
        Add a new price version. Expires the previous active price for this model.
        """
        if base_price < 0 or tax < 0 or total < 0:
            raise ValueError("Prices cannot be negative")

        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            # 1. Find or Create ProductModel
            product_model = db.query(ProductModel).filter(ProductModel.model_name == model).first()
            if not product_model:
                product_model = ProductModel(model_name=model, make="Honda", company_id=settings_service.get_active_company_id())
                db.add(product_model)
                db.flush()

            now = datetime.utcnow()
            # 2. Expire current active prices for the same model+color (if provided),
            #    otherwise expire all active prices for the model (legacy behavior).
            target_colors: List[str] = []
            if optional_features and isinstance(optional_features, dict):
                raw = optional_features.get("colors") or optional_features.get("color") or ""
                raw_str = str(raw or "")
                for part in raw_str.split(","):
                    value = re.sub(r"[^A-Za-z]", "", part or "").upper()
                    if value and value not in target_colors:
                        target_colors.append(value)

            active_prices = db.query(Price).filter(
                Price.product_model_id == product_model.id,
                Price.expiration_date.is_(None),
            ).all()

            if target_colors:
                for ap in active_prices:
                    opt = getattr(ap, "optional_features", None)
                    ap_colors: List[str] = []
                    if opt and isinstance(opt, dict):
                        raw = opt.get("colors") or opt.get("color") or ""
                        raw_str = str(raw or "")
                        for part in raw_str.split(","):
                            value = re.sub(r"[^A-Za-z]", "", part or "").upper()
                            if value and value not in ap_colors:
                                ap_colors.append(value)
                    if any(c in target_colors for c in ap_colors):
                        ap.expiration_date = now
            else:
                for ap in active_prices:
                    ap.expiration_date = now
            
            # 3. Create new price
            new_price = Price(
                product_model_id=product_model.id,
                base_price=base_price,
                tax_amount=tax,
                levy_amount=levy,
                total_price=total,
                optional_features=optional_features or {},
                effective_date=now,
                currency='Rs',
                company_id=settings_service.get_active_company_id(),
            )
            
            db.add(new_price)
            db.commit()
            db.refresh(new_price)
            
            # Invalidate cache
            self._cache_timestamp = None
            
            return new_price
        except Exception as e:
            db.rollback()
            raise e
        finally:
            if close_db:
                db.close()

    def update_price(self, price_id: int, model: str, base_price: float, tax: float, levy: float, 
                     total: float, optional_features: Dict = None, db: Session = None) -> Price:
        """
        Update an existing price record in-place (correction mode).
        """
        if base_price < 0 or tax < 0 or total < 0:
            raise ValueError("Prices cannot be negative")

        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            price = db.query(Price).filter(Price.id == price_id).first()
            if not price:
                raise ValueError(f"Price with ID {price_id} not found")

            # Update ProductModel if changed
            if price.product_model.model_name != model:
                product_model = db.query(ProductModel).filter(ProductModel.model_name == model).first()
                if not product_model:
                    product_model = ProductModel(model_name=model, make="Honda", company_id=settings_service.get_active_company_id())
                    db.add(product_model)
                    db.flush()
                price.product_model_id = product_model.id

            price.base_price = base_price
            price.tax_amount = tax
            price.levy_amount = levy
            price.total_price = total
            if optional_features is not None:
                price.optional_features = optional_features
            
            db.commit()
            db.refresh(price)
            
            # Invalidate cache
            self._cache_timestamp = None
            
            return price
        except Exception as e:
            db.rollback()
            raise e
        finally:
            if close_db:
                db.close()

    def delete_price_model(self, model: str, db: Session = None):
        """
        Expire the active price for a model.
        """
        close_db = False
        if db is None:
            db = self.get_db()
            close_db = True
            
        try:
            # Get product model first
            product_model = db.query(ProductModel).filter(ProductModel.model_name == model).first()
            
            if product_model:
                # Expire ALL active prices for this model
                db.query(Price).filter(
                    Price.product_model_id == product_model.id,
                    Price.expiration_date.is_(None)
                ).update({Price.expiration_date: datetime.utcnow()}, synchronize_session=False)
                
                db.commit()
                
            # Invalidate cache
            self._cache_timestamp = None
        finally:
            if close_db:
                db.close()

    # Column-header aliases accepted on import, matched case/space/punctuation
    # -insensitively (see _normalize_header) so a sheet exported by this same
    # feature, or a reasonably-named hand-made one, both work without the
    # user needing to match column names exactly.
    _IMPORT_HEADER_ALIASES = {
        "model": "model",
        "modelname": "model",
        "color": "color",
        "colour": "color",
        "baseprice": "base_price",
        "basepriceexcltax": "base_price",
        "price": "base_price",
        "salestax": "tax",
        "taxamount": "tax",
        "tax": "tax",
        "furthertax": "levy",
        "levyamount": "levy",
        "levy": "levy",
        "totalprice": "total",
        "totalpriceincltax": "total",
        "total": "total",
    }

    @staticmethod
    def _normalize_header(raw: Any) -> str:
        return re.sub(r"[^a-z0-9]", "", str(raw or "").strip().lower())

    def parse_import_rows(self, raw_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalizes raw {header: value} dicts (as read from an Excel sheet
        - see app/services/excel_service.py's header/row shape) into
        validated {model, color, base_price, tax, levy, total, error} dicts,
        one per input row. Never raises - validation failures are reported
        per-row via the 'error' key instead, so the caller can show a full
        preview (including bad rows) before committing anything."""
        parsed = []
        for raw_row in raw_rows:
            normalized = {}
            for key, value in raw_row.items():
                mapped = self._IMPORT_HEADER_ALIASES.get(self._normalize_header(key))
                if mapped:
                    normalized[mapped] = value

            model = str(normalized.get("model") or "").strip()
            color = str(normalized.get("color") or "").strip().upper()
            error = None

            def _to_float(key: str, default: Optional[float] = None) -> Optional[float]:
                value = normalized.get(key)
                if value is None or str(value).strip() == "":
                    return default
                try:
                    return float(value)
                except (TypeError, ValueError):
                    raise ValueError(f"'{key}' is not a valid number: {value!r}")

            base_price = tax = levy = total = None
            try:
                if not model:
                    raise ValueError("Model name is required.")
                base_price = _to_float("base_price")
                if base_price is None:
                    raise ValueError("Base Price is required.")
                tax = _to_float("tax", 0.0)
                levy = _to_float("levy", 0.0)
                total = _to_float("total")
                if total is None:
                    total = round(base_price + tax + levy, 2)
                if base_price < 0 or tax < 0 or levy < 0 or total < 0:
                    raise ValueError("Prices cannot be negative.")
            except ValueError as e:
                error = str(e)

            parsed.append({
                "model": model, "color": color, "base_price": base_price,
                "tax": tax, "levy": levy, "total": total, "error": error,
            })
        return parsed

    def import_prices(self, parsed_rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Commits the valid (error-free) rows from parse_import_rows via
        add_price (so find-or-create ProductModel, active-company stamping,
        and expiring the prior price all happen exactly as they do for a
        manually-entered price). Returns a summary; never raises - each
        row's own failure is collected instead of aborting the whole batch."""
        imported, failed = 0, []
        db = self.get_db()
        try:
            for row in parsed_rows:
                if row.get("error"):
                    failed.append(f"{row.get('model') or '(blank model)'}: {row['error']}")
                    continue
                try:
                    self.add_price(
                        model=row["model"],
                        base_price=row["base_price"],
                        tax=row["tax"],
                        levy=row["levy"],
                        total=row["total"],
                        optional_features={"colors": row["color"]} if row["color"] else {},
                        db=db,
                    )
                    imported += 1
                except Exception as e:
                    failed.append(f"{row['model']}: {e}")
        finally:
            db.close()
        return {"imported": imported, "failed": failed}

    def bulk_import_from_json(self, json_data: List[Dict], force: bool = False):
        """Import initial data from JSON. By default, skips if DB is not empty."""
        db = self.get_db()
        try:
            if not force and db.query(Price).count() > 0:
                return # Already data exists
            
            for item in json_data:
                self.add_price(
                    model=item["model"],
                    base_price=item["price_excl"],
                    tax=item["tax"],
                    levy=item["levy"],
                    total=item["price_incl"],
                    optional_features={"colors": item.get("colors", "")},
                    db=db
                )
        finally:
            db.close()

price_service = PriceService()
