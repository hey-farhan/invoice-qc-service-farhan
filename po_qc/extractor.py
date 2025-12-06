import pdfplumber
import re
import os
from typing import Dict, List, Any, Optional
from .utils import logger

def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text from PDF"""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                full_text += text + "\n"
    return full_text

def parse_german_float(value_str: str) -> float:
    """Parse German number format (1.234,56 -> 1234.56)"""
    if not value_str:
        return 0.0
    
    clean_str = value_str.strip().replace(' EUR', '').replace(' €', '').replace(' %', '')
    
    # Handle spaces in numbers
    if re.match(r'^[\d\s.,]+$', clean_str):
        clean_str = clean_str.replace(' ', '')
    
    # German format: comma as decimal separator
    if ',' in clean_str:
        clean_str = clean_str.replace('.', '').replace(',', '.')
    
    # Remove trailing non-numeric
    clean_str = re.sub(r'[^\d.]+$', '', clean_str)
    
    try:
        return float(clean_str)
    except ValueError:
        return 0.0

def extract_header_fields(text: str) -> Dict[str, Any]:
    """Extract header fields from purchase order text"""
    data = {}
    
    # Order number (5-6 digits)
    ord_match = re.search(r'AUFNR(\d{5,6})', text)
    data['order_number'] = f"AUFNR{ord_match.group(1)}" if ord_match else None
    
    # Order date
    date_match = re.search(r'vom\s+(\d{2}\.\d{2}\.\d{4})', text)
    data['order_date'] = date_match.group(1) if date_match else None
    
    # Creator name is always "Zentraleinkauf" for this business
    data['creator_name'] = "Zentraleinkauf"
    
    # Creator customer number = "Unsere Kundennummer" (FIRST number on next line)
    # Line structure: "Unsere Kundennummer Unser(e) Einkäufer(in) Telefon für Rückfragen Fax für Rückfragen"
    # Next line: "11223344 Beispielname 060/1212121 0102860405"
    # We want the FIRST number (11223344)
    creator_cust_match = re.search(r'Unsere\s+Kundennummer.*?\n\s*(\d{7,11})', text, re.DOTALL)
    data['creator_customer_number'] = creator_cust_match.group(1) if creator_cust_match else ""
    
    # Parent company ID
    parent_match = re.search(r'im\s+Auftrag\s+von\s+(\d{10})', text)
    data['parent_company_id'] = parent_match.group(1) if parent_match else ""
    
    # End customer number = "Endkundennummer"
    end_cust_match = re.search(r'Endkundennummer\s*\n\s*(\d{7,8})', text)
    data['end_customer_number'] = end_cust_match.group(1) if end_cust_match else ""
    
    # Delivery destination - extract multi-line address from table
    delivery_match = re.search(r'Bitte\s+liefern\s+Sie\s+an:(.+?)Zahlungsbedingungen', text, re.DOTALL)
    if delivery_match:
        block = delivery_match.group(1)
        lines = [line.strip() for line in block.split('\n') if line.strip()]
        
        # Filter out non-address lines
        filtered_lines = []
        skip_keywords = ['Gewünschtes', 'Lieferdatum', 'Lieferbedingungen', 'Keine Angabe', 'sofort']
        
        for line in lines:
            if any(kw in line for kw in skip_keywords):
                continue
            if re.match(r'^\d{2}\.\d{2}\.\d{4}$', line):
                continue
            if line and not line.isspace():
                filtered_lines.append(line)
        
        if filtered_lines:
            data['delivery_destination'] = ', '.join(filtered_lines)
        else:
            data['delivery_destination'] = "Zentraleinkauf"
    else:
        data['delivery_destination'] = "Zentraleinkauf"
    
    # Financial fields
    subtotal_match = re.search(r'Gesamtwert\s+EUR\s+([\d\.,]+)', text)
    data['subtotal'] = parse_german_float(subtotal_match.group(1)) if subtotal_match else 0.0
    
    vat_match = re.search(r'MwSt\.\s+(\d{1,2},\d{2})%\s+EUR\s+([\d\.,]+)', text)
    if vat_match:
        data['vat_rate'] = parse_german_float(vat_match.group(1))
        data['vat_amount'] = parse_german_float(vat_match.group(2))
    else:
        data['vat_rate'] = 19.0
        data['vat_amount'] = 0.0
    
    gross_match = re.search(r'Gesamtwert\s+inkl\.\s+MwSt\.\s+EUR\s+([\d\.,]+)', text)
    data['gross_total'] = parse_german_float(gross_match.group(1)) if gross_match else 0.0
    
    data['currency'] = 'EUR'
    
    # Payment terms
    payment_match = re.search(r'Zahlungsbedingungen\s*\n(.+?)(?=\n\n|Pos\.|$)', text, re.DOTALL)
    if payment_match:
        data['payment_terms'] = payment_match.group(1).strip()
    else:
        data['payment_terms'] = ""
    
    # Delivery date - extract last word from line (e.g., "sofort")
    del_date_match = re.search(r'Gewünschtes\s+Lieferdatum\s*\n(?:.*?\s+)?(\w+)\s*$', text, re.MULTILINE)
    if del_date_match:
        data['delivery_date'] = del_date_match.group(1)
    else:
        data['delivery_date'] = "sofort"
    
    # Document Type
    data['doc_type'] = 'PurchaseOrder'
    
    return data

def extract_line_items(pdf_path: str, full_text: str) -> List[Dict[str, Any]]:
    """Extract line items with cost_center, supplier_art_no, internal_mat_no"""
    items = []
    
    table_settings = {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 3,
    }
    
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            tables = page.extract_tables(table_settings)
            
            for table in tables:
                header_index = -1
                for i, row in enumerate(table):
                    row_str = " ".join([c for c in row if c]).lower()
                    if 'pos' in row_str and ('artikel' in row_str or 'beschreibung' in row_str):
                        header_index = i
                        break
                
                if header_index != -1:
                    current_item = None
                    
                    for row in table[header_index+1:]:
                        if not row or not any(row): continue
                        clean_row = [c.strip() if c else "" for c in row]
                        row_text = " ".join(clean_row)
                        
                        # New item starts with position number
                        if clean_row[0].isdigit():
                            if current_item: items.append(current_item)
                            
                            pos = int(clean_row[0])
                            
                            # Extract total (last numeric value)
                            total = 0.0
                            for val in reversed(clean_row):
                                parsed = parse_german_float(val)
                                if parsed > 0:
                                    total = parsed
                                    break
                            
                            # Extract quantity (X VE)
                            qty = 1
                            qty_match = re.search(r'(\d+)\s*VE', row_text, re.IGNORECASE)
                            if qty_match:
                                qty = int(qty_match.group(1))
                            
                            # Product name (usually second column)
                            product_name = clean_row[1] if len(clean_row) > 1 else ""
                            
                            current_item = {
                                "position": pos,
                                "product_name": product_name,
                                "supplier_article_no": None,
                                "internal_material_no": None,
                                "cost_center": None,
                                "quantity_ve": qty,
                                "unit_conversion": None,
                                "price_per_ve": 0.0,
                                "line_total": total
                            }
                        
                        else:
                            # Continuation line - extract metadata
                            if current_item:
                                # Supplier Article Number (Lief.Art.Nr)
                                supplier_match = re.search(r'Lief\.Art\.Nr:\s*(\w+)', row_text, re.IGNORECASE)
                                if supplier_match:
                                    current_item['supplier_article_no'] = supplier_match.group(1)
                                
                                # Internal Material Number (Interne Mat.Nr)
                                internal_match = re.search(r'Interne\s+Mat\.Nr:\s*(\d+)', row_text, re.IGNORECASE)
                                if internal_match:
                                    current_item['internal_material_no'] = internal_match.group(1)
                                
                                # Cost center (required field)
                                cost_match = re.search(r'Kostenstelle:\s*(\d+)', row_text, re.IGNORECASE)
                                if cost_match:
                                    current_item['cost_center'] = cost_match.group(1)
                                
                                # Price per VE - try multiple patterns
                                price_match = re.search(r'(\d{1,4},\d{2,4})\s+pro\s+1\s+VE', row_text, re.IGNORECASE)
                                if not price_match:
                                    price_match = re.search(r'(\d{1,5},\d{2,4})\s+pro\s+1\s+VE', row_text, re.IGNORECASE)
                                if not price_match:
                                    price_match = re.search(r'(\d{1,5},\s*\d{2,4})\s+pro\s+1\s+VE', row_text, re.IGNORECASE)
                                if price_match:
                                    current_item['price_per_ve'] = parse_german_float(price_match.group(1))
                                
                                # Unit conversion
                                conv_match = re.search(r'1\s+VE\s*=\s*(\d+)\s*St[üu]ck', row_text, re.IGNORECASE)
                                if conv_match:
                                    current_item['unit_conversion'] = f"1 VE={conv_match.group(1)} Stück"
                                
                                # Append continuation text to product name
                                if not any(k in row_text for k in ['Lief.Art', 'Interne', 'Kostenstelle', 'Gesamtw', 'MwSt']):
                                    current_item['product_name'] += " " + row_text
                    
                    if current_item: items.append(current_item)
    
    # Fallback: search full text for missing prices
    for item in items:
        if item['price_per_ve'] == 0.0 and item['internal_material_no']:
            pattern = rf"Interne\s+Mat\.Nr:\s*{re.escape(item['internal_material_no'])}\s+(\d{{1,5}},\d{{2,4}})\s+pro\s+1\s+VE"
            price_match = re.search(pattern, full_text, re.IGNORECASE)
            if price_match:
                item['price_per_ve'] = parse_german_float(price_match.group(1))
                logger.info(f"Found price {item['price_per_ve']} for item {item['position']} via full text search")
    
    # TEXT-BASED FALLBACK if no items found
    if not items:
        logger.info("No table items found, trying text-based extraction...")
        lines = full_text.split('\n')
        current_item = None
        
        for line in lines:
            line = line.strip()
            # Look for line starting with position number (1-99)
            match = re.match(r'^(\d{1,2})\s+(.+)', line)
            if match:
                pos_num = int(match.group(1))
                if 1 <= pos_num <= 99:
                    if current_item:
                        items.append(current_item)
                    
                    rest = match.group(2)
                    
                    # Extract quantity
                    qty = 1
                    qty_match = re.search(r'(\d+)\s+VE', rest)
                    if qty_match:
                        qty = int(qty_match.group(1))
                    
                    # Extract total (last number on line)
                    total = 0.0
                    total_match = re.search(r'(\d+,\d{2})$', rest)
                    if total_match:
                        total = parse_german_float(total_match.group(1))
                    
                    # Product name (first part before numbers)
                    product_name = re.split(r'\d+\s+VE', rest)[0].strip()
                    
                    current_item = {
                        "position": pos_num,
                        "product_name": product_name,
                        "supplier_article_no": None,
                        "internal_material_no": None,
                        "cost_center": None,
                        "quantity_ve": qty,
                        "unit_conversion": None,
                        "price_per_ve": 0.0,
                        "line_total": total
                    }
            
            elif current_item:
                # Continuation lines
                supplier_match = re.search(r'Lief\.Art\.Nr:\s*(\w+)', line)
                if supplier_match:
                    current_item['supplier_article_no'] = supplier_match.group(1)
                
                internal_match = re.search(r'Interne\s+Mat\.Nr:\s*(\d+)', line)
                if internal_match:
                    current_item['internal_material_no'] = internal_match.group(1)
                
                cost_match = re.search(r'Kostenstelle:\s*(\d+)', line)
                if cost_match:
                    current_item['cost_center'] = cost_match.group(1)
                
                price_match = re.search(r'(\d+,\d{2,4})\s+pro\s+1\s+VE', line)
                if price_match:
                    current_item['price_per_ve'] = parse_german_float(price_match.group(1))
                
                conv_match = re.search(r'1\s+VE\s*=\s*(\d+)\s*St[üu]ck', line)
                if conv_match:
                    current_item['unit_conversion'] = f"1 VE={conv_match.group(1)} Stück"
        
        if current_item:
            items.append(current_item)
    
    # Cleanup product names
    for item in items:
        item['product_name'] = re.sub(r'\s+', ' ', item['product_name']).strip()[:100]
    
    return items

def extract_purchase_order(pdf_path: str) -> Dict[str, Any]:
    """Extract complete purchase order from PDF"""
    text = extract_text_from_pdf(pdf_path)
    data = extract_header_fields(text)
    data['line_items'] = extract_line_items(pdf_path, text)
    return data

def extract_from_directory(dir_path: str) -> List[Dict[str, Any]]:
    """Extract all purchase orders from a directory of PDFs"""
    purchase_orders = []
    for f in os.listdir(dir_path):
        if f.lower().endswith('.pdf'):
            path = os.path.join(dir_path, f)
            try:
                logger.info(f"Extracting {f}...")
                po = extract_purchase_order(path)
                purchase_orders.append(po)
                logger.info(f"  Extracted {len(po['line_items'])} line items")
            except Exception as e:
                logger.error(f"Failed to extract {f}: {e}")
    return purchase_orders
