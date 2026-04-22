"""
Simple test script for the permit validator API.
Runs against a local server and prints the compliance report.

Usage:
    python test_api.py --file sample_permit.pdf --jurisdiction "Los Angeles"
"""

import argparse
import requests
import json
import sys


def test_validate(file_path: str, jurisdiction: str = None, project_id: str = None):
    url = "http://localhost:8000/validate_permit"
    files = {"file": open(file_path, "rb")}
    data = {}
    if jurisdiction:
        data["jurisdiction"] = jurisdiction
    if project_id:
        data["project_id"] = project_id

    print(f"Uploading {file_path} to {url}...")
    resp = requests.post(url, files=files, data=data)
    files["file"].close()

    if resp.status_code != 200:
        print(f"Error {resp.status_code}: {resp.text}")
        sys.exit(1)

    report = resp.json()
    print("\n" + "=" * 70)
    print(f"  PERMIT VALIDATION REPORT: {report['project_id']}")
    print("=" * 70)
    print(f"  AHJ:        {report['ahj_name']}")
    print(f"  Status:     {report['overall_status']}")
    print(f"  Pass Rate:  {report['pass_rate']}%")
    print(f"  Fix Time:   {report.get('estimated_fix_time_hours', 'N/A')} hours")
    print("-" * 70)

    if report["violations"]:
        print(f"  VIOLATIONS ({len(report['violations'])} total):")
        for v in report["violations"]:
            emoji = {"critical": "\u274c", "major": "\u26a0\ufe0f", "minor": "\ud83d\udcdd", "info": "\u2139\ufe0f"}.get(v["severity"], "?")
            print(f"\n    {emoji} [{v['severity'].upper()}] {v['rule_id']}")
            print(f"       Field: {v['field']}")
            print(f"       Issue: {v['message']}")
            if v.get("expected_value"):
                print(f"       Expected: {v['expected_value']} | Actual: {v['actual_value']}")
            print(f"       Fix: {v['fix_suggestion']}")
            print(f"       Ref: {v['reference']}")
    else:
        print("  \u2705 No violations found. Permit ready for submission!")

    print("\n" + "=" * 70)
    print(f"  SUMMARY: {report['summary']}")
    print("=" * 70)


def test_health():
    resp = requests.get("http://localhost:8000/health")
    print(f"Health: {resp.json()}")


def test_rules(jurisdiction: str = None):
    url = "http://localhost:8000/rules"
    params = {}
    if jurisdiction:
        params["jurisdiction"] = jurisdiction
    resp = requests.get(url, params=params)
    data = resp.json()
    print(f"Loaded {data['count']} rules")
    for r in data["rules"][:5]:
        print(f"  - [{r['id']}] {r['name']} ({r['severity']})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the Solar Permit Validator API")
    parser.add_argument("--file", help="PDF file to validate")
    parser.add_argument("--jurisdiction", help="Override jurisdiction")
    parser.add_argument("--project-id", help="Set project ID")
    parser.add_argument("--health", action="store_true", help="Check health endpoint")
    parser.add_argument("--rules", action="store_true", help="List loaded rules")

    args = parser.parse_args()

    if args.health:
        test_health()
    elif args.rules:
        test_rules(args.jurisdiction)
    elif args.file:
        test_validate(args.file, args.jurisdiction, args.project_id)
    else:
        test_health()
        test_rules(args.jurisdiction)
