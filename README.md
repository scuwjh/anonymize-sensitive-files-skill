# 敏感文件脱敏 Skill

这是一个用于文档脱敏的 AI Agent Skill。它可以扫描并替换文档中的姓名、手机号、邮箱、身份证号、统一社会信用代码、银行卡号、银行联行号、地址、合同编号、公司/机构名、自定义敏感词等信息，同时尽量保留原文档的可读结构。

适合用于合同、客户资料、采购文件、财务文件、内部报告、简历、业务文档等需要在共享前去除敏感信息的场景。

## 支持的文件格式

当前支持：

- Markdown：`.md`, `.markdown`
- 纯文本：`.txt`, `.text`
- 表格文本：`.csv`, `.tsv`
- 结构化文本：`.json`, `.yaml`, `.yml`
- Word 文档：`.docx`
- PDF：`.pdf`

暂不直接支持 `.xlsx` / `.xls` 工作簿。Excel 文件可以先导出为 CSV/TSV 后处理；如果需要保留工作表、公式和单元格格式，需要另外扩展 Excel 专用处理逻辑。

## 主要能力

- 扫描敏感信息并生成 JSON 报告。
- 生成不覆盖原文件的脱敏副本。
- 使用真实感假数据替换原值，而不是简单写成 `[REDACTED]`。
- 同一次运行中，相同原值会替换为相同假值。
- 支持自定义敏感词表。
- 支持 Markdown 表格和 DOCX 表格里的相邻字段，例如：

```markdown
| 字段 | 值 |
| --- | --- |
| 法定代表人 | 某姓名 |
| 采购联系人 | 某姓名 |
| 紧急联系人 | 某姓名 某手机号 |
```

字段名会保留，右侧值会被脱敏。

## 仓库结构

```text
skills/anonymize-sensitive-files/
├── SKILL.md
├── agents/
├── references/
│   ├── anonymization-rules.md
│   ├── sensitive-field-rules.yaml
│   └── supported-formats.md
└── scripts/
    ├── anonymize_files.py
    ├── detectors.py
    ├── fake_data.py
    ├── requirements.txt
    └── run_anonymize.py
```

`skills/anonymize-sensitive-files/` 是实际 skill 目录。支持从 GitHub repo path 安装 skill 的平台，可以指向这个目录。

## 快速开始

进入 skill 目录：

```bash
cd skills/anonymize-sensitive-files
```

扫描文件：

```bash
python3 scripts/run_anonymize.py path/to/input.md --mode scan --report scan-report.json
```

生成脱敏副本：

```bash
python3 scripts/run_anonymize.py path/to/input.md --report anonymize-report.json
```

指定输出路径：

```bash
python3 scripts/run_anonymize.py path/to/input.md \
  --output path/to/input.anonymized.md \
  --report anonymize-report.json
```

验证脱敏结果：

```bash
python3 scripts/run_anonymize.py path/to/input.anonymized.md \
  --mode verify \
  --report verify-report.json
```

`run_anonymize.py` 会自动创建本地 `.venv` 并安装依赖，避免污染全局 Python 环境。

## 目录批处理

递归处理目录：

```bash
python3 scripts/run_anonymize.py ./docs \
  --recursive \
  --output-dir ./anonymized \
  --report report.json
```

显式传入但不支持的文件会记录在报告的 `skipped_inputs` 中，并让命令返回非零退出码，避免批处理时静默漏处理文件。

## 自定义敏感词

可以通过 `--terms` 提供自定义词表：

```bash
python3 scripts/run_anonymize.py contract.md \
  --terms sensitive_terms.txt \
  --seed 20260603
```

词表格式：

```text
name:李雷
org:星河集团
project:天枢计划
customer:华东重点客户
自定义敏感短语
```

带分类的词会使用对应假数据池；未分类的词会按通用自定义敏感词处理。

## 报告与映射

默认报告不会输出原始敏感值，只包含类别、位置、长度、统计信息和警告。

如果需要映射文件：

```bash
python3 scripts/run_anonymize.py input.md --mapping mapping.json
```

默认映射文件保存的是原值哈希到假值的映射。只有显式加上 `--export-mapping` 时才会导出原始值到假值的明文映射：

```bash
python3 scripts/run_anonymize.py input.md \
  --mapping raw-mapping.json \
  --export-mapping
```

明文映射文件本身是敏感文件，应谨慎保存和共享。

## 安全策略

- 不覆盖原始输入文件。
- 默认不在 stdout 或报告中暴露原始敏感值。
- 手机号假值使用纯数字格式，例如 `19999999999`。
- PDF 使用真正的 redaction，而不是只画黑框遮挡。
- 扫描件、图片中的文字、PDF 注释、DOCX 页眉页脚、文本框、批注和修订痕迹需要额外人工复核。

## 测试

首次运行可先准备依赖：

```bash
python3 scripts/run_anonymize.py --help
```

然后运行测试：

```bash
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

## 发布说明

本仓库是一个通用 GitHub 发布结构，实际 skill 位于：

```text
skills/anonymize-sensitive-files/
```

发布到 GitHub 后，支持 repo path 安装的 agent/skill 平台可以引用这个目录。

当前仓库暂未附带开源许可证。公开发布前请根据你的分发目标选择合适的 LICENSE。

