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

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, File, UploadFile, HTTPException, Query, Depends, Header, status
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

from models import ComplianceReport, ComplianceViolation, ViolationSeverity
from extractor import extract_permit_data
from rules import validate_document, init_db
from database import (
    init_project_db, verify_api_key, create_api_key, list_api_keys,
    save_project, get_project, list_projects, delete_project, get_stats
)

app = FastAPI(
    title="Solar Permit Pre-Flight Validator",
    description="AI-powered solar permit pre-submission compliance checker",
    version="0.1.0"
)

# CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static frontend files
import os as _os
frontend_dir = _os.path.join(_os.path.dirname(__file__), "frontend")
if _os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

# Initialize databases on startup
init_db()
init_project_db()

# --- Auth dependency ---
async def require_api_key(x_api_key: str = Header(None, alias="X-API-Key")):
    """Require a valid API key for protected endpoints."""
    if not x_api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    if not verify_api_key(x_api_key):
        raise HTTPException(status_code=403, detail="Invalid or expired API key")
    return x_api_key


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


# --- Project endpoints ---

@app.get("/projects")
def projects_list(limit: int = 50, offset: int = 0, api_key: str = Depends(require_api_key)):
    """List all validation projects."""
    return {"projects": list_projects(limit, offset)}


@app.get("/projects/{project_id}")
def projects_get(project_id: str, api_key: str = Depends(require_api_key)):
    """Get a single project with violations."""
    project = get_project(project_id)
    if not project:
        raise HTTPException(404, detail="Project not found")
    return project


@app.delete("/projects/{project_id}")
def projects_delete(project_id: str, api_key: str = Depends(require_api_key)):
    """Delete a project and its violations."""
    if delete_project(project_id):
        return {"message": "Project deleted"}
    raise HTTPException(404, detail="Project not found")


@app.get("/stats")
def stats_overview(api_key: str = Depends(require_api_key)):
    """Get aggregate statistics across all projects."""
    return get_stats()


# --- Auth endpoints ---

@app.post("/auth/keys")
def auth_create_key(name: str = None, admin_key: str = Header(None, alias="X-Admin-Key")):
    """Create a new API key. Requires admin key (set ADMIN_KEY env var)."""
    expected = os.getenv("ADMIN_KEY")
    if expected and admin_key != expected:
        raise HTTPException(403, detail="Invalid admin key")
    key = create_api_key(name)
    return {"api_key": key, "name": name, "message": "Store this key securely - it will not be shown again"}


@app.get("/auth/keys")
def auth_list_keys(admin_key: str = Header(None, alias="X-Admin-Key")):
    """List all API keys (admin only)."""
    expected = os.getenv("ADMIN_KEY")
    if expected and admin_key != expected:
        raise HTTPException(403, detail="Invalid admin key")
    return {"keys": list_api_keys()}


@app.post("/validate_permit", response_model=ComplianceReport)
async def validate_permit(
    file: UploadFile = File(..., description="Permit PDF (plan set, SLD, or spec sheet)"),
    project_id: Optional[str] = Query(None, description="Optional project identifier"),
    jurisdiction: Optional[str] = Query(None, description="Override jurisdiction name"),
    save: bool = Query(True, description="Save result to project database"),
    api_key: Optional[str] = Depends(require_api_key)
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
        doc = await extract_permit_data(pdf_bytes)
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

    # Save to database
    if save:
        import json
        violations_dict = [v.model_dump() for v in violations]
        save_project(
            project_id=project_id,
            name=file.filename,
            jurisdiction=doc.site_info.jurisdiction_name or jurisdiction or "Unknown",
            status=status,
            pass_rate=round(pass_rate, 1),
            violations=violations_dict,
            raw_json=json.dumps({
                "project_id": project_id,
                "filename": file.filename,
                "status": status,
                "pass_rate": pass_rate,
                "violations_count": len(violations),
                "jurisdiction": doc.site_info.jurisdiction_name,
            })
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
    """Serve the React frontend."""
    frontend_index = _os.path.join(frontend_dir, "index.html")
    if _os.path.exists(frontend_index):
        return FileResponse(frontend_index)
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
