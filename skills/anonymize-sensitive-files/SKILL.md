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
4. Run `anonymize` to create new output files; the CLI refuses outputs that overwrite originals.
5. Run `verify` on anonymized outputs when the source values or terms file are available; verification ignores the CLI's built-in fake values but still reports custom terms. Residual findings make the CLI exit non-zero.
6. For field-rule misses, update `references/sensitive-field-rules.yaml` and add or update tests before rerunning anonymization.
7. Review the JSON report for residual findings, skipped inputs, unsupported content, and warnings.

## CLI

From the skill directory:

```bash
python3 scripts/run_anonymize.py input.md
python3 scripts/run_anonymize.py input.docx --report report.json
python3 scripts/run_anonymize.py input.xlsx --mode scan
python3 scripts/run_anonymize.py input.pdf --mode scan
python3 scripts/run_anonymize.py ./docs --recursive --output-dir ./anonymized
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

## Replacement Policy

Use fake data, not `[REDACTED_*]` placeholders. The CLI keeps the same real value mapped to the same fake value within one run, so repeated names, phone numbers, organizations, and custom terms remain internally consistent.

If a source value already matches the first fake candidate for its category, the CLI chooses a different fake value so the original is not preserved by accident.

Default examples:

- Names: `张三`, `李四`, `王五`
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
- For Excel, scan workbook properties, worksheet titles, string cells, formula expressions, hyperlink text, and non-string field-rule values. Anonymization rewrites string workbook properties, worksheet titles, string cells, and hyperlink text, but refuses to save output when formula expressions or non-string field-rule values still contain detected sensitive values.
- For PDF, require true redaction application, not visual black boxes. The bundled CLI uses PyMuPDF redaction annotations and `apply_redactions()`, and fails if detected text cannot be matched to redaction rectangles.
- For scanned PDFs, images, forms, annotations, comments, tracked changes, footnotes, and text boxes, report the limitation and ask for OCR/manual review when needed.

## Format Notes

Read `references/supported-formats.md` when processing DOCX/Excel/PDF files, when preserving layout matters, or when the report contains warnings.
