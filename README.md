# 敏感文件脱敏 Skill

[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE) [![Agent Skills](https://img.shields.io/badge/Agent%20Skills-SKILL.md-4b7cff.svg)](skills/anonymize-sensitive-files/SKILL.md) [![skills.sh](https://img.shields.io/badge/skills.sh-compatible-2ea44f.svg)](https://skills.sh/) [![Codex](https://img.shields.io/badge/Codex-compatible-111827.svg)](skills/anonymize-sensitive-files/SKILL.md) [![Python](https://img.shields.io/badge/Python-3.10%2B-3776ab.svg)](skills/anonymize-sensitive-files/scripts/requirements.txt)

用于 Markdown、文本、CSV/TSV、JSON/YAML、DOCX、PDF 和 Excel 工作簿的本地敏感信息扫描与脱敏 Agent Skill。它默认生成不覆盖原文件的脱敏副本，并避免在报告中暴露原始敏感值。

适合用于合同、客户资料、采购文件、财务文件、内部报告、简历、业务文档等需要在共享前去除敏感信息的场景。

## 目录

- [安装](#安装)
- [快速开始](#快速开始)
- [效果示例](#效果示例)
- [支持的文件格式](#支持的文件格式)
- [主要能力](#主要能力)
- [自定义敏感词](#自定义敏感词)
- [报告与映射](#报告与映射)
- [安全策略](#安全策略)
- [测试](#测试)
- [维护说明](#维护说明)
- [开源协议](#开源协议)

## 安装

通过 `npx skills` 安装到 Codex：

```bash
npx --yes skills add zongzack/anonymize-sensitive-files-skill \
  --skill anonymize-sensitive-files \
  --agent codex \
  -g
```

安装到所有支持的 agent：

```bash
npx --yes skills add zongzack/anonymize-sensitive-files-skill --all
```

只生成一次性使用提示、不安装：

```bash
npx --yes skills use zongzack/anonymize-sensitive-files-skill@anonymize-sensitive-files
```

如需先确认仓库内可用的 skill：

```bash
npx --yes skills add zongzack/anonymize-sensitive-files-skill -l
```

支持从 GitHub repo path 安装 skill 的平台，也可以直接指向：

```text
skills/anonymize-sensitive-files/
```

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

## 效果示例

输入：

```text
姓名：示例姓名
手机号：13812345678
邮箱：user@example.com
```

输出示例：

```text
姓名：张三
手机号：19999999999
邮箱：zhangsan@example.com
```

报告默认只包含类别、位置、长度、统计信息和警告，不包含原始敏感值：

```json
{
  "category": "phone",
  "source": "cn_mobile",
  "start": 4,
  "end": 15,
  "length": 11
}
```

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
- 覆盖诉讼与上市核查类文本：案号（`（2020）京0105民初28200号`）、行政处罚决定书文号（`京市监罚字〔2019〕123号`）、固定电话与传真、以及 `原告/被告/委托诉讼代理人/发行人/被处罚单位/受理法院/项目名称/地块` 等标签字段。
- 中文地址识别要求两级行政区划加门牌要素，不再把 `境外上市`、`资本市场` 这类整句误判为地址。
- DOCX 额外覆盖页眉页脚与核心属性（作者、最后保存者等），PDF 额外覆盖文档元数据。
- 生成不覆盖原文件的脱敏副本。
- 使用真实感假数据替换原值，而不是简单写成 `[REDACTED]`。
- 同一次运行中，相同原值会替换为相同假值。
- 支持自定义敏感词表。
- 支持脱敏输出文件名（`--anonymize-filenames`），避免 `FS-02_某某项目-统计表.docx` 这类文件名继续泄露项目代号。
- 替换值不会包含任何已知敏感原值：当假值候选等于或内含词表词、或内含本次已替换过的原值时自动换下一个候选，避免出现 `星河集团 → 北京星河科技有限公司` 这种品牌字面残留。
- 业务类假值池按下拉生成扩容到 60-84 个候选，避免上百个真实实体挤进 12 个假名。
- 支持 Markdown 表格、DOCX 表格和 Excel 工作表里的相邻字段，例如 `A1=法定代表人`, `B1=某姓名`；Excel 也支持列头在上、值在下的字段规则，例如 `A1=姓名`, `A2=某姓名`。
- Excel 处理覆盖工作簿属性、工作表名、字符串单元格和 hyperlink 文本/目标，并会尽量保留工作簿、样式、隐藏表和宏；批注、图片、图表、文本框、透视表、嵌入对象和宏代码需要额外复核。
- `.xlsm` 会保留 VBA 项目，但不会扫描或修改宏代码。
- 公式表达式会在 scan/verify 中扫描，但 anonymize 不会改写公式；如果公式里检出敏感值，命令会拒绝生成可能残留敏感值的输出文件。
- 数字、日期和布尔值单元格默认不改，避免破坏类型和格式；如果相邻字段规则在这类单元格中检出敏感值，anonymize 会失败而不是保存残留敏感值的工作簿。如需自动替换这类值，可先将目标列转换为文本或导出为 CSV/TSV。
- Excel 纵向表头（如 `A1=项目名称`、`A2..An=各项目名`）的上下文会持续到该列数据结束，中途出现与标签同形的数据单元格（如某列填了律师事务所全称）不会冲掉已有表头上下文。

相邻字段示例：

```markdown
| 字段 | 值 |
| --- | --- |
| 法定代表人 | 某姓名 |
| 采购联系人 | 某姓名 |
| 紧急联系人 | 某姓名 某手机号 |
```

字段名会保留，右侧值会被脱敏。

## 目录批处理

递归处理目录：

```bash
python3 scripts/run_anonymize.py ./docs \
  --recursive \
  --output-dir ./anonymized \
  --report report.json
```

同一批文件请放在一条命令里处理完。假值按首次出现顺序分配，拆成多次运行会让同一个真实实体在不同批次拿到不同假名，而 `--seed` 只稳定报告里的哈希，不能跨运行保持假值一致。文件名本身也可能带项目代号或人名时，再加 `--anonymize-filenames`，输出文件名会沿用同一套映射并保留编号前缀便于回溯。

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
name:示例姓名
org:示例公司
project:示例项目
customer:示例客户
自定义敏感短语
```

带分类的词会使用对应假数据池；未分类的词会按通用自定义敏感词处理。

## 报告与映射

默认报告不会输出原始敏感值或原始文件路径，只包含安全路径引用、扩展名、类别、脱敏位置、长度、统计信息和警告。`verify` 会忽略假值本身，也会忽略“假值 + 无敏感信息的括号日期尾巴”这类组合串，但对仍包含词表词或正则可检值的单元格一律报残留。Excel 报告位置使用 `sheet 1!A1`、`workbook property title` 这类不含原始工作表名或属性值的坐标。

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

本工具不能替代最终人工审核。高风险文件建议按 `scan` -> `anonymize` -> `verify` 的顺序处理，并根据报告中的 warning 复核不受自动处理覆盖的内容。

扫描件 PDF、图片、`.xls`、`.doc` 和 `.jpg` 不在自动覆盖范围内：状态为 `anonymized` 但检出为 0 且带 `no extractable text layer` 警告的 PDF，应视为尚未处理，需要 OCR 或人工复核。

没有现成敏感词表时，可以先扫一遍语料、汇总标签规则已经检出的取值，再补上跨文件共享前缀和文件名里的项目代号，生成词表后带 `--terms` 重跑。

## 测试

首次运行可先准备依赖：

```bash
python3 scripts/run_anonymize.py --help
```

然后运行测试：

```bash
.venv/bin/python -m unittest discover -s scripts -p 'test_*.py'
```

## 维护说明

仓库结构：

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

公开发布时请只提交源码、规则、文档和测试，不要提交真实业务文件、脱敏输入样本、运行报告、明文映射文件、生成的脱敏副本或本地虚拟环境目录。尤其是 `--export-mapping` 生成的映射文件包含原始敏感值，只应保存在受控位置。

## 开源协议

本项目使用 Apache License 2.0 发布，详见仓库根目录的 `LICENSE` 文件。
