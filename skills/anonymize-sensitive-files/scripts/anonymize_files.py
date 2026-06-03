#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

from detectors import (
    FieldRule,
    Finding,
    detect_field_rule_values,
    detect_sensitive_values,
    field_rule_matches_label,
    load_custom_terms,
    load_field_rules,
)
from fake_data import KNOWN_FAKE_VALUES, FakeDataFactory, normalize_category


SUPPORTED_TEXT_EXTENSIONS = {".md", ".markdown", ".txt", ".text", ".csv", ".tsv", ".json", ".yaml", ".yml"}
SUPPORTED_EXTENSIONS = SUPPORTED_TEXT_EXTENSIONS | {".docx", ".pdf"}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.export_mapping and not args.mapping:
        print(
            json.dumps({"error": "--export-mapping requires --mapping so raw values are not printed to stdout."}, ensure_ascii=False),
            file=sys.stderr,
        )
        return 2
    if args.no_field_rules and args.field_rules:
        print(json.dumps({"error": "--no-field-rules cannot be combined with --field-rules."}, ensure_ascii=False), file=sys.stderr)
        return 2

    inputs, skipped_inputs = collect_inputs(args.inputs, args.recursive)
    if not inputs:
        print(
            json.dumps(
                {
                    "error": "No supported input files found.",
                    "summary": skipped_summary(skipped_inputs),
                    "skipped_inputs": skipped_inputs,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=sys.stderr,
        )
        return 2
    try:
        output_paths = plan_outputs(inputs, args)
    except ValueError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2

    custom_terms = load_custom_terms(args.terms)
    field_rules = load_field_rules(args.field_rules, use_default=not args.no_field_rules)
    factory = FakeDataFactory(seed=args.seed)
    results = []

    for path in inputs:
        try:
            results.append(process_file(path, args, custom_terms, field_rules, factory, output_paths.get(path)))
        except Exception as exc:
            results.append(
                {
                    "input_path": str(path),
                    "status": "error",
                    "error": str(exc),
                    "findings": [],
                    "warnings": [],
                }
            )

    report = build_report(results, factory, skipped_inputs)

    if args.report:
        args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.mapping:
        mapping = factory.sensitive_mapping() if args.export_mapping else factory.safe_mapping()
        args.mapping.write_text(json.dumps(mapping, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps(report, ensure_ascii=False, indent=2))
    return exit_code_for(results, skipped_inputs)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scan or anonymize sensitive data in text, Markdown, DOCX, and PDF files.",
    )
    parser.add_argument("inputs", nargs="+", type=Path, help="File or directory paths to process.")
    parser.add_argument(
        "--mode",
        choices=["scan", "anonymize", "verify"],
        default="anonymize",
        help="scan reports findings only; anonymize writes output files; verify scans files after anonymization.",
    )
    parser.add_argument("--recursive", action="store_true", help="Recurse into input directories.")
    parser.add_argument("--output", type=Path, help="Output file path for a single input file.")
    parser.add_argument("--output-dir", type=Path, help="Directory for anonymized output files.")
    parser.add_argument("--report", type=Path, help="Write the JSON report to this path.")
    parser.add_argument("--terms", type=Path, help="Custom terms file. Lines may be 'category:value' or plain values.")
    parser.add_argument(
        "--field-rules",
        type=Path,
        help="YAML file containing global label/value field rules. Defaults to the bundled rules.",
    )
    parser.add_argument("--no-field-rules", action="store_true", help="Disable bundled and explicit field rules.")
    parser.add_argument("--seed", help="Optional seed label used for stable safe mapping hashes.")
    parser.add_argument("--mapping", type=Path, help="Optional mapping output path. Required with --export-mapping.")
    parser.add_argument(
        "--export-mapping",
        action="store_true",
        help="Write raw original-to-fake mappings to --mapping. This creates a sensitive artifact.",
    )
    return parser.parse_args(argv)


def resolve_inputs(inputs: list[Path], recursive: bool) -> Iterable[Path]:
    supported, _skipped = collect_inputs(inputs, recursive)
    yield from supported


def collect_inputs(inputs: list[Path], recursive: bool) -> tuple[list[Path], list[dict]]:
    supported: list[Path] = []
    skipped: list[dict] = []
    for item in inputs:
        item = item.expanduser()
        if item.is_dir():
            iterator = item.rglob("*") if recursive else item.glob("*")
            for child in iterator:
                if not child.is_file():
                    continue
                if child.suffix.lower() in SUPPORTED_EXTENSIONS:
                    supported.append(child)
                else:
                    skipped.append(skipped_input(child, "unsupported_extension", explicit=False))
        elif item.is_file():
            if item.suffix.lower() in SUPPORTED_EXTENSIONS:
                supported.append(item)
            else:
                skipped.append(skipped_input(item, "unsupported_extension", explicit=True))
        else:
            skipped.append(skipped_input(item, "missing", explicit=True))
    return supported, skipped


def skipped_input(path: Path, reason: str, explicit: bool) -> dict:
    item = {"path": str(path), "reason": reason, "explicit": explicit}
    if path.suffix:
        item["extension"] = path.suffix.lower()
    return item


def process_file(
    path: Path,
    args: argparse.Namespace,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
    factory: FakeDataFactory,
    output_path: Path | None,
) -> dict:
    suffix = path.suffix.lower()
    if args.mode == "scan":
        findings, warnings = scan_file(path, custom_terms, field_rules)
        return result_for(path, None, "scanned", findings, warnings)

    if args.mode == "verify":
        findings, warnings = verify_file(path, custom_terms, field_rules)
        status = "verified" if not findings else "residual_findings"
        return result_for(path, None, status, findings, warnings)

    if output_path is None:
        raise ValueError("Missing output path for anonymization.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        text = path.read_text(encoding="utf-8")
        anonymized, findings = anonymize_text(text, custom_terms, field_rules, factory)
        output_path.write_text(anonymized, encoding="utf-8")
        return result_for(path, output_path, "anonymized", findings, [])

    if suffix == ".docx":
        findings, warnings = anonymize_docx(path, output_path, custom_terms, field_rules, factory)
        return result_for(path, output_path, "anonymized", findings, warnings)

    if suffix == ".pdf":
        findings, warnings = anonymize_pdf(path, output_path, custom_terms, field_rules, factory)
        return result_for(path, output_path, "anonymized", findings, warnings)

    raise ValueError(f"Unsupported file extension: {suffix}")


def scan_file(
    path: Path,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
) -> tuple[list[Finding], list[str]]:
    if path.suffix.lower() == ".docx":
        return scan_docx(path, custom_terms, field_rules)
    text, warnings = extract_text(path)
    return detect_sensitive_values(text, custom_terms, field_rules), warnings


def verify_file(
    path: Path,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
) -> tuple[list[Finding], list[str]]:
    findings, warnings = scan_file(path, custom_terms, field_rules)
    return verify_findings(findings), warnings


def extract_text(path: Path) -> tuple[str, list[str]]:
    suffix = path.suffix.lower()
    if suffix in SUPPORTED_TEXT_EXTENSIONS:
        return path.read_text(encoding="utf-8"), []
    if suffix == ".docx":
        try:
            from docx import Document
        except ImportError as exc:
            raise RuntimeError("DOCX support requires python-docx. Install with: pip install python-docx") from exc
        doc = Document(path)
        parts = []
        for paragraph in doc.paragraphs:
            parts.append(paragraph.text)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
        return "\n".join(parts), ["DOCX scan covers paragraphs and tables; headers, footers, comments, and text boxes may need manual review."]
    if suffix == ".pdf":
        try:
            import fitz
        except ImportError as exc:
            raise RuntimeError("PDF support requires PyMuPDF. Install with: pip install pymupdf") from exc
        doc = fitz.open(path)
        text = "\n".join(page.get_text("text") for page in doc)
        warnings = []
        if not text.strip():
            warnings.append("No PDF text layer found. Use OCR or manual review for scanned pages and image-only content.")
        else:
            warnings.append("PDF scan covers extractable text; images and annotations may need manual review.")
        return text, warnings
    raise ValueError(f"Unsupported file extension: {suffix}")


def anonymize_text(
    text: str,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
    factory: FakeDataFactory,
) -> tuple[str, list[Finding]]:
    findings = detect_sensitive_values(text, custom_terms, field_rules)
    output = []
    cursor = 0
    for finding in non_overlapping(findings):
        output.append(text[cursor : finding.start])
        output.append(factory.replacement_for(finding.category, finding.value))
        cursor = finding.end
    output.append(text[cursor:])
    return "".join(output), findings


def verify_findings(findings: list[Finding]) -> list[Finding]:
    return [
        finding
        for finding in findings
        if finding.source == "custom_terms" or finding.value not in KNOWN_FAKE_VALUES
    ]


def non_overlapping(findings: list[Finding]) -> list[Finding]:
    selected: list[Finding] = []
    occupied_until = -1
    for finding in sorted(findings, key=lambda item: (item.start, -(item.end - item.start))):
        if finding.start >= occupied_until:
            selected.append(finding)
            occupied_until = finding.end
    return selected


def anonymize_docx(
    input_path: Path,
    output_path: Path,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
    factory: FakeDataFactory,
) -> tuple[list[Finding], list[str]]:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("DOCX anonymization requires python-docx. Install with: pip install python-docx") from exc

    doc = Document(input_path)
    all_findings: list[Finding] = []
    warnings = [
        "DOCX anonymization covers paragraphs and tables. Review headers, footers, comments, tracked changes, footnotes, and text boxes separately.",
        "Paragraphs with matches are rewritten as plain text runs, which may simplify styling inside those paragraphs.",
    ]

    for paragraph in doc.paragraphs:
        new_text, findings = anonymize_text(paragraph.text, custom_terms, field_rules, factory)
        if findings:
            replace_paragraph_text(paragraph, new_text)
            all_findings.extend(findings)

    for table in doc.tables:
        for row in table.rows:
            label_contexts_by_cell = adjacent_field_label_contexts(row, field_rules)
            for cell_index, cell in enumerate(row.cells):
                for paragraph in cell.paragraphs:
                    new_text, findings = anonymize_docx_paragraph_text(
                        paragraph.text,
                        custom_terms,
                        field_rules,
                        label_contexts_by_cell.get(cell_index, []),
                        factory,
                    )
                    if findings:
                        replace_paragraph_text(paragraph, new_text)
                        all_findings.extend(findings)

    doc.save(output_path)
    return all_findings, warnings


def scan_docx(
    input_path: Path,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
) -> tuple[list[Finding], list[str]]:
    try:
        from docx import Document
    except ImportError as exc:
        raise RuntimeError("DOCX scanning requires python-docx. Install with: pip install python-docx") from exc

    doc = Document(input_path)
    all_findings: list[Finding] = []
    warnings = ["DOCX scan covers paragraphs and tables; headers, footers, comments, and text boxes may need manual review."]

    for paragraph in doc.paragraphs:
        all_findings.extend(detect_sensitive_values(paragraph.text, custom_terms, field_rules))

    for table in doc.tables:
        for row in table.rows:
            label_contexts_by_cell = adjacent_field_label_contexts(row, field_rules)
            for cell_index, cell in enumerate(row.cells):
                for paragraph in cell.paragraphs:
                    all_findings.extend(
                        docx_paragraph_findings(
                            paragraph.text,
                            custom_terms,
                            field_rules,
                            label_contexts_by_cell.get(cell_index, []),
                        )
                    )

    return all_findings, warnings


def anonymize_docx_paragraph_text(
    text: str,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
    label_contexts: list[str],
    factory: FakeDataFactory,
) -> tuple[str, list[Finding]]:
    findings = docx_paragraph_findings(text, custom_terms, field_rules, label_contexts)
    output = []
    cursor = 0
    for finding in non_overlapping(findings):
        output.append(text[cursor : finding.start])
        output.append(factory.replacement_for(finding.category, finding.value))
        cursor = finding.end
    output.append(text[cursor:])
    return "".join(output), findings


def docx_paragraph_findings(
    text: str,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
    label_contexts: list[str],
) -> list[Finding]:
    findings = detect_sensitive_values(text, custom_terms, field_rules)
    for label_context in label_contexts:
        for finding in detect_field_rule_values(text, field_rules, label_context=label_context):
            if not any(finding.start < item.end and finding.end > item.start for item in findings):
                findings.append(finding)
    return sorted(findings, key=lambda item: (item.start, -(item.end - item.start)))


def adjacent_field_label_contexts(row, field_rules: list[FieldRule]) -> dict[int, list[str]]:
    contexts: dict[int, list[str]] = {}
    if not field_rules:
        return contexts
    cells = row.cells
    for cell_index in range(len(cells) - 1):
        label_text = cells[cell_index].text
        if any(field_rule_matches_label(rule, label_text) for rule in field_rules):
            contexts.setdefault(cell_index + 1, []).append(label_text)
    return contexts


def replace_paragraph_text(paragraph, new_text: str) -> None:
    for run in paragraph.runs:
        run.text = ""
    if paragraph.runs:
        paragraph.runs[0].text = new_text
    else:
        paragraph.add_run(new_text)


def anonymize_pdf(
    input_path: Path,
    output_path: Path,
    custom_terms: list[tuple[str, str]],
    field_rules: list[FieldRule],
    factory: FakeDataFactory,
) -> tuple[list[Finding], list[str]]:
    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PDF anonymization requires PyMuPDF. Install with: pip install pymupdf") from exc

    doc = fitz.open(input_path)
    all_findings: list[Finding] = []
    warnings = [
        "PDF anonymization uses redaction annotations and inserts fake text near matched rectangles.",
        "Review scanned pages, images, annotations, forms, and unusual layouts manually.",
    ]

    for page in doc:
        text = page.get_text("text")
        if not text.strip():
            warnings.append(f"Page {page.number + 1} has no extractable text layer.")
            continue
        findings = non_overlapping(detect_sensitive_values(text, custom_terms, field_rules))
        all_findings.extend(findings)
        annotations_added = False
        missing_redactions = []
        searched_values = set()
        for finding in findings:
            if finding.value in searched_values:
                continue
            searched_values.add(finding.value)
            replacement = factory.replacement_for(finding.category, finding.value)
            rects = list(page.search_for(finding.value))
            if not rects:
                missing_redactions.append(
                    f"page {page.number + 1} {normalize_category(finding.category)} length {len(finding.value)}"
                )
                continue
            for rect in rects:
                page.add_redact_annot(rect, text=replacement, fill=(1, 1, 1), text_color=(0, 0, 0))
                annotations_added = True
        if missing_redactions:
            raise RuntimeError(
                "PDF redaction could not locate rectangles for detected text: " + "; ".join(missing_redactions)
            )
        if annotations_added:
            page.apply_redactions()

    doc.save(output_path, garbage=4, deflate=True)
    return all_findings, warnings


def plan_outputs(inputs: list[Path], args: argparse.Namespace) -> dict[Path, Path]:
    if args.mode != "anonymize":
        return {}

    outputs: dict[Path, Path] = {}
    seen: dict[Path, Path] = {}
    roots = input_roots(args.inputs)
    for path in inputs:
        output_path = output_for(path, args, roots, len(inputs))
        if same_path(path, output_path):
            raise ValueError(f"Refusing to overwrite original file: {path}")
        resolved_output = output_path.expanduser().resolve(strict=False)
        if resolved_output in seen:
            raise ValueError(f"Output path collision: {seen[resolved_output]} and {path} both map to {output_path}")
        seen[resolved_output] = path
        outputs[path] = output_path
    return outputs


def output_for(path: Path, args: argparse.Namespace, roots: list[Path], input_count: int) -> Path:
    if args.output:
        if input_count > 1:
            raise ValueError("--output can only be used with one input file.")
        return args.output
    if args.output_dir:
        return args.output_dir / relative_output_name(path, roots)
    return path.with_name(anonymized_name(path))


def anonymized_name(path: Path) -> str:
    return f"{path.stem}.anonymized{path.suffix}"


def relative_output_name(path: Path, roots: list[Path]) -> Path:
    resolved_path = path.expanduser().resolve(strict=False)
    for root in roots:
        try:
            relative = resolved_path.relative_to(root)
        except ValueError:
            continue
        return relative.with_name(anonymized_name(relative))
    return Path(anonymized_name(path))


def input_roots(inputs: list[Path]) -> list[Path]:
    roots = []
    for item in inputs:
        if item.is_dir():
            roots.append(item.expanduser().resolve(strict=False))
    return sorted(roots, key=lambda path: len(path.parts), reverse=True)


def same_path(left: Path, right: Path) -> bool:
    return left.expanduser().resolve(strict=False) == right.expanduser().resolve(strict=False)


def result_for(
    input_path: Path,
    output_path: Path | None,
    status: str,
    findings: list[Finding],
    warnings: list[str],
) -> dict:
    counts: dict[str, int] = {}
    for finding in findings:
        category = normalize_category(finding.category)
        counts[category] = counts.get(category, 0) + 1

    result = {
        "input_path": str(input_path),
        "status": status,
        "finding_counts": counts,
        "finding_count": len(findings),
        "findings": [
            {
                "category": normalize_category(finding.category),
                "source": finding.source,
                "start": finding.start,
                "end": finding.end,
                "length": len(finding.value),
            }
            for finding in findings
        ],
        "warnings": warnings,
    }
    if output_path:
        result["output_path"] = str(output_path)
    return result


def build_report(
    results: list[dict],
    factory: FakeDataFactory,
    skipped_inputs: list[dict] | None = None,
) -> dict:
    del factory
    skipped_inputs = skipped_inputs or []
    summary_counts: dict[str, int] = {}
    for result in results:
        for category, count in result.get("finding_counts", {}).items():
            summary_counts[category] = summary_counts.get(category, 0) + count

    report = {
        "summary": {
            "files_processed": len(results),
            "total_findings": sum(result.get("finding_count", 0) for result in results),
            "finding_counts": summary_counts,
            "errors": sum(1 for result in results if result.get("status") == "error"),
            **skipped_summary(skipped_inputs),
        },
        "outputs": results,
    }
    if skipped_inputs:
        report["skipped_inputs"] = skipped_inputs
    return report


def skipped_summary(skipped_inputs: list[dict]) -> dict:
    return {
        "skipped_inputs": len(skipped_inputs),
        "skipped_unsupported": sum(1 for item in skipped_inputs if item.get("reason") == "unsupported_extension"),
        "skipped_missing": sum(1 for item in skipped_inputs if item.get("reason") == "missing"),
    }


def exit_code_for(results: list[dict], skipped_inputs: list[dict]) -> int:
    if any(result.get("status") == "error" for result in results):
        return 1
    if any(result.get("status") == "residual_findings" for result in results):
        return 1
    if any(item.get("explicit") for item in skipped_inputs):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
