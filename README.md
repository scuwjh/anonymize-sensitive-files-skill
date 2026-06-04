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
- Excel 工作簿：`.xlsx`, `.xlsm`
- PDF：`.pdf`

暂不直接支持旧版 `.xls` 工作簿。`.xls` 文件可以先转换为 `.xlsx` 后处理。

## 主要能力

- 扫描敏感信息并生成 JSON 报告。
- 生成不覆盖原文件的脱敏副本。
- 使用真实感假数据替换原值，而不是简单写成 `[REDACTED]`。
- 同一次运行中，相同原值会替换为相同假值。
- 支持自定义敏感词表。
- 支持 Markdown 表格、DOCX 表格和 Excel 工作表里的相邻字段，例如 `A1=法定代表人`, `B1=某姓名`；Excel 也支持列头在上、值在下的字段规则，例如 `A1=姓名`, `A2=某姓名`。
- Excel 处理覆盖工作簿属性、工作表名、字符串单元格和 hyperlink 文本/目标，并会尽量保留工作簿、样式、隐藏表和宏；批注、图片、图表、文本框、透视表、嵌入对象和宏代码需要额外复核。
- `.xlsm` 会保留 VBA 项目，但不会扫描或修改宏代码。
- 公式表达式会在 scan/verify 中扫描，但 anonymize 不会改写公式；如果公式里检出敏感值，命令会拒绝生成可能残留敏感值的输出文件。
- 数字、日期和布尔值单元格默认不改，避免破坏类型和格式；如果相邻字段规则在这类单元格中检出敏感值，anonymize 会失败而不是保存残留敏感值的工作簿。如需自动替换这类值，可先将目标列转换为文本或导出为 CSV/TSV。

相邻字段示例：

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

默认报告不会输出原始敏感值或原始文件路径，只包含安全路径引用、扩展名、类别、脱敏位置、长度、统计信息和警告。Excel 报告位置使用 `sheet 1!A1`、`workbook property title` 这类不含原始工作表名或属性值的坐标。

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
- Excel 公式中如检出敏感值，脱敏模式会失败而不是保存残留敏感值的工作簿。
- Excel 相邻字段右侧的数字、日期、布尔值等非字符串单元格如检出敏感值，脱敏模式会失败而不是静默保留。
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

## GitHub 发布说明

实际 skill 位于：

```text
skills/anonymize-sensitive-files/
```

支持 repo path 安装的 agent/skill 平台可以引用这个目录。

公开发布时请只提交源码、规则、文档和测试，不要提交真实业务文件、脱敏输入样本、运行报告、明文映射文件、生成的脱敏副本或本地虚拟环境目录。尤其是 `--export-mapping` 生成的映射文件包含原始敏感值，只应保存在受控位置。

## 开源协议

本项目使用 Apache License 2.0 发布，详见仓库根目录的 `LICENSE` 文件。
