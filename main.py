"""
Solar Permit Pre-Flight Validator API
FastAPI backend for AI-powered permit document analysis.

Endpoints:
  POST /validate_permit  - Upload PDF, get compliance report
  GET  /health           - Health check
  GET  /rules            - List loaded AHJ rules
"""

import os
import uuid
from datetime import datetime
from typing import List, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import JSONResponse

from models import ComplianceReport, ComplianceViolation, ViolationSeverity
from extractor import extract_permit_data
from rules import validate_document, init_db

app = FastAPI(
    title="Solar Permit Pre-Flight Validator",
    description="AI-powered solar permit pre-submission compliance checker",
    version="0.1.0"
)

# Initialize rules database on startup
init_db()


@app.get("/health")
def health_check():
    return {"status": "ok", "version": "0.1.0", "mode": os.getenv("LLM_PROVIDER", "mock")}


@app.get("/rules")
def list_rules(
    jurisdiction: Optional[str] = Query(None, description="Filter by jurisdiction name"),
    category: Optional[str] = Query(None, description="Filter by category")
):
    """List all loaded validation rules."""
    from rules import get_applicable_rules
    rules = get_applicable_rules(jurisdiction=jurisdiction)
    if category:
        rules = [r for r in rules if r["category"] == category]
    return {"count": len(rules), "rules": rules}


@app.post("/validate_permit", response_model=ComplianceReport)
async def validate_permit(
    file: UploadFile = File(..., description="Permit PDF (plan set, SLD, or spec sheet)"),
    project_id: Optional[str] = Query(None, description="Optional project identifier"),
    jurisdiction: Optional[str] = Query(None, description="Override jurisdiction name")
):
    """
    Upload a solar permit PDF and receive a compliance report.

    The API:
    1. Extracts text and images from the PDF
    2. Uses AI (LLM or mock extractor) to parse structured data
    3. Runs AHJ-specific and NEC rules against the extracted data
    4. Returns a compliance report with violations, severity, and fix suggestions
    """
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, detail="Only PDF files are accepted")

    # Generate project ID if not provided
    if not project_id:
        project_id = f"PERM-{uuid.uuid4().hex[:8].upper()}"

    # Read PDF bytes
    pdf_bytes = await file.read()
    if len(pdf_bytes) > 50 * 1024 * 1024:
        raise HTTPException(413, detail="PDF too large. Max 50MB.")

    # Extract structured data from PDF
    try:
        doc = extract_permit_data(pdf_bytes)
    except Exception as e:
        raise HTTPException(500, detail=f"Document extraction failed: {str(e)}")

    # Override jurisdiction if provided
    if jurisdiction:
        doc.site_info.jurisdiction_name = jurisdiction

    # Run validation rules
    violations = validate_document(doc)

    # Determine overall status
    if any(v.severity == ViolationSeverity.CRITICAL for v in violations):
        status = "FAIL"
    elif any(v.severity == ViolationSeverity.MAJOR for v in violations):
        status = "NEEDS_REVIEW"
    elif violations:
        status = "NEEDS_REVIEW"
    else:
        status = "PASS"

    # Calculate pass rate
    from rules import get_applicable_rules
    total_rules = len(get_applicable_rules(
        doc.site_info.jurisdiction_name,
        doc.site_info.nec_edition
    ))
    passed = total_rules - len(violations)
    pass_rate = (passed / total_rules * 100) if total_rules > 0 else 100.0

    # Estimate fix time
    est_hours = sum({
        ViolationSeverity.CRITICAL: 4.0,
        ViolationSeverity.MAJOR: 2.0,
        ViolationSeverity.MINOR: 0.5,
        ViolationSeverity.INFO: 0.1,
    }.get(v.severity, 0.0) for v in violations)

    # Build summary
    if status == "PASS":
        summary = f"Permit {project_id} passed all {total_rules} validation rules. Ready for submission to {doc.site_info.jurisdiction_name or 'AHJ'}."
    else:
        crit = sum(1 for v in violations if v.severity == ViolationSeverity.CRITICAL)
        maj = sum(1 for v in violations if v.severity == ViolationSeverity.MAJOR)
        min_count = sum(1 for v in violations if v.severity == ViolationSeverity.MINOR)
        summary = (
            f"Permit {project_id} has {len(violations)} issues: "
            f"{crit} critical, {maj} major, {min_count} minor. "
            f"Estimated fix time: {est_hours:.1f} hours. "
            f"Address critical issues before submitting to {doc.site_info.jurisdiction_name or 'AHJ'}."
        )

    return ComplianceReport(
        project_id=project_id,
        ahj_name=doc.site_info.jurisdiction_name or "Unknown AHJ",
        overall_status=status,
        pass_rate=round(pass_rate, 1),
        violations=violations,
        summary=summary,
        estimated_fix_time_hours=round(est_hours, 1) if est_hours > 0 else None
    )


@app.get("/")
def root():
    return {
        "service": "Solar Permit Pre-Flight Validator",
        "version": "0.1.0",
        "endpoints": {
            "health": "/health",
            "rules": "/rules",
            "validate_permit": "POST /validate_permit"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
