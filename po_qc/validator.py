import re
from typing import List, Optional, Dict
from pydantic import BaseModel, Field, field_validator
import datetime

# --- Pydantic Models ---

class LineItem(BaseModel):
    """Line item in a Purchase Order"""
    position: int = Field(gt=0, description="Position number")
    product_name: str = Field(description="Product description")
    supplier_article_no: Optional[str] = Field(default=None, description="Lief.Art.Nr")
    internal_material_no: Optional[str] = Field(default=None, description="Interne Mat.Nr")
    cost_center: str = Field(description="Kostenstelle - REQUIRED for accounting")
    quantity_ve: int = Field(gt=0, description="Quantity in VE (Verpackungseinheit)")
    unit_conversion: Optional[str] = Field(default=None, description="e.g., '1 VE=20 Stück'")
    price_per_ve: float = Field(ge=0, description="Price per VE")
    line_total: float = Field(ge=0, description="Line total")

class PurchaseOrder(BaseModel):
    """German B2B Purchase Order (Bestellung) model"""
    doc_type: str = Field(default="PurchaseOrder", description="Document type identifier")
    order_number: str = Field(description="Order number (AUFNR format)")
    order_date: str = Field(description="Order date DD.MM.YYYY")
    
    # 4-Party hierarchy
    creator_name: str = Field(description="Purchaser creating PO")
    creator_customer_number: str = Field(description="Customer number (7-11 digits)")
    parent_company_id: str = Field(description="Parent company ID")
    end_customer_number: str = Field(description="End customer number (7-8 digits)")
    delivery_destination: str = Field(description="Delivery address")
    
    # Financials
    currency: str = Field(default="EUR", description="Currency code")
    subtotal: float = Field(ge=0, description="Gesamtwert (net total)")
    vat_rate: float = Field(default=19.0, description="VAT rate percentage")
    vat_amount: float = Field(ge=0, description="MwSt. amount")
    gross_total: float = Field(ge=0, description="Gesamtwert inkl. MwSt.")
    
    # Terms
    payment_terms: str = Field(description="Zahlungsbedingungen")
    delivery_date: str = Field(description="Gewünschtes Lieferdatum")
    
    line_items: List[LineItem] = Field(min_length=1, description="Line items (must have at least 1)")
    
    # Validation Rules
    
    @field_validator('order_number')
    def validate_order_number(cls, v):
        """Order number must be AUFNR + 5-6 digits"""
        if not re.match(r'AUFNR\d{5,6}', v):
            raise ValueError('Order number must be in format AUFNRxxxxx (5-6 digits)')
        return v
    
    @field_validator('order_date')
    def validate_order_date(cls, v):
        """Date must be DD.MM.YYYY and not after Dec 2025"""
        try:
            parsed_date = datetime.datetime.strptime(v, '%d.%m.%Y')
            max_date = datetime.datetime(2025, 12, 31)
            if parsed_date > max_date:
                raise ValueError(f"Order date cannot be after {max_date.strftime('%d.%m.%Y')}")
        except ValueError as e:
            if "does not match format" in str(e):
                raise ValueError("Order date must be in format DD.MM.YYYY")
            raise e
        return v
    
    @field_validator('creator_customer_number')
    def validate_creator_customer_number(cls, v):
        """Creator customer number: 7-11 digits"""
        if not re.match(r'^\d{7,11}$', v):
            raise ValueError('Creator customer number must be 7-11 digits')
        return v
    
    @field_validator('end_customer_number')
    def validate_end_customer_number(cls, v):
        """End customer number: 7-8 digits"""
        if not re.match(r'^\d{7,8}$', v):
            raise ValueError('End customer number must be 7-8 digits')
        return v
    
    @field_validator('currency')
    def validate_currency(cls, v):
        """Currency must be EUR"""
        if v != 'EUR':
            raise ValueError('Currency must be EUR for German B2B purchase orders')
        return v
    
    @field_validator('doc_type')
    def validate_doc_type(cls, v):
        """Document type must be PurchaseOrder"""
        if v != 'PurchaseOrder':
            raise ValueError('Document type must be "PurchaseOrder"')
        return v

# --- Validation Logic ---

def validate_purchase_order(po_data: Dict) -> Dict:
    """Validate a single purchase order against schema and business rules"""
    errors = []
    is_valid = True
    validated_po = None
    
    # Schema validation (completeness, format, type)
    try:
        validated_po = PurchaseOrder(**po_data)
    except Exception as e:
        is_valid = False
        if hasattr(e, 'errors'):
            for err in e.errors():
                loc = ".".join([str(x) for x in err['loc']])
                errors.append(f"{loc}: {err['msg']}")
        else:
            errors.append(str(e))
        
        return {
            "po_id": f"{po_data.get('order_number', 'UNKNOWN')}-{po_data.get('order_date', 'UNKNOWN')}",
            "is_valid": False,
            "errors": errors,
            "data": po_data
        }
    
    # Business rules validation
    po = validated_po
    
    # Check cost center on all line items
    for idx, item in enumerate(po.line_items):
        if not item.cost_center or item.cost_center.strip() == "":
            is_valid = False
            errors.append(f"line_items[{idx}]: cost_center is required for accounting")
    
    # Subtotal must equal sum of line items (±0.01)
    line_sum = sum(item.line_total for item in po.line_items)
    if abs(line_sum - po.subtotal) > 0.01:
        is_valid = False
        errors.append(f"R10: Sum of line items ({line_sum:.2f}) does not equal subtotal ({po.subtotal:.2f})")
    
    # VAT amount must equal subtotal × VAT rate (±0.01)
    calculated_vat = po.subtotal * (po.vat_rate / 100)
    if abs(calculated_vat - po.vat_amount) > 0.01:
        is_valid = False
        errors.append(f"R11: Calculated VAT ({calculated_vat:.2f}) does not match stated VAT ({po.vat_amount:.2f})")
    
    # Gross total must equal subtotal + VAT (±0.01)
    if abs((po.subtotal + po.vat_amount) - po.gross_total) > 0.01:
        is_valid = False
        errors.append(f"R12: Subtotal + VAT ({po.subtotal + po.vat_amount:.2f}) does not match gross total ({po.gross_total:.2f})")
    
    # Anomaly detection: gross total should be < 10000
    if po.gross_total >= 10000:
        is_valid = False
        errors.append(f"R15: Gross total ({po.gross_total:.2f}) exceeds realistic threshold (10000)")
    
    return {
        "po_id": f"{po.order_number}-{po.order_date}",
        "is_valid": is_valid,
        "errors": errors,
        "data": po_data
    }

def validate_batch(purchase_orders: List[Dict]) -> Dict:
    """
    Validates a batch of purchase orders with duplicate detection.
    """
    results = []
    seen = set()
    
    total = len(purchase_orders)
    valid_count = 0
    invalid_count = 0
    all_errors = {}
    
    for po_data in purchase_orders:
        res = validate_purchase_order(po_data)
        
        # R14: Duplicate detection
        order_num = po_data.get('order_number')
        order_date = po_data.get('order_date')
        
        if order_num and order_date:
            key = f"{order_num}|{order_date}"
            if key in seen:
                res['is_valid'] = False
                res['errors'].append("R14: Duplicate purchase order detected in batch")
            seen.add(key)
        
        results.append(res)
        
        if res['is_valid']:
            valid_count += 1
        else:
            invalid_count += 1
            for err in res['errors']:
                if err not in all_errors:
                    all_errors[err] = 0
                all_errors[err] += 1
    
    return {
        "summary": {
            "total_purchase_orders": total,
            "valid": valid_count,
            "invalid": invalid_count,
            "error_counts": all_errors
        },
        "details": results
    }
