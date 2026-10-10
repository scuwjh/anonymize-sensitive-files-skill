---
name: anonymize-sensitive-files
description: Use when anonymizing, desensitizing, de-identifying, masking, replacing, or removing sensitive information from PDF, Word DOCX, Markdown, text, contracts, reports, resumes, customer files, or documents containing PII, credentials, financial data, business secrets, names, phones, emails, IDs, addresses, tokens, companies, projects, or custom terms; also use for Chinese requests about 脱敏, 匿名化, 敏感信息, 个人信息, 身份证, 手机号, 邮箱, 地址, 银行卡, 合同, 客户, 公司, 项目, 密钥, or 自定义敏感词.
---

# Anonymize Sensitive Files

## Overview

Use this skill to replace sensitive document data with realistic fake values while preserving readable structure. Prefer the bundled runner so the workflow works in Codex and in other skill-loading tools without manual dependency setup.

## Workflow

1. Identify the input files and file types.
2. Use the CLI's bundled global field rules for every supported document type; they are loaded by default from `references/sensitive-field-rules.yaml`.
3. Run `scan` first for unfamiliar or high-risk files.
4. Process the whole batch in ONE invocation (`--recursive` or all paths at once). Fake values are assigned in order of first appearance, so splitting a batch across separate runs maps the same original value to different fake values in different batches. `--seed` only stabilizes report hashes; it does not keep fake values consistent across runs.
5. Run `anonymize` to create new output files; the CLI refuses outputs that overwrite originals. Add `--anonymize-filenames` when file names contain entity names, project codenames, or person names, because default output names reuse the original stem.
6. Run `verify` on anonymized outputs with the same `--terms` file. Verification ignores findings that are built-in fake values, and ignores label-context values that are only fake value plus non-sensitive scaffolding (for example `北京星河科技有限公司（2019/6/15）`); any value that still contains a term or a detected pattern after removing fake values is reported. Residual findings make the CLI exit non-zero.
7. For field-rule misses, update `references/sensitive-field-rules.yaml` and add or update tests before rerunning anonymization.
8. Review the JSON report for residual findings, skipped inputs, unsupported content, and warnings. Treat `anonymized` results with zero findings and a `no extractable text layer` warning as unprocessed scanned PDFs that still need OCR.

## CLI

From the skill directory:

```bash
python3 scripts/run_anonymize.py input.md
python3 scripts/run_anonymize.py input.docx --report report.json
python3 scripts/run_anonymize.py input.xlsx --mode scan
python3 scripts/run_anonymize.py input.pdf --mode scan
python3 scripts/run_anonymize.py ./docs --recursive --output-dir ./anonymized
python3 scripts/run_anonymize.py ./docs --recursive --output-dir ./anonymized --anonymize-filenames --terms terms.txt
python3 scripts/run_anonymize.py contract.md --terms sensitive_terms.txt --seed 20260603
python3 scripts/run_anonymize.py input.docx --field-rules custom_field_rules.yaml
python3 scripts/run_anonymize.py input.docx --no-field-rules
python3 scripts/run_anonymize.py output.anonymized.md --mode verify --terms sensitive_terms.txt
```

`scripts/run_anonymize.py` automatically creates `.venv`, installs `scripts/requirements.txt`, and runs the real CLI through the virtual environment Python. This avoids polluting global Python installs and works even when the caller cannot activate a shell environment.

For text-only work in an environment that already has PyYAML installed, skip installation:

```bash
python3 scripts/run_anonymize.py input.md --no-install
```

If the caller already manages dependencies, call the lower-level CLI directly:

```bash
python3 scripts/anonymize_files.py input.md
```

The lower-level CLI loads the bundled field rules by default, so PyYAML is required unless `--no-field-rules` is used. Use `--field-rules` to replace the bundled rules, or `--no-field-rules` only for debugging false positives.

## Batch Reproduction

Reproducing a batch pins four things: the input file set, the terms file, the field rules, and the installed parser versions.

- Fake values are assigned in order of first appearance, so a whole batch must be one invocation. Splitting the same corpus across two runs changes the replacements and breaks cross-file consistency.
- Collected input paths are normalized to sorted order and duplicate input paths are processed once, so a directory walk and an explicit file list over the same corpus produce the same mapping. Filesystem readdir order no longer matters.
- Line order inside the terms file does not affect output. The category label does, because it selects the fake-value pool; unknown categories normalize to `custom`.
- `--seed` only stabilizes digest keys in reports and `--mapping`; it does not change which fake value is chosen.
- `scripts/requirements.txt` lists minimum bounds, not pins. PyMuPDF and openpyxl versions change which text is extractable and therefore which spans get replaced, so pin them in the environment that produced an audited batch.
- Outputs are content-deterministic but not byte-deterministic: OOXML `<dcterms:created>` / `<dcterms:modified>` and PDF trailer `/ID` plus `ModDate` are stamped at save time. Confirm a rerun by comparing OOXML part payloads and PDF text layers, redaction rectangles, and non-date metadata, not file hashes.

## Replacement Policy

Use fake data, not `[REDACTED_*]` placeholders. The CLI keeps the same real value mapped to the same fake value within one run, so repeated names, phone numbers, organizations, and custom terms remain internally consistent.

If a source value already matches a fake candidate, or if a fake candidate contains any known sensitive value (custom terms plus originals already replaced in the run), the CLI chooses a different fake value. This prevents replacements such as `星河集团` to `北京星河科技有限公司`, which would keep the sensitive brand visible. When every candidate is blocked, the CLI falls back to `示例值-<hash>`.

Business pools are generated combinatorially (about 60-84 values for `name`, `org`, `address`, `project`, `customer`, and `contract`) so a large corpus does not map many different real entities onto the same fake entity.

Default examples:

- Names: `张三`, `李四`, `王五`
- Case numbers: `（2026）示例0100民初00001号`
- Document numbers: `示例监罚字〔2026〕001号`
- Phones: `19999999999`, `18888888888`
- Emails: `zhangsan@example.com`
- IDs: structurally valid fake Chinese ID numbers
- Organizations: `北京星河科技有限公司`
- Projects: `星云迁移项目`
- Secrets and tokens: non-production fake values such as `fake_00000000000000000000000000000000`

For detailed categories and term-file syntax, read `references/anonymization-rules.md`.

## Custom Terms

Use `--terms` for one-off names, organizations, customer names, project names, contract numbers, or other business-specific values that regexes and bundled field rules cannot infer.

Term file format:

```text
name:李雷
org:星河集团
project:天枢计划
customer:华东重点客户
plain sensitive phrase
```

Lines without a category use the generic custom fake-value pool.

## Global Field Rules

The bundled rules in `references/sensitive-field-rules.yaml` apply to all supported file types, not only contracts. They cover common label/value fields such as emergency contacts, finance contacts, recipients, phone/email fields, addresses, bank accounts, bank routing codes, organizations, and common identifiers.

For Markdown, DOCX, and Excel tables, the CLI also checks adjacent cells: when a cell contains a configured label such as `财务联系人`, `收件人`, or `联行号`, the cell immediately to its right is scanned with that rule. Excel also applies field rules to values below header-like rows, such as `A1=姓名`, `A2=某姓名`. Field labels themselves are preserved; only values are replaced. Excel reports use safe coordinates such as `sheet 1!B2` rather than raw worksheet titles.

## Safety Rules

- Do not overwrite original files.
- Do not show full original sensitive values in chat unless the user explicitly provided them and needs them referenced.
- Do not export raw mappings unless the user asks; raw mappings are sensitive artifacts and are written only to `--mapping`, never to stdout or reports.
- Prefer reports with category counts, safe path references, locations, and warnings over reports containing original values or raw file paths.
- Treat `skipped_inputs` as incomplete processing. Explicit unsupported or missing input paths make the CLI exit non-zero.
- For Excel, scan workbook properties, worksheet titles, string cells, formula expressions, hyperlink text, cell comments (body and author), and non-string field-rule values. Anonymization rewrites string workbook properties, worksheet titles, string cells, hyperlink text, and cell comments, but refuses to save output when formula expressions or non-string field-rule values still contain detected sensitive values.
- For PDF, require true redaction application, not visual black boxes. The bundled CLI uses PyMuPDF redaction annotations and `apply_redactions()`, and fails if detected text cannot be matched to redaction rectangles.
- DOCX core properties (author, last modified by, title, subject, comments, keywords, category) and PDF document metadata are scanned and anonymized; still verify the report for these locations.
- DOCX paragraph text cached inside field results and hyperlinks, such as table-of-contents entries, is rewritten run by run instead of collapsed into the first run. Collapsing leaves the original visible next to the replacement and destroys `w:fldChar`, so paragraphs containing field instructions always use in-place rewriting.
- Still review DOCX comments, footnotes, endnotes, and text boxes, Excel charts, shapes, and pivot tables, and PDF images and annotations separately. These are reported as warnings, not silently covered.
- For scanned PDFs, images, forms, annotations, comments, tracked changes, footnotes, and text boxes, report the limitation and ask for OCR/manual review when needed.

## Format Notes

Read `references/supported-formats.md` when processing DOCX/Excel/PDF files, when preserving layout matters, or when the report contains warnings.
