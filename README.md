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
- [目录批处理](#目录批处理)
- [自定义敏感词](#自定义敏感词)
- [词表生成](#词表生成)
- [LLM 辅助审核](#llm-辅助审核)
- [报告与映射](#报告与映射)
- [安全策略](#安全策略)
- [人工审核](#人工审核)
- [测试](#测试)
- [维护说明](#维护说明)
- [开源协议](#开源协议)

## 安装

通过 `npx skills` 安装到 Codex：

```bash
npx --yes skills add scuwjh/anonymize-sensitive-files-skill \
  --skill anonymize-sensitive-files \
  --agent codex \
  -g
```

安装到所有支持的 agent：

```bash
npx --yes skills add scuwjh/anonymize-sensitive-files-skill --all
```

只生成一次性使用提示、不安装：

```bash
npx --yes skills use scuwjh/anonymize-sensitive-files-skill@anonymize-sensitive-files
```

如需先确认仓库内可用的 skill：

```bash
npx --yes skills add scuwjh/anonymize-sensitive-files-skill -l
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
- PDF 脱敏的替换文字使用内置中文字体（`china-s`）写入，保证简体、繁体和全角标点正确渲染；替换文字过长时会自动缩小字号以适应原占位框。
- 提供词表生成器 `scripts/build_terms.py`：从语料自动挖掘公司、项目、机构、人员等候选实体，做类别判定与文件级覆盖校验，输出可直接使用的候选词表和人工审计表。
- 可选接入大模型做候选语义审核（`scripts/review_terms_llm.py`）：只做判定、不生成内容、不写文件，所有判定须过四道闸门（结构校验 / 原文锚定 / 交叉校验 / 非对称权限），并带请求级缓存。
- 提供审核标记工具 `scripts/mark_review.py`：在脱敏产物上标出每一处替换（假值对应哪个原值），并生成 diff 清单，便于逐条人工复核。
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

## 词表生成

没有现成词表时，`scripts/build_terms.py` 可以从语料自动生成候选词表。它是纯本地规则实现，不调用任何外部模型或接口：

```bash
.venv/bin/python scripts/build_terms.py ./docs --out-dir ./terms-build
```

处理流程分六个阶段：

1. **文件分级** —— 区分可解析（有文本层）、扫描件（无文本层，需 OCR）和不支持的格式，避免把「零检出」误当成「已处理」。
2. **候选发现** —— 多通道正则并集：公司全称、无后缀公司（如 `哈尔滨综合开发公司`）、简称定义点（`（下称"XX"）`）、机构、项目名、人名定义点（`法定代表人XX`）、中介简称列表、文件名片段。此处宁可多收，准确性交给后续过滤。
3. **词干聚类** —— 去掉公司/机构/项目后缀后聚成实体簇，只搜集语料中实际出现过的形态，不生成语料里没有的词条。
4. **类别判定** —— 依据通道来源与后缀特征投票判定 `org` / `project` / `name`，类别决定后续使用哪个假值池。
5. **规则过滤** —— 通用词、行政区划、句法碎片、跨实体拼接体、与假值池冲突的词条会被剔除或降到低置信桶。
6. **覆盖校验** —— 逐文件统计「候选实体数」与「词表命中数」，覆盖率异常低的文件会被点名，提示存在遗漏或该文件是扫描件。

产出：

| 文件 | 内容 |
| --- | --- |
| `terms-draft.txt` | 可直接用于 `--terms` 的候选词表（高/中置信） |
| `terms-audit.md` / `terms-audit.json` | 全部候选簇：类别、出现文件数、证据上下文；低置信候选（人名、宽泛项目名、文件名片段、拼接体）单独分桶 |
| `regression.md` | 回归结果：已知实体是否命中、通用词是否被误收 |
| `coverage.md` | 逐文件覆盖率明细与疑似漏检清单 |

词表是脱敏效果的上限：正则和字段规则只能发现「有固定形态」的敏感值，公司名、项目代号这类开放集合实体若不在词表里就不会被替换，`verify` 也不会报错。因此建议先跑一次词表生成，人工确认低置信分桶后，再带 `--terms` 执行正式脱敏。

## LLM 辅助审核

`scripts/build_terms.py` 的候选里，类别判定和「是不是敏感实体」本质是语义问题，纯规则会有天花板（人名边界、宽泛项目名、未定义简称等）。可选接入大模型对候选做语义审核。配置全部通过**环境变量**注入，密钥不落盘：

```bash
# 1. 注入配置（方式 A：仅当前终端会话有效）
export ANONYMIZE_LLM_ENDPOINT="https://你的端点/v1/chat/completions"
export ANONYMIZE_LLM_MODEL="deepseek-v41-flash"
export ANONYMIZE_LLM_API_KEY="sk-..."

# 方式 B：单次注入，密钥不进 shell history，也不残留到后续命令
ANONYMIZE_LLM_API_KEY="sk-..." ANONYMIZE_LLM_ENDPOINT="https://…" ANONYMIZE_LLM_MODEL="…" \
  .venv/bin/python scripts/review_terms_llm.py --audit … --out-dir …

# 2. 先用演练模式验证流程（不联网、不需要任何环境变量）
.venv/bin/python scripts/review_terms_llm.py \
  --audit ./terms-build/terms-audit.json \
  --out-dir ./terms-build \
  --dry-run

# 3. 正式审核
.venv/bin/python scripts/review_terms_llm.py \
  --audit ./terms-build/terms-audit.json \
  --out-dir ./terms-build \
  --batch-size 15 --min-confidence 0.6
```

环境变量（优先级：CLI 参数 > 环境变量 > 默认值）：

| 变量 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- |
| `ANONYMIZE_LLM_ENDPOINT` | ✅ | — | OpenAI 兼容的 `/chat/completions` 地址 |
| `ANONYMIZE_LLM_MODEL` | ✅ | — | 模型名 |
| `ANONYMIZE_LLM_API_KEY` | ✅ | — | 密钥；未设置时回退读 `DEEPSEEK_API_KEY` |
| `ANONYMIZE_LLM_TIMEOUT` | | `60` | 单次请求超时（秒） |
| `ANONYMIZE_LLM_MAX_RETRIES` | | `2` | 失败重试次数 |
| `ANONYMIZE_LLM_MAX_TOKENS` | | `4096` | 单次响应上限 |
| `ANONYMIZE_LLM_TEMPERATURE` | | `0` | 采样温度 |
| `ANONYMIZE_LLM_CACHE_DIR` | | `.llm-cache` | 请求缓存目录 |
| `ANONYMIZE_LLM_EXTRA_BODY` | | — | 透传到请求体的额外 JSON；推理模型建议 `{"enable_thinking": false}` |

临时切换端点或模型可用 `--llm-endpoint` / `--llm-model` / `--cache-dir` 覆盖。启动时会打印一行配置摘要（端点主机、模型、缓存目录），密钥一律显示为 `sk-***`；密钥不会出现在报告、日志或缓存里。

**推理模型的坑（务必先读）**：部分模型（实测 `deepseek-v4-flash-0731`）会先输出大段思考，且思考 token **计入 `max_tokens` 上限**。批量送审时思考可能吃光全部额度，返回的正文为空——表现为请求很慢/超时，重试后整批降级为待人工。解决方式是透传关闭思考的参数：

```bash
export ANONYMIZE_LLM_EXTRA_BODY='{"enable_thinking": false}'
```

实测同一批 3 条候选：默认参数 19.8 秒 / 输出 1706 token（其中思考 1581），关闭思考后 **3.0 秒 / 141 token**，判定质量不变；30 条候选从「跑不完」变成 17 秒完成。若你的模型不认这个参数，网关通常只是忽略它；若报错则去掉该变量即可。

**四道闸门**（每条模型判定都要过，不过即丢弃并计数）：

1. **结构闸门** —— `term` 必须逐字等于本批输入中的候选（改写、缩写或编造一律丢弃）、`action`/`category` 必须在枚举内、`confidence` 必须在 `[0,1]`；
2. **原文锚定闸门** —— 判 `keep` 时必须给出原文引文 `quote`，且该引文去掉空白后必须是输入证据的子串，否则视为幻觉丢弃；
3. **交叉闸门** —— 与代码层建议类别冲突的判定降级为待人工；
4. **非对称权限** —— 模型的 `veto` 只产出「建议否决」清单交由人工确认，**不自动剔除候选**；否决含公司/机构后缀的候选会被改判为待人工。因为漏脱敏远比误脱敏严重，模型在「删除」方向上的权限被收紧。

产出：

| 文件 | 内容 |
| --- | --- |
| `llm-review.json` | 全部判定与分桶（含被闸门丢弃的明细，用于观察模型幻觉率） |
| `llm-review.md` | 人读版：自动采纳 / 建议否决 / 待人工 / 丢弃统计 |
| `terms-llm-accepted.txt` | 经模型确认的候选词表，供与人工裁决结果合并 |

稳定性和可复现性：审核是**构建期的离线一次性环节**，正式脱敏运行不调用任何模型；审核结果按 `(model, prompt 版本, 输入)` 落盘缓存，重跑命中缓存不重复请求（实测第二遍 0 次网络调用）；词表经人工确认后冻结，同一批次重跑结果一致。单批调用失败只会把该批候选降级为待人工，不会中断整批，也不会漏候选。

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
- 使用 LLM 辅助审核时，送审内容与请求缓存都包含原文片段，属于敏感产物：只应发往你信任的端点，缓存目录按敏感数据处理，不要入库或对外分发。模型输出永远不直接写入文件——替换只由本地代码依据冻结词表执行。
- 密钥只从环境变量读取，不写入任何文件、报告或缓存；打印配置摘要时统一遮蔽为 `sk-***`。注意环境变量对同机同用户的进程可见，多用户或存在不可信进程的机器上建议改用钥匙串临时注入，不要把密钥写进 `~/.zshrc`。

本工具不能替代最终人工审核。高风险文件建议按 `scan` -> `anonymize` -> `verify` 的顺序处理，并根据报告中的 warning 复核不受自动处理覆盖的内容。

扫描件 PDF、图片、`.xls`、`.doc` 和 `.jpg` 不在自动覆盖范围内：状态为 `anonymized` 但检出为 0 且带 `no extractable text layer` 警告的 PDF，应视为尚未处理，需要 OCR 或人工复核。

没有现成敏感词表时，先用 `scripts/build_terms.py` 从语料生成候选词表（见 [词表生成](#词表生成)），人工确认低置信候选后带 `--terms` 重跑；也可以先扫一遍语料、汇总标签规则已经检出的取值，再补上跨文件共享前缀和文件名里的项目代号。

## 人工审核

自动脱敏的结果需要人工确认。`scripts/mark_review.py` 会在脱敏副本上标出每一处替换及对应原值，便于逐条比对：

```bash
.venv/bin/python scripts/mark_review.py \
  --input-dir ./anonymized \
  --mapping raw-mapping.json \
  --out-dir ./review
```

各格式的标记方式：

- **DOCX**：替换处高亮，并写入 Word 批注（原值 → 假值、类别）
- **XLSX / XLSM**：单元格填充色标记，并写入批注
- **PDF**：高亮注解，并叠加备注（原值 → 假值）
- **文本类**：行内标注，形如 `假值〔原:原值〕`

除标记副本外，还会输出 `review-diff.txt`（通读用）和 `review-diff.json`（结构化清单，便于筛选和统计）。

该工具需要 `--export-mapping` 生成的明文映射作为输入。`review/` 目录与明文映射文件一样含原始敏感值，必须存放在受控位置，不要随脱敏产物一起对外分发。

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
    ├── run_anonymize.py      # 入口：自动创建 .venv 并转发到 anonymize_files.py
    ├── anonymize_files.py    # scan / anonymize / verify 主流程与各格式读写
    ├── detectors.py          # 内置正则与字段规则检测
    ├── fake_data.py          # 假值池与映射（假值一致性、防品牌残留）
    ├── build_terms.py        # 实体词表生成器（候选发现 → 聚类 → 覆盖校验）
    ├── llm_client.py         # OpenAI 兼容调用与请求级缓存（配置走环境变量，标准库实现）
    ├── review_terms_llm.py   # 可选：LLM 候选审核（四道闸门 + 三桶分流）
    ├── mark_review.py        # 脱敏产物审核标记（批注 / 高亮 / diff 清单）
    ├── requirements.txt
    └── test_*.py             # unittest 回归测试
```

公开发布时请只提交源码、规则、文档和测试，不要提交真实业务文件、脱敏输入样本、运行报告、明文映射文件、生成的脱敏副本或本地虚拟环境目录。尤其是 `--export-mapping` 生成的映射文件包含原始敏感值，只应保存在受控位置。

## 开源协议

本项目使用 Apache License 2.0 发布，详见仓库根目录的 `LICENSE` 文件。
