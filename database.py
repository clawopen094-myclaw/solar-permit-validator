"""
Persistent storage for solar permit validation projects.
SQLite database with project history, API key auth, and audit logging.
"""

import sqlite3
import uuid
import secrets
import hashlib
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

DB_PATH = Path(__file__).parent / "permits.db"


def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_project_db():
    """Initialize project and auth tables."""
    conn = _get_conn()
    c = conn.cursor()

    # Projects table
    c.execute("""
        CREATE TABLE IF NOT EXISTS projects (
            id TEXT PRIMARY KEY,
            name TEXT,
            jurisdiction TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            overall_status TEXT,
            pass_rate REAL,
            violation_count INTEGER DEFAULT 0,
            raw_json TEXT
        )
    """)

    # Violations table (linked to projects)
    c.execute("""
        CREATE TABLE IF NOT EXISTS project_violations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id TEXT NOT NULL,
            rule_id TEXT NOT NULL,
            category TEXT,
            severity TEXT,
            message TEXT,
            fix_suggestion TEXT,
            reference TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id)
        )
    """)

    # API keys table
    c.execute("""
        CREATE TABLE IF NOT EXISTS api_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key_hash TEXT UNIQUE NOT NULL,
            name TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_used_at TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


def verify_api_key(api_key: str) -> bool:
    """Verify an API key against stored hashes."""
    if not api_key:
        return False
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT 1 FROM api_keys WHERE key_hash = ? AND is_active = 1", (key_hash,))
    result = c.fetchone() is not None
    if result:
        c.execute("UPDATE api_keys SET last_used_at = CURRENT_TIMESTAMP WHERE key_hash = ?", (key_hash,))
        conn.commit()
    conn.close()
    return result


def create_api_key(name: str = None) -> str:
    """Generate a new API key. Returns the plaintext key (store it!)."""
    api_key = "spv_" + secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(api_key.encode()).hexdigest()
    conn = _get_conn()
    c = conn.cursor()
    c.execute(
        "INSERT INTO api_keys (key_hash, name) VALUES (?, ?)",
        (key_hash, name)
    )
    conn.commit()
    conn.close()
    return api_key


def list_api_keys() -> List[Dict[str, Any]]:
    """List all API keys (without hashes)."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT id, name, is_active, created_at, last_used_at FROM api_keys ORDER BY created_at DESC")
    keys = [dict(row) for row in c.fetchall()]
    conn.close()
    return keys


def save_project(project_id: str, name: str, jurisdiction: str,
                 status: str, pass_rate: float, violations: List[Dict],
                 raw_json: str = None) -> str:
    """Save a validation result as a project."""
    conn = _get_conn()
    c = conn.cursor()

    # Upsert project
    c.execute("""
        INSERT INTO projects (id, name, jurisdiction, overall_status, pass_rate, violation_count, raw_json)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            jurisdiction = excluded.jurisdiction,
            overall_status = excluded.overall_status,
            pass_rate = excluded.pass_rate,
            violation_count = excluded.violation_count,
            raw_json = excluded.raw_json,
            updated_at = CURRENT_TIMESTAMP
    """, (project_id, name, jurisdiction, status, pass_rate, len(violations), raw_json))

    # Clear old violations and insert new ones
    c.execute("DELETE FROM project_violations WHERE project_id = ?", (project_id,))
    for v in violations:
        c.execute("""
            INSERT INTO project_violations
            (project_id, rule_id, category, severity, message, fix_suggestion, reference)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            project_id, v.get("rule_id"), v.get("category"),
            v.get("severity"), v.get("message"),
            v.get("fix_suggestion"), v.get("reference")
        ))

    conn.commit()
    conn.close()
    return project_id


def get_project(project_id: str) -> Optional[Dict[str, Any]]:
    """Get a project by ID with its violations."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM projects WHERE id = ?", (project_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return None

    project = dict(row)
    c.execute("SELECT * FROM project_violations WHERE project_id = ? ORDER BY severity, created_at", (project_id,))
    project["violations"] = [dict(r) for r in c.fetchall()]
    conn.close()
    return project


def list_projects(limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    """List projects with violation counts."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT * FROM projects
        ORDER BY updated_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    projects = [dict(row) for row in c.fetchall()]
    conn.close()
    return projects


def delete_project(project_id: str) -> bool:
    """Delete a project and its violations."""
    conn = _get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM project_violations WHERE project_id = ?", (project_id,))
    c.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    deleted = c.rowcount > 0
    conn.commit()
    conn.close()
    return deleted


def get_stats() -> Dict[str, Any]:
    """Get aggregate statistics."""
    conn = _get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) as total FROM projects")
    total = c.fetchone()["total"]

    c.execute("SELECT COUNT(*) as passed FROM projects WHERE overall_status = 'PASS'")
    passed = c.fetchone()["passed"]

    c.execute("SELECT AVG(pass_rate) as avg FROM projects")
    avg_rate = c.fetchone()["avg"] or 0.0

    c.execute("SELECT COUNT(*) as total_v FROM project_violations")
    total_v = c.fetchone()["total_v"]

    c.execute("""
        SELECT severity, COUNT(*) as count
        FROM project_violations
        GROUP BY severity
        ORDER BY count DESC
    """)
    severity_breakdown = {r["severity"]: r["count"] for r in c.fetchall()}

    conn.close()
    return {
        "total_projects": total,
        "pass_count": passed,
        "fail_count": total - passed,
        "average_pass_rate": round(avg_rate, 1),
        "total_violations": total_v,
        "severity_breakdown": severity_breakdown
    }
