from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Finding:
    category: str
    value: str
    start: int
    end: int
    source: str
    location: str | None = None


@dataclass(frozen=True)
class FieldComponent:
    category: str
    pattern: str


@dataclass(frozen=True)
class FieldRule:
    labels: tuple[str, ...]
    category: str
    pattern: str | None = None
    components: tuple[FieldComponent, ...] = ()


DEFAULT_FIELD_RULES_PATH = Path(__file__).resolve().parent.parent / "references" / "sensitive-field-rules.yaml"


BUILTIN_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (
        "secret",
        "api_key",
        re.compile(
            r"\b(?:sk|pk|rk|ak|api|token|secret|key)[-_](?:live|test|prod|dev)?[-_][A-Za-z0-9_\-]{16,}\b",
            re.IGNORECASE,
        ),
    ),
    (
        "email",
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
    ),
    (
        "id_card",
        "cn_id_card",
        re.compile(r"(?<!\d)(?:[1-9]\d{5}(?:19|20)\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])\d{3}[\dXx])(?!\d)"),
    ),
    (
        "phone",
        "cn_mobile",
        re.compile(r"(?<!\d)(?:\+?86[- ]?)?1[3-9](?:[- ]?\d){9}(?!\d)"),
    ),
    (
        "social_credit_code",
        "cn_social_credit_code",
        re.compile(r"\b[0-9A-HJ-NPQRTUWXY]{2}\d{6}[0-9A-HJ-NPQRTUWXY]{10}\b"),
    ),
    (
        "bank_card",
        "bank_card",
        re.compile(r"(?<!\d)(?:\d[ -]?){15,19}\d(?!\d)"),
    ),
    (
        "ip",
        "ipv4",
        re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b"),
    ),
    (
        "url",
        "url",
        re.compile(r"\bhttps?://[^\s<>\"]+"),
    ),
    (
        "domain",
        "domain",
        re.compile(r"\b(?:[A-Za-z0-9-]+\.)+(?:com|cn|net|org|io|test|local)\b"),
    ),
    (
        "contract",
        "contract_number",
        re.compile(r"\b(?:HT|CONTRACT|合同)[-_]?\d{4}[-_]?\d{4,8}\b", re.IGNORECASE),
    ),
    (
        "passport",
        "passport",
        re.compile(r"\b[EGPSeps][0-9]{8}\b"),
    ),
    (
        "phone",
        "cn_landline",
        re.compile(r"(?<!\d)0\d{2,3}[- ]\d{3,4}[- ]?\d{3,4}(?:[- ]\d{1,4})?(?!\d)"),
    ),
    (
        "case_number",
        "cn_case_number",
        re.compile(
            r"[（(]\s*(?:19|20)\d{2}\s*[）)]\s*[\u4e00-\u9fff]{1,8}\d{0,8}[\u4e00-\u9fff]{1,8}\d{1,8}\s*号",
        ),
    ),
    (
        "doc_number",
        "cn_doc_number",
        re.compile(
            r"[\u4e00-\u9fff]{2,12}字?\s*[〔\[（]\s*(?:19|20)\d{2}\s*[〕\]）]\s*(?:第)?\s*\d{1,6}\s*号",
        ),
    ),
]


NAME_LABEL_PATTERN = re.compile(r"(?P<label>姓名|联系人|客户经理|负责人|经办人)\s*[:：]\s*(?P<name>[\u4e00-\u9fff]{2,4})")
ADDRESS_PATTERN = re.compile(
    r"(?:[\u4e00-\u9fff]{2,8}(?:省|自治区))?"
    r"[\u4e00-\u9fff]{2,8}市"
    r"[\u4e00-\u9fff]{1,8}(?:区|县|市|旗)"
    r"[\u4e00-\u9fff0-9A-Za-z\-（）()]{0,12}"
    r"(?:大厦|广场|中心|大道|街道|路|街|道|巷|弄|里|村|镇|号|栋|幢|单元|层|室)"
    r"[\u4e00-\u9fff0-9A-Za-z\-（）()号室单元栋幢弄巷]{0,16}"
)
VERSION_CONTEXT_PATTERN = re.compile(r"(?:版本|version|ver\.?|v)\s*$", re.IGNORECASE)
MARKDOWN_TABLE_HEADER_VALUES = frozenset({"项目", "日期", "签字", "签名", "盖章", "签章"})


def is_valid_cn_id_card(value: str) -> bool:
    value = value.upper()
    if not re.fullmatch(r"[1-9]\d{16}[\dX]", value):
        return False
    weights = [7, 9, 10, 5, 8, 4, 2, 1, 6, 3, 7, 9, 10, 5, 8, 4, 2]
    checks = "10X98765432"
    total = sum(int(value[index]) * weights[index] for index in range(17))
    return checks[total % 11] == value[-1]


def luhn_valid(value: str) -> bool:
    digits = [int(char) for char in re.sub(r"\D", "", value)]
    if len(digits) < 13:
        return False
    checksum = 0
    parity = len(digits) % 2
    for index, digit in enumerate(digits):
        if index % 2 == parity:
            digit *= 2
            if digit > 9:
                digit -= 9
        checksum += digit
    return checksum % 10 == 0


def load_custom_terms(path: Path | None) -> list[tuple[str, str]]:
    if path is None:
        return []
    terms: list[tuple[str, str]] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            category, value = line.split(":", 1)
            terms.append((category.strip(), value.strip()))
        else:
            terms.append(("custom", line))
    return [(category, value) for category, value in terms if value]


def load_field_rules(path: Path | None = None, *, use_default: bool = True) -> list[FieldRule]:
    if path is None:
        if not use_default:
            return []
        path = DEFAULT_FIELD_RULES_PATH
        if not path.exists():
            return []
    elif not path.exists():
        raise FileNotFoundError(f"Field rules file not found: {path}")

    try:
        import yaml
    except ImportError as exc:
        raise RuntimeError("Field rules require PyYAML. Install with: pip install pyyaml") from exc

    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    fields = data.get("fields", [])
    if not isinstance(fields, list):
        raise ValueError("Field rules file must contain a top-level 'fields' list.")

    rules: list[FieldRule] = []
    for index, raw_rule in enumerate(fields, 1):
        if not isinstance(raw_rule, dict):
            raise ValueError(f"Field rule #{index} must be a mapping.")
        labels = _as_string_tuple(raw_rule.get("labels") or raw_rule.get("label"))
        if not labels:
            raise ValueError(f"Field rule #{index} must define at least one label.")
        category = str(raw_rule.get("category") or "custom").strip() or "custom"
        pattern = raw_rule.get("pattern")
        components = tuple(_load_field_components(raw_rule.get("components", []), index))
        rules.append(
            FieldRule(
                labels=labels,
                category=category,
                pattern=str(pattern) if pattern else None,
                components=components,
            )
        )
    return rules


def detect_sensitive_values(
    text: str,
    custom_terms: list[tuple[str, str]] | None = None,
    field_rules: list[FieldRule] | None = None,
) -> list[Finding]:
    findings: list[Finding] = []

    for category, source, pattern in BUILTIN_PATTERNS:
        for match in pattern.finditer(text):
            value = match.group(0)
            if _overlaps_existing(match.start(), match.end(), findings):
                continue
            if category == "ip" and _looks_like_version_context(text, match.start()):
                continue
            if category == "id_card" and not is_valid_cn_id_card(value):
                continue
            if category == "bank_card" and not luhn_valid(value):
                continue
            findings.append(Finding(category, value, match.start(), match.end(), source))

    for match in NAME_LABEL_PATTERN.finditer(text):
        start, end = match.span("name")
        findings.append(Finding("name", match.group("name"), start, end, "labeled_name"))

    for match in ADDRESS_PATTERN.finditer(text):
        if _followed_by_field_separator(text, match.end()):
            continue
        start, end, value = _trim_address_intro(text, match.start(), match.end())
        if _looks_like_field_label(value, field_rules or []):
            continue
        if len(value) >= 6 and not _overlaps_existing(start, end, findings):
            findings.append(Finding("address", value, start, end, "address"))

    for finding in detect_field_rule_values(text, field_rules or []):
        if not _overlaps_existing(finding.start, finding.end, findings):
            findings.append(finding)

    for finding in detect_markdown_table_field_values(text, field_rules or []):
        if not _overlaps_existing(finding.start, finding.end, findings):
            findings.append(finding)

    for category, value in custom_terms or []:
        start = 0
        while True:
            index = text.find(value, start)
            if index < 0:
                break
            end = index + len(value)
            if not _overlaps_existing(index, end, findings):
                findings.append(Finding(category, value, index, end, "custom_terms"))
            start = end

    return sorted(findings, key=lambda item: (item.start, -(item.end - item.start)))


def detect_markdown_table_field_values(text: str, field_rules: list[FieldRule]) -> list[Finding]:
    findings: list[Finding] = []
    if not text or not field_rules:
        return findings

    line_start = 0
    for raw_line in text.splitlines(keepends=True):
        line = raw_line.rstrip("\r\n")
        cells = _markdown_table_cells(line, line_start)
        cells_are_labels = [_looks_like_field_label(cell_text, field_rules) for cell_text, _start, _end in cells]
        for cell_index in range(len(cells) - 1):
            label_text, _label_start, _label_end = cells[cell_index]
            if not cells_are_labels[cell_index]:
                continue
            if cell_index > 0 and cells_are_labels[cell_index - 1]:
                continue
            if cells_are_labels[cell_index + 1]:
                continue
            value_text, value_start, _value_end = cells[cell_index + 1]
            if _looks_like_markdown_table_header_value(value_text):
                continue
            for finding in detect_field_rule_values(value_text, field_rules, label_context=label_text):
                shifted = Finding(
                    finding.category,
                    finding.value,
                    value_start + finding.start,
                    value_start + finding.end,
                    "markdown_table_field_rules",
                )
                if not _overlaps_existing(shifted.start, shifted.end, findings):
                    findings.append(shifted)
        line_start += len(raw_line)

    return sorted(findings, key=lambda item: (item.start, -(item.end - item.start)))


def detect_field_rule_values(
    text: str,
    field_rules: list[FieldRule],
    *,
    label_context: str | None = None,
) -> list[Finding]:
    findings: list[Finding] = []
    if not text or not field_rules:
        return findings

    if label_context is not None:
        for rule in best_field_rules_for_label(field_rules, label_context):
            findings.extend(_find_value_findings(text, 0, rule))
        return sorted(findings, key=lambda item: (item.start, -(item.end - item.start)))

    for rule in field_rules:
        for label in sorted(rule.labels, key=len, reverse=True):
            pattern = re.compile(
                r"(?<![\u4e00-\u9fffA-Za-z0-9])"
                + re.escape(label)
                + r"\s*[:：]\s*(?P<value>[^\n\r；;，,。]+)",
                re.IGNORECASE,
            )
            for match in pattern.finditer(text):
                value_start, value_end = _trim_span(text, *match.span("value"))
                if value_start >= value_end:
                    continue
                for finding in _find_value_findings(text[value_start:value_end], value_start, rule):
                    if not _overlaps_existing(finding.start, finding.end, findings):
                        findings.append(finding)
    return sorted(findings, key=lambda item: (item.start, -(item.end - item.start)))


def field_rule_matches_label(rule: FieldRule, label_text: str) -> bool:
    return field_rule_label_match_length(rule, label_text) > 0


def best_field_rules_for_label(field_rules: list[FieldRule], label_text: str) -> list[FieldRule]:
    matches = [(field_rule_label_match_length(rule, label_text), rule) for rule in field_rules]
    matches = [(length, rule) for length, rule in matches if length > 0]
    if not matches:
        return []
    best_length = max(length for length, _rule in matches)
    return [rule for length, rule in matches if length == best_length]


def field_rule_label_match_length(rule: FieldRule, label_text: str) -> int:
    normalized = _normalize_label(label_text)
    if not normalized:
        return 0
    return max(
        (
            len(label)
            for label in (_normalize_label(label) for label in rule.labels)
            if _label_occurs_as_field_label(label, normalized)
        ),
        default=0,
    )


def _overlaps_existing(start: int, end: int, findings: list[Finding]) -> bool:
    return any(start < finding.end and end > finding.start for finding in findings)


def _looks_like_version_context(text: str, start: int) -> bool:
    before = text[max(0, start - 16) : start]
    return bool(VERSION_CONTEXT_PATTERN.search(before))


def _trim_address_intro(text: str, start: int, end: int) -> tuple[int, int, str]:
    value = text[start:end]
    marker = "位于"
    marker_index = value.rfind(marker)
    if marker_index >= 0:
        start += marker_index + len(marker)
        value = text[start:end]
    return start, end, value


def _as_string_tuple(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    values = value if isinstance(value, list) else [value]
    return tuple(str(item).strip() for item in values if str(item).strip())


def _load_field_components(raw_components: Any, rule_index: int) -> list[FieldComponent]:
    if not raw_components:
        return []
    if not isinstance(raw_components, list):
        raise ValueError(f"Field rule #{rule_index} components must be a list.")
    components: list[FieldComponent] = []
    for component_index, raw_component in enumerate(raw_components, 1):
        if not isinstance(raw_component, dict):
            raise ValueError(f"Field rule #{rule_index} component #{component_index} must be a mapping.")
        category = str(raw_component.get("category") or "custom").strip() or "custom"
        pattern = raw_component.get("pattern")
        if not pattern:
            raise ValueError(f"Field rule #{rule_index} component #{component_index} must define a pattern.")
        components.append(FieldComponent(category=category, pattern=str(pattern)))
    return components


def _find_value_findings(value_text: str, base_start: int, rule: FieldRule) -> list[Finding]:
    findings: list[Finding] = []
    start, end = _trim_span(value_text, 0, len(value_text))
    if start >= end:
        return findings
    value = value_text[start:end]
    absolute_start = base_start + start

    if rule.components:
        for component in rule.components:
            for match in re.finditer(component.pattern, value):
                finding_start = absolute_start + match.start()
                finding_end = absolute_start + match.end()
                if not _overlaps_existing(finding_start, finding_end, findings):
                    findings.append(
                        Finding(component.category, match.group(0), finding_start, finding_end, "field_rules")
                    )
        return findings

    if rule.pattern:
        for match in re.finditer(rule.pattern, value):
            finding_start = absolute_start + match.start()
            finding_end = absolute_start + match.end()
            if not _overlaps_existing(finding_start, finding_end, findings):
                findings.append(Finding(rule.category, match.group(0), finding_start, finding_end, "field_rules"))
        return findings

    return [Finding(rule.category, value, absolute_start, absolute_start + len(value), "field_rules")]


def _trim_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _looks_like_field_label(text: str, field_rules: list[FieldRule]) -> bool:
    return any(field_rule_matches_label(rule, text) for rule in field_rules)


def _looks_like_markdown_table_header_value(text: str) -> bool:
    return _normalize_label(text) in MARKDOWN_TABLE_HEADER_VALUES


def _label_occurs_as_field_label(label: str, normalized_text: str) -> bool:
    if not label:
        return False
    start = 0
    while True:
        index = normalized_text.find(label, start)
        if index < 0:
            return False
        end = index + len(label)
        if normalized_text == label or normalized_text.endswith(label):
            return True
        before = normalized_text[index - 1] if index > 0 else ""
        after = normalized_text[end] if end < len(normalized_text) else ""
        if (not before or not _is_label_word_char(before)) and (not after or not _is_label_word_char(after)):
            return True
        start = index + 1


def _is_label_word_char(char: str) -> bool:
    return bool(re.match(r"[\u4e00-\u9fffA-Za-z0-9]", char))


def _markdown_table_cells(line: str, line_start: int) -> list[tuple[str, int, int]]:
    pipe_indexes = [index for index, char in enumerate(line) if char == "|"]
    if len(pipe_indexes) < 2:
        return []

    if line[: pipe_indexes[0]].strip():
        pipe_indexes = [-1] + pipe_indexes
    if line[pipe_indexes[-1] + 1 :].strip():
        pipe_indexes = pipe_indexes + [len(line)]

    cells: list[tuple[str, int, int]] = []
    for left, right in zip(pipe_indexes, pipe_indexes[1:]):
        cell_start, cell_end = _trim_span(line, left + 1, right)
        cells.append((line[cell_start:cell_end], line_start + cell_start, line_start + cell_end))
    return cells


def _normalize_label(text: str) -> str:
    return re.sub(r"[\s:：；;，,。]", "", text or "")


def _followed_by_field_separator(text: str, end: int) -> bool:
    cursor = end
    while cursor < len(text) and text[cursor].isspace():
        cursor += 1
    return cursor < len(text) and text[cursor] in ":："
