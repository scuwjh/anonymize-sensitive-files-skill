import json
import subprocess
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import anonymize_files

SCRIPT = Path(__file__).with_name("anonymize_files.py")


class AnonymizeFilesTest(unittest.TestCase):
    def test_markdown_anonymization_uses_fake_data_without_leaking_originals(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "case.md"
            source.write_text(
                "\n".join(
                    [
                        "# 客户资料",
                        "姓名：李雷",
                        "联系人：李雷",
                        "手机号：13812345678",
                        "邮箱：lilei@example.com",
                        "身份证号：110105199001010002",
                        "API Key: sk-live-abcdefghijklmnopqrstuvwxyz123456",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--seed",
                    "20260603",
                    "--report",
                    str(tmp_path / "report.json"),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            output = Path(payload["outputs"][0]["output_path"])
            report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
            anonymized = output.read_text(encoding="utf-8")

            self.assertTrue(output.exists())
            self.assertEqual(source.read_text(encoding="utf-8").count("李雷"), 2)
            self.assertNotIn("李雷", anonymized)
            self.assertNotIn("13812345678", anonymized)
            self.assertNotIn("lilei@example.com", anonymized)
            self.assertNotIn("110105199001010002", anonymized)
            self.assertNotIn("sk-live-abcdefghijklmnopqrstuvwxyz123456", anonymized)
            self.assertNotIn("[REDACTED", anonymized)
            self.assertIn("19999999999", anonymized)
            self.assertEqual(anonymized.count("张三"), 2)
            self.assertEqual(report["summary"]["total_findings"], 6)
            self.assertNotIn("李雷", json.dumps(report, ensure_ascii=False))
            self.assertNotIn("13812345678", json.dumps(report, ensure_ascii=False))

    def test_scan_mode_does_not_create_an_output_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            source.write_text("电话：13812345678\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--mode",
                    "scan",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["files_processed"], 1)
            self.assertEqual(payload["summary"]["total_findings"], 1)
            self.assertFalse((tmp_path / "note.anonymized.txt").exists())

    def test_custom_terms_are_replaced_with_stable_fake_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "memo.md"
            terms = tmp_path / "terms.txt"
            source.write_text("客户：星河集团\n项目：天枢计划\n星河集团复核。\n", encoding="utf-8")
            terms.write_text("org:星河集团\nproject:天枢计划\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--terms",
                    str(terms),
                    "--seed",
                    "1",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            anonymized = (tmp_path / "memo.anonymized.md").read_text(encoding="utf-8")
            self.assertNotIn("星河集团", anonymized)
            self.assertNotIn("天枢计划", anonymized)
            self.assertEqual(anonymized.count("北京星河科技有限公司"), 2)
            self.assertIn("星云迁移项目", anonymized)

    def test_global_field_rules_anonymize_labeled_text_without_terms_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "fields.md"
            source.write_text(
                "\n".join(
                    [
                        "财务联系人：顾安琪",
                        "联行号：313305007918",
                        "收件人：沈亦然",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--seed",
                    "field-rules",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            anonymized = (tmp_path / "fields.anonymized.md").read_text(encoding="utf-8")
            self.assertNotIn("顾安琪", anonymized)
            self.assertNotIn("313305007918", anonymized)
            self.assertNotIn("沈亦然", anonymized)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(tmp_path / "fields.anonymized.md"),
                    "--mode",
                    "verify",
                ],
                text=True,
                capture_output=True,
                check=True,
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["total_findings"], 0)

    def test_global_field_rules_anonymize_labeled_mobile_with_separators(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "phone.md"
            source.write_text("财务手机：138 1234 5678\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            anonymized = (tmp_path / "phone.anonymized.md").read_text(encoding="utf-8")
            self.assertNotIn("138 1234 5678", anonymized)
            self.assertIn("19999999999", anonymized)

    def test_global_field_rules_anonymize_markdown_table_adjacent_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "table-fields.md"
            source.write_text(
                "\n".join(
                    [
                        "| 字段 | 值 | 字段 | 值 |",
                        "| --- | --- | --- | --- |",
                        "| 法定代表人 | 林若航 | 采购联系人 | 顾安琪 |",
                        "| 紧急联系人 | 沈亦然 138-1234-5678 | 销售联系人 | 唐若云 |",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--seed",
                    "markdown-table-field-rules",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            anonymized = (tmp_path / "table-fields.anonymized.md").read_text(encoding="utf-8")
            for original in ["林若航", "顾安琪", "沈亦然", "唐若云", "138-1234-5678"]:
                self.assertNotIn(original, anonymized)
            self.assertIn("19999999999", anonymized)
            self.assertNotRegex(anonymized, r"1[3-9]\d-\d{4}-\d{4}")
            self.assertEqual(payload["summary"]["finding_counts"], {"name": 4, "phone": 1})

    def test_verify_reports_residual_markdown_table_adjacent_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "residual-table.md"
            source.write_text(
                "\n".join(
                    [
                        "| 字段 | 值 |",
                        "| --- | --- |",
                        "| 法定代表人 | 林若航 |",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--mode",
                    "verify",
                ],
                text=True,
                capture_output=True,
                check=False,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(payload["summary"]["finding_counts"], {"name": 1})

    def test_markdown_table_adjacent_rules_ignore_sentence_cells(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "sentence-table.md"
            source.write_text(
                "\n".join(
                    [
                        "| 条款 | 条件 | 说明 |",
                        "| --- | --- | --- |",
                        "| 付款条件 | 合同生效并收到乙方合格发票 | 甲方信息 |",
                        "| 甲方 | 乙方 | 签署栏 | 盖章 |",
                        "| 项目 | 甲方 | 项目 | 乙方 |",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--mode",
                    "scan",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["total_findings"], 0)

    def test_markdown_table_adjacent_phone_label_does_not_match_contact_name_rule(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "contact-phone-table.md"
            source.write_text(
                "\n".join(
                    [
                        "| 字段 | 值 |",
                        "| --- | --- |",
                        "| 联系人手机号 | 010-12345678 |",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            anonymized = (tmp_path / "contact-phone-table.anonymized.md").read_text(encoding="utf-8")
            self.assertEqual(payload["summary"]["finding_counts"], {"phone": 1})
            self.assertIn("19999999999", anonymized)
            self.assertNotIn("张三", anonymized)

    def test_expanded_global_field_rules_cover_common_business_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "expanded.md"
            source.write_text(
                "\n".join(
                    [
                        "法定代表人：林若航",
                        "甲方：北京北辰采购有限公司",
                        "开票邮箱：invoice@example.com",
                        "纳税人识别号：91110000000000000X",
                        "运单号：SF1234567890",
                        "微信号：wxid_demo_12345",
                        "MAC地址：AA:BB:CC:DD:EE:FF",
                    ]
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--seed",
                    "expanded-field-rules",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            anonymized = (tmp_path / "expanded.anonymized.md").read_text(encoding="utf-8")
            for original in [
                "林若航",
                "北京北辰采购有限公司",
                "invoice@example.com",
                "91110000000000000X",
                "SF1234567890",
                "wxid_demo_12345",
                "AA:BB:CC:DD:EE:FF",
            ]:
                self.assertNotIn(original, anonymized)
            self.assertIn("纳税人识别号：", anonymized)
            self.assertIn("MAC地址：", anonymized)

    def test_global_field_rules_anonymize_docx_adjacent_table_cells(self):
        try:
            from docx import Document
        except ImportError:
            self.skipTest("python-docx is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "fields.docx"
            doc = Document()
            table = doc.add_table(rows=3, cols=2)
            table.cell(0, 0).text = "收件人"
            table.cell(0, 1).text = "沈亦然"
            table.cell(1, 0).text = "财务联系人"
            table.cell(1, 1).text = "顾安琪"
            table.cell(2, 0).text = "联行号"
            table.cell(2, 1).text = "313305007918"
            doc.save(source)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--seed",
                    "field-rules",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            output = tmp_path / "fields.anonymized.docx"
            anonymized_doc = Document(output)
            text = "\n".join(
                cell.text
                for table in anonymized_doc.tables
                for row in table.rows
                for cell in row.cells
            )
            self.assertNotIn("沈亦然", text)
            self.assertNotIn("顾安琪", text)
            self.assertNotIn("313305007918", text)

    def test_docx_adjacent_phone_label_uses_phone_replacement_for_landline(self):
        try:
            from docx import Document
        except ImportError:
            self.skipTest("python-docx is not installed")

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "phone-table.docx"
            doc = Document()
            table = doc.add_table(rows=1, cols=2)
            table.cell(0, 0).text = "联系人电话"
            table.cell(0, 1).text = "010-12345678"
            doc.save(source)

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            output = tmp_path / "phone-table.anonymized.docx"
            anonymized_doc = Document(output)
            self.assertEqual(anonymized_doc.tables[0].cell(0, 1).text, "19999999999")

    def test_mapping_file_hashes_originals_by_default(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            mapping = tmp_path / "mapping.json"
            source.write_text("联系人：李雷\n电话：13812345678\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--mapping",
                    str(mapping),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            mapping_text = mapping.read_text(encoding="utf-8")
            self.assertNotIn("李雷", mapping_text)
            self.assertNotIn("13812345678", mapping_text)
            self.assertIn("张三", mapping_text)

    def test_output_cannot_overwrite_original_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            original = "电话：13812345678\n"
            source.write_text(original, encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--output",
                    str(source),
                ],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(source.read_text(encoding="utf-8"), original)
            self.assertIn("overwrite", result.stderr + result.stdout)

    def test_output_dir_preserves_relative_paths_for_duplicate_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source_a = tmp_path / "north" / "case.txt"
            source_b = tmp_path / "south" / "case.txt"
            output_dir = tmp_path / "out"
            source_a.parent.mkdir()
            source_b.parent.mkdir()
            source_a.write_text("电话：13812345678\n", encoding="utf-8")
            source_b.write_text("电话：13912345678\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(tmp_path),
                    "--recursive",
                    "--output-dir",
                    str(output_dir),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            outputs = {Path(item["output_path"]) for item in payload["outputs"]}
            self.assertEqual(
                outputs,
                {
                    output_dir / "north" / "case.anonymized.txt",
                    output_dir / "south" / "case.anonymized.txt",
                },
            )
            self.assertIn("19999999999", (output_dir / "north" / "case.anonymized.txt").read_text(encoding="utf-8"))
            self.assertIn("18888888888", (output_dir / "south" / "case.anonymized.txt").read_text(encoding="utf-8"))

    def test_verify_ignores_values_generated_by_anonymizer(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            source.write_text("电话：13812345678\n邮箱：lilei@example.com\n", encoding="utf-8")
            subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                text=True,
                capture_output=True,
                check=True,
            )

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(tmp_path / "note.anonymized.txt"),
                    "--mode",
                    "verify",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["total_findings"], 0)
            self.assertEqual(payload["outputs"][0]["status"], "verified")

    def test_verify_ignores_generated_secret_replacements(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "secret.txt"
            original_secret = "sk-live-abcdefghijklmnopqrstuvwxyz123456"
            source.write_text(f"API Key: {original_secret}\n", encoding="utf-8")

            subprocess.run(
                [sys.executable, str(SCRIPT), str(source)],
                text=True,
                capture_output=True,
                check=True,
            )

            anonymized_path = tmp_path / "secret.anonymized.txt"
            anonymized = anonymized_path.read_text(encoding="utf-8")
            self.assertNotIn(original_secret, anonymized)

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(anonymized_path),
                    "--mode",
                    "verify",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["total_findings"], 0)
            self.assertEqual(payload["outputs"][0]["status"], "verified")

    def test_verify_returns_nonzero_when_residual_findings_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            terms = tmp_path / "terms.txt"
            source.write_text("客户：星河集团\n", encoding="utf-8")
            terms.write_text("org:星河集团\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--mode",
                    "verify",
                    "--terms",
                    str(terms),
                ],
                text=True,
                capture_output=True,
            )

            payload = json.loads(result.stdout)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(payload["outputs"][0]["status"], "residual_findings")
            self.assertEqual(payload["summary"]["total_findings"], 1)

    def test_export_mapping_does_not_put_raw_values_in_stdout_or_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            mapping = tmp_path / "mapping.json"
            report = tmp_path / "report.json"
            source.write_text("联系人：李雷\n电话：13812345678\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--mapping",
                    str(mapping),
                    "--export-mapping",
                    "--report",
                    str(report),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            report_text = report.read_text(encoding="utf-8")
            mapping_text = mapping.read_text(encoding="utf-8")
            self.assertNotIn("李雷", result.stdout)
            self.assertNotIn("13812345678", result.stdout)
            self.assertNotIn("李雷", report_text)
            self.assertNotIn("13812345678", report_text)
            self.assertIn("李雷", mapping_text)
            self.assertIn("13812345678", mapping_text)

    def test_export_mapping_requires_mapping_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "note.txt"
            source.write_text("联系人：李雷\n", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--export-mapping",
                ],
                text=True,
                capture_output=True,
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn("--export-mapping requires --mapping", result.stderr)
            self.assertNotIn("李雷", result.stdout + result.stderr)

    def test_recursive_directory_reports_unsupported_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            supported = tmp_path / "note.txt"
            unsupported = tmp_path / "legacy.doc"
            supported.write_text("电话：13812345678\n", encoding="utf-8")
            unsupported.write_text("secret", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(tmp_path),
                    "--recursive",
                    "--mode",
                    "scan",
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            payload = json.loads(result.stdout)
            self.assertEqual(payload["summary"]["skipped_unsupported"], 1)
            self.assertEqual(payload["skipped_inputs"][0]["path"], str(unsupported))
            self.assertEqual(payload["skipped_inputs"][0]["reason"], "unsupported_extension")

    def test_explicit_unsupported_input_returns_nonzero_and_reports_skip(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            unsupported = tmp_path / "legacy.doc"
            unsupported.write_text("secret", encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(unsupported),
                    "--mode",
                    "scan",
                ],
                text=True,
                capture_output=True,
            )

            payload = json.loads(result.stderr)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(payload["summary"]["skipped_unsupported"], 1)
            self.assertEqual(payload["skipped_inputs"][0]["explicit"], True)

    def test_pdf_anonymization_errors_when_detected_text_has_no_redaction_rectangles(self):
        class FakePage:
            number = 0

            def get_text(self, mode):
                if mode != "text":
                    raise AssertionError(f"unexpected text extraction mode: {mode}")
                return "电话：13812345678"

            def search_for(self, value):
                if value != "13812345678":
                    raise AssertionError(f"unexpected search value: {value}")
                return []

            def add_redact_annot(self, *args, **kwargs):
                raise AssertionError("redaction annotation should not be added without rectangles")

            def apply_redactions(self):
                raise AssertionError("redactions should not be applied without rectangles")

        class FakeDoc:
            def __init__(self):
                self.page = FakePage()
                self.saved = False

            def __iter__(self):
                return iter([self.page])

            def save(self, *args, **kwargs):
                self.saved = True

        fake_doc = FakeDoc()
        fake_fitz = types.SimpleNamespace(open=lambda path: fake_doc)

        with patch.dict(sys.modules, {"fitz": fake_fitz}):
            with self.assertRaisesRegex(RuntimeError, "could not locate"):
                anonymize_files.anonymize_pdf(
                    Path("input.pdf"),
                    Path("output.pdf"),
                    [],
                    [],
                    anonymize_files.FakeDataFactory(),
                )
        self.assertFalse(fake_doc.saved)

    def test_custom_terms_do_not_keep_original_when_original_matches_first_fake_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = tmp_path / "memo.md"
            terms = tmp_path / "terms.txt"
            source.write_text("公司：北京星河科技有限公司\n项目：星云迁移项目\n", encoding="utf-8")
            terms.write_text("org:北京星河科技有限公司\nproject:星云迁移项目\n", encoding="utf-8")

            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    str(source),
                    "--terms",
                    str(terms),
                ],
                text=True,
                capture_output=True,
                check=True,
            )

            anonymized = (tmp_path / "memo.anonymized.md").read_text(encoding="utf-8")
            self.assertNotIn("北京星河科技有限公司", anonymized)
            self.assertNotIn("星云迁移项目", anonymized)


if __name__ == "__main__":
    unittest.main()
