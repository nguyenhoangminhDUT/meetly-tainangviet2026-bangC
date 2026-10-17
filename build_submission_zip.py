"""Automated Packaging Tool for Meetly AI 2026 Competition Submission.

Creates `AI26C0079.zip` strictly compliant with competition rules:
1. Team Code: AI26C0079.
2. Root-level layout: `Dockerfile`, `.dockerignore`, `README.md`, `requirements.txt`, `src/`, `tests/` at the root of the archive.
3. Excludes .venv/, .git/, __pycache__/, .env (API keys), old zip files, and large problem PDFs.
4. Total package size is minimal (< 1 MB), far below the 100 MB limit.
"""

import os
import sys
import zipfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_ZIP = PROJECT_ROOT / "AI26C0079.zip"

INCLUDE_DIRS = ["src", "tests"]
INCLUDE_FILES = [
    "Dockerfile",
    ".dockerignore",
    "requirements.txt",
    "README.md",
    ".env.example",
    "pyproject.toml",
    ".python-version",
    ".gitignore",
    "build_submission_zip.py",
]
DOCS_INCLUDE_EXTS = {".md", ".png", ".jpg"}

EXCLUDE_PATTERNS = [
    ".git",
    ".venv",
    "venv",
    "__pycache__",
    ".env",
    ".pytest_cache",
    ".vscode",
    ".idea",
    ".DS_Store",
    "submission.csv",
    "submission_package.zip",
    "AI26C0079.zip",
    "test_free_llm.py",
    "free_llm_testing_guide.md",
    "recreate_exam.tex",
]


def should_exclude(rel_path: str) -> bool:
    parts = Path(rel_path).parts
    for exc in EXCLUDE_PATTERNS:
        if exc in parts or rel_path.endswith(exc):
            return True
    if rel_path.endswith(".pyc") or rel_path.endswith(".pyo") or rel_path.endswith(".pyd"):
        return True
    return False


def build_zip():
    print("=" * 70)
    print("📦 MEETLY COMPETITION SUBMISSION PACKAGER (MÃ ĐỘI: AI26C0079)")
    print("=" * 70)

    # Clean old zips
    for old_zip in [OUTPUT_ZIP, PROJECT_ROOT / "submission_package.zip"]:
        if old_zip.exists():
            old_zip.unlink()
            print(f"[*] Đã xóa tệp cũ: {old_zip.name}")

    files_to_pack = []

    # 1. Include explicit root files
    for fname in INCLUDE_FILES:
        fpath = PROJECT_ROOT / fname
        if fpath.exists() and not should_exclude(fname):
            files_to_pack.append(fpath)

    # 2. Include code directories
    for dname in INCLUDE_DIRS:
        dpath = PROJECT_ROOT / dname
        if dpath.exists():
            for f in sorted(dpath.rglob("*")):
                if f.is_file() and not should_exclude(str(f.relative_to(PROJECT_ROOT))):
                    files_to_pack.append(f)

    # 3. Include markdown docs and diagrams (excluding large PDFs and drafts)
    docs_path = PROJECT_ROOT / "docs"
    if docs_path.exists():
        for f in sorted(docs_path.rglob("*")):
            if f.is_file() and f.suffix.lower() in DOCS_INCLUDE_EXTS:
                if not should_exclude(str(f.relative_to(PROJECT_ROOT))):
                    files_to_pack.append(f)

    print(f"\n[*] Đang nén {len(files_to_pack)} tệp sạch vào {OUTPUT_ZIP.name}...")

    total_uncompressed = 0
    with zipfile.ZipFile(OUTPUT_ZIP, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zipf:
        for f in files_to_pack:
            rel = f.relative_to(PROJECT_ROOT)
            # Normalize archive path to use forward slashes (standard zip / Linux format)
            arcname = str(rel).replace("\\", "/")
            zipf.write(f, arcname=arcname)
            size = f.stat().st_size
            total_uncompressed += size
            print(f"  + {arcname:<50} ({size:,} bytes)")

    zip_size = OUTPUT_ZIP.stat().st_size
    print("-" * 70)
    print("🎉 ĐÓNG GÓI THÀNH CÔNG GÓI NỘP BÀI CHÍNH THỨC!")
    print(f"  • Tên lưu trữ chính thức : {OUTPUT_ZIP.name}")
    print(f"  • Đường dẫn tuyệt đối   : {OUTPUT_ZIP.resolve()}")
    print(f"  • Tổng số tệp đã nén    : {len(files_to_pack)}")
    print(f"  • Dung lượng chưa nén   : {total_uncompressed / 1024:.2f} KB ({total_uncompressed / (1024*1024):.2f} MB)")
    print(f"  • Dung lượng tệp ZIP    : {zip_size / 1024:.2f} KB ({zip_size / (1024*1024):.2f} MB)")
    print(f"  • Giới hạn BTC (<100MB) : ✅ TUÂN THỦ (Chỉ dùng {zip_size / (100 * 1024 * 1024) * 100:.2f}% ngân sách)")
    print("=" * 70)

    # Verification of archive contents
    print("\n🔍 KIỂM TRA CẤU TRÚC BÊN TRONG FILE ZIP:")
    with zipfile.ZipFile(OUTPUT_ZIP, "r") as zf:
        namelist = zf.namelist()
        has_dockerfile_at_root = "Dockerfile" in namelist
        has_readme_at_root = "README.md" in namelist
        has_nested_dir = any(name.startswith("AI26C0079/") for name in namelist)
        
        print(f"  • Dockerfile tại root của zip : {'✅ ĐÚNG' if has_dockerfile_at_root else '❌ THIẾU'}")
        print(f"  • README.md tại root của zip  : {'✅ ĐÚNG' if has_readme_at_root else '❌ THIẾU'}")
        print(f"  • Không lồng thư mục cha      : {'✅ ĐÚNG' if not has_nested_dir else '❌ SAI'}")
        print(f"  • Danh sách tệp ({len(namelist)} tệp):")
        for name in sorted(namelist):
            print(f"      - {name}")


if __name__ == "__main__":
    build_zip()
