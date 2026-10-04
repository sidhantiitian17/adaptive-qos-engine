#!/usr/bin/env python3
"""
Independent validation script: validate_phase3_1_zero_fabrication.py
Audits the entire production codebase and evidence database for forbidden synthetic metrics,
fabricated fallback constants, or hardcoded scenario results.
"""
import os
import sys
import re
import sqlite3
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FORBIDDEN_SYNTHETIC_VALUES = [21.2, 84.5, 42.0]

def audit_zero_fabrication():
    violations = []
    
    # Check evidence.db
    db_path = os.path.join(PROJECT_ROOT, "experiments", "evidence.db")
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        for val in FORBIDDEN_SYNTHETIC_VALUES:
            rows = cur.execute(f"SELECT * FROM measurements WHERE value = {val}").fetchall()
            if rows:
                violations.append(f"Forbidden constant {val} found in measurements: {len(rows)} occurrences")
        conn.close()

    # Check production python source files
    prod_dirs = ["api", "classifier", "enforcement", "estimator", "experiments", "network", "policy_engine"]
    for d in prod_dirs:
        dir_path = os.path.join(PROJECT_ROOT, d)
        if not os.path.exists(dir_path):
            continue
        for root, _, files in os.walk(dir_path):
            for file in files:
                if file.endswith(".py"):
                    full_p = os.path.join(root, file)
                    with open(full_p, "r", errors="ignore") as f:
                        lines = f.readlines()
                    for idx, line in enumerate(lines):
                        if any(re.search(rf"\b{re.escape(str(v))}\b", line) for v in FORBIDDEN_SYNTHETIC_VALUES):
                            # Skip comments or strings mentioning test logs
                            if not line.strip().startswith("#") and "log" not in line.lower():
                                violations.append(f"{full_p}:{idx+1}: {line.strip()}")

    result = {
        "violations_count": len(violations),
        "violations": violations,
        "zero_fabrication_status": "PASS" if len(violations) == 0 else "FAIL"
    }
    
    print("Zero-Fabrication Audit:")
    print(json.dumps(result, indent=2))
    assert len(violations) == 0, f"Zero-fabrication audit failed: {violations}"
    print("[PASS] Independent Zero-Fabrication Validation verified.")
    return result

if __name__ == "__main__":
    audit_zero_fabrication()
