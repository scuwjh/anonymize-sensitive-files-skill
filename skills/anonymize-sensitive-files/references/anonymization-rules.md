# Anonymization Rules

## Built-In Categories

The CLI detects and anonymizes:

- Chinese names when labeled with terms such as `姓名`, `联系人`, `负责人`, `经办人`
- Chinese mobile phone numbers and landline/fax numbers (`010-65991234`, `021-8888 5678`), reported as category `phone`
- Email addresses
- Chinese resident ID numbers with checksum validation
- Passport-like numbers
- Bank-card-like numbers with Luhn validation
- Unified social credit code-like values
- Chinese addresses that name at least two administrative levels plus a street or house number, for example `上海市浦东新区世纪大道100号`. Single-word matches such as `境外上市`, `资本市场`, or `市场部` are no longer treated as addresses.
- Litigation case numbers such as `（2020）京0105民初28200号`
- Administrative document numbers such as `京市监罚字〔2019〕123号`
- IPv4 addresses, excluding version-like contexts such as `版本 1.2.3.4`
- URLs and common domains
- API keys, tokens, secrets, and key-like strings
- Contract numbers such as `HT-2026-000001`
- Global label/value field rules from `sensitive-field-rules.yaml`
- Custom terms supplied by file

Regex-based detection is conservative. Use `--terms` for business-specific names, organizations, project names, customer names, and values that are not reliably discoverable from syntax.

## Global Field Rules

The CLI loads `references/sensitive-field-rules.yaml` by default for every supported input type. These rules detect labeled values that are not reliable regex-only patterns, including:

- `紧急联系人`, `财务联系人`, `收件人`, `收货人`, `授权代表`, `项目经理`
- `联系电话`, `财务手机号`, `电子邮箱`
- `联行号`, `银行账号`, `开户行`, `户名`
- `注册地址`, `收货地址`, `送达地址`, `签署地点`
- `合同编号`, `订单编号`, `项目编号`, `序列号`, `资产编号`

Rules support `字段：值` text, DOCX table rows, Excel worksheet rows where the label is in one cell and the value is in the cell immediately to the right, and simple Excel column headers where values appear below a header label. Excel field rules skip neighboring field labels and common header cells to avoid rewriting table headers as values. Use `--field-rules custom.yaml` to replace the bundled rules or `--no-field-rules` to disable them while debugging false positives.

## Fake Data Pools

Default fake data is realistic but clearly non-production. Business categories (`name`, `org`, `customer`, `project`, `address`, `contract`, `phone`) keep 60-84 candidates each, generated combinatorially at import so a large corpus does not collapse many different real entities onto one fake entity. Structured categories such as IDs, cards, IPs, URLs, domains, and secrets keep at least 6 candidates each. The full pools live in `scripts/fake_data.py`.

- `name`: `张三`, `李四`, `王五`, `赵六`, `孙七`
- `phone`: `19999999999`, `18888888888`, `16666666666`
- `email`: `zhangsan@example.com`, `lisi@example.com`
- `id_card`: structurally valid fake Chinese ID numbers
- `bank_card`: test-like card numbers that pass basic format/Luhn checks
- `bank_routing_code`: 12-digit test bank routing codes
- `org`: `北京星河科技有限公司`, `上海云启信息技术有限公司`
- `customer`: `华东客户A`, `北方客户B`
- `project`: `星云迁移项目`, `北辰数据平台`
- `address`: `北京市朝阳区示例路88号`
- `ip`: private network examples such as `10.0.0.1`
- `url` / `domain`: `example.com`, `internal.example.test`
- `secret`: non-production fake values such as `fake_00000000000000000000000000000000`
- `case_number`: `（2026）示例0100民初00001号`
- `doc_number`: `示例监罚字〔2026〕001号`

Within one run, identical originals map to identical fake values. Across runs the mapping can change because candidates are assigned in order of first appearance, so process a corpus in a single invocation.

A candidate is skipped when it equals or contains any already-known sensitive value (custom terms plus every original replaced so far in the run). If no candidate survives, the CLI emits `示例值-<hash>` instead of reusing a blocked value.

## Custom Terms File

Use one term per line:

```text
category:value
category:value
plain value
```

Supported useful categories include:

- `name`
- `phone`
- `email`
- `id_card`
- `org`
- `customer`
- `project`
- `contract`
- `address`
- `secret`
- `bank_routing_code`
- `custom`

Aliases such as `company`, `organization`, `person`, `mobile`, `token`, and Chinese labels such as `姓名`, `公司`, `客户`, `项目`, `联行号` are normalized.

Blank lines and lines starting with `#` are ignored.

## Mapping Artifacts

Default reports do not contain original sensitive values or raw file paths. File paths are represented as safe hash-like references plus extensions. Excel findings use safe coordinates such as `sheet 1!B2` and do not include raw worksheet titles. If `--mapping` is used without `--export-mapping`, the mapping file stores salted hashes of originals and fake replacements. Without `--seed`, the salt is random for each run.

Use `--seed` only when stable mapping hashes are needed across runs. Choose a high-entropy seed; low-entropy seeds can make phone numbers, IDs, and other enumerable values vulnerable to dictionary checks.

Only use `--export-mapping` with `--mapping` when the user explicitly needs raw original-to-fake mappings. Raw mappings are written to the mapping file only; stdout and JSON reports stay sanitized. Treat mapping outputs as sensitive and store them separately from anonymized deliverables.

## Legal And Securities Field Rules

The bundled rules also cover litigation and IPO-review wording: parties and staff such as `原告`, `被告`,
`申请人`, `被申请人`, `第三人`, `委托诉讼代理人`, `经办律师`, `审判长`, and `书记员` map to `name`;
subjects and authorities such as `发行人`, `上市公司`, `拟上市主体`, `被处罚单位`, `处罚机关`, `受理法院`,
`目标公司`, and `关联方` map to `org`; `项目名称`, `地块`, `宗地`, `楼盘`, and `重组标的` map to `project`;
`案号` maps to `case_number` and `决定书文号` maps to `doc_number`.

Entity names that regexes cannot discover, such as project codenames, are best handled with a `--terms`
file. For a corpus without a ready-made list, derive one: scan the corpus once, harvest the values that
label rules already detect, add shared prefixes and codenames found in file names, then rerun
anonymization with that terms file.
