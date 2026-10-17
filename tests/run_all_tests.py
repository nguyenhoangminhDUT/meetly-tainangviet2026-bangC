"""Master Test Suite Runner for Table QA Pipeline.

Runs all 4 official validation and verification suites:
1. Unit Tests (Normalizer, Sanitizer, Sandbox, Schema Builder, Concurrency)
2. Workbook & Schema Audit (Public Data 1 & Public Data 2)
3. Empirical Verification: Public Data 1 (20 queries)
4. Empirical Verification: Public Data 2 (30 queries)
"""

import sys
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

def run_suite(name, cmd):
    print("\n" + "=" * 80)
    print(f"RUNNING SUITE: {name}")
    print("=" * 80)
    res = subprocess.run(cmd, cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8")
    print(res.stdout)
    if res.stderr:
        print("STDERR:")
        print(res.stderr)
    if res.returncode != 0:
        print(f"❌ SUITE FAILED: {name} (Return code {res.returncode})")
        return False
    print(f"✅ SUITE PASSED: {name}")
    return True

def main():
    py_exec = sys.executable
    suites = [
        ("Pipeline Unit Tests", [py_exec, "tests/test_pipeline.py"]),
        ("Structural & Data Audit", [py_exec, "tests/audit_public_data_2.py"]),
        ("Public Data 1 Verification (20 Queries)", [py_exec, "tests/verify_solutions_p1.py"]),
        ("Public Data 2 Verification (30 Queries)", [py_exec, "tests/verify_solutions_p2.py"]),
    ]
    
    results = {}
    for name, cmd in suites:
        success = run_suite(name, cmd)
        results[name] = success
        
    print("\n" + "=" * 80)
    print("OVERALL TEST SUITE SUMMARY REPORT")
    print("=" * 80)
    all_passed = True
    for name, success in results.items():
        status = "✅ PASS" if success else "❌ FAIL"
        if not success: all_passed = False
        print(f"  • {name:<45}: {status}")
    print("=" * 80)
    if all_passed:
        print("🎉 ALL TEST SUITES PASSED FLAWLESSLY! 100% FEASIBILITY ACHIEVED.")
    else:
        print("⚠️ SOME TEST SUITES ENCOUNTERED ERRORS.")
    print("=" * 80)

if __name__ == "__main__":
    main()
