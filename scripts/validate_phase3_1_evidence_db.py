#!/usr/bin/env python3
"""
Independent validation script: validate_phase3_1_evidence_db.py
Independently connects to experiments/evidence.db, executes relational integrity audits,
validates schema relationships, and asserts zero orphan records.
"""
import os
import sys
import sqlite3
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "experiments", "evidence.db")

def validate_evidence_db():
    assert os.path.exists(DB_PATH), f"Database not found at {DB_PATH}"
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() if r[0] != "sqlite_sequence"]
    counts = {t: cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tables}
    
    # Audit orphan records
    orphans = 0
    if "measurements" in tables and "experiments" in tables:
        orphans += cur.execute("""
            SELECT COUNT(*) FROM measurements 
            WHERE experiment_id NOT IN (SELECT experiment_id FROM experiments)
        """).fetchone()[0]
        
    if "policy_changes" in tables and "experiments" in tables:
        orphans += cur.execute("""
            SELECT COUNT(*) FROM policy_changes 
            WHERE experiment_id NOT IN (SELECT experiment_id FROM experiments)
        """).fetchone()[0]
        
    conn.close()
    
    report = {
        "db_path": DB_PATH,
        "tables": tables,
        "counts": counts,
        "orphan_records": orphans,
        "integrity_verified": (orphans == 0)
    }
    
    print("Database Integrity Report:")
    print(json.dumps(report, indent=2))
    assert orphans == 0, f"Integrity failure: {orphans} orphan records found!"
    print("[PASS] Independent Evidence DB Validation verified.")
    return report

if __name__ == "__main__":
    validate_evidence_db()
