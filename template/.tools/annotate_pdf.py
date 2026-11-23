#!/usr/bin/env python
"""과목 볼트용 PDF 필기 도구 (PyMuPDF). 볼트 루트는 이 .tools 폴더의 상위 폴더다.

사용 (볼트 폴더에서 실행):
  python -I .tools/annotate_pdf.py current
  python -I .tools/annotate_pdf.py read  <pdf> <쪽> [--to <끝쪽>]
  python -I .tools/annotate_pdf.py list  <pdf> [--page <쪽>]
  python -I .tools/annotate_pdf.py add   <pdf> <쪽> --note "Q: ...\nA: ..." [--quote "하이라이트할 원문"] [--color yellow]
  python -I .tools/annotate_pdf.py label <pdf> <쪽> --text "★ 시험 출제: ..." [--size 14] [--y <위쪽 좌표> --x <왼쪽 좌표> --w <최대 폭>]
  python -I .tools/annotate_pdf.py table <pdf> <쪽> --spec <표.json> [--preview <미리보기.png>]
  python -I .tools/annotate_pdf.py remove <pdf> --xref <번호>

label은 슬라이드 위에 바로 보이는 빨간 글자 상자를 붙인다(빈 공간을 아래에서 위로 찾음).
결과의 covers_content가 true이면 빈 공간이 없어 맨 위에 겹쳐 붙은 것이므로 --y로 옮긴다.

<pdf>는 파일 이름(확장자 생략 가능) 또는 볼트 기준 상대 경로. 쪽 번호는 1부터.
PDF에 처음 쓰기 전에 원본을 볼트 루트의 `_pdf_원본백업/`에 같은 상대 경로로 한 번 복사해 둔다.
(예: `강의자료/03강.pdf` → `_pdf_원본백업/강의자료/03강.pdf`)
필기는 PDF 끝에 덧붙이는 방식(증분 저장)이라 기존 내용은 바뀌지 않는다.
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

import fitz  # PyMuPDF

VAULT = Path(__file__).resolve().parent.parent
BACKUP_NAME = "_pdf_원본백업"
BACKUP_DIR = VAULT / BACKUP_NAME
AUTHOR = "Claude"
SUBJECT = "Claude Q&A"
COLORS = {
    "yellow": (1.0, 0.92, 0.2),
    "green": (0.45, 0.85, 0.45),
    "blue": (0.45, 0.65, 1.0),
    "pink": (1.0, 0.6, 0.75),
    "orange": (1.0, 0.7, 0.3),
}


def die(msg, code=1):
    print(f"오류: {msg}", file=sys.stderr)
    sys.exit(code)


def out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def resolve_pdf(name):
    """볼트 안의 PDF만 허용한다. 이름만 주면 볼트 전체에서 찾는다."""
    cand = (VAULT / name)
    if cand.suffix.lower() != ".pdf":
        cand = cand.with_name(cand.name + ".pdf")
    found = []
    if cand.is_file():
        found = [cand]
    else:
        stem = Path(name).stem if name.lower().endswith(".pdf") else Path(name).name
        found = [p for p in VAULT.rglob("*.pdf")
                 if ".obsidian" not in p.parts and BACKUP_NAME not in p.parts
                 and p.stem == stem]
    if not found:
        die(f"볼트에서 PDF를 찾지 못했습니다: {name}")
    if len(found) > 1:
        die("같은 이름의 PDF가 여러 개입니다. 볼트 기준 상대 경로로 지정하세요: "
            + ", ".join(str(p.relative_to(VAULT)) for p in found))
    p = found[0].resolve()
    if VAULT.resolve() not in p.parents:
        die("볼트 밖의 파일은 다루지 않습니다.")
    if BACKUP_DIR.resolve() in p.parents:
        die("원본 백업 폴더의 PDF는 고치지 않습니다.")
    return p


def check_page(doc, page_no):
    if not 1 <= page_no <= doc.page_count:
        die(f"쪽 번호 {page_no}가 범위(1~{doc.page_count})를 벗어났습니다.")
    return doc[page_no - 1]


def ensure_backup(pdf):
    dest = BACKUP_DIR / pdf.relative_to(VAULT)
    if not dest.exists():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, dest)
        return str(dest)
    return None


def save(doc, pdf):
    """증분 저장을 우선하고, 안 되면 임시 파일을 거쳐 교체한다."""
    if doc.can_save_incrementally():
        doc.saveIncr()
        return "incremental"
    tmp = pdf.with_suffix(".pdf.tmp")
    doc.save(str(tmp), garbage=0, deflate=True)
    doc.close()
    tmp.replace(pdf)
    return "rewrite"


def cmd_current(_):
    ws_path = VAULT / ".obsidian" / "workspace.json"
    if not ws_path.is_file():
        die("workspace.json이 없습니다.")
    ws = json.loads(ws_path.read_text(encoding="utf-8"))
    leaves = []

    def walk(n):
        if isinstance(n, dict):
            if n.get("type") == "leaf" and n.get("state", {}).get("type") == "pdf":
                leaves.append(n)
            for v in n.values():
                walk(v)
        elif isinstance(n, list):
            for v in n:
                walk(v)

    walk(ws)
    active_id = ws.get("active")
    leaf = next((l for l in leaves if l.get("id") == active_id), leaves[0] if leaves else None)
    if not leaf:
        die("열려 있는 PDF를 workspace.json에서 찾지 못했습니다.")
    st = leaf["state"]["state"]
    out({
        "file": st.get("file"),
        "page": st.get("page"),
        "주의": "Obsidian이 마지막으로 저장한 값이라 쪽 번호가 실제와 다를 수 있습니다. 답변에 기준 쪽을 밝히고, 불확실하면 사용자에게 쪽 번호를 물으세요.",
    })


def cmd_read(a):
    pdf = resolve_pdf(a.pdf)
    doc = fitz.open(pdf)
    end = a.to or a.page
    for n in range(a.page, end + 1):
        page = check_page(doc, n)
        print(f"===== {pdf.name} p.{n}/{doc.page_count} =====")
        print(page.get_text("text").strip() or "(텍스트 없음: 이미지 슬라이드일 수 있음)")


def cmd_list(a):
    pdf = resolve_pdf(a.pdf)
    doc = fitz.open(pdf)
    rows = []
    for page in doc:
        if a.page and page.number + 1 != a.page:
            continue
        for an in page.annots() or []:
            info = an.info
            rows.append({
                "page": page.number + 1,
                "xref": an.xref,
                "type": an.type[1],
                "author": info.get("title", ""),
                "content": info.get("content", ""),
            })
    out(rows)


def cmd_add(a):
    pdf = resolve_pdf(a.pdf)
    doc = fitz.open(pdf)
    page = check_page(doc, a.page)
    note = a.note.replace("\\n", "\n")
    backup = ensure_backup(pdf)
    color = COLORS.get(a.color, COLORS["yellow"])
    kind, quote_found = None, None

    if a.quote:
        rects = page.search_for(a.quote)
        quote_found = bool(rects)
        if rects:
            annot = page.add_highlight_annot(quads=rects)
            annot.set_colors(stroke=color)
            kind = "highlight"
    if kind is None:
        mine = [x for x in (page.annots() or []) if x.info.get("subject") == SUBJECT
                and x.type[1] == "Text"]
        x = page.rect.x1 - 28
        y = page.rect.y0 + 10 + 24 * len(mine)
        annot = page.add_text_annot(fitz.Point(x, y), note, icon="Note")
        annot.set_colors(stroke=color)
        kind = "sticky-note"

    annot.set_info(title=AUTHOR, content=note, subject=SUBJECT)
    annot.update()
    mode = save(doc, pdf)
    out({"pdf": str(pdf.relative_to(VAULT)), "page": a.page, "type": kind,
         "xref": annot.xref, "quote_found": quote_found, "save": mode,
         "backup_created": backup})


def _est_width(text, fs):
    """글자 폭 대략 계산: 한글·기호는 글자 크기만큼, 영문·숫자는 절반 남짓."""
    return sum(fs * (1.0 if ord(c) > 0x2E80 else 0.56) for c in text)


def _occupied(page):
    """슬라이드에서 글자·그림·도형·기존 글자 상자가 차지한 영역. 배경 전체 그림과 쪽 번호는 뺀다."""
    W = page.rect
    big = 0.6 * W.width * W.height
    rects = []
    for b in page.get_text("dict")["blocks"]:
        r = fitz.Rect(b["bbox"])
        if b["type"] == 0:
            t = "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()
            if not t or t.isdigit():
                continue
        if r.get_area() < big:
            rects.append(r)
    for d in page.get_drawings():
        r = fitz.Rect(d["rect"])
        if r.width * r.height < big and (r.width > 0 or r.height > 0):
            rects.append(r + (-1, -1, 1, 1))
    for im in page.get_image_info():
        r = fitz.Rect(im["bbox"])
        if r.get_area() < big:
            rects.append(r)
    for an in page.annots() or []:
        if an.type[1] == "FreeText":
            rects.append(an.rect)
    return rects


def _box_size(text, fs, wmax, pad=14):
    """폭 wmax 안에서 줄을 접을 때의 상자 크기 (대략)."""
    import math
    parts = text.split("\n")
    lines = sum(max(1, math.ceil((_est_width(t, fs) + pad) / wmax)) for t in parts)
    w = min(wmax, max(_est_width(t, fs) for t in parts) + pad + 6)
    return w, lines * fs * 1.4 + 8


def _find_slot(page, text, fs, margin=8):
    """빈 공간을 아래에서 위로 찾는다. 넓은 상자부터 시도하고, 안 되면 좁게 접어 다시 찾는다.
    끝내 없으면 맨 위에 겹쳐 둔다."""
    W = page.rect
    occ = _occupied(page)
    maxw = W.width - 2 * margin
    for frac in (1.0, 0.62, 0.46, 0.36, 0.24):
        w, h = _box_size(text, fs, maxw * frac)
        xs = [W.x0 + margin, W.x1 - margin - w]
        y = W.y1 - margin - h
        while y >= W.y0 + margin:
            for x in xs:
                r = fitz.Rect(x, y, x + w, y + h)
                if not any(r.intersects(o) for o in occ):
                    return r, False
            y -= 4
    w, h = _box_size(text, fs, maxw)
    return fitz.Rect(W.x0 + margin, W.y0 + margin, W.x0 + margin + w, W.y0 + margin + h), True


def cmd_label(a):
    """슬라이드 위에 바로 보이는 빨간 글자 상자(FreeText)를 붙인다. 시험 출제 표시용."""
    import html
    pdf = resolve_pdf(a.pdf)
    doc = fitz.open(pdf)
    page = check_page(doc, a.page)
    text = a.text.replace("\\n", "\n").strip()
    fs = a.size
    W = page.rect
    if a.y is not None:
        x0 = W.x0 + 8 if a.x is None else a.x
        w, h = _box_size(text, fs, (a.w or W.x1 - 8 - x0))
        rect, overlap = fitz.Rect(x0, a.y, x0 + w, a.y + h), None
    else:
        rect, overlap = _find_slot(page, text, fs)
    backup = ensure_backup(pdf)
    # PyMuPDF의 rich text 틀은 white-space:pre-wrap이라 틀 안의 줄바꿈·공백이 그대로 그려진다.
    # normal로 바꾸고 줄바꿈은 <br/>로 넣는다.
    body = "<br/>".join(html.escape(t) for t in text.split("\n"))
    annot = page.add_freetext_annot(
        rect, body, fontsize=fs, richtext=True,
        style=f"color:#c00000;font-weight:bold;font-size:{fs}pt;white-space:normal;",
        fill_color=(1, 0.98, 0.82), border_color=(0.75, 0, 0), border_width=1, opacity=0.96)
    annot.set_info(title=AUTHOR, subject=SUBJECT)
    annot.update()
    mode = save(doc, pdf)
    out({"pdf": str(pdf.relative_to(VAULT)), "page": a.page, "type": "label",
         "xref": annot.xref, "rect": [round(v) for v in rect],
         "covers_content": overlap, "save": mode, "backup_created": backup})


def _first_font(cands):
    for c in cands:
        if Path(c).is_file():
            return Path(c)
    return Path(cands[0])


# 한글 글꼴: Windows 맑은 고딕 → macOS 애플 SD 고딕 → Linux 나눔고딕/Noto CJK 순서로 찾는다.
FONT_REG = _first_font(["C:/Windows/Fonts/malgun.ttf",
                        "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"])
FONT_BOLD = _first_font(["C:/Windows/Fonts/malgunbd.ttf",
                         "/System/Library/Fonts/AppleSDGothicNeo.ttc",
                         "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf",
                         "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"])
TABLE_LAYER = "Claude 추가 표"


def _rgb(hexstr):
    h = hexstr.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _wrap(font, text, fs, width):
    """띄어쓰기 단위로 줄을 접고, 한 단어가 폭을 넘으면 글자 단위로 자른다."""
    lines = []
    for para in str(text).split("\n"):
        cur = ""
        for word in para.split(" "):
            cand = word if not cur else cur + " " + word
            if font.text_length(cand, fs) <= width:
                cur = cand
                continue
            if cur:
                lines.append(cur)
            cur = ""
            for ch in word:
                if font.text_length(cur + ch, fs) > width and cur:
                    lines.append(cur)
                    cur = ""
                cur += ch
        lines.append(cur)
    return lines


def _wrap_runs(runs, fs, width, fonts):
    """글꼴이 섞인 문단을 접는다. runs = [[글, 모양], ...], 모양은 r(보통)·b(굵게)·h(굵은 파랑).
    글 안의 \\n은 줄바꿈. 결과는 줄마다 [(조각, 모양), ...]."""
    import re
    lines, w = [[]], 0.0
    for text, style in runs:
        f = fonts[style][0]
        for part_i, part in enumerate(str(text).split("\n")):
            if part_i:
                lines.append([]); w = 0.0
            for tok in re.findall(r"\S+\s*|\s+", part):
                tw = f.text_length(tok.rstrip(), fs)
                if lines[-1] and w + tw > width:
                    lines.append([]); w = 0.0
                    tok = tok.lstrip()
                    if not tok:
                        continue
                    tw = f.text_length(tok.rstrip(), fs)
                while tw > width:  # 한 덩어리가 줄보다 길면 글자 단위로 자른다
                    cut = ""
                    for ch in tok:
                        if f.text_length(cut + ch, fs) > width - w and cut:
                            break
                        cut += ch
                    lines[-1].append((cut, style)); lines.append([]); w = 0.0
                    tok = tok[len(cut):]
                    tw = f.text_length(tok.rstrip(), fs)
                lines[-1].append((tok, style))
                w += f.text_length(tok, fs)
    return lines


def cmd_table(a):
    """해설 쪽 안에 문단과 표를 직접 그린다(주석이 아니라 쪽 내용). '{TABLE_LAYER}' 레이어에 넣어 구분한다.
    --spec JSON: {"x","y","w","ymax","size","title",
                  "blocks":[{"runs":[[글, "r|b|h"], ...], "gap":5}, ...],   (표 위 문단, 선택)
                  "cols":[비율...], "rows":[[머리행...],[...]...]}           (표, 선택)
    --preview <png>를 주면 저장하지 않고 미리보기 그림만 만든다."""
    spec = json.loads(Path(a.spec).read_text(encoding="utf-8"))
    pdf = resolve_pdf(a.pdf)
    doc = fitz.open(pdf)
    page = check_page(doc, a.page)
    fs = float(spec.get("size", 10.5))
    x0, y, W = float(spec["x"]), float(spec["y"]), float(spec["w"])
    ymax = float(spec.get("ymax", page.rect.y1 - 8))
    fr = spec.get("cols", [1])
    widths = [W * f / sum(fr) for f in fr]
    reg, bold = fitz.Font(fontfile=str(FONT_REG)), fitz.Font(fontfile=str(FONT_BOLD))
    pad, lh = float(spec.get("pad", 4.0)), fs * 1.32
    c_title, c_head, c_body = _rgb("111827"), _rgb("1E3A5F"), _rgb("1F2937")
    fill_head, c_border = (0.945, 0.961, 0.976), (0.796, 0.835, 0.882)
    fonts = {"r": (reg, "MgR", FONT_REG, c_body), "b": (bold, "MgB", FONT_BOLD, c_title),
             "h": (bold, "MgB", FONT_BOLD, c_head)}

    # 배치 계산
    title = spec.get("title")
    ty = y
    if title:
        y += (fs + 1) * 1.5
    paras = []
    for blk in spec.get("blocks", []):
        lines = _wrap_runs(blk["runs"], fs, W, fonts)
        paras.append((y, lines))
        y += (len(lines) - 1) * lh + fs * 1.15 + blk.get("gap", 5)
    layout = []
    for ri, row in enumerate(spec.get("rows", [])):
        cells = []
        for ci, text in enumerate(row):
            strong = str(text).startswith("!")  # 칸 글자 앞에 !를 붙이면 그 칸만 굵게
            text = str(text).lstrip("!")
            f = bold if (ri == 0 or ci == 0 or strong) else reg
            cells.append((f, _wrap(f, text, fs, widths[ci] - 2 * pad)))
        n = max(len(ls) for _, ls in cells)
        h = 2 * pad + (n - 1) * lh + fs * 1.15
        layout.append((ri, y, h, cells))
        y += h
    box = fitz.Rect(x0, ty, x0 + W, y)
    if y > ymax:
        die(f"표가 아래 한계(ymax={ymax:.0f})를 넘습니다: 표 끝 y={y:.0f}. 글자 크기나 문구를 줄이세요.")
    hits = [b for b in page.get_text("dict")["blocks"]
            if b["type"] == 0 and fitz.Rect(b["bbox"]).intersects(box)
            and "".join(s["text"] for l in b["lines"] for s in l["spans"]).strip()]
    if hits:
        die("표 자리에 이미 글자가 있습니다: "
            + "; ".join("".join(s["text"] for l in b["lines"] for s in l["spans"])[:30] for b in hits))

    # 그리기 (같은 이름의 레이어가 있으면 다시 쓴다)
    ocg = next((x for x, v in doc.get_ocgs().items() if v["name"] == TABLE_LAYER), None) \
        or doc.add_ocg(TABLE_LAYER, on=True)
    kw = dict(oc=ocg)
    if title:
        page.insert_text((x0, ty + fs + 1), title, fontsize=fs + 1, fontname="MgB",
                         fontfile=str(FONT_BOLD), color=c_title, **kw)
    for top, lines in paras:
        for li, line in enumerate(lines):
            cx = x0
            for tok, style in line:
                f, name, ff, col = fonts[style]
                page.insert_text((cx, top + fs * 0.92 + li * lh), tok, fontsize=fs,
                                 fontname=name, fontfile=str(ff), color=col, **kw)
                cx += f.text_length(tok, fs)
    for ri, top, h, cells in layout:
        cx = x0
        for ci, (f, lines) in enumerate(cells):
            r = fitz.Rect(cx, top, cx + widths[ci], top + h)
            if ri == 0:
                page.draw_rect(r, color=None, fill=fill_head, **kw)
            page.draw_rect(r, color=c_border, width=0.75, **kw)
            name, ff = ("MgB", FONT_BOLD) if f is bold else ("MgR", FONT_REG)
            col = c_head if ri == 0 else (c_title if ci == 0 else c_body)
            for li, line in enumerate(lines):
                page.insert_text((cx + pad, top + pad + fs * 0.92 + li * lh), line, fontsize=fs,
                                 fontname=name, fontfile=str(ff), color=col, **kw)
            cx += widths[ci]

    if a.preview:
        page.get_pixmap(dpi=150).save(a.preview)
        out({"preview": a.preview, "table_rect": [round(v) for v in box], "saved": False})
        return
    backup = ensure_backup(pdf)
    # 맑은 고딕 전체가 들어가면 수 MB가 늘어나므로 쓴 글자만 남긴다(전체 다시 쓰기).
    doc.subset_fonts()
    tmp = pdf.with_suffix(".pdf.tmp")
    doc.save(str(tmp), garbage=1, deflate=True)
    doc.close()
    tmp.replace(pdf)
    out({"pdf": str(pdf.relative_to(VAULT)), "page": a.page, "type": "table",
         "layer": TABLE_LAYER, "ocg_xref": ocg, "table_rect": [round(v) for v in box],
         "save": "rewrite", "backup_created": backup})


def cmd_remove(a):
    pdf = resolve_pdf(a.pdf)
    doc = fitz.open(pdf)
    for page in doc:
        for an in page.annots() or []:
            if an.xref == a.xref:
                if an.info.get("subject") != SUBJECT:
                    die("Claude가 만든 필기만 지울 수 있습니다.")
                ensure_backup(pdf)
                page.delete_annot(an)
                mode = save(doc, pdf)
                out({"removed_xref": a.xref, "page": page.number + 1, "save": mode})
                return
    die(f"xref {a.xref} 필기를 찾지 못했습니다.")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("current").set_defaults(fn=cmd_current)

    p = sub.add_parser("read")
    p.add_argument("pdf"); p.add_argument("page", type=int); p.add_argument("--to", type=int)
    p.set_defaults(fn=cmd_read)

    p = sub.add_parser("list")
    p.add_argument("pdf"); p.add_argument("--page", type=int)
    p.set_defaults(fn=cmd_list)

    p = sub.add_parser("add")
    p.add_argument("pdf"); p.add_argument("page", type=int)
    p.add_argument("--note", required=True); p.add_argument("--quote")
    p.add_argument("--color", default="yellow", choices=sorted(COLORS))
    p.set_defaults(fn=cmd_add)

    p = sub.add_parser("label")
    p.add_argument("pdf"); p.add_argument("page", type=int)
    p.add_argument("--text", required=True); p.add_argument("--size", type=float, default=14)
    p.add_argument("--y", type=float); p.add_argument("--x", type=float); p.add_argument("--w", type=float)
    p.set_defaults(fn=cmd_label)

    p = sub.add_parser("table")
    p.add_argument("pdf"); p.add_argument("page", type=int)
    p.add_argument("--spec", required=True); p.add_argument("--preview")
    p.set_defaults(fn=cmd_table)

    p = sub.add_parser("remove")
    p.add_argument("pdf"); p.add_argument("--xref", type=int, required=True)
    p.set_defaults(fn=cmd_remove)

    a = ap.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
