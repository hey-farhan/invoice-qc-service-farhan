from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import List
from pydantic import BaseModel
import tempfile
import os
from .validator import validate_batch
from .extractor import extract_purchase_order

app = FastAPI(
    title="German B2B Purchase Order QC API",
    description="Extract and validate German Purchase Orders (Bestellung)",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health_check():
    """Health check endpoint"""
    return {"status": "ok", "service": "Purchase Order QC"}

@app.post("/validate-json")
def validate_json(purchase_orders: List[dict]):
    """
    Validate a list of purchase order JSON objects.
    
    Request body: List of purchase order dictionaries
    Response: Validation summary + per-PO results
    """
    try:
        results = validate_batch(purchase_orders)
        return results
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/extract-and-validate")
async def extract_and_validate_pdfs(files: List[UploadFile] = File(...)):
    """
    Extract and validate purchase orders from uploaded PDFs.
    
    Accepts: Multiple PDF files (multipart/form-data)
    Returns: Extracted data + validation results
    """
    try:
        extracted_pos = []
        
        for file in files:
            if not file.filename.lower().endswith('.pdf'):
                continue
            
            # Save to temp file
            with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp:
                content = await file.read()
                tmp.write(content)
                tmp_path = tmp.name
            
            try:
                # Extract
                po_data = extract_purchase_order(tmp_path)
                extracted_pos.append(po_data)
            finally:
                # Cleanup
                os.unlink(tmp_path)
        
        # Validate
        validation_results = validate_batch(extracted_pos)
        
        return {
            "extracted_data": extracted_pos,
            "validation": validation_results
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
