from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from typing import Iterable
from itertools import chain, product


FAKE_VALUES = {
    "name": [
        "张三",
        "李四",
        "王五",
        "赵六",
        "孙七",
        "周八",
        "吴九",
        "郑十",
        "陈一",
        "刘二",
        "黄小明",
        "林小雨",
        "何佳",
        "郭晨",
        "唐宁",
        "宋雪",
    ],
    "phone": [
        "19999999999",
        "18888888888",
        "16666666666",
        "15555555555",
        "17777777777",
        "13333333333",
        "19900000001",
        "19900000002",
        "19900000003",
        "19900000004",
        "19900000005",
        "19900000006",
    ],
    "email": [
        "zhangsan@example.com",
        "lisi@example.com",
        "wangwu@example.com",
        "zhaoliu@example.com",
        "sunqi@example.com",
        "zhouba@example.com",
        "wujiu@example.com",
        "zhengshi@example.com",
        "chenyi@example.com",
        "liuer@example.com",
        "huangxm@example.com",
        "linxy@example.com",
    ],
    "id_card": [
        "110101199001010011",
        "310101198802020022",
        "440101199503030033",
        "110101199001010038",
        "310101198802020043",
        "440101199503030052",
        "320101199604040063",
        "510101198705050078",
    ],
    "passport": ["E00000001", "E00000002", "G00000001", "G00000002", "P00000001", "S00000001"],
    "bank_card": [
        "6222020000000000000",
        "4111111111111111",
        "5555555555554444",
        "4000000000000002",
        "5200828282828210",
        "6200000000000005",
    ],
    "bank_routing_code": [
        "990000000001",
        "990000000002",
        "990000000003",
        "990000000004",
        "990000000005",
        "990000000006",
    ],
    "social_credit_code": [
        "91110000000000000X",
        "913100000000000001",
        "914401000000000002",
        "915101000000000003",
        "913201000000000004",
        "914403000000000005",
    ],
    "address": [
        "北京市朝阳区示例路88号",
        "上海市浦东新区样例街66号",
        "广州市天河区测试大道100号",
        "深圳市南山区演示路18号",
        "杭州市西湖区文档街9号",
        "成都市高新区数据路28号",
        "南京市鼓楼区样本巷6号",
        "武汉市武昌区示范路16号",
        "西安市雁塔区星光路33号",
        "苏州市工业园区云杉街12号",
        "青岛市市南区海风路5号",
        "厦门市思明区观海路19号",
    ],
    "org": [
        "北京星河科技有限公司",
        "上海云启信息技术有限公司",
        "深圳远山数据有限公司",
        "广州明澈网络有限公司",
        "杭州青石软件有限公司",
        "成都启明数字科技有限公司",
        "南京松柏咨询有限公司",
        "武汉蓝湖系统有限公司",
        "西安辰光智能有限公司",
        "苏州云杉科技有限公司",
        "青岛海岳信息有限公司",
        "厦门白鹭数据有限公司",
    ],
    "customer": [
        "华东客户A",
        "北方客户B",
        "南方客户C",
        "西部客户D",
        "重点客户E",
        "渠道客户F",
        "集团客户G",
        "区域客户H",
        "试点客户I",
        "长期客户J",
        "战略客户K",
        "样例客户L",
    ],
    "project": [
        "星云迁移项目",
        "北辰数据平台",
        "清源风控系统",
        "云帆门户改造",
        "青岚报表中心",
        "明台合同系统",
        "澄海客户画像",
        "松月归档平台",
        "晨星支付联调",
        "远桥运维平台",
        "白石审计项目",
        "紫竹知识库",
    ],
    "contract": [
        "HT-2026-000001",
        "HT-2026-000002",
        "HT-2026-000003",
        "HT-2026-000004",
        "HT-2026-000005",
        "HT-2026-000006",
        "HT-2026-000007",
        "HT-2026-000008",
        "HT-2026-000009",
        "HT-2026-000010",
        "HT-2026-000011",
        "HT-2026-000012",
    ],
    "ip": ["10.0.0.1", "192.168.1.100", "172.16.0.10", "10.1.2.3", "192.168.10.20", "172.20.30.40"],
    "url": [
        "https://example.com",
        "https://internal.example.test",
        "https://portal.example.test",
        "https://api.example.test",
        "https://docs.example.test",
        "https://files.example.test",
    ],
    "domain": [
        "example.com",
        "internal.example.test",
        "portal.example.test",
        "api.example.test",
        "docs.example.test",
        "files.example.test",
    ],
    "secret": [
        "fake_00000000000000000000000000000000",
        "fake_11111111111111111111111111111111",
        "fake_22222222222222222222222222222222",
        "fake_33333333333333333333333333333333",
        "fake_44444444444444444444444444444444",
        "fake_55555555555555555555555555555555",
    ],
    "custom": [
        "示例敏感词A",
        "示例敏感词B",
        "示例敏感词C",
        "示例敏感词D",
        "示例敏感词E",
        "示例敏感词F",
        "示例敏感词G",
        "示例敏感词H",
        "示例敏感词I",
        "示例敏感词J",
        "示例敏感词K",
        "示例敏感词L",
    ],
    "case_number": [
        "（2026）示例0100民初00001号",
        "（2026）示例0100民初00002号",
        "（2026）示例0100民终00003号",
        "（2025）示例0200民初00004号",
        "（2025）示例0200刑初00005号",
        "（2025）示例0300民终00006号",
        "（2024）示例0400民初00007号",
        "（2024）示例0500行初00008号",
        "（2024）示例0600执00009号",
        "（2023）示例0700民初00010号",
        "（2023）示例0800民辖终00011号",
        "（2023）示例0900民初00012号",
    ],
    "doc_number": [
        "示例监罚字〔2026〕001号",
        "示例监罚字〔2026〕002号",
        "示例监罚字〔2026〕003号",
        "示例监罚字〔2025〕004号",
        "示例监罚字〔2025〕005号",
        "示例监罚字〔2025〕006号",
        "示例监决字〔2024〕007号",
        "示例监决字〔2024〕008号",
        "示例监决字〔2024〕009号",
        "示例监决字〔2023〕010号",
        "示例监决字〔2023〕011号",
        "示例监决字〔2023〕012号",
    ],
}

_NAME_SURNAMES = [
    "张", "王", "李", "赵", "刘", "陈", "杨", "黄", "周", "吴",
    "徐", "孙", "马", "朱", "胡", "郭", "何", "林", "罗", "郑",
]
_NAME_GIVENS = [
    "伟", "敏", "静", "磊", "洋", "芳", "娜", "强", "军", "杰",
    "涛", "明", "超", "霞", "平", "刚", "桂英", "晓东", "雅琴", "志强",
]
_ORG_CITIES = [
    "北京", "上海", "深圳", "广州", "杭州", "成都", "南京", "武汉",
    "西安", "苏州", "青岛", "厦门", "天津", "重庆", "合肥", "长沙",
]
_ORG_MARKS = [
    "星河", "云启", "远山", "晨光", "博雅", "恒信", "泰合", "海纳",
    "沃德", "锐进", "锦程", "天成", "海川", "晟世", "嘉禾", "望舒",
    "青梧", "长风", "北辰", "金台",
]
_ORG_TRADES = [
    "科技有限公司", "信息技术有限公司", "数据有限公司", "智能装备有限公司",
    "建设有限公司", "地产咨询有限公司", "商贸有限公司", "实业有限公司",
    "股权投资基金有限公司", "物业管理有限公司",
]
_CUSTOMER_REGIONS = [
    "华东", "华北", "华南", "西南", "西北", "东北", "华中", "港澳台",
]
_CUSTOMER_CODES = [
    "A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M",
]
_PROJECT_MARKS = [
    "星云", "北辰", "朝阳", "长风", "望海", "天枢", "锦云", "沧澜",
    "赤霄", "白鹭", "青岚", "紫宸", "金乌", "灵犀", "承影", "曳光",
]
_PROJECT_PHASES = [
    "迁移项目", "数据平台", "整合项目", "扩建项目", "合规整改项目",
    "重组项目", "系统升级项目", "尽调项目", "试点项目", "交付项目",
]
_ADDRESS_DISTRICTS = [
    "北京市朝阳区", "北京市海淀区", "上海市浦东新区", "上海市静安区",
    "深圳市南山区", "深圳市福田区", "广州市天河区", "杭州市西湖区",
    "成都市武侯区", "南京市鼓楼区", "武汉市武昌区", "西安市雁塔区",
    "苏州市工业园区", "青岛市市南区", "天津市和平区", "长沙市岳麓区",
]
_ADDRESS_STREETS = [
    "示例路", "星光路", "云杉街", "观海路", "长风街", "清河路",
    "丹桂路", "白露街", "太行路", "瀛洲街", "锦华路", "望京街",
    "源深路", "梧桐街", "龙泉路", "含光街",
]
_ADDRESS_NUMBERS = [
    "1号", "9号", "18号", "33号", "56号", "66号", "79号", "88号",
    "101号", "128号", "166号", "200号",
]
_CONTRACT_SERIES = [f"HT-2026-{index:06d}" for index in range(13, 61)]
_MOBILE_SERIES = [f"199{index:08d}" for index in range(13, 61)]


def _expand(category: str, *parts: list[str], limit: int) -> None:
    values = FAKE_VALUES[category]
    existing = set(values)
    target = len(values) + limit
    for combination in product(*parts):
        if len(values) >= target:
            return
        candidate = "".join(combination)
        if candidate not in existing:
            existing.add(candidate)
            values.append(candidate)


_expand("name", _NAME_SURNAMES, _NAME_GIVENS, limit=60)
_expand("org", _ORG_CITIES, _ORG_MARKS, _ORG_TRADES, limit=72)
_expand("customer", _CUSTOMER_REGIONS, ["客户"] + _CUSTOMER_CODES, limit=48)
_expand("project", _PROJECT_MARKS, _PROJECT_PHASES, limit=48)
_expand("address", _ADDRESS_DISTRICTS, _ADDRESS_STREETS, _ADDRESS_NUMBERS, limit=72)
values = FAKE_VALUES["contract"]
values.extend([value for value in _CONTRACT_SERIES if value not in set(values)])
values = FAKE_VALUES["phone"]
values.extend([value for value in _MOBILE_SERIES if value not in set(values)])


CATEGORY_ALIASES = {
    "person": "name",
    "姓名": "name",
    "name": "name",
    "mobile": "phone",
    "phone": "phone",
    "手机号": "phone",
    "邮箱": "email",
    "mail": "email",
    "email": "email",
    "id": "id_card",
    "id_card": "id_card",
    "身份证": "id_card",
    "company": "org",
    "organization": "org",
    "org": "org",
    "公司": "org",
    "固定电话": "phone",
    "传真": "phone",
    "案号": "case_number",
    "文号": "doc_number",
    "决定书文号": "doc_number",
    "bank_routing_code": "bank_routing_code",
    "routing": "bank_routing_code",
    "联行号": "bank_routing_code",
    "客户": "customer",
    "customer": "customer",
    "项目": "project",
    "project": "project",
    "secret": "secret",
    "token": "secret",
    "api_key": "secret",
    "key": "secret",
}


KNOWN_FAKE_VALUES = frozenset(chain.from_iterable(FAKE_VALUES.values()))


def normalize_category(category: str) -> str:
    normalized = category.strip().lower().replace("-", "_")
    return CATEGORY_ALIASES.get(normalized, normalized if normalized in FAKE_VALUES else "custom")


@dataclass
class FakeDataFactory:
    seed: str | None = None
    mappings: dict[tuple[str, str], str] = field(default_factory=dict)
    counters: dict[str, int] = field(default_factory=dict)
    mapping_salt: str = field(default_factory=lambda: secrets.token_hex(16))
    reserved: set[str] = field(default_factory=set)

    def reserve(self, values: Iterable[str]) -> None:
        self.reserved.update(value for value in values if value)

    def replacement_for(self, category: str, original: str) -> str:
        category = normalize_category(category)
        key = (category, original)
        if key in self.mappings:
            return self.mappings[key]

        values = FAKE_VALUES.get(category, FAKE_VALUES["custom"])
        index = self.counters.get(category, 0)
        replacement = first_distinct_value(values, original, index, self.reserved)
        self.counters[category] = index + 1

        self.mappings[key] = replacement
        self.reserve([original])
        return replacement

    def safe_mapping(self) -> dict[str, dict[str, str]]:
        output: dict[str, dict[str, str]] = {}
        seed = self.seed if self.seed is not None else self.mapping_salt
        for (category, original), replacement in self.mappings.items():
            digest = hashlib.sha256(f"{seed}:{original}".encode("utf-8")).hexdigest()
            output.setdefault(category, {})[digest] = replacement
        return output

    def sensitive_mapping(self) -> dict[str, dict[str, str]]:
        output: dict[str, dict[str, str]] = {}
        for (category, original), replacement in self.mappings.items():
            output.setdefault(category, {})[original] = replacement
        return output


def first_distinct_value(
    values: list[str],
    original: str,
    start_index: int,
    reserved: set[str] | None = None,
) -> str:
    blocked = set(reserved or set()) | {original}
    for offset in range(len(values)):
        candidate = values[(start_index + offset) % len(values)]
        if candidate == original or _embeds_sensitive(candidate, blocked):
            continue
        return candidate
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:8]
    return f"示例值-{digest}"


def _embeds_sensitive(candidate: str, blocked: set[str]) -> bool:
    return any(term and term in candidate for term in blocked)
