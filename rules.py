"""
AHJ Rules Engine for solar permit validation.
Rules are stored in SQLite and loaded dynamically.
For the MVP, we include a seed set of common NEC 2020/2023 rules
plus a few jurisdiction-specific rules.
"""

import sqlite3
import json
from pathlib import Path
from typing import List, Optional, Any
from models import PermitDocument, ComplianceViolation, ViolationSeverity

DB_PATH = Path(__file__).parent / "ahj_rules.db"


def init_db():
    """Initialize the SQLite rules database with seed data."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS rules (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            severity TEXT NOT NULL,
            jurisdictions TEXT,  -- JSON array of jurisdiction names, or NULL for universal
            nec_editions TEXT,   -- JSON array of applicable NEC editions
            field_path TEXT NOT NULL,  -- dot-notation path to the field being checked
            condition_type TEXT NOT NULL,  -- eq, ne, gt, gte, lt, lte, in, regex, exists
            expected_value TEXT,  -- stored as JSON for flexibility
            error_message TEXT NOT NULL,
            reference TEXT NOT NULL,
            fix_suggestion TEXT NOT NULL
        )
    """)
    conn.commit()

    # Seed universal NEC 2020/2023 electrical rules
    seeds = [
        # --- Electrical Rules ---
        {
            "id": "NEC690.7-01",
            "name": "DC System Size Residential Limit",
            "category": "electrical",
            "severity": "critical",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.system_size_kw_dc",
            "condition_type": "lte",
            "expected_value": json.dumps(100.0),  # Commercial can be larger
            "error_message": "DC system size exceeds reasonable limit. Verify calculations.",
            "reference": "NEC 690.7, 705.12",
            "fix_suggestion": "Verify system size calculation and service panel capacity."
        },
        {
            "id": "NEC690.8-01",
            "name": "OCPD Sizing",
            "category": "electrical",
            "severity": "critical",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.ocpd_rating_a",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Overcurrent protection device (OCPD) rating is missing from permit documentation.",
            "reference": "NEC 690.8, 690.9",
            "fix_suggestion": "Add breaker/fuse rating to single-line diagram."
        },
        {
            "id": "NEC690.12-01",
            "name": "Rapid Shutdown Required",
            "category": "electrical",
            "severity": "critical",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.rapid_shutdown",
            "condition_type": "eq",
            "expected_value": json.dumps(True),
            "error_message": "Rapid shutdown compliance (NEC 690.12) not confirmed.",
            "reference": "NEC 690.12",
            "fix_suggestion": "Verify rapid shutdown device is specified and annotated on plans."
        },
        {
            "id": "NEC705.12-01",
            "name": "Busbar Derating 120% Rule",
            "category": "electrical",
            "severity": "critical",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.busbar_rating_a",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Panel busbar rating is missing. Cannot verify 120% rule compliance.",
            "reference": "NEC 705.12(D)(2)",
            "fix_suggestion": "Add busbar rating to permit documents."
        },
        {
            "id": "NEC110.3-01",
            "name": "Inverter Listing Required",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.inverter_model",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Inverter model number is missing. UL 1741 listing cannot be verified.",
            "reference": "NEC 110.3(B), 690.4(C)",
            "fix_suggestion": "Add inverter model number and UL 1741-SA listing to spec sheet."
        },
        {
            "id": "NEC690.31-01",
            "name": "Wire Gauge Present",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.wire_gauge_awg",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Wire gauge not specified on plans.",
            "reference": "NEC 690.31",
            "fix_suggestion": "Annotate wire gauge (e.g., 10 AWG, 12 AWG) on single-line diagram."
        },
        {
            "id": "NEC250-01",
            "name": "Grounding Method Specified",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": None,
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.grounding_method",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "System grounding method not specified.",
            "reference": "NEC 250, 690.43",
            "fix_suggestion": "Specify grounding electrode conductor size and connection point."
        },
        # --- Structural Rules ---
        {
            "id": "IBC1607-01",
            "name": "Structural Load Check",
            "category": "structural",
            "severity": "critical",
            "jurisdictions": None,
            "nec_editions": None,
            "field_path": "structural.structural_load_limit_psf",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Structural load limit is missing. Cannot verify roof can support array.",
            "reference": "IBC 1607, ASCE 7",
            "fix_suggestion": "Add structural engineer stamp or load calculation."
        },
        {
            "id": "FIRE-SETBACK-01",
            "name": "Fire Setback Distance",
            "category": "fire_safety",
            "severity": "critical",
            "jurisdictions": None,
            "nec_editions": None,
            "field_path": "structural.setback_distance_inches",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Fire setback distance not specified on plans.",
            "reference": "IBC 1204, IRC R324, local fire marshal requirements",
            "fix_suggestion": "Annotate fire setbacks (typically 18\"-36\" from ridge/hip) on roof plan."
        },
        {
            "id": "FIRE-RIDGE-01",
            "name": "Ridge Setback Minimum",
            "category": "fire_safety",
            "severity": "major",
            "jurisdictions": None,
            "nec_editions": None,
            "field_path": "structural.ridge_setback_inches",
            "condition_type": "gte",
            "expected_value": json.dumps(18.0),
            "error_message": "Ridge setback is less than 18 inches.",
            "reference": "IRC R324.4.1, IBC 1204",
            "fix_suggestion": "Increase ridge setback to at least 18 inches."
        },
        {
            "id": "MOUNT-ATTACH-01",
            "name": "Roof Attachment Method",
            "category": "structural",
            "severity": "major",
            "jurisdictions": None,
            "nec_editions": None,
            "field_path": "structural.attachment_method",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Roof attachment method not specified.",
            "reference": "IRC R905, manufacturer installation instructions",
            "fix_suggestion": "Specify lag bolt size, embedment depth, and flashing method."
        },
        {
            "id": "WIND-LOAD-01",
            "name": "Wind Speed Design",
            "category": "structural",
            "severity": "major",
            "jurisdictions": None,
            "nec_editions": None,
            "field_path": "structural.max_wind_speed_mph",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Design wind speed not specified.",
            "reference": "ASCE 7-22, IBC 1609",
            "fix_suggestion": "Add design wind speed from local wind map to structural notes."
        },
        # --- California Rules ---
        {
            "id": "LA-CITY-01",
            "name": "LA City: Structural Engineer Stamp",
            "category": "documentation",
            "severity": "critical",
            "jurisdictions": json.dumps(["Los Angeles", "City of Los Angeles"]),
            "nec_editions": None,
            "field_path": "structural.structural_load_limit_psf",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "LA City requires a structural engineer stamp for all rooftop solar installations.",
            "reference": "LADBS Information Bulletin P/BC 2020-069",
            "fix_suggestion": "Obtain structural engineering letter or stamp from a California-licensed PE."
        },
        {
            "id": "CA-SDI-01",
            "name": "California: SDI Electrical Compliance",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["California", "CA"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.interconnection_type",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "California requires explicit interconnection method (supply-side vs load-side).",
            "reference": "California Electrical Code, CPUC Rule 21",
            "fix_suggestion": "Annotate supply-side or load-side connection on single-line diagram."
        },
        {
            "id": "CA-Title24-01",
            "name": "California: Title 24 Compliance",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["California", "CA"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.afci_protection",
            "condition_type": "eq",
            "expected_value": json.dumps(True),
            "error_message": "California Title 24 requires AFCI protection for solar PV systems.",
            "reference": "California Title 24, Part 6, JA7",
            "fix_suggestion": "Ensure AFCI protection is specified (inverter-integrated or external)."
        },
        {
            "id": "SD-CITY-01",
            "name": "San Diego: Fire Dept Approval",
            "category": "fire_safety",
            "severity": "critical",
            "jurisdictions": json.dumps(["San Diego", "City of San Diego"]),
            "nec_editions": None,
            "field_path": "structural.setback_distance_inches",
            "condition_type": "gte",
            "expected_value": json.dumps(36.0),
            "error_message": "San Diego requires 36-inch setbacks from all roof edges for commercial buildings.",
            "reference": "San Diego Fire-Rescue Department, Solar PV Guideline",
            "fix_suggestion": "Increase setbacks to 36 inches or obtain SDFD variance."
        },
        # --- New York Rules ---
        {
            "id": "NYC-01",
            "name": "NYC: FDNY Fire Safety Plan",
            "category": "fire_safety",
            "severity": "critical",
            "jurisdictions": json.dumps(["New York City", "NYC", "City of New York"]),
            "nec_editions": None,
            "field_path": "structural.setback_distance_inches",
            "condition_type": "gte",
            "expected_value": json.dumps(36.0),
            "error_message": "NYC FDNY requires 36-inch setbacks from all roof edges.",
            "reference": "FDNY Fire Code, NYC Building Code 1504.2",
            "fix_suggestion": "Increase all setbacks to 36 inches or obtain FDNY variance."
        },
        {
            "id": "NYC-02",
            "name": "NYC: Registered Design Professional",
            "category": "documentation",
            "severity": "critical",
            "jurisdictions": json.dumps(["New York City", "NYC", "City of New York"]),
            "nec_editions": None,
            "field_path": "structural.structural_load_limit_psf",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "NYC requires stamped structural drawings from a NYS-registered design professional.",
            "reference": "NYC Building Code 1704, 1609",
            "fix_suggestion": "Obtain structural engineering stamp from a NYS-licensed PE or RA."
        },
        # --- Florida Rules ---
        {
            "id": "FL-MIAMI-01",
            "name": "Miami-Dade: HVHZ Product Approval",
            "category": "structural",
            "severity": "critical",
            "jurisdictions": json.dumps(["Miami", "Miami-Dade", "City of Miami"]),
            "nec_editions": None,
            "field_path": "structural.max_wind_speed_mph",
            "condition_type": "gte",
            "expected_value": json.dumps(170.0),
            "error_message": "Miami-Dade HVHZ requires product approval for 170+ mph wind speeds.",
            "reference": "Miami-Dade County Code, Florida Building Code TAS 201",
            "fix_suggestion": "Verify all components have Miami-Dade NOA or Florida Product Approval."
        },
        {
            "id": "FL-BATTERY-01",
            "name": "Florida: Battery Storage Requirements",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["Florida", "FL", "Miami", "Tampa", "Orlando"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.inverter_type",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Florida requires battery storage systems to meet UL 9540 and UL 1973.",
            "reference": "Florida Building Code 609, NEC 706",
            "fix_suggestion": "If battery storage is included, provide UL 9540 test reports and installation manual."
        },
        # --- Texas Rules ---
        {
            "id": "TX-ERCOT-01",
            "name": "Texas: ERCOT Interconnection",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["Texas", "TX", "Austin", "Houston", "Dallas"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.interconnection_type",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Texas ERCOT requires interconnection agreement and IEEE 1547 compliance.",
            "reference": "ERCOT Interconnection Guide, IEEE 1547-2018",
            "fix_suggestion": "Submit ERCOT interconnection application and IEEE 1547 test results."
        },
        {
            "id": "TX-WIND-01",
            "name": "Texas: Wind Load Design",
            "category": "structural",
            "severity": "major",
            "jurisdictions": json.dumps(["Texas", "TX"]),
            "nec_editions": None,
            "field_path": "structural.max_wind_speed_mph",
            "condition_type": "gte",
            "expected_value": json.dumps(115.0),
            "error_message": "Texas requires minimum 115 mph design wind speed for solar installations.",
            "reference": "Texas Administrative Code Title 16, IBC 1609",
            "fix_suggestion": "Verify design wind speed meets local requirements (typically 115-140 mph)."
        },
        # --- Arizona Rules ---
        {
            "id": "AZ-SETBACK-01",
            "name": "Arizona: Fire Setback Requirements",
            "category": "fire_safety",
            "severity": "critical",
            "jurisdictions": json.dumps(["Arizona", "AZ", "Phoenix", "Tucson"]),
            "nec_editions": None,
            "field_path": "structural.setback_distance_inches",
            "condition_type": "gte",
            "expected_value": json.dumps(18.0),
            "error_message": "Arizona requires minimum 18-inch setbacks from all roof edges.",
            "reference": "Arizona Fire Code, IFC 605",
            "fix_suggestion": "Ensure setbacks meet minimum 18-inch requirement."
        },
        {
            "id": "AZ-HEAT-01",
            "name": "Arizona: High Temperature Derating",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["Arizona", "AZ", "Phoenix", "Tucson"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.wire_gauge_awg",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Arizona high temperatures require conductor ampacity derating per NEC 310.15.",
            "reference": "NEC 310.15, Phoenix ambient 115°F design",
            "fix_suggestion": "Verify conductor ampacity at 75°C or 90°C rating for ambient conditions."
        },
        # --- Nevada Rules ---
        {
            "id": "NV-SEISMIC-01",
            "name": "Nevada: Seismic Bracing",
            "category": "structural",
            "severity": "critical",
            "jurisdictions": json.dumps(["Nevada", "NV", "Las Vegas", "Reno"]),
            "nec_editions": None,
            "field_path": "structural.attachment_method",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Nevada seismic zones require seismic bracing for solar arrays.",
            "reference": "Nevada Administrative Code, IBC 1613, ASCE 7",
            "fix_suggestion": "Provide seismic bracing details and calculations per ASCE 7 Chapter 13."
        },
        # --- Colorado Rules ---
        {
            "id": "CO-SNOW-01",
            "name": "Colorado: Snow Load Design",
            "category": "structural",
            "severity": "major",
            "jurisdictions": json.dumps(["Colorado", "CO", "Denver", "Boulder"]),
            "nec_editions": None,
            "field_path": "structural.max_snow_load_psf",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Colorado requires snow load calculations for solar arrays.",
            "reference": "Colorado Building Code, IBC 1608, ASCE 7-22",
            "fix_suggestion": "Provide snow load calculations per ASCE 7-22 Section 7."
        },
        # --- Massachusetts Rules ---
        {
            "id": "MA-SMART-01",
            "name": "Massachusetts: SMART Program",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["Massachusetts", "MA", "Boston"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.system_size_kw_ac",
            "condition_type": "lte",
            "expected_value": json.dumps(5000.0),
            "error_message": "Massachusetts SMART program has capacity limits.",
            "reference": "Massachusetts SMART Program, 225 CMR 14.00",
            "fix_suggestion": "Verify system qualifies for SMART program incentives."
        },
        # --- New Jersey Rules ---
        {
            "id": "NJ-SREC-01",
            "name": "New Jersey: SREC-II Registration",
            "category": "documentation",
            "severity": "major",
            "jurisdictions": json.dumps(["New Jersey", "NJ"]),
            "nec_editions": None,
            "field_path": "electrical.system_size_kw_dc",
            "condition_type": "lte",
            "expected_value": json.dumps(5000.0),
            "error_message": "New Jersey SREC-II program requires registration for systems over 1 MW.",
            "reference": "New Jersey Board of Public Utilities, SREC-II",
            "fix_suggestion": "Register system with NJ SREC-II program if applicable."
        },
        # --- Illinois Rules ---
        {
            "id": "IL-NETMETER-01",
            "name": "Illinois: Net Metering Agreement",
            "category": "electrical",
            "severity": "major",
            "jurisdictions": json.dumps(["Illinois", "IL", "Chicago"]),
            "nec_editions": json.dumps(["2020", "2023"]),
            "field_path": "electrical.interconnection_type",
            "condition_type": "exists",
            "expected_value": None,
            "error_message": "Illinois requires net metering agreement with utility.",
            "reference": "Illinois Commerce Commission, 220 ILCS 5/16-107.5",
            "fix_suggestion": "Submit net metering application to ComEd or local utility."
        },
        # --- Hawaii Rules ---
        {
            "id": "HI-HURRICANE-01",
            "name": "Hawaii: Hurricane Resistance",
            "category": "structural",
            "severity": "critical",
            "jurisdictions": json.dumps(["Hawaii", "HI", "Honolulu"]),
            "nec_editions": None,
            "field_path": "structural.max_wind_speed_mph",
            "condition_type": "gte",
            "expected_value": json.dumps(130.0),
            "error_message": "Hawaii requires 130+ mph wind design for hurricane zones.",
            "reference": "Hawaii State Building Code, IBC 1609",
            "fix_suggestion": "Design for minimum 130 mph wind speed per Hawaii hurricane requirements."
        },
    ]

    c.execute("SELECT COUNT(*) FROM rules")
    if c.fetchone()[0] == 0:
        for rule in seeds:
            c.execute("""
                INSERT INTO rules (id, name, category, severity, jurisdictions, nec_editions,
                    field_path, condition_type, expected_value, error_message, reference, fix_suggestion)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                rule["id"], rule["name"], rule["category"], rule["severity"],
                rule["jurisdictions"], rule["nec_editions"],
                rule["field_path"], rule["condition_type"], rule["expected_value"],
                rule["error_message"], rule["reference"], rule["fix_suggestion"]
            ))
        conn.commit()
    conn.close()


def get_applicable_rules(jurisdiction: Optional[str] = None, nec_edition: Optional[str] = None) -> List[dict]:
    """Load rules applicable to a given jurisdiction and NEC edition."""
    init_db()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute("SELECT * FROM rules")
    all_rules = [dict(row) for row in c.fetchall()]
    conn.close()

    applicable = []
    for rule in all_rules:
        # Check jurisdiction match (NULL = universal)
        if rule["jurisdictions"] is not None:
            jurs = json.loads(rule["jurisdictions"])
            if jurisdiction and jurisdiction not in jurs:
                continue

        # Check NEC edition match (NULL = universal)
        if rule["nec_editions"] is not None and nec_edition:
            nec_list = json.loads(rule["nec_editions"])
            if nec_edition not in nec_list:
                continue

        applicable.append(rule)

    return applicable


def _get_nested_value(obj: Any, path: str) -> Any:
    """Get a nested attribute value using dot notation."""
    parts = path.split(".")
    for part in parts:
        if obj is None:
            return None
        if isinstance(obj, dict):
            obj = obj.get(part)
        else:
            obj = getattr(obj, part, None)
    return obj


def evaluate_rule(rule: dict, doc: PermitDocument) -> Optional[ComplianceViolation]:
    """Evaluate a single rule against a permit document. Returns a violation if failed."""
    
    # --- Context-aware rule skipping ---
    mounting_type = (doc.structural.mounting_type or "").lower()
    roof_type = (doc.structural.roof_type or "").lower()
    
    # Skip roof-specific rules for ground mounts
    if mounting_type in ["ground-mounted", "ground mount", "ground_mount"]:
        if rule["id"] in ["IBC1607-01", "FIRE-RIDGE-01", "MOUNT-ATTACH-01", "FIRE-SETBACK-01"]:
            return None
    
    # Skip ridge setback for flat roofs or N/A
    if rule["id"] == "FIRE-RIDGE-01":
        if any(x in roof_type for x in ["flat", "epdm", "tpo", "membrane", "n/a"]):
            return None
        ridge_val = _get_nested_value(doc, "structural.ridge_setback_inches")
        if ridge_val is not None and not isinstance(ridge_val, (int, float)):
            # Has a string value like "N/A" or "Not applicable" - skip
            return None
    
    # Skip structural load for ground mounts
    if rule["id"] == "IBC1607-01" and "ground" in mounting_type:
        return None
    
    # Skip system size limit for commercial (arbitrary threshold > 50kW)
    if rule["id"] == "NEC690.7-01":
        dc_size = doc.electrical.system_size_kw_dc
        if dc_size is not None and dc_size > 50:
            # Commercial system - skip residential limit
            return None
    
    value = _get_nested_value(doc, rule["field_path"])
    condition = rule["condition_type"]
    expected = json.loads(rule["expected_value"]) if rule["expected_value"] is not None else None

    passed = False
    if condition == "exists":
        passed = value is not None and value != ""
    elif condition == "eq":
        passed = value == expected
    elif condition == "ne":
        passed = value != expected
    elif condition == "gt":
        passed = isinstance(value, (int, float)) and value > expected
    elif condition == "gte":
        # For numeric comparisons, pass if value is not a number (e.g., "N/A", "Not applicable")
        # This handles cases like flat roofs where ridge setback is not applicable
        if not isinstance(value, (int, float)):
            passed = value is not None and value != ""  # Has some value = pass
        else:
            passed = value >= expected
    elif condition == "lt":
        passed = isinstance(value, (int, float)) and value < expected
    elif condition == "lte":
        passed = isinstance(value, (int, float)) and value <= expected
    elif condition == "in":
        passed = value in expected if isinstance(expected, list) else False
    else:
        passed = True  # Unknown condition = pass

    if passed:
        return None

    return ComplianceViolation(
        rule_id=rule["id"],
        category=rule["category"],
        severity=ViolationSeverity(rule["severity"]),
        field=rule["field_path"],
        message=rule["error_message"],
        expected_value=str(expected) if expected is not None else None,
        actual_value=str(value) if value is not None else "MISSING",
        reference=rule["reference"],
        fix_suggestion=rule["fix_suggestion"]
    )


def validate_document(doc: PermitDocument) -> List[ComplianceViolation]:
    """Run all applicable rules against a permit document."""
    jurisdiction = doc.site_info.jurisdiction_name
    nec = doc.site_info.nec_edition
    rules = get_applicable_rules(jurisdiction, nec)

    violations = []
    for rule in rules:
        v = evaluate_rule(rule, doc)
        if v:
            violations.append(v)
    return violations
