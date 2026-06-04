# Supported Formats

## Text, Markdown, CSV, JSON, YAML

The CLI reads these files as UTF-8 text, replaces sensitive spans, and writes a sibling file named `*.anonymized.ext` unless `--output` or `--output-dir` is provided.

The CLI refuses to write an anonymized output to the same path as the input file. When `--output-dir` is used with recursive directory input, output files keep their relative subdirectory paths to avoid same-name collisions.

Markdown structure is preserved because replacements happen in text content without reparsing Markdown. For Markdown table rows, bundled global field rules are also applied to adjacent cells: if a configured label such as `法定代表人`, `采购联系人`, or `紧急联系人` appears in one cell, the value in the cell immediately to the right is scanned and anonymized with that rule.

When processing directories, unsupported files are listed in `skipped_inputs`. Explicit unsupported or missing input paths make the CLI exit non-zero so batch jobs cannot silently skip requested files.

## DOCX

DOCX support requires:

```bash
python3 scripts/run_anonymize.py input.docx --report report.json
```

The runner creates `.venv`, installs `python-docx` from `scripts/requirements.txt`, and runs the lower-level CLI with the virtual environment Python.

The CLI processes paragraphs and table cells. Paragraphs containing findings are rewritten as text runs, so fine-grained styling inside those paragraphs may be simplified.

Bundled global field rules are also applied to DOCX tables. If a configured label such as `财务联系人`, `收件人`, or `联行号` appears in one cell, the value in the cell immediately to the right is scanned and anonymized with that rule.

Review or handle separately:

- Headers and footers
- Footnotes and endnotes
- Comments
- Tracked changes
- Text boxes and shapes
- Embedded objects
- Images containing text

If high-fidelity formatting is required, scan first, inspect findings, then anonymize a copy and visually review the result.

## Excel

Excel support covers `.xlsx` and `.xlsm` workbooks:

```bash
python3 scripts/run_anonymize.py input.xlsx --report report.json
python3 scripts/run_anonymize.py input.xlsm --mode scan
```

The runner creates `.venv`, installs `openpyxl` from `scripts/requirements.txt`, and runs the lower-level CLI with the virtual environment Python.

The CLI processes workbook core/custom properties, worksheet titles, string cell values, and hyperlink text/targets in worksheets, including hidden sheets. Workbook structure, styles, merged cells, hidden sheets, and most workbook metadata are preserved by `openpyxl`, but complex workbook features still need manual review after saving. Rich text formatting is preserved for cells that do not require replacement; matched rich text cells may be rewritten as plain strings. `.xlsm` files are opened with VBA preservation enabled, but macro code is not scanned or modified.

Bundled global field rules are also applied to adjacent worksheet cells and simple column headers. If a configured label such as `财务联系人`, `收件人`, or `联行号` appears in one cell, the value in the cell immediately to the right is scanned and anonymized with that rule. If a row looks like a header row, such as `A1=姓名`, values below that header are scanned with the same rule.

Formula expressions are scanned in `scan` and `verify` mode, including quoted string literals when an adjacent field label supplies context. Formula cells are not modified because rewriting formulas can corrupt workbook behavior or turn formulas into static strings. If `anonymize` detects sensitive values in formulas, it fails without writing an output workbook. Reports use safe coordinates such as `sheet 1!A1` rather than raw worksheet titles.

Numeric, date, and boolean cells are not modified by default to avoid changing cell types or formatting. When these cells appear in field-rule contexts, such as immediately to the right of a configured sensitive field label or below a sensitive column header, they are scanned as display text; if sensitive values are found, `anonymize` fails rather than writing a workbook with known residual sensitive values. If those cells must be automatically replaced, convert the target cells to text first or export a review copy to CSV/TSV.

Review or handle separately:

- Calculated formula results
- Comments and threaded comments
- Charts, images, shapes, and text boxes
- Pivot tables and slicers
- External workbook links and embedded objects
- Macro code in `.xlsm`
- Legacy `.xls` files, which should be converted to `.xlsx` before processing

## PDF

PDF support requires:

```bash
python3 scripts/run_anonymize.py input.pdf --mode scan
```

The runner creates `.venv`, installs `pymupdf` from `scripts/requirements.txt`, and runs the lower-level CLI with the virtual environment Python.

The CLI uses PyMuPDF redaction annotations and applies redactions before saving. This removes the matched text rather than drawing a visual cover over it.

If extractable sensitive text is detected but PyMuPDF cannot locate a matching redaction rectangle for it, the CLI fails instead of saving an output that may still contain the original text.

PDF output may need manual review when:

- The PDF is scanned or image-only
- Text is split across unusual layout fragments
- Sensitive text appears in images, stamps, annotations, forms, or embedded files
- Replacement text does not fit the original rectangle cleanly

If the scan report says no text layer was found, use OCR before anonymization or perform manual redaction with a tool that can inspect image content.

## Verification

`--mode verify` scans anonymized outputs for residual sensitive values using built-in detectors, bundled field rules, and any supplied custom terms. For Excel, verification includes workbook properties, worksheet titles, string cells, formula expressions, hyperlink text/targets, and non-string field-rule values. Built-in fake values from the CLI's replacement pools are ignored during verification, while values supplied through `--terms` are still reported if they remain. Residual findings make the CLI exit non-zero.

Reports use safe path references instead of raw input, output, or skipped-file paths because file and directory names may themselves contain sensitive values.

## Unsupported Formats

Convert unsupported formats to text, DOCX, Excel `.xlsx`, or PDF before using this skill. Keep the original file unchanged and preserve a copy of the conversion process for auditability. Check `skipped_inputs` in every directory report before considering the job complete.
