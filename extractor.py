"""
Document extraction layer.
Converts PDFs to images and text, then uses Pydantic AI or mock extraction
to populate PermitDocument structured models.

For the MVP, a MOCK mode is included so the app runs without API keys.
Set LLM_PROVIDER in .env to 'gemini', 'openai', or 'mock'.
"""

import os
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional, List
from PIL import Image
import io

from models import PermitDocument, ElectricalSpec, StructuralSpec, SiteInfo

try:
    from pydantic_ai import Agent
    from pydantic_ai.models.gemini import GeminiModel
    from pydantic_ai.models.openai import OpenAIModel
    HAS_PYDANTIC_AI = True
except ImportError:
    HAS_PYDANTIC_AI = False

LLM_PROVIDER = os.getenv("LLM_PROVIDER", "mock")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")


def _get_gemini_keys() -> List[str]:
    """Collect all available Gemini API keys from env."""
    keys = []
    for k in ["GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3"]:
        v = os.getenv(k, "").strip()
        if v:
            keys.append(v)
    return keys

GEMINI_KEYS = _get_gemini_keys()

# Try to import pydantic-ai error type for quota detection
try:
    from pydantic_ai.exceptions import ModelHTTPError
    HAS_MODEL_HTTP_ERROR = True
except ImportError:
    HAS_MODEL_HTTP_ERROR = False


def pdf_to_images(pdf_bytes: bytes, dpi: int = 200) -> List[Image.Image]:
    """Convert PDF pages to PIL Images."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    images = []
    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        images.append(img)
    doc.close()
    return images


def extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract raw text from a PDF."""
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    text = ""
    for page in doc:
        text += page.get_text()
    doc.close()
    return text


def _mock_extract(text: str) -> PermitDocument:
    """
    Mock extraction for demo/testing without API keys.
    Attempts to pull values from the raw text using simple keyword matching.
    Falls back to a minimal demo document if nothing is found.
    """
    import re

    doc = PermitDocument(
        site_info=SiteInfo(),
        electrical=ElectricalSpec(),
        structural=StructuralSpec()
    )

    text_upper = text.upper()

    # Site info extraction
    zip_match = re.search(r'\b(\d{5}(-\d{4})?)\b', text)
    if zip_match:
        doc.site_info.zip_code = zip_match.group(1)

    state_match = re.search(r'\b(CA|TX|FL|NY|AZ|NV|CO|NC|NJ|IL|PA|OH|GA|MA|MD|WA|MN|UT|WI|MI|MO|IN|VA|CT|OR|TN|SC|LA|AL|KY|OK|KS|AR|IA|NE|NM|WV|HI|DE|DC|RI|VT|NH|ME|ND|SD|MT|WY|ID|AK)\b', text_upper)
    if state_match:
        doc.site_info.state = state_match.group(1)

    # Electrical extraction
    kw_match = re.search(r'(\d+\.?\d*)\s*(KW|KILOWATT)', text_upper)
    if kw_match:
        doc.electrical.system_size_kw_dc = float(kw_match.group(1))

    panel_match = re.search(r'(\d+)\s*(?:MODULE|S|PANEL)', text_upper)
    if panel_match:
        doc.electrical.panel_quantity = int(panel_match.group(1))

    inv_match = re.search(r'(\d+)\s*(?:INVERTER|INV)', text_upper)
    if inv_match:
        doc.electrical.inverter_quantity = int(inv_match.group(1))

    wire_match = re.search(r'(\d+)\s*AWG', text_upper)
    if wire_match:
        doc.electrical.wire_gauge_awg = wire_match.group(1) + " AWG"

    ocpd_match = re.search(r'(\d+)\s*A\s*(?:BREAKER|OCPD|FUSE)', text_upper)
    if ocpd_match:
        doc.electrical.ocpd_rating_a = float(ocpd_match.group(1))

    bus_match = re.search(r'(\d+)\s*A\s*(?:BU[SZ]BAR|BUS)', text_upper)
    if bus_match:
        doc.electrical.busbar_rating_a = float(bus_match.group(1))

    main_match = re.search(r'(\d+)\s*A\s*(?:MAIN|SERVICE)', text_upper)
    if main_match:
        doc.electrical.main_breaker_rating_a = float(main_match.group(1))

    # Structural extraction
    setback_match = re.search(r'(\d+\.?\d*)\s*["\u201d\u201d]\s*(?:SETBACK|CLEARANCE)', text_upper)
    if setback_match:
        doc.structural.setback_distance_inches = float(setback_match.group(1))

    wind_match = re.search(r'(\d+)\s*(?:MPH|MI/HR)', text_upper)
    if wind_match:
        doc.structural.max_wind_speed_mph = int(wind_match.group(1))

    # Check for rapid shutdown keywords
    if "RAPID SHUTDOWN" in text_upper or "RSD" in text_upper:
        doc.electrical.rapid_shutdown = True

    # Check for AFCI keywords
    if "AFCI" in text_upper:
        doc.electrical.afci_protection = True

    # Default NEC edition guess
    if "2023" in text or "NEC 2023" in text_upper:
        doc.site_info.nec_edition = "2023"
    elif "2020" in text or "NEC 2020" in text_upper:
        doc.site_info.nec_edition = "2020"
    else:
        doc.site_info.nec_edition = "2020"

    return doc


def _build_extraction_prompt(text: str) -> str:
    """Build the prompt for LLM extraction."""
    return f"""You are a solar permit document analyzer. Extract the following structured information from the engineering document text below.

Output a JSON object matching this schema:
{{
  "site_info": {{
    "project_address": "string or null",
    "city": "string or null",
    "state": "2-letter code or null",
    "zip_code": "string or null",
    "jurisdiction_name": "municipality name or null",
    "nec_edition": "2020, 2023, or null",
    "utility_company": "string or null",
    "service_voltage_v": "integer or null",
    "service_amperage_a": "integer or null"
  }},
  "electrical": {{
    "inverter_capacity_kw": "float or null",
    "inverter_quantity": "integer or null",
    "inverter_type": "string or null",
    "inverter_model": "string or null",
    "panel_capacity_w": "float or null",
    "panel_quantity": "integer or null",
    "panel_model": "string or null",
    "system_size_kw_dc": "float or null",
    "system_size_kw_ac": "float or null",
    "wire_gauge_awg": "string or null",
    "ocpd_rating_a": "float or null",
    "main_breaker_rating_a": "float or null",
    "busbar_rating_a": "float or null",
    "grounding_method": "string or null",
    "interconnection_type": "string or null",
    "rapid_shutdown": "boolean or null",
    "afci_protection": "boolean or null"
  }},
  "structural": {{
    "mounting_type": "string or null",
    "roof_type": "string or null",
    "structural_load_limit_psf": "float or null",
    "max_wind_speed_mph": "integer or null",
    "max_snow_load_psf": "float or null",
    "attachment_method": "string or null",
    "flashing_method": "string or null",
    "setback_distance_inches": "float or null",
    "ridge_setback_inches": "float or null",
    "edge_setback_inches": "float or null",
    "rail_manufacturer": "string or null"
  }}
}}

DOCUMENT TEXT:
{text[:12000]}

Respond with ONLY the JSON object. No markdown, no explanations."""


async def _llm_extract_with_key(text: str, api_key: str) -> PermitDocument:
    """Extract using a single Gemini API key."""
    from pydantic_ai.providers.google_gla import GoogleGLAProvider
    model = GeminiModel("gemini-3.1-flash-lite-preview", provider=GoogleGLAProvider(api_key=api_key))
    agent = Agent(model, output_type=PermitDocument)
    result = await agent.run(_build_extraction_prompt(text))
    return result.output


async def _llm_extract(text: str) -> PermitDocument:
    """Extract using Pydantic AI with configured LLM provider."""
    if not HAS_PYDANTIC_AI:
        raise RuntimeError("pydantic-ai not installed. Use mock mode.")

    if LLM_PROVIDER == "gemini":
        last_error = None
        for idx, key in enumerate(GEMINI_KEYS):
            try:
                return await _llm_extract_with_key(text, key)
            except Exception as e:
                err_str = str(e)
                # If it's a quota/rate-limit error, try next key
                is_quota = (
                    "429" in err_str
                    or "503" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "UNAVAILABLE" in err_str
                    or "quota" in err_str.lower()
                    or "rate limit" in err_str.lower()
                    or "high demand" in err_str.lower()
                )
                if is_quota and idx < len(GEMINI_KEYS) - 1:
                    continue
                last_error = e
        if last_error:
            raise last_error
        raise RuntimeError("No Gemini API keys configured. Set GEMINI_API_KEY in .env")

    elif LLM_PROVIDER == "openai" and OPENAI_API_KEY:
        model = OpenAIModel("gpt-4o", api_key=OPENAI_API_KEY)
        agent = Agent(model, output_type=PermitDocument)
        result = await agent.run(_build_extraction_prompt(text))
        return result.output
    else:
        raise RuntimeError(f"LLM provider '{LLM_PROVIDER}' not configured. Set API key in .env")


async def extract_permit_data(pdf_bytes: bytes) -> PermitDocument:
    """
    Main entry point: extract structured data from a permit PDF.

    Strategy:
    1. Extract raw text from PDF
    2. If MOCK mode: use keyword extraction
    3. If LLM mode: try each configured API key in order;
       if all fail due to quota, fallback to mock extraction.
    """
    text = extract_pdf_text(pdf_bytes)

    if LLM_PROVIDER == "mock":
        return _mock_extract(text)

    try:
        return await _llm_extract(text)
    except Exception as e:
        err_str = str(e)
        is_quota = (
            "429" in err_str
            or "503" in err_str
            or "RESOURCE_EXHAUSTED" in err_str
            or "UNAVAILABLE" in err_str
            or "quota" in err_str.lower()
            or "high demand" in err_str.lower()
        )
        if is_quota:
            import logging
            logging.warning("All Gemini keys rate-limited. Falling back to mock extraction.")
            return _mock_extract(text)
        raise
