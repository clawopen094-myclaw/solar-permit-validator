"""
Pydantic data models for solar permit validation.
Structured schemas that the LLM extracts from engineering documents.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from enum import Enum


class ElectricalSpec(BaseModel):
    """Electrical system specifications extracted from permit docs."""
    inverter_capacity_kw: Optional[float] = Field(None, description="Total inverter capacity in kW")
    inverter_quantity: Optional[int] = Field(None, description="Number of inverters")
    inverter_type: Optional[str] = Field(None, description="Type of inverter system (string, power_optimizer, micro, hybrid)")
    inverter_model: Optional[str] = Field(None, description="Inverter manufacturer model number")
    panel_capacity_w: Optional[float] = Field(None, description="Panel wattage rating")
    panel_quantity: Optional[int] = Field(None, description="Total number of panels")
    panel_model: Optional[str] = Field(None, description="Panel manufacturer model number")
    system_size_kw_dc: Optional[float] = Field(None, description="Total DC system size in kW")
    system_size_kw_ac: Optional[float] = Field(None, description="Total AC system size in kW")
    dc_ac_ratio: Optional[float] = Field(None, description="DC to AC ratio")
    wire_gauge_awg: Optional[str] = Field(None, description="Primary conductor wire gauge")
    wire_type: Optional[str] = Field(None, description="Wire type (THHN, XHHW, etc.)")
    conduit_size_inch: Optional[float] = Field(None, description="Conduit size in inches")
    ocpd_rating_a: Optional[float] = Field(None, description="Overcurrent protection device rating in amps")
    main_breaker_rating_a: Optional[float] = Field(None, description="Main breaker rating in amps")
    busbar_rating_a: Optional[float] = Field(None, description="Panel busbar rating in amps")
    grounding_method: Optional[str] = Field(None, description="System grounding method")
    interconnection_type: Optional[str] = Field(None, description="Supply-side or load-side interconnection")
    rapid_shutdown: Optional[bool] = Field(None, description="Rapid shutdown compliance per NEC 690.12")
    afci_protection: Optional[bool] = Field(None, description="AFCI protection per NEC 690.11")


class StructuralSpec(BaseModel):
    """Structural and mounting specifications."""
    mounting_type: Optional[str] = Field(None, description="Type of mounting system")
    roof_type: Optional[str] = Field(None, description="Type of roof covering")
    roof_age_years: Optional[int] = Field(None, description="Estimated roof age in years")
    roof_condition: Optional[str] = Field(None, description="Roof condition assessment")
    structural_load_limit_psf: Optional[float] = Field(None, description="Maximum structural load in psf")
    max_wind_speed_mph: Optional[int] = Field(None, description="Design wind speed in mph")
    max_snow_load_psf: Optional[float] = Field(None, description="Design snow load in psf")
    attachment_method: Optional[str] = Field(None, description="Roof attachment method")
    flashing_method: Optional[str] = Field(None, description="Flashing/waterproofing method")
    setback_distance_inches: Optional[float] = Field(None, description="Required fire setback distance in inches")
    ridge_setback_inches: Optional[float] = Field(None, description="Ridge setback distance in inches")
    hip_setback_inches: Optional[float] = Field(None, description="Hip/valley setback distance in inches")
    edge_setback_inches: Optional[float] = Field(None, description="Edge/rake setback distance in inches")
    rail_manufacturer: Optional[str] = Field(None, description="Mounting rail manufacturer")
    rail_model: Optional[str] = Field(None, description="Mounting rail model")


class SiteInfo(BaseModel):
    """Project site and jurisdiction information."""
    project_address: Optional[str] = Field(None, description="Project street address")
    city: Optional[str] = Field(None, description="City")
    state: Optional[str] = Field(None, description="State abbreviation")
    zip_code: Optional[str] = Field(None, description="ZIP code")
    jurisdiction_name: Optional[str] = Field(None, description="AHJ / municipality name")
    nec_edition: Optional[str] = Field(None, description="NEC edition year (2020, 2023, etc.)")
    ibc_edition: Optional[str] = Field(None, description="IBC edition year")
    utility_company: Optional[str] = Field(None, description="Electric utility company")
    service_voltage_v: Optional[int] = Field(None, description="Service voltage")
    service_amperage_a: Optional[int] = Field(None, description="Service amperage")


class PermitDocument(BaseModel):
    """Complete structured extraction from a solar permit document set."""
    site_info: SiteInfo = Field(default_factory=SiteInfo)
    electrical: ElectricalSpec = Field(default_factory=ElectricalSpec)
    structural: StructuralSpec = Field(default_factory=StructuralSpec)


class ViolationSeverity(str, Enum):
    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"
    INFO = "info"


class ComplianceViolation(BaseModel):
    """A single compliance issue found during validation."""
    rule_id: str = Field(..., description="Internal rule identifier")
    category: str = Field(..., description="Category: electrical, structural, fire_safety, documentation")
    severity: ViolationSeverity = Field(..., description="Severity level")
    field: str = Field(..., description="Which field violated the rule")
    message: str = Field(..., description="Human-readable violation description")
    expected_value: Optional[str] = Field(None, description="What the value should be")
    actual_value: Optional[str] = Field(None, description="What the value actually is")
    reference: str = Field(..., description="Code reference: NEC article, IBC section, AHJ rule")
    fix_suggestion: str = Field(..., description="Suggested correction")


class ComplianceReport(BaseModel):
    """Final compliance report output."""
    project_id: str = Field(..., description="Unique project identifier")
    ahj_name: str = Field(..., description="Authority Having Jurisdiction")
    overall_status: str = Field(..., description="PASS, FAIL, or NEEDS_REVIEW")
    pass_rate: float = Field(..., description="Percentage of rules passed (0-100)")
    violations: List[ComplianceViolation] = Field(default_factory=list)
    summary: str = Field(..., description="Executive summary of findings")
    estimated_fix_time_hours: Optional[float] = Field(None, description="Estimated time to fix all issues")

