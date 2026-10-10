#!/usr/bin/env python3
"""为脱敏产物生成「人工审核」辅助物：

  A. review-diff.txt / review-diff.json —— 逐处列出 位置/类别/原文/假值/上下文
  B. review_marked/                    —— 带标记的审核副本
       DOCX  假值黄色高亮 + Word 原生批注（批注里写原值）
       XLSX  假值单元格填充色 + 单元格批注（写明原值）
       PDF   假值高亮标注 + 弹出注释（写明原值）
       文本  `假值〔原:原文〕` 内联

安全约定：本脚本产物**含原始敏感值**，只应放在受控目录、用完即删，
绝不与干净脱敏产物一起分发。

用法（用 skill 自带 venv 运行，保证与脱敏同一套解析器版本）：
  .venv/bin/python scripts/mark_review.py \
      --input-dir  <干净产物目录> \
      --mapping    <明文映射 json，来自 --export-mapping> \
      --out-dir    <输出目录> \
      --clean-mapping <可选：干净映射 json，用于回填类别>
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".text", ".csv", ".tsv", ".json", ".yaml", ".yml"}
EXCEL_EXTENSIONS = {".xlsx", ".xlsm"}
MAX_CANDIDATES_PER_RUN = 400  # 单段落/单元格最多标记的假值个数，防御性上限


@dataclass
class Replacement:
    category: str
    original: str
    fake: str


@dataclass
class Hit:
    """一次改动：文件 + 位置 + 原文 + 假值。"""

    file: str
    location: str
    category: str
    original: str
    fake: str
    before: str = ""
    after: str = ""


# --------------------------------------------------------------------------
# 映射表
# --------------------------------------------------------------------------
def load_reverse_mapping(mapping_path: Path, clean_mapping_path: Path | None) -> tuple[dict[str, list[Replacement]], dict[str, str]]:
    """返回 假值 -> [候选替换]，以及 类别名 -> 类别名（用于 --mapping 的哈希键回填）。"""
    raw = json.loads(mapping_path.read_text(encoding="utf-8"))
    reverse: dict[str, list[Replacement]] = {}
    for category, pairs in raw.items():
        for original, fake in pairs.items():
            reverse.setdefault(fake, []).append(Replacement(category, original, fake))

    clean_keys: dict[str, str] = {}
    if clean_mapping_path and clean_mapping_path.exists():
        clean = json.loads(clean_mapping_path.read_text(encoding="utf-8"))
        for category, pairs in clean.items():
            for digest, fake in pairs.items():
                clean_keys[digest] = category
    return reverse, clean_keys


def build_pattern(reverse: dict[str, list[Replacement]]) -> re.Pattern[str] | None:
    """最长假值优先的扫描正则，避免短假值抢先切分长假值。"""
    values = sorted((v for v in reverse if len(v) >= 2), key=len, reverse=True)
    if not values:
        return None
    values = values[:MAX_CANDIDATES_PER_RUN]
    return re.compile("|".join(re.escape(v) for v in values))


def pick(reverse: dict[str, list[Replacement]], fake: str) -> Replacement:
    """同一假值对应多个原值时取第一个（用于批注展示）。"""
    return reverse[fake][0]


def snippet(text: str, start: int, end: int, span: int = 40) -> str:
    left = max(0, start - span)
    right = min(len(text), end + span)
    return text[left:right].replace("\n", "⏎")


def spatial_snippet(page, match: "re.Match[str]") -> str:
    """按版面取上下文：返回替换值所在整行的文本。

    PDF redaction 会把替换值写进新的内容流，``get_text("text")`` 默认顺序会把它们
    排到页尾，按字符偏移取上下文没有意义。这里先定位替换值的矩形，再返回与之垂直
    重叠的行文本，得到真正可读的上下文。
    """
    import fitz

    rects = page.search_for(match.group(0))
    if not rects:
        return ""
    rect = rects[0]
    try:
        lines = [
            line
            for block in page.get_text("dict")["blocks"]
            if block.get("type") == 0
            for line in block["lines"]
        ]
    except Exception:
        return ""
    picked = []
    for line in lines:
        lbox = fitz.Rect(line["bbox"])
        if lbox.y1 < rect.y0 - 2 or lbox.y0 > rect.y1 + 2:
            continue
        text = "".join(span["text"] for span in line["spans"]).strip()
        if text:
            picked.append((lbox.y0, lbox.x0, text))
    picked.sort()
    joined = " ｜ ".join(text for _y, _x, text in picked)
    return joined[:400]


# --------------------------------------------------------------------------
# 纯文本 / Markdown / CSV
# --------------------------------------------------------------------------
def scan_text(text: str, pattern: re.Pattern[str], reverse: dict[str, list[Replacement]]):
    for match in pattern.finditer(text):
        rep = pick(reverse, match.group(0))
        yield match.start(), match.end(), rep


def mark_text_file(path: Path, out_path: Path, pattern, reverse, file_hits: list[Hit]) -> None:
    text = path.read_text(encoding="utf-8")
    spans = list(scan_text(text, pattern, reverse))
    if not spans:
        out_path.write_text(text, encoding="utf-8")
        return
    pieces, cursor = [], 0
    for start, end, rep in spans:
        pieces.append(text[cursor:start])
        pieces.append(f"{rep.fake}〔原:{rep.original}〕")
        file_hits.append(
            Hit(path.name, "inline", rep.category, rep.original, rep.fake,
                snippet(text, start, end))
        )
        cursor = end
    pieces.append(text[cursor:])
    out_path.write_text("".join(pieces), encoding="utf-8")


# --------------------------------------------------------------------------
# DOCX
# --------------------------------------------------------------------------
def iter_all_runs(doc):
    """深度遍历所有 run —— python-docx 的 paragraph.runs 看不到超链接/域里的 run。"""
    for paragraph in doc.paragraphs:
        yield paragraph, paragraph.runs
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    yield paragraph, paragraph.runs
    for section in doc.sections:
        for part_name in ("header", "footer", "first_page_header", "first_page_footer",
                          "even_page_header", "even_page_footer"):
            part = getattr(section, part_name, None)
            if part is None:
                continue
            for paragraph in getattr(part, "paragraphs", []):
                yield paragraph, paragraph.runs
            for table in getattr(part, "tables", []):
                for row in table.rows:
                    for cell in row.cells:
                        for paragraph in cell.paragraphs:
                            yield paragraph, paragraph.runs


def mark_docx(path: Path, out_path: Path, pattern, reverse, file_hits: list[Hit]) -> list[str]:
    from docx import Document
    from docx.enum.text import WD_COLOR_INDEX

    doc = Document(path)
    warnings: list[str] = []
    annotated_runs = 0

    for paragraph, runs in iter_all_runs(doc):
        if not runs:
            continue
        for run in runs:
            text = run.text or ""
            matches = list(scan_text(text, pattern, reverse))
            if not matches:
                continue
            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
            para_text = paragraph.text
            locator = para_text.find(run.text) if run.text else -1
            note_parts = []
            for start, end, rep in matches:
                note_parts.append(f"原值: {rep.original}  →  现为: {rep.fake}（类别 {rep.category}）")
                base = locator if locator >= 0 else 0
                file_hits.append(
                    Hit(path.name, "docx 段落", rep.category, rep.original, rep.fake,
                        snippet(para_text, base + start, base + end))
                )
            # Word 原生批注：锚定在被替换的 run 上
            try:
                doc.add_comment(runs=[run], text="；".join(note_parts))
                annotated_runs += 1
            except Exception as exc:  # 批注失败不影响高亮
                warnings.append(f"add_comment 失败（{type(exc).__name__}: {exc}），已保留高亮")
                if len(warnings) > 3:
                    break
    if annotated_runs == 0 and file_hits:
        warnings.append("未成功添加任何 Word 批注，仅高亮了假值")
    doc.save(out_path)
    return warnings


# --------------------------------------------------------------------------
# Excel
# --------------------------------------------------------------------------
def mark_excel(path: Path, out_path: Path, pattern, reverse, file_hits: list[Hit]) -> list[str]:
    from openpyxl import load_workbook
    from openpyxl.comments import Comment
    from openpyxl.styles import Font, PatternFill

    keep_vba = path.suffix.lower() == ".xlsm"
    wb = load_workbook(path, data_only=False, keep_vba=keep_vba, rich_text=True)
    fill = PatternFill(start_color="FFFF00", end_color="FFFF00", fill_type="solid")
    notes = 0
    try:
        for sheet_index, ws in enumerate(wb.worksheets, 1):
            for row in ws.iter_rows():
                for cell in row:
                    value = cell.value
                    if not isinstance(value, str) or not value:
                        continue
                    matches = list(scan_text(value, pattern, reverse))
                    if not matches:
                        continue
                    cell.fill = fill
                    lines = []
                    for _start, _end, rep in matches:
                        lines.append(f"原值: {rep.original}  →  现为: {rep.fake}（类别 {rep.category}）")
                        file_hits.append(
                            Hit(path.name, f"sheet {sheet_index}!{cell.coordinate}",
                                rep.category, rep.original, rep.fake, snippet(value, 0, len(value)))
                        )
                    cell.comment = Comment("\n".join(lines), "anonymize-review")
                    cell.comment.width = 380
                    cell.comment.height = max(90, 18 * len(lines))
                    notes += 1
        wb.save(out_path)
    finally:
        wb.close()
    warnings = []
    if notes == 0 and file_hits:
        warnings.append("未标记任何单元格，但清单里有记录，需人工确认")
    return warnings


# --------------------------------------------------------------------------
# PDF
# --------------------------------------------------------------------------
def mark_pdf(path: Path, out_path: Path, pattern, reverse, file_hits: list[Hit]) -> list[str]:
    import fitz

    doc = fitz.open(path)
    warnings: list[str] = []
    marked = 0
    try:
        for page in doc:
            text = page.get_text("text")
            if not text.strip():
                continue
            seen: set[str] = set()
            for match in pattern.finditer(text):
                fake = match.group(0)
                if fake in seen:
                    continue
                seen.add(fake)
                rep = pick(reverse, fake)
                rects = list(page.search_for(fake))
                if not rects:
                    warnings.append(
                        f"page {page.number + 1}: 假值定位失败（{len(fake)} 字符），未做高亮"
                    )
                    continue
                note = f"原值: {rep.original}\n现为: {rep.fake}\n类别: {rep.category}"
                for rect in rects:
                    annot = page.add_highlight_annot(rect)
                    annot.set_info(title="anonymize-review", content=note)
                    annot.set_colors(stroke=(1, 1, 0))
                    annot.update()
                    marked += 1
                file_hits.append(
                    Hit(path.name, f"page {page.number + 1}", rep.category,
                        rep.original, rep.fake, spatial_snippet(page, match))
                )
        if not marked and file_hits:
            warnings.append("PDF 未成功添加任何高亮标注")
        doc.save(out_path, garbage=0, deflate=True)
    finally:
        doc.close()
    return warnings


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="为脱敏产物生成审核标记与 diff 清单。")
    parser.add_argument("--input-dir", type=Path, required=True, help="干净产物目录")
    parser.add_argument("--mapping", type=Path, required=True, help="明文映射（--export-mapping 产出）")
    parser.add_argument("--clean-mapping", type=Path, help="干净映射，用于回填类别")
    parser.add_argument("--out-dir", type=Path, required=True, help="审核产物输出目录")
    args = parser.parse_args(argv)

    reverse, _clean_keys = load_reverse_mapping(args.mapping, args.clean_mapping)
    pattern = build_pattern(reverse)
    if pattern is None:
        print(json.dumps({"error": "映射为空，无法生成审核物"}, ensure_ascii=False), file=sys.stderr)
        return 2

    out_dir: Path = args.out_dir
    marked_dir = out_dir / "review_marked"
    marked_dir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in args.input_dir.iterdir() if p.is_file())
    all_hits: list[Hit] = []
    warnings: list[str] = []
    summary: dict[str, dict] = {}

    for path in files:
        suffix = path.suffix.lower()
        out_path = marked_dir / path.name
        before = len(all_hits)
        file_warnings: list[str] = []
        try:
            if suffix == ".docx":
                file_warnings = mark_docx(path, out_path, pattern, reverse, all_hits)
            elif suffix in EXCEL_EXTENSIONS:
                file_warnings = mark_excel(path, out_path, pattern, reverse, all_hits)
            elif suffix == ".pdf":
                file_warnings = mark_pdf(path, out_path, pattern, reverse, all_hits)
            elif suffix in TEXT_EXTENSIONS:
                mark_text_file(path, out_path, pattern, reverse, all_hits)
            else:
                file_warnings = [f"不支持的扩展名 {suffix}，未生成审核副本"]
        except Exception as exc:
            file_warnings = [f"生成审核副本失败: {type(exc).__name__}: {exc}"]
        count = len(all_hits) - before
        summary[path.name] = {"replacements": count, "warnings": file_warnings}
        for w in file_warnings:
            warnings.append(f"{path.name}: {w}")

    # 清单输出
    (out_dir / "review-diff.json").write_text(
        json.dumps(
            {
                "summary": {
                    "files": len(files),
                    "total_replacements": len(all_hits),
                    "warnings": len(warnings),
                },
                "files": summary,
                "replacements": [
                    {
                        "file": h.file,
                        "location": h.location,
                        "category": h.category,
                        "original": h.original,
                        "replacement": h.fake,
                        "context": h.before,
                    }
                    for h in all_hits
                ],
                "warnings": warnings,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    lines = [
        "# 脱敏改动审核清单",
        "",
        "> 本文件含**原始敏感值**，仅供人工审核，勿随脱敏产物分发。",
        "",
        "上下文列说明：XLSX 取单元格、DOCX 取段落（均带偏移片段）；PDF 取替换值所在",
        "物理行，因 redaction 后替换值跨行、故可能呈现为若干片段加 `｜` 分隔，",
        "以「页码 + 原文 + 改为」为准即可。",
        "",
        f"- 审核文件：{len(files)} 个",
        f"- 改动处数：{len(all_hits)} 处",
        f"- 警告：{len(warnings)} 条",
        "",
    ]
    current = None
    for h in all_hits:
        if h.file != current:
            current = h.file
            lines += ["", f"## {current}", "",
                      "| 位置 | 类别 | 原文 | 改为 | 上下文 |", "|---|---|---|---|---|"]
        ctx = h.before.replace("|", "\\|")
        orig = h.original.replace("|", "\\|")
        lines.append(f"| {h.location} | {h.category} | `{orig}` | `{h.fake}` | …{ctx}… |")
    if warnings:
        lines += ["", "## 警告", ""]
        lines += [f"- {w}" for w in warnings]
    (out_dir / "review-diff.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(
        {
            "files": len(files),
            "total_replacements": len(all_hits),
            "warnings": warnings[:20],
            "warning_count": len(warnings),
            "marked_dir": str(marked_dir),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
