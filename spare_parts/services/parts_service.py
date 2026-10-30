"""Service layer for parts, categories and brands (Phase 1).

Every function takes the caller's `db: Session` explicitly rather than
opening its own - from Phase 2 onward this lets a single caller-owned
session span an entire save (header + items + stock ledger) as one
transaction. Phase 1 has no multi-step saves yet, but the pattern is set
here so later phases don't have to retrofit it.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from spare_parts.db.models import SpBrand, SpCategory, SpPart
from spare_parts.errors import SparePartsValidationError
from spare_parts.logging_config import get_logger
from spare_parts.utils import to_decimal as _to_decimal

logger = get_logger(__name__)


# --- Categories ---------------------------------------------------------

def list_categories(db: Session) -> list[SpCategory]:
    return db.query(SpCategory).order_by(SpCategory.name).all()


def get_category(db: Session, category_id: int) -> Optional[SpCategory]:
    return db.query(SpCategory).filter(SpCategory.id == category_id).first()


def create_category(db: Session, name: str, parent_id: Optional[int] = None) -> SpCategory:
    name = (name or "").strip()
    if not name:
        raise SparePartsValidationError("Category name is required.")
    category = SpCategory(name=name, parent_id=parent_id or None)
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


def _category_descendant_ids(db: Session, category_id: int) -> set[int]:
    """All ids below this category in the tree, so a rename's parent
    picker can refuse to make a category its own descendant's child
    (which would create a cycle)."""
    all_categories = list_categories(db)
    children_by_parent: dict[Optional[int], list[int]] = {}
    for cat in all_categories:
        children_by_parent.setdefault(cat.parent_id, []).append(cat.id)

    descendants: set[int] = set()
    frontier = children_by_parent.get(category_id, [])
    while frontier:
        descendants.update(frontier)
        next_frontier = []
        for cid in frontier:
            next_frontier.extend(children_by_parent.get(cid, []))
        frontier = next_frontier
    return descendants


def get_valid_parent_choices(db: Session, category_id: Optional[int] = None) -> list[SpCategory]:
    """Categories eligible to be the parent of `category_id` (or of a
    brand-new category, when None) - excludes itself and its own
    descendants, so the UI's parent picker can never offer a choice that
    would create a cycle."""
    exclude_ids: set[int] = set()
    if category_id is not None:
        exclude_ids.add(category_id)
        exclude_ids.update(_category_descendant_ids(db, category_id))
    return [c for c in list_categories(db) if c.id not in exclude_ids]


def update_category(
    db: Session, category_id: int, *, name: Optional[str] = None, parent_id=...,
) -> SpCategory:
    """parent_id uses an unset-sentinel default so None can be passed
    explicitly (meaning "make this a top-level category")."""
    category = get_category(db, category_id)
    if not category:
        raise SparePartsValidationError(f"Category id={category_id} not found.")

    if name is not None:
        new_name = name.strip()
        if not new_name:
            raise SparePartsValidationError("Category name is required.")
        category.name = new_name

    if parent_id is not ...:
        if parent_id == category_id:
            raise SparePartsValidationError("A category cannot be its own parent.")
        if parent_id is not None and parent_id in _category_descendant_ids(db, category_id):
            raise SparePartsValidationError(
                "Can't move a category under its own subcategory - that would create a loop."
            )
        category.parent_id = parent_id or None

    db.commit()
    db.refresh(category)
    logger.info(f"Updated category {category.name} (id={category.id})")
    return category


def delete_category(db: Session, category_id: int) -> None:
    category = get_category(db, category_id)
    if not category:
        return
    parts_using_it = db.query(SpPart.id).filter(SpPart.category_id == category_id).first()
    if parts_using_it:
        raise SparePartsValidationError(
            f"'{category.name}' is used by one or more parts and can't be deleted. "
            "Reassign those parts to a different category first."
        )
    children = db.query(SpCategory.id).filter(SpCategory.parent_id == category_id).first()
    if children:
        raise SparePartsValidationError(
            f"'{category.name}' has subcategories under it and can't be deleted. "
            "Delete or move those first."
        )
    db.delete(category)
    db.commit()
    logger.info(f"Deleted category id={category_id}")


# --- Brands --------------------------------------------------------------

def list_brands(db: Session) -> list[SpBrand]:
    return db.query(SpBrand).order_by(SpBrand.name).all()


def get_brand(db: Session, brand_id: int) -> Optional[SpBrand]:
    return db.query(SpBrand).filter(SpBrand.id == brand_id).first()


def create_brand(db: Session, name: str) -> SpBrand:
    name = (name or "").strip()
    if not name:
        raise SparePartsValidationError("Brand name is required.")
    existing = db.query(SpBrand).filter(SpBrand.name == name).first()
    if existing:
        return existing
    brand = SpBrand(name=name)
    db.add(brand)
    db.commit()
    db.refresh(brand)
    return brand


def update_brand(db: Session, brand_id: int, *, name: str) -> SpBrand:
    brand = get_brand(db, brand_id)
    if not brand:
        raise SparePartsValidationError(f"Brand id={brand_id} not found.")
    new_name = (name or "").strip()
    if not new_name:
        raise SparePartsValidationError("Brand name is required.")
    clash = db.query(SpBrand).filter(SpBrand.name == new_name, SpBrand.id != brand_id).first()
    if clash:
        raise SparePartsValidationError(f"A brand named '{new_name}' already exists.")
    brand.name = new_name
    db.commit()
    db.refresh(brand)
    logger.info(f"Updated brand {brand.name} (id={brand.id})")
    return brand


def delete_brand(db: Session, brand_id: int) -> None:
    brand = get_brand(db, brand_id)
    if not brand:
        return
    parts_using_it = db.query(SpPart.id).filter(SpPart.brand_id == brand_id).first()
    if parts_using_it:
        raise SparePartsValidationError(
            f"'{brand.name}' is used by one or more parts and can't be deleted. "
            "Reassign those parts to a different brand first."
        )
    db.delete(brand)
    db.commit()
    logger.info(f"Deleted brand id={brand_id}")


# --- Parts -----------------------------------------------------------------

def search_parts(
    db: Session,
    query: str = "",
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    active_only: bool = True,
) -> list[SpPart]:
    q = db.query(SpPart)
    if active_only:
        q = q.filter(SpPart.is_active == True)  # noqa: E712
    if category_id:
        q = q.filter(SpPart.category_id == category_id)
    if brand_id:
        q = q.filter(SpPart.brand_id == brand_id)
    query = (query or "").strip()
    if query:
        like = f"%{query}%"
        q = q.filter(
            or_(
                SpPart.part_no.ilike(like),
                SpPart.name.ilike(like),
                SpPart.barcode.ilike(like),
                SpPart.compatible_models.ilike(like),
            )
        )
    return q.order_by(SpPart.name).all()


def get_part(db: Session, part_id: int) -> Optional[SpPart]:
    return db.query(SpPart).filter(SpPart.id == part_id).first()


def get_part_by_no(db: Session, part_no: str) -> Optional[SpPart]:
    part_no = (part_no or "").strip().upper()
    if not part_no:
        return None
    return db.query(SpPart).filter(SpPart.part_no == part_no).first()


def create_part(
    db: Session,
    *,
    part_no: str,
    name: str,
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    compatible_models: str = "",
    unit: str = "pcs",
    pack_size: int = 1,
    barcode: str = "",
    rack_location: str = "",
    cost_price=0,
    retail_price=0,
    wholesale_price=0,
    min_wholesale_qty: int = 1,
    reorder_level: int = 0,
    reorder_qty: int = 0,
    warranty_days: int = 0,
    notes: str = "",
) -> SpPart:
    part_no = (part_no or "").strip().upper()
    name = (name or "").strip()
    if not part_no:
        raise SparePartsValidationError("Part No. is required.")
    if not name:
        raise SparePartsValidationError("Part name is required.")

    if get_part_by_no(db, part_no):
        raise SparePartsValidationError(f"Part No. '{part_no}' already exists.")

    part = SpPart(
        part_no=part_no,
        name=name,
        category_id=category_id or None,
        brand_id=brand_id or None,
        compatible_models=(compatible_models or "").strip(),
        unit=(unit or "pcs").strip() or "pcs",
        pack_size=max(1, int(pack_size or 1)),
        barcode=(barcode or "").strip() or None,
        rack_location=(rack_location or "").strip() or None,
        cost_price=_to_decimal(cost_price, "Cost price"),
        retail_price=_to_decimal(retail_price, "Retail price"),
        wholesale_price=_to_decimal(wholesale_price, "Wholesale price"),
        min_wholesale_qty=max(1, int(min_wholesale_qty or 1)),
        reorder_level=max(0, int(reorder_level or 0)),
        reorder_qty=max(0, int(reorder_qty or 0)) or None,
        warranty_days=max(0, int(warranty_days or 0)) or None,
        notes=(notes or "").strip() or None,
        is_active=True,
    )
    db.add(part)
    db.commit()
    db.refresh(part)
    logger.info(f"Created part {part.part_no} (id={part.id})")
    return part


def update_part(db: Session, part_id: int, **fields) -> SpPart:
    part = get_part(db, part_id)
    if not part:
        raise SparePartsValidationError(f"Part id={part_id} not found.")

    if "part_no" in fields:
        new_part_no = (fields["part_no"] or "").strip().upper()
        if not new_part_no:
            raise SparePartsValidationError("Part No. is required.")
        clash = get_part_by_no(db, new_part_no)
        if clash and clash.id != part.id:
            raise SparePartsValidationError(f"Part No. '{new_part_no}' already exists.")
        part.part_no = new_part_no

    if "name" in fields:
        new_name = (fields["name"] or "").strip()
        if not new_name:
            raise SparePartsValidationError("Part name is required.")
        part.name = new_name

    for simple_field in (
        "category_id", "brand_id", "unit", "barcode", "rack_location",
        "compatible_models", "notes",
    ):
        if simple_field in fields:
            value = fields[simple_field]
            if isinstance(value, str):
                value = value.strip() or None
            setattr(part, simple_field, value)

    for int_field in ("pack_size", "min_wholesale_qty", "reorder_level"):
        if int_field in fields and fields[int_field] is not None:
            setattr(part, int_field, max(0, int(fields[int_field])))

    for nullable_int_field in ("reorder_qty", "warranty_days"):
        if nullable_int_field in fields and fields[nullable_int_field] is not None:
            setattr(part, nullable_int_field, max(0, int(fields[nullable_int_field])) or None)

    for money_field in ("cost_price", "retail_price", "wholesale_price"):
        if money_field in fields and fields[money_field] is not None:
            setattr(part, money_field, _to_decimal(fields[money_field], money_field))

    db.commit()
    db.refresh(part)
    logger.info(f"Updated part {part.part_no} (id={part.id})")
    return part


_BULK_PRICE_FIELDS = ("cost_price", "retail_price", "wholesale_price")
_BULK_PRICE_MODES = ("PERCENT", "FIXED")


def bulk_update_prices(
    db: Session,
    *,
    category_id: Optional[int] = None,
    brand_id: Optional[int] = None,
    field: str,
    mode: str,
    value,
) -> list[dict]:
    """Applies a %/fixed change to ONE price field across every active
    part matching the optional category/brand filter (omit both to
    apply to every active part). A negative `value` lowers prices in
    either mode. Never takes a price below 0. One commit at the end
    (atomic - either the whole batch lands or none of it does, matching
    the rest of this module's save conventions); the UI is expected to
    compute its own before/after preview client-side before calling this.

    Returns [{part, old_price, new_price}, ...] for every part that
    actually changed (parts already at the floor of 0, or whose rounded
    result doesn't move, are skipped)."""
    if field not in _BULK_PRICE_FIELDS:
        raise SparePartsValidationError(f"Unknown price field: {field!r}")
    mode = (mode or "").upper()
    if mode not in _BULK_PRICE_MODES:
        raise SparePartsValidationError("Mode must be PERCENT or FIXED.")
    value = _to_decimal(value, "Value")

    parts = search_parts(db, category_id=category_id, brand_id=brand_id, active_only=True)
    results = []
    for part in parts:
        old_price = Decimal(str(getattr(part, field) or 0))
        if mode == "PERCENT":
            new_price = old_price * (Decimal("1") + value / Decimal("100"))
        else:
            new_price = old_price + value
        new_price = max(Decimal("0"), new_price).quantize(Decimal("0.01"))
        if new_price != old_price:
            setattr(part, field, new_price)
            results.append(dict(part=part, old_price=old_price, new_price=new_price))

    if results:
        db.commit()
        logger.info(
            f"Bulk price update: {field} {mode} {value} applied to {len(results)} part(s) "
            f"(category_id={category_id}, brand_id={brand_id})"
        )
    return results


def set_part_active(db: Session, part_id: int, is_active: bool) -> SpPart:
    """Soft activate/deactivate. There is no hard-delete for parts: once
    Phase 2/3 transaction tables exist, a part referenced by any
    purchase/sale/adjustment must never be removable, only deactivated -
    so deactivation is the only "removal" exposed from day one."""
    part = get_part(db, part_id)
    if not part:
        raise SparePartsValidationError(f"Part id={part_id} not found.")
    part.is_active = bool(is_active)
    db.commit()
    db.refresh(part)
    logger.info(f"Part {part.part_no} (id={part.id}) is_active={part.is_active}")
    return part
