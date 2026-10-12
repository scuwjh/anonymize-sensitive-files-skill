---
name: anonymize-sensitive-files
description: Use when anonymizing, desensitizing, de-identifying, masking, replacing, or removing sensitive information from PDF, Word DOCX, Markdown, text, contracts, reports, resumes, customer files, or documents containing PII, credentials, financial data, business secrets, names, phones, emails, IDs, addresses, tokens, companies, projects, or custom terms; also use for Chinese requests about 脱敏, 匿名化, 敏感信息, 个人信息, 身份证, 手机号, 邮箱, 地址, 银行卡, 合同, 客户, 公司, 项目, 密钥, or 自定义敏感词; also use when mining or building a sensitive-term list from a corpus before anonymizing, or when marking anonymized output for human review of each change (词表生成, 敏感词提取, 脱敏审核, 修改处标记).
---

# Anonymize Sensitive Files

## Overview

Use this skill to replace sensitive document data with realistic fake values while preserving readable structure. Prefer the bundled runner so the workflow works in Codex and in other skill-loading tools without manual dependency setup.

## Workflow

1. Identify the input files and file types.
2. Use the CLI's bundled global field rules for every supported document type; they are loaded by default from `references/sensitive-field-rules.yaml`.
3. Run `scan` first for unfamiliar or high-risk files.
4. If the corpus has no terms file yet, run `scripts/build_terms.py` to mine candidate entities from the corpus, then confirm the low-confidence buckets in its audit output before using the draft as `--terms`. Regexes and field rules only catch fixed shapes, so open-set entities such as company names, project codenames, and person names are replaced only if they are in the terms file; this step sets the ceiling of what gets replaced. When an OpenAI-compatible endpoint is configured, `scripts/review_terms_llm.py` can pre-judge the candidates, but every verdict must pass the four gates below and never writes files itself.
5. Process the whole batch in ONE invocation (`--recursive` or all paths at once). Fake values are assigned in order of first appearance, so splitting a batch across separate runs maps the same original value to different fake values in different batches. `--seed` only stabilizes report hashes; it does not keep fake values consistent across runs.
6. Run `anonymize` to create new output files; the CLI refuses outputs that overwrite originals. Add `--anonymize-filenames` when file names contain entity names, project codenames, or person names, because default output names reuse the original stem.
7. Run `verify` on anonymized outputs with the same `--terms` file. Verification ignores findings that are built-in fake values, and ignores label-context values that are only fake value plus non-sensitive scaffolding (for example `北京星河科技有限公司（2019/6/15）`); any value that still contains a term or a detected pattern after removing fake values is reported. Residual findings make the CLI exit non-zero.
8. When the user needs to review what changed, run `scripts/mark_review.py` on the anonymized outputs with the raw mapping. It marks each replacement with the original value it came from (DOCX comments, Excel fill plus comments, PDF highlights, inline text annotation) and writes a diff list. Treat its output directory as sensitive as the raw mapping.
9. For field-rule misses, update `references/sensitive-field-rules.yaml` and add or update tests before rerunning anonymization.
10. Review the JSON report for residual findings, skipped inputs, unsupported content, and warnings. Treat `anonymized` results with zero findings and a `no extractable text layer` warning as unprocessed scanned PDFs that still need OCR.

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
.venv/bin/python scripts/build_terms.py ./docs --out-dir ./terms-build
.venv/bin/python scripts/review_terms_llm.py --audit ./terms-build/terms-audit.json --out-dir ./terms-build --dry-run
.venv/bin/python scripts/mark_review.py --input-dir ./anonymized --mapping raw-mapping.json --out-dir ./review
```

`run_anonymize.py` only wraps the scan/anonymize/verify CLI. `build_terms.py`, `review_terms_llm.py`, and `mark_review.py` reuse the same virtual environment, so run `run_anonymize.py --help` once (which prepares `.venv`) before using them.

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

## Term List Generation

When the corpus has no terms file, `scripts/build_terms.py` mines candidates locally with plain rules; it calls no external model or service.

```bash
.venv/bin/python scripts/build_terms.py ./docs --out-dir ./terms-build
```

It runs six stages: file triage (parsable / scanned / unsupported) → multi-channel candidate discovery (full company names, suffix-less companies, defined abbreviations such as `（下称"XX"）`, institutions, project names, person names after labels such as `法定代表人`, advisor short lists, filename fragments) → stem clustering that only collects forms actually present in the corpus → rule-based category assignment (`org` / `project` / `name`) → filtering of generic words, sentence fragments, cross-entity joins, and fake-pool collisions → per-file coverage check that names files whose hit rate is abnormally low.

Outputs:

| File | Content |
| --- | --- |
| `terms-draft.txt` | Draft terms ready for `--terms` (high/medium confidence) |
| `terms-audit.md` / `.json` | Every candidate cluster with category, file count, and evidence context; low-confidence buckets (person names, broad project names, filename fragments, joined strings) are separate |
| `regression.md` | Regression check: known entities hit, generic words not wrongly collected |
| `coverage.md` | Per-file coverage plus a suspected-miss list |

Review the low-confidence buckets and merge in any terms only a human can confirm before relying on the draft. Treat low coverage on a parsable file as a signal of missed entities, and low coverage on a scanned PDF as confirmation that it has no text layer.

## LLM-Assisted Review (optional)

When an OpenAI-compatible endpoint is available, `scripts/review_terms_llm.py` reviews mined candidates semantically (category, keep/veto). It is a build-time offline step: the anonymize run itself never calls a model, and the model never generates terms, fake values, or file content.

```bash
.venv/bin/python scripts/review_terms_llm.py \
  --audit ./terms-build/terms-audit.json --out-dir ./terms-build --dry-run
```

Copy `scripts/llm-config.example.json` to `scripts/llm-config.json` and fill `endpoint`, `model`, and `api_key` (or leave `api_key` empty and set the environment variable named by `api_key_env`). The real config file and the request cache are gitignored.

Every verdict must pass four gates; a failing verdict is dropped and counted, never silently accepted:

1. **Structure** — `term` must be byte-identical to a candidate in the batch (rewrites, abbreviations, and invented terms are dropped); `action` and `category` must be inside the allowed sets; `confidence` must be within `[0, 1]`.
2. **Grounding** — a `keep` verdict must carry a `quote` that occurs verbatim in the supplied evidence (whitespace-insensitive); otherwise it is treated as a hallucination and dropped.
3. **Cross-check** — a category that disagrees with the code-layer suggestion is downgraded to manual review.
4. **Asymmetric authority** — a model `veto` only produces a "suggested veto" list for humans; candidates are never removed automatically, and vetoes of entity-looking names are escalated to manual review. Missing an entity is worse than over-redacting, so the model's authority to delete is restricted.

`--dry-run` exercises the whole pipeline with a local stub and no network. Verdicts are cached per `(model, prompt version, input)`, so a rerun does not call the API again. Use `--dry-run` to confirm plumbing, then run for real and merge `terms-llm-accepted.txt` with the human-confirmed buckets.

## Global Field Rules

The bundled rules in `references/sensitive-field-rules.yaml` apply to all supported file types, not only contracts. They cover common label/value fields such as emergency contacts, finance contacts, recipients, phone/email fields, addresses, bank accounts, bank routing codes, organizations, and common identifiers.

For Markdown, DOCX, and Excel tables, the CLI also checks adjacent cells: when a cell contains a configured label such as `财务联系人`, `收件人`, or `联行号`, the cell immediately to its right is scanned with that rule. Excel also applies field rules to values below header-like rows, such as `A1=姓名`, `A2=某姓名`. Field labels themselves are preserved; only values are replaced. Excel reports use safe coordinates such as `sheet 1!B2` rather than raw worksheet titles.

## Review Marking

When a human needs to audit what changed, `scripts/mark_review.py` marks every replacement with the original value it came from and emits a diff list. It requires the raw mapping produced by `--export-mapping`.

```bash
.venv/bin/python scripts/mark_review.py \
  --input-dir ./anonymized \
  --mapping raw-mapping.json \
  --out-dir ./review
```

- DOCX: highlight the replacement and add a Word comment with original value, fake value, and category.
- XLSX / XLSM: fill the cell and add a comment.
- PDF: highlight annotation plus a note carrying the original and fake value.
- Text formats: inline annotation in the form `fake〔orig:original〕`.

It also writes `review-diff.txt` for reading and `review-diff.json` for filtering. The output directory, like the raw mapping, contains original sensitive values: keep it in a controlled location and never ship it with the anonymized deliverables.

## Safety Rules

- Do not overwrite original files.
- Do not show full original sensitive values in chat unless the user explicitly provided them and needs them referenced.
- Do not export raw mappings unless the user asks; raw mappings are sensitive artifacts and are written only to `--mapping`, never to stdout or reports.
- Treat review-marked copies from `mark_review.py` as sensitive as the raw mapping: they pair original values with replacements, so keep them in a controlled location.
- When using `review_terms_llm.py`, the submitted evidence and the request cache both contain verbatim source excerpts: send them only to an endpoint the user trusts, treat the cache directory as sensitive, and never commit either. Model output must never be written into documents — replacements come only from the frozen terms file applied by the local code.
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
