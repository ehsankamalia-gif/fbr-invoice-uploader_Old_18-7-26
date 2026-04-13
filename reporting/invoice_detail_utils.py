from typing import Any, Dict, List, Optional


def invoice_to_detail_dict(invoice: Any) -> Dict[str, Any]:
    customer = getattr(invoice, "customer", None)
    items_src = getattr(invoice, "items", None) or []

    items: List[Dict[str, Any]] = []
    subtotal = 0.0
    tax_total = 0.0
    further_tax_total = 0.0

    for it in items_src:
        qty = float(getattr(it, "quantity", 0.0) or 0.0)
        sale_value = float(getattr(it, "sale_value", 0.0) or 0.0)
        tax_charged = float(getattr(it, "tax_charged", 0.0) or 0.0)
        further_tax = float(getattr(it, "further_tax", 0.0) or 0.0)
        total_amount = float(getattr(it, "total_amount", sale_value + tax_charged + further_tax) or 0.0)

        motorcycle = getattr(it, "motorcycle", None)
        product_model = getattr(motorcycle, "product_model", None) if motorcycle else None

        subtotal += sale_value
        tax_total += tax_charged
        further_tax_total += further_tax

        items.append(
            {
                "item_code": getattr(it, "item_code", "") or "",
                "item_name": getattr(it, "item_name", "") or "",
                "pct_code": getattr(it, "pct_code", None),
                "quantity": qty,
                "sale_value": sale_value,
                "tax_charged": tax_charged,
                "further_tax": further_tax,
                "total_amount": total_amount,
                "discount": float(getattr(it, "discount", 0.0) or 0.0),
                "model": getattr(product_model, "model_name", "") or "",
                "color": (getattr(motorcycle, "color", "") or "") if motorcycle else "",
                "chassis_number": (getattr(motorcycle, "chassis_number", "") or "") if motorcycle else "",
                "engine_number": (getattr(motorcycle, "engine_number", "") or "") if motorcycle else "",
            }
        )

    inv_total = float(getattr(invoice, "total_amount", subtotal + tax_total + further_tax_total) or 0.0)

    dt_value = getattr(invoice, "datetime", None)
    dt_text = dt_value.isoformat(sep=" ") if dt_value else ""

    return {
        "invoice_number": getattr(invoice, "invoice_number", "") or "",
        "date": dt_text,
        "pos_id": getattr(invoice, "pos_id", "") or "",
        "payment_mode": getattr(invoice, "payment_mode", "") or "",
        "sync_status": getattr(invoice, "sync_status", "") or "",
        "is_fiscalized": bool(getattr(invoice, "is_fiscalized", False)),
        "fbr_invoice_number": getattr(invoice, "fbr_invoice_number", None),
        "customer": {
            "name": getattr(customer, "name", "") if customer else "",
            "father_name": getattr(customer, "father_name", "") if customer else "",
            "cnic": getattr(customer, "cnic", "") if customer else "",
            "ntn": getattr(customer, "ntn", "") if customer else "",
            "phone": getattr(customer, "phone", "") if customer else "",
            "address": getattr(customer, "address", "") if customer else "",
            "type": getattr(customer, "type", "") if customer else "",
            "business_name": getattr(customer, "business_name", "") if customer else "",
        },
        "items": items,
        "totals": {
            "subtotal": float(getattr(invoice, "total_sale_value", subtotal) or 0.0),
            "tax": float(getattr(invoice, "total_tax_charged", tax_total) or 0.0),
            "further_tax": float(getattr(invoice, "total_further_tax", further_tax_total) or 0.0),
            "total": inv_total,
        },
    }
