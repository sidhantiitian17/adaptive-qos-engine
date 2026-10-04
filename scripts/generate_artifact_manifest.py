#!/usr/bin/env python3
"""
Generates SHA-256 cryptographic manifest for all Phase 3.1 artifacts:
phase3_1_artifact_manifest.json
"""
import os
import sys
import hashlib
import json
import time
import subprocess

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARTIFACTS_DIR = os.path.join(PROJECT_ROOT, "phase3_artifacts")

def get_git_commit():
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, text=True).strip()
    except Exception:
        return "git:local-working-tree"

def compute_manifest():
    manifest = {
        "manifest_version": "1.0",
        "generated_at_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "source_git_commit": get_git_commit(),
        "artifacts_directory": ARTIFACTS_DIR,
        "files": []
    }
    
    files = sorted(os.listdir(ARTIFACTS_DIR))
    for f in files:
        full_p = os.path.join(ARTIFACTS_DIR, f)
        if os.path.isfile(full_p) and not f.endswith("artifact_manifest.json"):
            size = os.path.getsize(full_p)
            sha256 = hashlib.sha256()
            with open(full_p, "rb") as fp:
                while chunk := fp.read(65536):
                    sha256.update(chunk)
            digest = sha256.hexdigest()
            mtime = os.path.getmtime(full_p)
            manifest["files"].append({
                "filename": f,
                "size_bytes": size,
                "sha256": digest,
                "last_modified_utc": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime(mtime))
            })
            
    out_file = os.path.join(ARTIFACTS_DIR, "phase3_1_artifact_manifest.json")
    with open(out_file, "w") as fp:
        json.dump(manifest, fp, indent=2)
    print(f"[+] Artifact manifest generated with {len(manifest['files'])} entries -> phase3_1_artifact_manifest.json")
    return manifest

if __name__ == "__main__":
    compute_manifest()
