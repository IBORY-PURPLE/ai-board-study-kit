#!/usr/bin/env python
"""강의 PDF의 특정 슬라이드 바로 다음에 해설 PDF 쪽을 끼워 넣는다 (PyMuPDF).

사용 (볼트 폴더에서 실행):
  python -I .tools/insert_pages.py <강의.pdf> --after <쪽> --src <해설.pdf> [--out <새파일.pdf>]

- <쪽>은 1부터 센다. --after 0이면 맨 앞에 넣는다.
- --out이 없으면 강의 PDF를 직접 고친다. 고치기 전에 원본을 `_pdf_원본백업/`에 같은 상대 경로로 한 번 복사한다.
- 결과는 JSON으로 출력한다: 넣은 쪽 범위(inserted_pages), 바뀐 총 쪽수(page_count).
  끼워 넣은 뒤에는 뒤쪽 슬라이드의 PDF 쪽 번호가 밀리므로, 링크를 만들 때는 이 값을 다시 확인한다.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import fitz  # PyMuPDF

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

VAULT = Path(__file__).resolve().parent.parent
BACKUP_DIR = VAULT / "_pdf_원본백업"


def die(msg):
    print(f"오류: {msg}", file=sys.stderr)
    sys.exit(1)


def in_vault(p):
    p = (VAULT / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
    try:
        p.relative_to(VAULT)
    except ValueError:
        die(f"볼트 밖 파일은 다루지 않습니다: {p}")
    if BACKUP_DIR in p.parents:
        die("백업 폴더 안의 PDF는 고치지 않습니다.")
    return p


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("pdf")
    ap.add_argument("--after", type=int, required=True)
    ap.add_argument("--src", required=True)
    ap.add_argument("--out")
    a = ap.parse_args()

    target, src = in_vault(a.pdf), in_vault(a.src)
    if not target.is_file() or not src.is_file():
        die("PDF 파일을 찾지 못했습니다.")
    doc, add = fitz.open(target), fitz.open(src)
    if not 0 <= a.after <= doc.page_count:
        die(f"--after는 0~{doc.page_count} 사이여야 합니다.")

    backup = None
    if not a.out:
        dest = BACKUP_DIR / target.relative_to(VAULT)
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(target, dest)
            backup = str(dest.relative_to(VAULT))

    doc.insert_pdf(add, start_at=a.after)
    out = in_vault(a.out) if a.out else target
    tmp = out.with_suffix(".pdf.tmp")
    doc.save(str(tmp), garbage=3, deflate=True)
    n = doc.page_count
    doc.close()
    tmp.replace(out)
    print(json.dumps({
        "pdf": str(out.relative_to(VAULT)).replace("\\", "/"),
        "inserted_pages": [a.after + 1, a.after + add.page_count],
        "page_count": n,
        "backup_created": backup,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
