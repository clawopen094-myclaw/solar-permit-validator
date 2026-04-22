# Solar Permit Pre-Flight Validator

AI-powered solar permit pre-submission compliance checker. Extracts structured data from engineering PDFs (plan sets, single-line diagrams, spec sheets) and validates against AHJ-specific rules and the National Electrical Code (NEC).

**Problem it solves:** 30-40% of solar permits are rejected on first submission, costing EPCs $2,000-$5,000 per project in delays and resubmission fees. This tool catches issues *before* submission.

## Quick Start

```bash
# 1. Clone and enter directory
cd solar-permit-validator

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env: set LLM_PROVIDER=mock (demo mode) or add your Gemini/OpenAI key

# 5. Run the server
python main.py
```

Server starts at `http://localhost:8000`

## API Usage

### Upload a permit PDF for validation

```bash
curl -X POST "http://localhost:8000/validate_permit" \
  -F "file=@permit_plan_set.pdf" \
  -F "project_id=PROJ-2026-001" \
  -F "jurisdiction=Los Angeles"
```

### Response

```json
{
  "project_id": "PROJ-2026-001",
  "ahj_name": "Los Angeles",
  "overall_status": "FAIL",
  "pass_rate": 62.5,
  "violations": [
    {
      "rule_id": "NEC690.12-01",
      "category": "electrical",
      "severity": "critical",
      "field": "electrical.rapid_shutdown",
      "message": "Rapid shutdown compliance (NEC 690.12) not confirmed.",
      "expected_value": "True",
      "actual_value": "MISSING",
      "reference": "NEC 690.12",
      "fix_suggestion": "Verify rapid shutdown device is specified and annotated on plans."
    }
  ],
  "summary": "Permit PROJ-2026-001 has 3 issues: 1 critical, 1 major, 1 minor...",
  "estimated_fix_time_hours": 6.5
}
```

## Architecture

```
PDF Upload
    |
    v
[PyMuPDF] -> text + images
    |
    v
[Extractor] -> Mock keyword parsing OR LLM (Gemini/OpenAI)
    |
    v
[PermitDocument] structured Pydantic model
    |
    v
[Rules Engine] SQLite-backed AHJ + NEC rules
    |
    v
[ComplianceReport] violations + fix suggestions
```

## Modes

### Mock Mode (default, no API keys needed)
Uses keyword extraction from PDF text. Good for demos and testing. Limited accuracy.

### LLM Mode (production)
Set `LLM_PROVIDER=gemini` and add `GEMINI_API_KEY`. Uses Gemini 1.5 Pro for multimodal PDF understanding. Much higher accuracy on complex engineering diagrams.

## Rules Database

Rules are stored in SQLite (`ahj_rules.db`) and include:

- **Universal NEC rules:** Voltage limits, OCPD sizing, rapid shutdown, busbar derating, grounding
- **Structural rules:** Load limits, fire setbacks, wind speed, attachment methods
- **Jurisdiction-specific rules:** LA City structural stamp, California interconnection, NYC FDNY setbacks

Add custom rules via the SQLite database or PR.

## Deployment

### Docker (coming soon)

### Production checklist

- [ ] Switch from `mock` to `gemini` or `openai` LLM provider
- [ ] Add authentication (API keys or OAuth)
- [ ] Configure persistent storage for rules DB
- [ ] Set up async task queue for large PDFs (Celery/Redis)
- [ ] Add webhook notifications for completed validations
- [ ] Build frontend dashboard for EPC users

## Roadmap

- [ ] Add support for DWG/DXF CAD files
- [ ] Build AHJ rules for top 100 U.S. jurisdictions
- [ ] Integrate with SolarAPP+ API
- [ ] Add proposal generation module
- [ ] White-label mode for EPC branding

## License

MIT

## Built With

- FastAPI + Uvicorn
- Pydantic AI (structured LLM extraction)
- PyMuPDF (PDF processing)
- SQLite (rules engine)
