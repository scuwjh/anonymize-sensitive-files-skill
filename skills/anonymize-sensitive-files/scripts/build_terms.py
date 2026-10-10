#!/usr/bin/env python3
"""实体词表生成器（纯代码版，不调用任何大模型 API）。

实现阶段：
  0 文件分级：可解析(有文本层) / 扫描件(无文本层) / 不可解析(xls/doc/jpg)
  1 候选发现：多通道正则，每文件独立产出「候选 + 证据」（宁多勿漏）
  2 词干聚合：去公司/机构/项目后缀后按词干聚类，同簇搜集语料内全部变体
  3 类别判定：规则投票 org / project / name（附置信度）
  4 规则审核：停用词/行政区划/假值池 veto；分 HIGH/MEDIUM/LOW 三桶；
     语料外变体建议单独列出（供人工确认，不自动入表）
  5 覆盖校验：文件级「词表命中/候选」覆盖率 + 疑似漏检清单

输出到 out-dir/：
  terms-draft.txt   可直接使用的词表（HIGH+MEDIUM 桶）
  terms-audit.json  全部实体簇 + 证据 + 桶 + 建议（机器可读）
  terms-audit.md    同上（人读版）
  coverage.md       文件级覆盖报告
  regression.md     正/负样本回归结果

用法（skill venv）： .venv/bin/python scripts/build_terms.py \
      <input_files_dir> --out-dir <terms-build> [--existing <terms-ok.txt>]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# 停用与过滤表
# ---------------------------------------------------------------------------
# 作为候选「开头」时直接丢弃（我公司/该公司…）
PREFIX_STOP = set("我该本两各此一多其你他她上以这那任")
# 机构名主体前面的可剥离虚词（该公司【有】哈尔滨市国资部门 -> 剥「有」）
INST_LEAD_STOP = set("有该本此其之的与及或因由从对把被将已未不就再又可会能没还均更越很最并连到完"
                     "全各每只仅却便则即且皆都首其现曾原应该当须需为之于则而或报提请系兹等若另如"
                     "此次同时今明昨今各再每每某单仅仅")
# company/xcompany 的 X 不允许以这些虚词开头（下称世纪文创公司 / 与美加公司 / 为金辉集团…）
STEM_PREFIX_BAD = ("下称", "以下简称", "简称", "与", "及", "或", "在", "对", "把", "被", "将", "已", "未",
                   "不", "为", "向", "由", "作", "若", "如", "因", "据", "按", "经", "通过", "根据",
                   "按照", "不能", "无法", "应", "須", "需", "请", "之", "的", "和", "该", "本", "此",
                   "其", "上", "下", "后", "前", "中", "内", "外", "左", "右", "有", "无", "再", "又",
                   "须", "将", "至", "以", "于", "则", "即", "且", "而", "或", "报", "提", "请", "系",
                   "兹", "則", "來自", "我們", "附屬", "於", "股份", "本", "例", "如", "的", "等", "予",
                   "另", "嗣", "後", "再", "尚", "未", "并", "並", "及", "其", "有", "關", "相", "若", "該")
# 公司/机构名主体内不应出现的句法词（出现在其中 = 跨实体/句子碎片）
BAD_SUBSTRINGS = re.compile(
    "部门|委派|情况|约定|日期|竣工|延期|相关|政府|甲方|乙方|根据|按照|请示|截至|报告期|期间|"
    "本合同|本协议|我们|我们|鉴于|导致|有关|问题|证明|材料|清单|汇总|台账|报表|定稿|初稿|模板|"
    "提交|签署|出具|履行|要求|提供|报送|谈判|协商|讨论|审议|批准|同意|安排|处理|发生|存在|涉及|"
    "位于|适用于|分为|合计|共计|目前|已经|尚未|正在|需要|将于|约|部|"
    "原告|被告|判决|裁定|诉讼|起诉|受理|开庭|一审|二审|执行|上诉|处罚|罚款|责令|整改|立案|"
    "调查|检查|通知|书面|不能|无法|下称|简称|截至|依据|依照|根据|按照|认为|主张|请求|"
    "例如|万元|人民币|元以|增至|减少|增加|組合|業績|集团整體|集團整")
# 候选完全等于这些词 → veto
WHOLE_STOP = set("""
公司 集团 项目 中国 备案 节选 后时间表 收并购事宜 环渤海 草案 初稿 定稿 终稿 清洁版 模板
说明 答复 回复 意见 函 证明 台账 汇总 一览表 统计表 报表 清单 报告 通知 批复 申请 承诺
备忘录 补充 修订 版本 公告 公示 上市 发行 重组 股权 转让 增资 委托 协议 合同 纠纷 诉讼
判决 裁定 立案 调查 检查 处罚 罚款 滞纳金 保证金 社保 公积金 税务 发票 审计 评估 法律
合规 监管 核查 问询 投诉 联交所 香港联合交易所 上市规则 主板 港交所 简介 目录 封面
开发 置业 投资 房地产 房地产开发 物业 建设 工程 管理 咨询 科技 实业 房产 金融 贸易 物流 材料
机械 建材 园林 市政 装修 设计 规划 经纪 代理 顾问 服务 有限 责任 股份 控股 集团有限 部分
住宅 业态 交付 预售 物业公司 标的 地块
""".split())
# 候选以这些结尾且总长 <=7 → veto（行政区划单独成条：佛山市/哈尔滨市…）
SUFFIX_STOP = ("市", "省", "区", "县", "镇", "乡", "村", "街道", "自治区", "特别行政区")
SUFFIX_STOP_LEN = 7
# 行政区划整词（单独出现不敏感）
REGION_STOP = set("""
北京 上海 天津 重庆 广东 江苏 浙江 福建 四川 陕西 山东 湖北 湖南 河南 河北 辽宁 吉林
黑龙江 安徽 江西 广西 云南 贵州 山西 甘肃 青海 宁夏 新疆 西藏 内蒙古 海南 哈尔滨 佛山
廊坊 扬州 苏州 西安 成都 武汉 郑州 长沙 无锡 太仓 淮安 沈阳 荆州 仁寿 徐州 连云港 盐城
福清 石家庄 南京 杭州 宁波 青岛 唐山 沧州 保定 合肥 平潭 珠海 惠州 滁州 张家港 扬州
""".split())
# 文件名片段里常见的非实体词
FILENAME_STOP = set("""
HK AG CP FS LO ME PR RI RD TD PE LI AG- 香港 联交所 问题回复 说明 模板 底稿 汇总 台账 报表 统计
清单 证明 函 初稿 定稿 草案 终稿 意见 核查 结论 回复 合规证明 开具 标准 控制表 列表 表 附件
""".split())

# ---------------------------------------------------------------------------
# 通道正则
# ---------------------------------------------------------------------------
# 公司/机构 X 部分的「内容字符」：排除连接词、虚词、常见标点与空白，
# 防止把「A和B有限公司」「根据公司」「确认立即通知公司」这类拼接误判为实体名。
_NOSEP = """，。；:：、的向系确该此其等由从对据经按因将把被给当个如若虽但倘须應將給當進係某各種若于之者亦既且而或以是為為乃諸总之为已未不就再又可会能没还其均更越很最并连由到完全各每只仅却便则即且皆都首先现曾原应该将需须 \t\u3000\xa0\n\r.。．（）()%#&*《》「」『』【】〔〕<>{} \'"\u2018\u2019\u201c\u201d·"""
_COMP_SUF = ("股份有限公司|集團股份有限公司|集團有限公司|發展有限公司|開發有限公司|置業有限公司|"
             "房地產開發有限公司|地產開發有限公司|建設集團有限公司|有限责任公司|有限公司")

CH_COMPANY = re.compile(r"([^%sA-Za-z0-9·（）()]{3,28}?(?:%s))" % (_NOSEP, _COMP_SUF))
CH_XCOMPANY = re.compile(r"([^%s]{2,14}公司)" % (_NOSEP + "()（）"))  # 哈尔滨综合开发公司 / 融侨公司…
CH_DEFINE = re.compile(r"(?:下称|以下简称|简称|原名称为|公司原名称为|原为|后更名为|随后更名为|后又更名为|现更名为|现已更名为|已更名为|曾用名|更名为|变更名称为|变更后名称为|改名为)(?:为|作)?[“\"「『]?([\u4e00-\u9fffA-Za-z0-9·]{1,20})[”\"」』]?")
CH_INST = re.compile(r"([\u4e00-\u9fffA-Za-z0-9·（）()]{2,16}(?:市场监督管理局|住房和城乡建设委员会|人民法院|人民检察院|人民政府|监督管理委员会|自然资源和规划局|税务局|公安局|委员会|事务所|律師事務所|會計師事務所|支行|分行|銀行|银行|管理局|办公室|办公室|部门|部門|中心))")
CH_PROJECT = re.compile(r"([^%s]{2,12}(?:項目|项目|地块|花园|家园|湖畔|学府|翡翠湾|风雅轩|院子|山庄|新城|小区|壹号))" % _NOSEP)
CH_PROJECT_WIDE = re.compile(r"([^%s市区省县乡镇政府机关]{2,10}(?:城|期|苑|樓|楼|广场))" % _NOSEP)  # 低置信
CH_NAME = re.compile(r"(?:法定代表人|委托代理人|董事长|总经理|常务副总|执行董事|负责人|联系人|经办人|签字人|项目负责人|主办律师|召集人|财务负责人|实际控制人|监事|代理律师)(?:[:：为是\s])?([\u4e00-\u9fff·]{2,4})")
# 中介/机构简称列表：保荐人、德恒、安永 -> 德恒/安永（LOW 桶，人工确认）
CH_LIST = re.compile(r"(?:保荐人|联席保荐人|法律顾问|中國法律顧問|中国法律顾问|核数师|独立核数师|申报会计师|印刷商|收款银行|承销商|联席全球协调人|律师|法律顧問|公司中国法律顾问)[:：、\s]*((?:[\u4e00-\u9fff·]{2,4}[、，,])+[\u4e00-\u9fff·]{2,4})")

# XCOMPANY 的 X 末尾字符黑名单：介词/通用词/行政区划尾字，防「根据公司」「城市公司」「山市…」
XCOMPANY_TAIL_WORDS = ("据", "照", "括", "至", "依", "述", "下", "于", "过", "中", "及", "或", "与", "对", "关", "通",
                 "等", "各", "该", "我", "本", "两", "数", "多", "上", "前", "后", "同", "期", "次", "项",
                 "市", "省", "区", "县", "镇", "乡", "街道", "有限", "责任", "和", "与", "及", "或")
XCOMPANY_TAIL_STOP = set(XCOMPANY_TAIL_WORDS)  # 兼容旧引用（仅用于单字检查）

PROJECT_BAD = re.compile(
    r"[\d]+年|[\d]+月|[个個]|我们|我們|请提供|截至|相关|相關|有關|该|該|这|這|其中|涉及|关于|對於|上述|以下|包括|以及|位于|位於|"
    "建设|单位|备案|报批|依法|抽查|才进行|即|合同|均|包含|取得|处建|暂停|约定|完成|竣工|延期|之日起|根据|按照|通过|"
    "由|于|在|被|将|已|未|不|及|或|与|和|的|之|者|以|所|其|这|那|今|当|于|对|从|把|向|让|"
    "房地产开发|部分|其它|其他|该等|已在|下列|如下|所述|于上述|该等|本等|"
    "倉儲|高级|高級|业態|业态|項目|本公司|本集团|本集團")
# CH_COMPANY 中 X 首字符不可为行政区划尾字（防「山市高明区…」错位变体）
COMPANY_HEAD_STOP = set("市省区县镇乡")

CATEGORY = {"company": "org", "company_join": "org", "xcompany": "org", "define": "org", "inst": "org",
            "project": "project", "project_wide": "project", "name": "name", "list": "org"}

# 词干提取用的尾部后缀（最长优先）
STEM_SUFFIXES = ["股份有限公司", "集团股份有限公司", "集團股份有限公司", "集團有限公司",
                 "控股（集团）有限公司", "控股(集团)有限公司", "集团有限公司", "集团控股有限公司",
                 "项目管理有限公司", "發展有限公司", "開發有限公司", "置業有限公司",
                 "房地產開發有限公司", "地產開發有限公司", "建設集團有限公司", "有限责任公司",
                 "有限公司", "公司", "控股集團", "控股集团", "集團", "控股",
                 "市场监督管理局", "住房和城乡建设委员会", "自然资源和规划局", "监督管理委员会",
                 "人民法院", "人民检察院", "人民政府", "律师事务所", "律師事務所",
                 "會計師事務所", "事务所", "委員會", "委员会", "管理局", "税务局", "财政厅",
                 "支行", "分行", "銀行", "银行", "办公室", "辦公", "部门", "部門", "中心",
                 "項目", "项目", "地块", "花园", "家园", "湖畔", "学府", "翡翠湾", "风雅轩",
                 "院子", "山庄", "新城", "小区", "壹号", "壹期", "二期", "三期", "城", "期", "苑", "樓", "楼", "广场"]

PROJECT_HINT = ("项目", "地块", "花园", "家园", "湖畔", "学府", "翡翠湾", "风雅轩", "院子", "山庄", "新城", "小区", "壹号", "中心", "城", "期")
NAME_CHANNEL = "name"
WIDE_CHANNELS = {"project_wide", "name", "xcompany", "filename"}


# ---------------------------------------------------------------------------
@dataclass
class Candidate:
    term: str
    channel: str
    file: str
    context: str
    source: str = "text"  # text | filename


@dataclass
class Cluster:
    stem: str
    variants: set = field(default_factory=set)
    files: set = field(default_factory=set)
    channels: set = field(default_factory=set)
    category_votes: dict = field(default_factory=lambda: defaultdict(int))
    evidence: list = field(default_factory=list)
    bucket: str = "HIGH"

    @property
    def vote(self) -> str:
        return max(self.category_votes, key=lambda k: self.category_votes[k])


# ---------------------------------------------------------------------------
# 阶段 0：文本提取与分级
# ---------------------------------------------------------------------------
def extract_text(path: Path) -> tuple[str, str]:
    """返回 (文本, 分级)。分级: ok / scanned / unsupported。"""
    s = path.suffix.lower()
    try:
        if s == ".pdf":
            import fitz
            doc = fitz.open(path)
            t = "\n".join(pg.get_text("text") for pg in doc)
            doc.close()
            if len(t.strip()) < 50:
                return t, "scanned"
            return t, "ok"
        if s == ".docx":
            from docx import Document
            doc = Document(path)
            parts = [p.text for p in doc.paragraphs]
            for tb in doc.tables:
                for row in tb.rows:
                    for c in row.cells:
                        parts.append(c.text)
            return "\n".join(parts), "ok"
        if s in (".xlsx", ".xlsm"):
            from openpyxl import load_workbook
            wb = load_workbook(path, data_only=False, rich_text=True)
            parts = []
            for ws in wb.worksheets:
                for row in ws.iter_rows():
                    for c in row:
                        if isinstance(c.value, str):
                            parts.append(c.value)
            wb.close()
            return "\n".join(parts), "ok"
        if s in (".md", ".markdown", ".txt", ".text", ".csv", ".tsv", ".json", ".yaml", ".yml"):
            return path.read_text(encoding="utf-8", errors="ignore"), "ok"
    except Exception:
        return "", "error"
    return "", "unsupported"


def context_of(text: str, start: int, mlen: int, span: int = 40) -> str:
    lo = max(0, start - span)
    hi = min(len(text), start + mlen + span)
    return text[lo:hi].replace("\n", "⏎").replace("\t", " ")[:160]


# ---------------------------------------------------------------------------
# 阶段 1：候选发现（每文件独立）
# ---------------------------------------------------------------------------
def find_candidates(text: str, fname: str) -> list[Candidate]:
    out: list[Candidate] = []
    seen: set[tuple] = set()

    def add(term: str, channel: str, start: int, mlen: int, src="text"):
        term = term.strip(" 　，。；：、""''（）()《》「」『』【】.．·")
        if len(term) < 2 or len(term) > 30:
            return
        if term[0] in PREFIX_STOP:
            return
        if channel not in ("list", "name") and not re.match(r"[\u4e00-\u9fff·]", term):
            return  # 实体名须以中文字符开头（防数字/日期/符号开头的碎片）
        if channel in ("company", "xcompany") and re.search(BAD_SUBSTRINGS, term):
            return  # X 内出现句法词（部门/委派/情况…）说明是跨实体碎片
        key = (term, channel)
        if key in seen:
            return
        seen.add(key)
        out.append(Candidate(term, channel, fname, context_of(text, start, mlen), src))

    for m in CH_COMPANY.finditer(text):
        term = m.group(1)
        if term[0] in COMPANY_HEAD_STOP:
            continue
        # 拼接体判定：去掉结尾公司后缀后，若被连接词分出的每一侧都 >= 4 字
        # （如「石家庄金辉天宁房地产和兴业国际信托有限公司」），标为拼接体 -> LOW 人工裁决；
        # 商号内嵌连接词（福州世和投资咨询）两侧有 <4 字片段，保持正常 company 通道。
        inner = re.sub(r"(股份有限公司|有限责任公司|有限公司)$", "", term)
        if inner.startswith(STEM_PREFIX_BAD):
            continue
        parts = re.split(r"[和与及或與]", inner)
        if len(parts) >= 2 and (all(len(pp) >= 4 for pp in parts)
                                or any(re.search(r"(公司|有限|集团|集團)", pp) for pp in parts)):
            add(term, "company_join", m.start(), len(term))
        else:
            add(term, "company", m.start(), len(term))
    # 把「XX有限公司」区间挖掉，避免 XCOMPANY 在其内部做错位截断（山市…/有限…/根据…）
    masked = list(text)
    for m in CH_COMPANY.finditer(text):
        for i in range(m.start(), m.end()):
            masked[i] = " "
    masked_t = "".join(masked)
    for m in CH_XCOMPANY.finditer(masked_t):
        term = m.group(1)
        x = term[:-2]  # 去掉「公司」
        if not x or x.endswith(XCOMPANY_TAIL_WORDS):
            continue
        if "公司" in x:
            continue  # X 内嵌「公司」= 并列拼接误配（…公司和…公司）
        if x.startswith(STEM_PREFIX_BAD):
            continue
        if re.search(r"[和与及或與]", x):
            parts = re.split(r"[和与及或與]", x)
            if any(re.search(r"(公司|有限|集团|集團)", pp) for pp in parts) or any(len(pp) == 2 for pp in parts):
                add(term, "company_join", m.start(), len(term))
                continue
        add(term, "xcompany", m.start(), len(term))
    for m in CH_DEFINE.finditer(text):
        add(m.group(1), "define", m.start(), len(m.group(1)))
    INST_SUF = re.compile(r"(?:市场监督管理局|住房和城乡建设委员会|人民法院|人民检察院|人民政府|监督管理委员会|自然资源和规划局|税务局|公安局|委员会|事务所|律师事务所|律師事務所|會計師事務所|支行|分行|銀行|银行|管理局|办公室|办公室|部门|部門|中心)$")
    for m in CH_INST.finditer(text):
        term = m.group(1)
        inner = INST_SUF.sub("", term)
        suf = term[len(inner):]
        stripped = inner.lstrip("".join(INST_LEAD_STOP))
        if not stripped or len(stripped) < 2:
            continue
        if INST_BAD.search(stripped):
            continue
        new_term = stripped + suf
        if new_term != term:
            add(new_term, "inst", m.start() + inner.find(stripped), len(new_term))
        else:
            add(term, "inst", m.start(), len(term))
    for m in CH_PROJECT.finditer(text):
        term = m.group(1)
        if PROJECT_BAD.search(term):
            continue
        add(term, "project", m.start(), len(term))
    for m in CH_PROJECT_WIDE.finditer(text):
        term = m.group(1)
        if PROJECT_BAD.search(term):
            continue
        add(term, "project_wide", m.start(), len(term))
    for m in CH_NAME.finditer(text):
        add(m.group(1), "name", m.start(), len(m.group(1)))
    for m in CH_LIST.finditer(text):
        for item in re.split(r"[、，,]", m.group(1)):
            add(item, "list", m.start(), len(item))
    return out


def filename_candidates(stem: str) -> list[str]:
    """从文件名拆中文片段（哈综开这样的主体简称），并迭代去除说明性尾词。"""
    parts = re.split(r"[_\-（）()\s.]+", stem)
    cands = []
    for p in parts:
        chunks = re.findall(r"[\u4e00-\u9fff]{2,10}", p)
        for ch in chunks:
            # 迭代去掉尾部说明词：哈综开说明 -> 哈综开
            reduced = ch
            while True:
                hit = None
                for w in sorted(FILENAME_STOP, key=len, reverse=True):
                    if reduced.endswith(w) and len(reduced) > len(w):
                        hit = w
                        break
                if hit:
                    reduced = reduced[: -len(hit)]
                else:
                    break
            if len(reduced) < 2:
                continue
            if reduced in WHOLE_STOP or reduced in FILENAME_STOP or reduced in REGION_STOP:
                continue
            if reduced[0] in PREFIX_STOP:
                continue
            cands.append(reduced)
    return cands


# ---------------------------------------------------------------------------
# 阶段 2：词干与聚类
# ---------------------------------------------------------------------------
def stem_of(term: str) -> str:
    s = term
    changed = True
    while changed:
        changed = False
        for suf in STEM_SUFFIXES:
            if s.endswith(suf) and len(s) - len(suf) >= 1:
                s = s[: -len(suf)]
                changed = True
                break
    return s


# ---------------------------------------------------------------------------
# 阶段 4：规则审核（veto / 分桶 / 变体建议）
# ---------------------------------------------------------------------------
INST_BAD = re.compile(
    "委派|情况|约定|日期|竣工|延期|相关|政府|甲方|乙方|根据|按照|请示|截至|报告期|期间|"
    "本合同|本协议|我们|鉴于|导致|有关|问题|证明|材料|清单|汇总|台账|报表|定稿|初稿|模板|"
    "提交|签署|出具|履行|要求|提供|报送|谈判|协商|讨论|审议|批准|同意|安排|处理|发生|存在|涉及|"
    "位于|适用于|分为|合计|共计|目前|已经|尚未|正在|需要|将于|公司|集团|有限|至|下午|上午|"
    "與|與|期間|期間|之日起|于|在|及|或|和|与|为")

GENERIC_ORG_TWOCHAR = set("政府 主管 相关 有关 房屋 税务 银行 建筑 物业 管理 咨询 投资 开发 置业 建设 工程 科技 信息 文化 教育 食品 药品 医疗 体育 交通 公安 消防 民政 财政 人社 发改 规划 国土 证券 保险 国资 工商 农业 林业 水利 电力 铁路 民航 邮政 质检 药监 环保 劳动 人事 宣传 组织 纪检 应急 城管 房管 高法 高检 中级 基层".split())


def veto(cl: Cluster) -> str | None:
    """返回 veto 原因；None 表示通过。"""
    if cl.stem in WHOLE_STOP or cl.stem in REGION_STOP:
        return "通用词/行政区划"
    if cl.vote == "org" and len(cl.stem) == 2 and cl.stem in GENERIC_ORG_TWOCHAR:
        return "通用机构泛称"
    if len(cl.stem) < 2:
        return "词干过短"
    # 单独行政区划：候选本身就是 'XX市' 形态且后缀为市/省等且长度 <= 阈值
    for suf in SUFFIX_STOP:
        if cl.stem.endswith(suf) and len(cl.stem) <= SUFFIX_STOP_LEN:
            return f"行政区划后缀 {suf}"
    # 全是数字/字母
    if re.fullmatch(r"[0-9A-Za-z]+", cl.stem):
        return "纯数字字母"
    # 动词/形容词形态（以已知通用动词结尾）——轻量
    return None


def assign_bucket(cl: Cluster) -> str:
    if "name" in cl.channels or "project_wide" in cl.channels or "list" in cl.channels or "company_join" in cl.channels:
        return "LOW"
    # 来源含 filename 的片段 → MEDIUM（进 draft，但需人留意）
    if "filename" in cl.channels:
        return "MEDIUM"
    if cl.bucket == "LOW":
        return "LOW"
    # 公司/机构/定义点 → HIGH
    return "HIGH"


# ---------------------------------------------------------------------------
def build_channel_overrides(cl: Cluster) -> list[str]:
    """语料外变体『建议』（不自动入表，供人工确认）。"""
    sugg: list[str] = []
    if len(cl.variants) < 2 and len(cl.files) < 3:
        return sugg
    has_company = any("公司" in v for v in cl.variants) or "公司" in cl.stem
    if has_company and cl.stem and len(cl.stem) >= 3:
        for form in (f"{cl.stem}有限公司", f"{cl.stem}集团", f"{cl.stem}股份有限公司"):
            if not any(form == v for v in cl.variants) and len(form) <= 30:
                sugg.append(form)
    return sugg


# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input_dir", type=Path)
    ap.add_argument("--out-dir", type=Path, required=True)
    ap.add_argument("--existing", type=Path, help="现有词表（对比用）")
    ap.add_argument("--min-context-files", type=int, default=1,
                    help="候选至少出现在 N 个文件才入 draft（默认 1=全收）")
    args = ap.parse_args()

    OUT: Path = args.out_dir
    OUT.mkdir(parents=True, exist_ok=True)
    files = sorted(p for p in args.input_dir.iterdir() if p.is_file())

    # ---- 阶段 0：分级 + 提取 ----
    grades: dict[str, list[str]] = defaultdict(list)
    texts: dict[str, str] = {}
    for p in files:
        t, g = extract_text(p)
        texts[p.name] = t
        grades[g].append(p.name)

    # ---- 阶段 1：候选（文本通道）----
    cand_by_file: dict[str, list[Candidate]] = {}
    all_cands: list[Candidate] = []
    for name, t in texts.items():
        if not t.strip():
            continue
        cands = find_candidates(t, name)
        cand_by_file[name] = cands
        all_cands.extend(cands)

    # ---- 阶段 1b：文件名通道 ----
    for p in files:
        stem = p.stem
        for ch in filename_candidates(stem):
            all_cands.append(Candidate(ch, "filename", p.name, "", source="filename"))

    # ---- 阶段 2：词干聚类 ----
    clusters: dict[str, Cluster] = {}
    for c in all_cands:
        st = stem_of(c.term)
        key = f"p:{st}" if CATEGORY.get(c.channel) == "project" else f"o:{st}"
        cl = clusters.setdefault(key, Cluster(stem=st))
        cl.variants.add(c.term)
        cl.files.add(c.file)
        cl.channels.add(c.channel)
        cl.category_votes[CATEGORY.get(c.channel, "org")] += 1
        if len(cl.evidence) < 3 and c.context:
            cl.evidence.append({"file": c.file, "channel": c.channel, "context": c.context})
        if c.source == "filename":
            cl.bucket = "LOW"

    # ---- 阶段 3：类别判定（规则投票）----
    for cl in clusters.values():
        if any(h in cl.stem for h in PROJECT_HINT):
            if "project" not in cl.category_votes:
                cl.category_votes["project"] += 1
        if "name" in cl.channels and "org" not in cl.channels:
            cl.category_votes["name"] += 1
        if "company" in cl.channels or "inst" in cl.channels or "define" in cl.channels:
            cl.category_votes["org"] += 1

    # ---- 阶段 4：veto + 分桶 ----
    kept: list[Cluster] = []
    vetoed: list[tuple[str, str, str]] = []  # (stem, reason, variants)
    fake_pool = None
    try:
        sys.path.insert(0, str(Path(__file__).parent))
        from fake_data import KNOWN_FAKE_VALUES  # type: ignore
        fake_pool = KNOWN_FAKE_VALUES
    except Exception:
        fake_pool = None

    for st, cl in clusters.items():
        if veto(cl):
            vetoed.append((st, veto(cl), ",".join(sorted(cl.variants))))
            continue
        if fake_pool and cl.stem in fake_pool:
            vetoed.append((st, f"假值池冲突({cl.stem})", ",".join(sorted(cl.variants))))
            continue
        cl.bucket = assign_bucket(cl)
        kept.append(cl)
    kept.sort(key=lambda c: (-len(c.files), c.stem))

    # ---- 输出 draft：HIGH + MEDIUM ----
    draft_lines: list[str] = []
    suggestions: list[tuple[str, list[str]]] = []
    for cl in kept:
        if cl.bucket == "LOW":
            continue
        for v in sorted(cl.variants):
            draft_lines.append(f"{cl.vote}:{v}")
        sg = build_channel_overrides(cl)
        if sg:
            suggestions.append((cl.stem, sg))

    # ---- 阶段 5：覆盖校验 ----
    draft_terms = [l.split(":", 1)[1] for l in draft_lines]
    coverage_rows = []
    for name, cands in cand_by_file.items():
        stems = {stem_of(c.term) for c in cands}
        if not stems:
            continue
        hit = 0
        for st in stems:
            if any(st in dt or dt in st for dt in draft_terms):
                hit += 1
        cov = hit / len(stems)
        coverage_rows.append((name, len(stems), hit, cov))
    coverage_rows.sort(key=lambda r: r[3])

    low_files = [r for r in coverage_rows if r[1] >= 3 and r[3] < 0.3]

    # ---- 回归：正负样本 ----
    positive = [
        "哈尔滨综合开发公司", "哈尔滨市国资部门", "福州世和投资咨询有限公司",
        "融侨集团有限公司", "融侨集团股份有限公司", "北京融侨置业有限公司", "融侨公司",
        "金辉集团有限公司", "金辉集团股份有限公司", "金辉控股（集团）有限公司",
        "竞天公诚", "国浩", "德恒", "哈综开", "融侨城", "启阳项目", "世界城",
        "北京美加投资有限公司", "国浩律师(北京)事务所", "于学文",
    ]
    negative = ["中国", "备案", "节选", "后时间表", "收并购事宜", "置业有限公司", "公司",
                "集团", "项目", "开发", "佛山", "廊坊", "环渤海", "投资", "说明", "回复",
                "联交所", "哈尔滨市", "北京市朝阳区", "有限公司"]
    all_terms = set(draft_lines) | {f"{cl.vote}:{v}"
                                    for cl in kept if cl.bucket == "LOW"
                                    for v in cl.variants}
    all_values = {l.split(":", 1)[1] for l in all_terms}

    def hit_by(value: str):
        for v in all_values:
            if v == value or v in value or value in v:
                return True
        return False

    def neg_hit_by(value: str):
        """负样本命中 = 该通用词被『独立收录』成词条（整词或词干相等），
        而不是被哪个长词条『包含』。"""
        for v in all_values:
            if v == value:
                return True
            if stem_of(v) == value:
                return True
        return False

    pos_hit = [(w, hit_by(w)) for w in positive]
    neg_hit = [(w, neg_hit_by(w)) for w in negative]

    # ---- 写文件 ----
    (OUT / "terms-draft.txt").write_text(
        "\n".join(f"{cl.vote}:{v}"
                  for cl in kept if cl.bucket != "LOW"
                  for v in sorted(cl.variants)) + "\n",
        encoding="utf-8")

    audit = {
        "input_files": len(files),
        "grades": {k: len(v) for k, v in grades.items()},
        "candidates": len(all_cands),
        "clusters": len(clusters),
        "kept": len(kept),
        "vetoed": len(vetoed),
        "draft_terms": len(draft_lines),
        "filename_examples": [c.term for c in all_cands if c.source == "filename"][:20],
        "clusters": [
            {
                "stem": c.stem, "votes": dict(c.category_votes), "category": c.vote,
                "bucket": c.bucket, "files": len(c.files),
                "variants": sorted(c.variants),
                "evidence": c.evidence,
            }
            for c in kept
        ],
        "vetoed": [{"term": a, "reason": b, "variants": d} for a, b, d in vetoed[:200]],
        "suggestions": [{"stem": a, "variants": b} for a, b in suggestions],
        "low_coverage_files": [{"file": r[0], "candidates": r[1], "hit": r[2], "coverage": round(r[3], 2)}
                               for r in low_files],
    }
    (OUT / "terms-audit.json").write_text(json.dumps(audit, ensure_ascii=False, indent=1), encoding="utf-8")

    md = ["# 实体词表审计（纯代码生成）", "",
          f"- 输入文件：{len(files)}（分级：{dict((k, len(v)) for k, v in grades.items())}）",
          f"- 文本候选：{len(all_cands)} 条 → 词干簇 {len(clusters)} 个 → 保留 {len(kept)} 个",
          f"- veto：{len(vetoed)} 条；draft 词条：{len(draft_lines)} 条", "",
          "## HIGH/MEDIUM（自动入 draft）", "| 词干 | 类别 | 桶 | 文件数 | 变体 |", "|---|---|---|---|---|"]
    for c in kept[:400]:
        if c.bucket == "LOW":
            continue
        md.append(f"| {c.stem} | {c.vote} | {c.bucket} | {len(c.files)} | {'、'.join(sorted(c.variants)[:4])} |")
    md += ["", "## LOW（待人工确认：人名/文件名片段/宽泛项目名）",
           "| 词干 | 类别 | 文件数 | 变体 |", "|---|---|---|---|"]
    for c in kept:
        if c.bucket == "LOW":
            md.append(f"| {c.stem} | {c.vote} | {len(c.files)} | {'、'.join(sorted(c.variants)[:4])} |")
    md += ["", "## 语料外变体建议（勿自动入表，人工确认）", "| 词干 | 建议变体 |", "|---|---|"]
    for a, sg in suggestions[:60]:
        md.append(f"| {a} | {'、'.join(sg)} |")
    md += ["", "## 疑似漏检文件（覆盖率 < 30%）", "| 文件 | 候选 | 命中 | 覆盖率 |", "|---|---|---|---|"]
    for r in low_files:
        md.append(f"| {r[0]} | {r[1]} | {r[2]} | {r[3]:.0%} |")
    (OUT / "terms-audit.md").write_text("\n".join(md) + "\n", encoding="utf-8")

    cov_lines = ["# 文件级覆盖校验", "", "| 文件 | 候选数 | 词表命中 | 覆盖率 |", "|---|---|---|---|"]
    for name, n, h, c in coverage_rows:
        cov_lines.append(f"| {name} | {n} | {h} | {c:.0%} |")
    (OUT / "coverage.md").write_text("\n".join(cov_lines) + "\n", encoding="utf-8")

    reg = ["# 正负样本回归", "", "## 正样本（必须命中）", "| 实体 | 命中 |", "|---|---|"]
    for w, h in pos_hit:
        reg.append(f"| {w} | {'✅' if h else '❌'} |")
    reg += ["", "## 负样本（必须不命中）", "| 词 | 误命中 |", "|---|---|"]
    for w, h in neg_hit:
        reg.append(f"| {w} | {'❌' if h else '✅'} |")
    (OUT / "regression.md").write_text("\n".join(reg) + "\n", encoding="utf-8")

    print(json.dumps({
        "grades": {k: len(v) for k, v in grades.items()},
        "candidates": len(all_cands), "clusters": len(clusters),
        "kept": len(kept), "vetoed": len(vetoed),
        "draft_terms": len(draft_lines), "suggestions": len(suggestions),
        "low_coverage_files": len(low_files),
        "positive_hit": sum(1 for _, h in pos_hit if h), "positive_total": len(pos_hit),
        "negative_hit": sum(1 for _, h in neg_hit if h),
    }, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())