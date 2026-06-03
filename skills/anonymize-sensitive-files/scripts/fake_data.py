from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from itertools import chain


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
}


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

    def replacement_for(self, category: str, original: str) -> str:
        category = normalize_category(category)
        key = (category, original)
        if key in self.mappings:
            return self.mappings[key]

        values = FAKE_VALUES.get(category, FAKE_VALUES["custom"])
        index = self.counters.get(category, 0)
        replacement = first_distinct_value(values, original, index)
        self.counters[category] = index + 1

        self.mappings[key] = replacement
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


def first_distinct_value(values: list[str], original: str, start_index: int) -> str:
    for offset in range(len(values)):
        candidate = values[(start_index + offset) % len(values)]
        if candidate != original:
            return candidate
    digest = hashlib.sha256(original.encode("utf-8")).hexdigest()[:8]
    return f"示例值-{digest}"
