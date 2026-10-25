# -*- coding: utf-8 -*-
"""从原版静态生成万邦之秋地图；同名覆盖，不改原版。

归属只搬运原版已经有主的地点，不把海洋、荒地或殖民点变成国家。
运行后同时同步人物、定义、藩镇触发器、外交与组织，避免旧 tag 残留。
"""
import os
import re
import json
from pathlib import Path
from collections import OrderedDict, defaultdict

from prince_data import PRINCES

GAME = "D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DEFS = os.path.join(GAME, "in_game/map_data/definitions.txt")
V_COUNTRIES = os.path.join(GAME, "main_menu/setup/1337/10_countries.txt")
OUT_COUNTRIES = os.path.join(MOD, "main_menu/setup/1337/10_countries.txt")
OUT_CHARS = os.path.join(MOD, "main_menu/setup/1337/05_sts_characters.txt")
OUT_LOC = os.path.join(MOD, "main_menu/localization/simp_chinese/sts_l_simp_chinese.yml")
SONG, DALI, SONG_CITY = "CSO", "CDL", "kaifeng"
CHINA_AREAS = [
    "hebei_area", "henan_area",
    "haiyou_area", "shandong_area", "shaanxi_area",
    "chuandong_area", "chuannan_area", "chuanxi_area",
    "huaidong_area", "huaixi_area", "jiangnan_area", "zhejiang_area",
    "jiangxi_area", "fujian_area", "hubei_area", "hunan_area", "wuling_area",
    "guangdong_area", "guangxi_area", "haibei_hainan_area", "liangjiang_area",
]
OTHER_PLAN = [
    ("ngari_area", "GUG", "古格"),
    ("kham_area", "DGS", "朵甘思"),
    ("amdo_area", "DSM", "朵思麻"),
    ("changtang_area", "DSM", "朵思麻"),
    ("dzungaria_area", "MGS", "蒙兀儿斯坦"),
    ("tarim_area", "YUT", "于阗"),
]
# 元仍据汉地：北平、燕南、山西整片归还元，作为绿巾军起义的爆点。
YUAN_RETURN_AREAS = ["beiping_area", "yannan_area", "shanxi_area"]
# 贵州：一省一国，全部加入丞相府（不入天朝，不算藩镇）。
GUIZHOU_AREAS = ["guizhou_area"]
# 山西南部：从元手中拆出，一省一国，全部加入丞相府（不入天朝，不算藩镇）。
SHANXI_SOUTH_PROVINCES = [
    "pingyang_province", "puzhou_shanxi_province", "jiangzhou_province",
    "xiezhou_province", "zezhou_province", "luan_province",
    "qinzhou_province", "huozhou_province", "liaozhou_province",
]
# 梁（KFE）开局吞并的三省：郑州、许州（徐州保持独立）。
LIANG_ANNEX_PROVINCES = ["zhengzhou_province", "xuzhou_henan_province"]
# 西安（XIA）改为秦，吞并乾州、耀州、邠州、凤翔。
XIA_ANNEX = {
    "QIA": "qianzhou_province",
    "YAD": "yaozhou_province",
    "BAE": "binzhou_shaanxi_province",
    "FEN": "fengxiang_province",
}
XIA_ANNEX_TAGS = set(XIA_ANNEX)
XIA_ANNEX_PROVINCES = list(XIA_ANNEX.values())
# 济南（JIN）改为齐，吞并武定、德州。
JIN_ANNEX = {
    "WUD": "wuding_shandong_province",
    "DEZ": "dezhou_province",
}
JIN_ANNEX_TAGS = set(JIN_ANNEX)
JIN_ANNEX_PROVINCES = list(JIN_ANNEX.values())
# 登州（DAD）改为莱，吞并宁海。
DAD_ANNEX = {
    "NIN": "ninghai_province",
}
DAD_ANNEX_TAGS = set(DAD_ANNEX)
DAD_ANNEX_PROVINCES = list(DAD_ANNEX.values())
# 成都（CAJ）改为蜀，吞并汉州、剑州、潼川、简州、遂宁。
CAJ_ANNEX = {
    "HAO": "hanzhou_province",
    "JAC": "jianzhou_province",
    "TAF": "tongchuan_province",
    "JAD": "jianzhou_west_province",
    "SAJ": "suining_province",
}
CAJ_ANNEX_TAGS = set(CAJ_ANNEX)
CAJ_ANNEX_PROVINCES = list(CAJ_ANNEX.values())
# 潞安（LAK）改为晋，吞并沁州、平阳、辽州、霍州。
LAK_ANNEX = {
    "QAF": "qinzhou_province",
    "PAI": "pingyang_province",
    "LAO": "liaozhou_province",
    "HUO": "huozhou_province",
}
LAK_ANNEX_TAGS = set(LAK_ANNEX)
LAK_ANNEX_PROVINCES = list(LAK_ANNEX.values())
# 应天（YAF）改为吴，吞并太平、镇江。
YAF_ANNEX = {
    "TAJ": "taiping_province",
    "ZAA": "zhenjiang_province",
}
YAF_ANNEX_TAGS = set(YAF_ANNEX)
YAF_ANNEX_PROVINCES = list(YAF_ANNEX.values())
# 襄阳（XAF）改为楚，吞并安陆、荆门。
XAF_ANNEX = {
    "AAA": "anlu_province",
    "JAK": "jingmen_province",
}
XAF_ANNEX_TAGS = set(XAF_ANNEX)
XAF_ANNEX_PROVINCES = list(XAF_ANNEX.values())
# 兴安（XAB）改为汉，吞并洋州。
XAB_ANNEX = {
    "YAC": "yangzhou_shaanxi_province",
}
XAB_ANNEX_TAGS = set(XAB_ANNEX)
XAB_ANNEX_PROVINCES = list(XAB_ANNEX.values())
# 杭州（HAS）改为越，吞并绍兴、嘉兴。
HAS_ANNEX = {
    "SBB": "shaoxing_province",
    "JAF": "jiaxing_province",
}
HAS_ANNEX_TAGS = set(HAS_ANNEX)
HAS_ANNEX_PROVINCES = list(HAS_ANNEX.values())

# 开局整国吞并：键为吞并者，值为被吞并的 tag。
# 这些是 1337 年剧本的势力整合，被吞并者从 setup 国家表中移除。
TAG_ANNEX = {
    "DAD": {"LAI", "JIA"},
    "JIN": {"BAB", "GAO", "DON", "LAA"},
    "LAK": {"ZAH", "JAO", "XIE", "PAJ"},
    "XIA": {"TAD", "HAJ"},
    "XAB": {"HAH"},
    "CAJ": {"LAB", "MAQ", "PAA"},
    "XAF": {"SBD", "JUN", "FAN"},
    "YAF": {"CAK", "GAE"},
    "HAS": {"SAT", "NAC"},
}
# 特殊国号：梁、秦、齐、莱。
SPECIAL_COUNTRY_NAMES = {
    "kaifeng_province": "梁",
    "xian_province": "秦",
    "jinan_province": "齐",
    "dengzhou_province": "莱",
    "chengdu_province": "蜀",
    "luan_province": "晋",
    "yingtian_province": "吴",
    "xiangyang_province": "楚",
    "xingan_province": "汉",
    "hangzhou_province": "越",
}
SPECIAL_CAPITALS = {
    "KFE": "kaifeng",
    "XIA": "jingzhao",
    "JIN": "licheng",
    "DAD": "penglai",
    "CAJ": "chengdu",
    "LAK": "shangdang",
    "YAF": "jiangning",
    "XAF": "xiangyang",
    "XAB": "xicheng",
    "HAS": "hangzhou",
}


def special_capital(tag, locs):
    return SPECIAL_CAPITALS.get(tag, "toling" if tag == "GUG" else locs[0])
SURNAMES = list("赵钱孙李周吴郑王冯陈褚卫蒋沈韩杨朱秦尤许何吕施张孔曹严华金魏陶姜")
GIVEN = ["承宗", "延寿", "守节", "从训", "继勋", "文德", "元礼", "仲武", "季昌", "叔度", "公度", "伯谦",
         "彦昭", "彦章", "德昭", "德全", "思远", "思敬", "克明", "克勤", "惟简", "惟孝", "敬之", "慎之",
         "子仪", "子昂", "子期", "子重", "大用", "大有"]
OWN_RE = re.compile(r"\bown_control_(?:core|integrated|conquered)\s*=\s*\{([^{}]*)\}", re.S)


def read(path):
    return Path(path).read_text(encoding="utf-8-sig")


def uncomment(text):
    return re.sub(r"#[^\n]*", "", text)


def block_spans(lines):
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^\t([A-Z][A-Z0-9]{1,2})\s*=\s*\{", line)
        if not m:
            continue
        depth = 0
        for j in range(i, len(lines)):
            code = uncomment(lines[j])
            depth += code.count("{") - code.count("}")
            if depth == 0:
                out.append((m.group(1), i, j))
                break
    return out


def parse_definitions():
    """按花括号解析，兼容多行省块；不能靠 tab 或行尾读取省内地点。"""
    tokens = re.findall(r"[A-Za-z0-9_]+|[{}=]", uncomment(read(DEFS)))
    regions = OrderedDict()
    stack = []
    i = 0
    while i < len(tokens):
        token = tokens[i]
        if i + 2 < len(tokens) and tokens[i + 1:i + 3] == ["=", "{"]:
            stack.append(token)
            if token.endswith("_region"):
                regions[token] = OrderedDict()
            elif token.endswith("_area"):
                region = next((x for x in reversed(stack[:-1]) if x.endswith("_region")), None)
                if region:
                    regions[region][token] = OrderedDict()
            i += 3
        elif token == "}":
            if stack:
                stack.pop()
            i += 1
        elif i + 1 < len(tokens) and tokens[i + 1] == "=":
            i += 3  # 属性如 not_eligible_for_dynamic_country_name = yes
        else:
            if len(stack) >= 3 and stack[-2].endswith("_area") and stack[-3].endswith("_region"):
                region, area, province = stack[-3:]
                regions[region][area].setdefault(province, []).append(token)
            i += 1
    return regions


def country_blocks(text):
    lines = text.splitlines()
    return OrderedDict((t, "\n".join(lines[s:e + 1])) for t, s, e in block_spans(lines))


def ownership(blocks):
    owners = defaultdict(list)
    for tag, block in blocks.items():
        for match in OWN_RE.finditer(uncomment(block)):
            for loc in match.group(1).split():
                owners[loc].append(tag)
    return dict(owners)


def definition_tags():
    tags = set()
    for path in Path(GAME, "in_game/setup/countries").glob("*.txt"):
        tags.update(re.findall(r"^([A-Z][A-Z0-9]{1,2})\s*=\s*\{", read(path), re.M))
    # 可成立国家也占用 tag，即便 1337 尚未激活也不能借用。
    for path in Path(GAME, "in_game/common/formable_countries").glob("*.txt"):
        tags.update(re.findall(r"^\ttag\s*=\s*([A-Z][A-Z0-9]{1,2})\b", read(path), re.M))
    return tags


def make_tag(province, used):
    base = (re.sub(r"[^A-Z]", "", province.upper()) + "AAA")[:3]
    for tag in [base] + [base[0] + a + b for a in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" for b in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"]:
        if tag not in used:
            used.add(tag)
            return tag
    raise ValueError("tag 用尽：" + province)


def load_names():
    # 原版有少量省键无 _province 后缀（例如 qingchi），沿用同键本地化。
    text = read(Path(GAME, "main_menu/localization/simp_chinese/location_names/location_names_l_simp_chinese.yml"))
    text += "\n" + read(Path(GAME, "main_menu/localization/simp_chinese/province_names_l_simp_chinese.yml"))
    return dict(re.findall(r'^\s+([a-z0-9_]+):(?:\d+)?\s*"([^"\n]*)"', text, re.M))


def replace_owned(block, remove):
    def replace(match):
        locs = [x for x in uncomment(match.group(1)).split() if x not in remove]
        head = match.group(0).split("{", 1)[0] + "{"
        return head + "\n" + "\n".join("\t\t\t" + " ".join(locs[i:i + 8]) for i in range(0, len(locs), 8)) + "\n\t\t}"
    return OWN_RE.sub(replace, block)


def add_owned(block, locs):
    """把地点并入已有国家块，用于把整片地区强制归还给元。"""
    if not locs:
        return block
    lines = block.rstrip().split("\n")
    close = lines[-1]
    indent = close[: len(close) - len(close.lstrip())]
    body = [f"{indent}\town_control_core = {{"]
    body += [f"{indent}\t\t" + " ".join(sorted(locs)[i:i + 8]) for i in range(0, len(locs), 8)]
    body += [f"{indent}\t}}"]
    return "\n".join(lines[:-1] + body + [close])


def template_laws(include):
    """读取原版政体模板的 laws 条目，避免局部 laws 覆盖模板法律。"""
    path = Path(GAME, "main_menu/setup/templates", include + ".txt")
    text = read(path)
    m = re.search(r"\n\tlaws = \{\n(.*?)\n\t\}", text, re.S)
    if not m:
        raise ValueError(f"{include} 模板没有 laws 块")
    return [line.strip() for line in m.group(1).splitlines() if line.strip()]


def make_block(tag, name, locs, capital=None, rank="rank_duchy", culture=None, religion=None):
    cap = capital or locs[0]
    ruler = "sts_song_ruler" if tag == SONG else f"sts_{tag.lower()}_ruler"
    include = "chinese_monarchy" if culture is None else "east_asia_monarchy_no_coast"
    body = [f"\t{tag} = {{ # {name}（{len(locs)} 个地点）", "\t\town_control_core = {"]
    body += ["\t\t\t" + " ".join(locs[i:i + 8]) for i in range(0, len(locs), 8)]
    body += ["\t\t}", f'\t\tinclude = "{include}"', f"\t\tcapital = {cap}", f"\t\tcountry_rank = {rank}",
             "\t\tgovernment = {", "\t\t\ttype = monarchy", "\t\t\their_selection = salic_law", f"\t\t\truler = {ruler}"]
    if tag in PRINCES:
        law = PRINCES[tag]["law"]
        entries = template_laws(include)
        body.append("\t\t\tlaws = {")
        body += ["\t\t\t\t" + line for line in entries]
        body.append(f"\t\t\t\t{law['key']} = {law['default']}")
        body.append("\t\t\t}")
        assert len(entries) + 1 > 0
    body += ["\t\t}", "\t}"]
    return "\n".join(body)


def make_song_block():
    """宋：静态建筑国家，无领土；首都开封由 KFE 实际拥有。"""
    return "\n".join([
        "\tCSO = { # 宋（建筑国家，无领土）",
        "\t\ttype = building",
        "\t\tinclude = \"chinese_monarchy\"",
        "\t\tcapital = kaifeng",
        "\t\tcountry_rank = rank_empire",
        "\t\tgovernment = { type = monarchy heir_selection = salic_law ruler = sts_song_ruler }",
        "\t}",
    ])


def main():
    regions = parse_definitions()
    areas = {a: ps for region in regions.values() for a, ps in region.items()}
    provinces = {p: ls for ps in areas.values() for p, ls in ps.items()}
    raw = read(V_COUNTRIES)
    blocks = country_blocks(raw)
    original_owners = ownership(blocks)
    owned = set(original_owners)
    have = definition_tags()
    used = have | set(blocks) | {SONG, DALI}
    names = load_names()
    states = []
    chinese = []
    kaifeng_tag = None
    # 必须是原版已有人主的地点；保持殖民地、海湖与荒地原状。
    for area in CHINA_AREAS:
        for province, locations in areas[area].items():
            locs = [x for x in locations if x in owned]
            if not locs:
                continue
            if province not in names:
                raise ValueError("缺少原版省名：" + province)
            tag = make_tag("KFE" if province == "kaifeng_province" else province, used)
            if province == "kaifeng_province":
                kaifeng_tag = tag
            display_name = SPECIAL_COUNTRY_NAMES.get(province, names[province])
            states.append((tag, display_name, [province], locs))
            chinese.append(tag)
    # 梁吞并徐州、郑州、许州：三省地点并入 KFE，三国从诸侯名单移除。
    annexed_tags = set()
    annexed_locs = set()
    found_provinces = set()
    for province in LIANG_ANNEX_PROVINCES:
        for tag, _, ps, locs in states:
            if ps == [province]:
                annexed_tags.add(tag)
                annexed_locs.update(locs)
                found_provinces.add(province)
                break
    if len(found_provinces) != len(LIANG_ANNEX_PROVINCES):
        raise ValueError("梁吞并省份缺失：" + str(set(LIANG_ANNEX_PROVINCES) - found_provinces))
    states = [
        (tag, name, ps, sorted(set(locs) | annexed_locs) if tag == kaifeng_tag else locs)
        for tag, name, ps, locs in states if tag not in annexed_tags
    ]
    chinese = [tag for tag in chinese if tag not in annexed_tags]
    # 西安改秦，吞并乾州、耀州、邠州、凤翔；四个源 tag 从诸侯名单移除。
    xia_locs = set()
    xia_found = set()
    for tag, _, _, locs in states:
        if tag in XIA_ANNEX_TAGS:
            xia_locs.update(locs)
            xia_found.add(tag)
    if xia_found != XIA_ANNEX_TAGS:
        raise ValueError("秦吞并 tag 缺失：" + str(XIA_ANNEX_TAGS - xia_found))
    if not any(tag == "XIA" for tag, _, _, _ in states):
        raise ValueError("西安 XIA 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | xia_locs) if tag == "XIA" else locs)
        for tag, name, ps, locs in states if tag not in XIA_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in XIA_ANNEX_TAGS]
    annexed_tags |= XIA_ANNEX_TAGS
    # 济南改齐，吞并武定、德州。
    jin_locs = set()
    jin_found = set()
    for tag, _, _, locs in states:
        if tag in JIN_ANNEX_TAGS:
            jin_locs.update(locs)
            jin_found.add(tag)
    if jin_found != JIN_ANNEX_TAGS:
        raise ValueError("齐吞并 tag 缺失：" + str(JIN_ANNEX_TAGS - jin_found))
    if not any(tag == "JIN" for tag, _, _, _ in states):
        raise ValueError("济南 JIN 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | jin_locs) if tag == "JIN" else locs)
        for tag, name, ps, locs in states if tag not in JIN_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in JIN_ANNEX_TAGS]
    annexed_tags |= JIN_ANNEX_TAGS
    # 登州改莱，吞并宁海。
    dad_locs = set()
    dad_found = set()
    for tag, _, _, locs in states:
        if tag in DAD_ANNEX_TAGS:
            dad_locs.update(locs)
            dad_found.add(tag)
    if dad_found != DAD_ANNEX_TAGS:
        raise ValueError("莱吞并 tag 缺失：" + str(DAD_ANNEX_TAGS - dad_found))
    if not any(tag == "DAD" for tag, _, _, _ in states):
        raise ValueError("登州 DAD 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | dad_locs) if tag == "DAD" else locs)
        for tag, name, ps, locs in states if tag not in DAD_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in DAD_ANNEX_TAGS]
    annexed_tags |= DAD_ANNEX_TAGS
    # 成都改蜀，吞并汉州、剑州、潼川、简州、遂宁。
    caj_locs = set()
    caj_found = set()
    for tag, _, _, locs in states:
        if tag in CAJ_ANNEX_TAGS:
            caj_locs.update(locs)
            caj_found.add(tag)
    if caj_found != CAJ_ANNEX_TAGS:
        raise ValueError("蜀吞并 tag 缺失：" + str(CAJ_ANNEX_TAGS - caj_found))
    if not any(tag == "CAJ" for tag, _, _, _ in states):
        raise ValueError("成都 CAJ 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | caj_locs) if tag == "CAJ" else locs)
        for tag, name, ps, locs in states if tag not in CAJ_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in CAJ_ANNEX_TAGS]
    annexed_tags |= CAJ_ANNEX_TAGS
    # 应天改吴，吞并太平、镇江。
    yaf_locs = set()
    yaf_found = set()
    for tag, _, _, locs in states:
        if tag in YAF_ANNEX_TAGS:
            yaf_locs.update(locs)
            yaf_found.add(tag)
    if yaf_found != YAF_ANNEX_TAGS:
        raise ValueError("吴吞并 tag 缺失：" + str(YAF_ANNEX_TAGS - yaf_found))
    if not any(tag == "YAF" for tag, _, _, _ in states):
        raise ValueError("应天 YAF 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | yaf_locs) if tag == "YAF" else locs)
        for tag, name, ps, locs in states if tag not in YAF_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in YAF_ANNEX_TAGS]
    annexed_tags |= YAF_ANNEX_TAGS
    # 襄阳改楚，吞并安陆、荆门。
    xaf_locs = set()
    xaf_found = set()
    for tag, _, _, locs in states:
        if tag in XAF_ANNEX_TAGS:
            xaf_locs.update(locs)
            xaf_found.add(tag)
    if xaf_found != XAF_ANNEX_TAGS:
        raise ValueError("楚吞并 tag 缺失：" + str(XAF_ANNEX_TAGS - xaf_found))
    if not any(tag == "XAF" for tag, _, _, _ in states):
        raise ValueError("襄阳 XAF 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | xaf_locs) if tag == "XAF" else locs)
        for tag, name, ps, locs in states if tag not in XAF_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in XAF_ANNEX_TAGS]
    annexed_tags |= XAF_ANNEX_TAGS
    # 兴安改汉，吞并洋州。
    xab_locs = set()
    xab_found = set()
    for tag, _, _, locs in states:
        if tag in XAB_ANNEX_TAGS:
            xab_locs.update(locs)
            xab_found.add(tag)
    if xab_found != XAB_ANNEX_TAGS:
        raise ValueError("汉吞并 tag 缺失：" + str(XAB_ANNEX_TAGS - xab_found))
    if not any(tag == "XAB" for tag, _, _, _ in states):
        raise ValueError("兴安 XAB 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | xab_locs) if tag == "XAB" else locs)
        for tag, name, ps, locs in states if tag not in XAB_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in XAB_ANNEX_TAGS]
    annexed_tags |= XAB_ANNEX_TAGS
    # 杭州改越，吞并绍兴、嘉兴。
    has_locs = set()
    has_found = set()
    for tag, _, _, locs in states:
        if tag in HAS_ANNEX_TAGS:
            has_locs.update(locs)
            has_found.add(tag)
    if has_found != HAS_ANNEX_TAGS:
        raise ValueError("越吞并 tag 缺失：" + str(HAS_ANNEX_TAGS - has_found))
    if not any(tag == "HAS" for tag, _, _, _ in states):
        raise ValueError("杭州 HAS 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | has_locs) if tag == "HAS" else locs)
        for tag, name, ps, locs in states if tag not in HAS_ANNEX_TAGS
    ]
    chinese = [tag for tag in chinese if tag not in HAS_ANNEX_TAGS]
    annexed_tags |= HAS_ANNEX_TAGS
    # 贵州：土司地区按省拆成一省一国，全部加入丞相府（不列入藩镇、不入天朝）。
    guizhou = []
    for area in GUIZHOU_AREAS:
        for province, locations in areas[area].items():
            locs = [x for x in locations if x in owned]
            if not locs:
                continue
            if province not in names:
                raise ValueError("缺少原版省名：" + province)
            tag = make_tag(province, used)
            states.append((tag, names[province], [province], locs))
            guizhou.append(tag)
    # 山西南部：从元手中拆出，一省一国，全部加入丞相府。
    shanxi_south = []
    shanxi_south_locs = set()
    for province in SHANXI_SOUTH_PROVINCES:
        locations = areas["shanxi_area"].get(province, [])
        locs = [x for x in locations if x in owned]
        if not locs:
            continue
        if province not in names:
            raise ValueError("缺少原版省名：" + province)
        tag = make_tag(province, used)
        display_name = SPECIAL_COUNTRY_NAMES.get(province, names[province])
        states.append((tag, display_name, [province], locs))
        shanxi_south.append(tag)
        shanxi_south_locs.update(locs)
    # 潞安改晋，吞并沁州、平阳、辽州、霍州；四个源 tag 从山西南名单移除。
    lak_locs = set()
    lak_found = set()
    for tag, _, _, locs in states:
        if tag in LAK_ANNEX_TAGS:
            lak_locs.update(locs)
            lak_found.add(tag)
    if lak_found != LAK_ANNEX_TAGS:
        raise ValueError("晋吞并 tag 缺失：" + str(LAK_ANNEX_TAGS - lak_found))
    if not any(tag == "LAK" for tag, _, _, _ in states):
        raise ValueError("潞安 LAK 不存在")
    states = [
        (tag, name, ps, sorted(set(locs) | lak_locs) if tag == "LAK" else locs)
        for tag, name, ps, locs in states if tag not in LAK_ANNEX_TAGS
    ]
    shanxi_south = [tag for tag in shanxi_south if tag not in LAK_ANNEX_TAGS]
    annexed_tags |= LAK_ANNEX_TAGS
    # 开局整国吞并：莱、齐、晋、秦、汉、蜀、楚、吴、越各自整合周边小国。
    for owner, targets in TAG_ANNEX.items():
        merged = set()
        found = set()
        if not any(tag == owner for tag, _, _, _ in states):
            raise ValueError(f"吞并者 {owner} 不存在")
        for tag, _, _, locs in states:
            if tag in targets:
                merged.update(locs)
                found.add(tag)
        if found != targets:
            raise ValueError(f"{owner} 吞并 tag 缺失：" + str(targets - found))
        states = [
            (tag, name, ps, sorted(set(locs) | merged) if tag == owner else locs)
            for tag, name, ps, locs in states if tag not in targets
        ]
        chinese = [tag for tag in chinese if tag not in targets]
        shanxi_south = [tag for tag in shanxi_south if tag not in targets]
        annexed_tags |= targets
    groups = OrderedDict()
    for area, preferred, name in OTHER_PLAN:
        if preferred not in groups:
            tag = "GUG" if preferred == "GUG" else make_tag(preferred, used)
            groups[preferred] = [tag, name, [], []]
        groups[preferred][2].extend(areas[area])
        groups[preferred][3].extend(x for ls in areas[area].values() for x in ls if x in owned)
    states.extend(tuple(x) for x in groups.values())
    if not kaifeng_tag:
        raise ValueError("开封省势力缺失")
    target = OrderedDict((tag, locs) for tag, _, _, locs in states)
    target[SONG] = []
    yunnan_locs = {x for a in ("dali_area", "yunnan_area") for ls in areas[a].values() for x in ls}
    deleted = {"LNG"} | annexed_tags
    dali = yunnan_locs & owned
    for tag, block in blocks.items():
        cap = re.search(r"\bcapital\s*=\s*(\w+)", uncomment(block))
        if tag != DALI and cap and cap.group(1) in yunnan_locs:
            deleted.add(tag)
    for loc, tags in original_owners.items():
        if any(t in deleted or t == DALI for t in tags):
            dali.add(loc)
    # 云南被删除国家在川边的既有领土随并入大理，不能再重复给西藏方案。
    states = [(t, n, ps, [x for x in ls if x not in dali]) for t, n, ps, ls in states]
    target = OrderedDict((t, ls) for t, _, _, ls in states)
    target[SONG] = []
    target[DALI] = sorted(dali)
    assigned = {x for ls in target.values() for x in ls}
    # 北平、燕南、山西整片强制归元；山西南部已拆成相府诸侯，需从归元集合中扣除。
    yuan_return = {x for a in YUAN_RETURN_AREAS for ls in areas[a].values() for x in ls if x in owned}
    yuan_return -= shanxi_south_locs
    chi_own = {x for x, ts in original_owners.items() if "CHI" in ts}
    assigned |= yuan_return
    for tag in list(blocks):
        if tag in deleted:
            del blocks[tag]
        else:
            blocks[tag] = replace_owned(blocks[tag], assigned)
    blocks["CHI"] = add_owned(blocks["CHI"], yuan_return)
    # 被整省收走全部领土的原版地方国家不再作为无地普通国家留在 setup。
    remaining = ownership(blocks)
    had_land = {t for ts in original_owners.values() for t in ts}
    has_land = {t for ts in remaining.values() for t in ts}
    for tag in list(blocks):
        if tag not in target and tag in had_land and tag not in has_land:
            deleted.add(tag)
            del blocks[tag]
    templates = dict(re.findall(r"^(\w+)\s*=\s*\{([^{}]*)\}", read(Path(GAME, "in_game/map_data/location_templates.txt")), re.M))
    attrs = {}
    leader_cultures = {}
    for tag, name, ps, locs in states:
        cap = special_capital(tag, locs)
        tpl = templates[cap]
        culture = re.search(r"\bculture\s*=\s*(\w+)", tpl).group(1)
        religion = re.search(r"\breligion\s*=\s*(\w+)", tpl).group(1)
        attrs[tag] = ("zhongyuan_culture", "sanjiao") if tag in chinese else (culture, religion)
        leader_cultures[tag] = culture
        capital = SPECIAL_CAPITALS.get(tag, "toling" if tag == "GUG" else None)
        rank = "rank_kingdom" if tag in ("XIA", "JIN", "DAD", "CAJ", "LAK", "YAF", "XAF", "XAB", "HAS") else "rank_duchy"
        blocks[tag] = make_block(tag, name, locs, capital=capital, rank=rank,
                                 culture=None if tag in chinese else culture)
    blocks[SONG] = make_song_block()
    blocks[DALI] = make_block(DALI, "大理", target[DALI], capital="taihe_dali", rank="rank_kingdom", culture="bai_culture")
    # 保留部分领土的原版地方国家若失去旧首都，迁往其剩余领土。
    remaining_owners = ownership(blocks)
    for tag, block in list(blocks.items()):
        cap = re.search(r"\bcapital\s*=\s*(\w+)", uncomment(block))
        locs = [x for x, ts in remaining_owners.items() if tag in ts]
        if cap and locs and tag not in remaining_owners.get(cap.group(1), []) and tag in original_owners.get(cap.group(1), []):
            blocks[tag] = re.sub(r"\bcapital\s*=\s*" + re.escape(cap.group(1)) + r"\b", "capital = " + locs[0], block)
    # 元以大都为都；只有绿巾军结局失败时才退往上都、转为蒙古（北元）。
    blocks["CHI"] = re.sub(r"\bcapital\s*=\s*\w+", "capital = dadu", blocks["CHI"])
    if "dadu" not in [x for x, ts in ownership(blocks).items() if "CHI" in ts]:
        raise ValueError("元定都失败：大都未归元")
    new_owners = ownership(blocks)
    lost = owned - set(new_owners)
    dup = {x: ts for x, ts in new_owners.items() if len(ts) > 1}
    new = set(new_owners) - owned
    if lost or dup or new:
        raise ValueError(f"归属不变量失败：丢失={sorted(lost)} 重复={dup} 新殖民={sorted(new)}")
    # 保持原版文件其余顶层内容，仅替换 countries 外壳内国家块。
    lines = raw.splitlines()
    spans = block_spans(lines)
    text = "\n".join(lines[:spans[0][1]]) + "\n" + "\n\n".join(blocks.values()) + "\n" + "\n".join(lines[spans[-1][2] + 1:]) + "\n"
    Path(OUT_COUNTRIES).write_text(text, encoding="utf-8")
    province_tags = {p: t for t, _, ps, _ in states for p in ps}
    for province in LIANG_ANNEX_PROVINCES:
        province_tags[province] = kaifeng_tag
    for province in XIA_ANNEX_PROVINCES:
        province_tags[province] = "XIA"
    for province in JIN_ANNEX_PROVINCES:
        province_tags[province] = "JIN"
    for province in DAD_ANNEX_PROVINCES:
        province_tags[province] = "DAD"
    for province in CAJ_ANNEX_PROVINCES:
        province_tags[province] = "CAJ"
    for province in LAK_ANNEX_PROVINCES:
        province_tags[province] = "LAK"
    for province in YAF_ANNEX_PROVINCES:
        province_tags[province] = "YAF"
    for province in XAF_ANNEX_PROVINCES:
        province_tags[province] = "XAF"
    for province in XAB_ANNEX_PROVINCES:
        province_tags[province] = "XAB"
    for province in HAS_ANNEX_PROVINCES:
        province_tags[province] = "HAS"
    tags_data = {"kaifeng": kaifeng_tag, "chinese": chinese,
                 "guizhou": guizhou, "shanxi_south": shanxi_south,
                 "chancellery": chinese + guizhou + shanxi_south,
                 "other": [t for t, _, _, _ in states if t not in chinese and t not in guizhou and t not in shanxi_south],
                 "all": [t for t, _, _, _ in states],
                 "deleted": sorted(deleted), "province_tags": province_tags}
    Path(MOD, "tools/sts_tags.json").write_text(json.dumps(tags_data, ensure_ascii=False, indent=2), encoding="utf-8")
    gen_country_defs(states, attrs, have, leader_cultures)
    gen_characters(states, attrs, leader_cultures)
    gen_triggers(chinese)
    gen_diplomacy(deleted)
    # 同步组织不能再是可遗忘的手工步骤。
    import importlib
    import gen_io
    importlib.reload(gen_io)
    gen_io.main()
    import gen_buildings
    importlib.reload(gen_buildings)
    gen_buildings.main()
    # 八国 advance / 法律 / 本地化与地图同源生成，避免手改漂移。
    import gen_prince_content
    importlib.reload(gen_prince_content)
    gen_prince_content.main()
    print(f"北宋省势力 {len(chinese)} 家；贵州土司 {len(guizhou)} 家；山西南部 {len(shanxi_south)} 家；非宋 {len(states) - len(chinese) - len(guizhou) - len(shanxi_south)} 家；国家块 {len(blocks)}")
    print(f"原版有主 {len(owned)}；生成后有主 {len(new_owners)}；丢失 {len(lost)}；重复 {len(dup)}；新增殖民 {len(new)}")
    print(f"元 {sum('CHI' in ts for ts in new_owners.values())} 点（含归还的北平/燕南/山西 {len(yuan_return)} 点）；大理 {len(target[DALI])} 点")
    print(f"宋：无地建筑国家，宋廷固定开封；开封归 {kaifeng_tag}")
    print("完成")


def gen_country_defs(states, attrs, have, leader_cultures=None):
    out = ["# 万邦之秋：自动生成国家定义，禁止撞用原版其他国家 tag。", ""]
    n = 0
    for tag, name, _, _ in states:
        if tag in have:
            continue
        n += 1
        culture, religion = attrs[tag]
        if leader_cultures:
            culture = leader_cultures.get(tag, culture)
        out += [f"{tag} = {{ # {name}", f"\tcolor = rgb {{ {60 + n * 7 % 180} {70 + n * 11 % 150} {50 + n * 13 % 160} }}",
                "\tcolor2 = rgb { 16 41 202 }", f"\tculture_definition = {culture}", f"\treligion_definition = {religion}", "}", ""]
    Path(MOD, "in_game/setup/countries/sts_countries.txt").write_text("\n".join(out), encoding="utf-8-sig")
    print(f"新增定义 {n} 个")


def gen_characters(states, attrs, leader_cultures=None):
    out = ["# 万邦之秋：男性统治者；与国家表同次生成。", "character_db = {"]
    loc = [" # ---------- 地图生成：国名与君主 ----------"]
    for idx, (tag, name, _, locs) in enumerate(states):
        key = f"sts_name_{tag.lower()}"
        religion = attrs[tag][1]
        culture = leader_cultures.get(tag, attrs[tag][0]) if leader_cultures else attrs[tag][0]
        birth = special_capital(tag, locs)
        ruler_key = f"sts_{tag.lower()}_ruler"
        wife_key = f"sts_{tag.lower()}_wife"
        son_key = f"sts_{tag.lower()}_son"
        wife_name_key = f"sts_name_{tag.lower()}_wife"
        son_name_key = f"sts_name_{tag.lower()}_son"

        if tag == "KFE":
            # 开封势力＝梁，首任丞相张嵩：男，38 岁，80/70/70，妻李氏，二子一女。
            ruler_name_key = "sts_name_zhang_song"
            ruler_name = "张嵩"
            adm, dip, mil = 80, 70, 70
            birth_date = "1299.3.15"
            wife_name_key = "sts_name_zhang_li_shi"
            wife_name = "李夫人"
            wife_birth = "1302.6.1"
            children = [
                ("sts_kfe_son1", "sts_name_zhang_chengzong", "张承宗", False, "1318.5.1"),
                ("sts_kfe_son2", "sts_name_zhang_chengsi", "张承嗣", False, "1322.8.1"),
                ("sts_kfe_daughter1", "sts_name_zhang_lingyi", "令仪", True, "1319.4.1"),
            ]
        elif tag == "XIA":
            # 西安改秦：秦王岳恒，男，48 岁，70/60/85，妻王夫人，三子二女。
            ruler_name_key = "sts_name_yue_heng"
            ruler_name = "岳恒"
            adm, dip, mil = 70, 60, 85
            birth_date = "1289.4.1"
            wife_name_key = "sts_name_yue_wang_shi"
            wife_name = "王夫人"
            wife_birth = "1293.6.1"
            children = [
                ("sts_xia_son1", "sts_name_yue_chengzong", "岳承宗", False, "1315.3.12"),
                ("sts_xia_son2", "sts_name_yue_chengsi", "岳承嗣", False, "1319.7.8"),
                ("sts_xia_son3", "sts_name_yue_chengye", "岳承业", False, "1323.11.2"),
                ("sts_xia_daughter1", "sts_name_yue_qingwan", "岳清婉", True, "1326.2.18"),
                ("sts_xia_daughter2", "sts_name_yue_qingyan", "岳清妍", True, "1329.9.5"),
            ]
        elif tag == "JIN":
            # 济南改齐：齐王韩承烈，男，28 岁，70/50/80，妻赵夫人，一子。
            ruler_name_key = "sts_name_han_chenglie"
            ruler_name = "韩承烈"
            adm, dip, mil = 70, 50, 80
            birth_date = "1309.4.1"
            wife_name_key = "sts_name_han_zhao_shi"
            wife_name = "赵夫人"
            wife_birth = "1313.6.1"
            children = [
                ("sts_jin_son1", "sts_name_han_chengye", "韩承业", False, "1329.5.1"),
            ]
        elif tag == "DAD":
            # 登州改莱：莱王赵岵，男，55 岁，70/75/60，妻孙夫人，二子二女。
            ruler_name_key = "sts_name_zhao_hu"
            ruler_name = "赵岵"
            adm, dip, mil = 70, 75, 60
            birth_date = "1282.4.1"
            wife_name_key = "sts_name_zhao_sun_shi"
            wife_name = "孙夫人"
            wife_birth = "1286.6.1"
            children = [
                ("sts_dad_son1", "sts_name_zhao_chengzong", "赵承宗", False, "1310.3.8"),
                ("sts_dad_son2", "sts_name_zhao_chengye", "赵承业", False, "1314.7.15"),
                ("sts_dad_daughter1", "sts_name_zhao_qingyuan", "赵清媛", True, "1318.2.21"),
                ("sts_dad_daughter2", "sts_name_zhao_qingshu", "赵清姝", True, "1322.9.10"),
            ]
        elif tag == "CAJ":
            # 成都改蜀：蜀王赵寻，男，44 岁，65/60/55，妻李夫人，二子一女。
            ruler_name_key = "sts_name_zhao_xun"
            ruler_name = "赵寻"
            adm, dip, mil = 65, 60, 55
            birth_date = "1293.4.1"
            wife_name_key = "sts_name_zhao_li_shi"
            wife_name = "李夫人"
            wife_birth = "1297.6.1"
            children = [
                ("sts_caj_son1", "sts_name_zhao_chengzu", "赵承祖", False, "1316.3.5"),
                ("sts_caj_son2", "sts_name_zhao_chengji", "赵承基", False, "1320.8.12"),
                ("sts_caj_daughter1", "sts_name_zhao_qingyao", "赵清瑶", True, "1324.11.20"),
            ]
        elif tag == "LAK":
            # 潞安改晋：晋王赵崇岳，男，36 岁，70/60/70，妻王夫人，一子。
            ruler_name_key = "sts_name_zhao_chongyue"
            ruler_name = "赵崇岳"
            adm, dip, mil = 70, 60, 70
            birth_date = "1301.4.1"
            wife_name_key = "sts_name_zhao_wang_shi"
            wife_name = "王夫人"
            wife_birth = "1305.6.1"
            children = [
                ("sts_lak_son1", "sts_name_zhao_chengjian", "赵承坚", False, "1326.3.9"),
            ]
        elif tag == "YAF":
            # 应天改吴：吴王赵崇绪，男，59 岁，60/65/60，妻孙夫人，三子二女。
            ruler_name_key = "sts_name_zhao_chongxu"
            ruler_name = "赵崇绪"
            adm, dip, mil = 60, 65, 60
            birth_date = "1278.4.1"
            wife_name_key = "sts_name_zhao_sun_shi_wu"
            wife_name = "孙夫人"
            wife_birth = "1282.6.1"
            children = [
                ("sts_yaf_son1", "sts_name_zhao_chengqing", "赵承庆", False, "1308.3.6"),
                ("sts_yaf_son2", "sts_name_zhao_chengxi", "赵承禧", False, "1312.7.14"),
                ("sts_yaf_son3", "sts_name_zhao_chengzuo", "赵承祚", False, "1316.9.2"),
                ("sts_yaf_daughter1", "sts_name_zhao_qingyi", "赵清漪", True, "1320.5.18"),
                ("sts_yaf_daughter2", "sts_name_zhao_qinglan", "赵清澜", True, "1324.11.7"),
            ]
        elif tag == "XAF":
            # 襄阳改楚：楚王赵崇汉，男，40 岁，中上 65/65/65，妻王夫人，二子一女。
            ruler_name_key = "sts_name_zhao_chonghan"
            ruler_name = "赵崇汉"
            adm, dip, mil = 65, 65, 65
            birth_date = "1297.4.1"
            wife_name_key = "sts_name_zhao_wang_shi_chu"
            wife_name = "王夫人"
            wife_birth = "1301.6.1"
            children = [
                ("sts_xaf_son1", "sts_name_zhao_chengze", "赵承泽", False, "1318.3.11"),
                ("sts_xaf_son2", "sts_name_zhao_chengxi_chu", "赵承熙", False, "1322.7.19"),
                ("sts_xaf_daughter1", "sts_name_zhao_qingyue", "赵清月", True, "1326.9.4"),
            ]
        elif tag == "XAB":
            # 兴安改汉：汉王吴继勋，男，33 岁，64/70/80，妻李夫人，一子一女。
            ruler_name_key = "sts_name_wu_jixun"
            ruler_name = "吴继勋"
            adm, dip, mil = 64, 70, 80
            birth_date = "1304.4.1"
            wife_name_key = "sts_name_wu_li_shi"
            wife_name = "李夫人"
            wife_birth = "1308.6.1"
            children = [
                ("sts_xab_son1", "sts_name_wu_chengzong", "吴承宗", False, "1328.3.7"),
                ("sts_xab_daughter1", "sts_name_wu_qingwan", "吴清婉", True, "1332.9.12"),
            ]
        elif tag == "HAS":
            # 杭州改越：越王宗良佐，男，39 岁，75/70/65，妻王夫人，二子一女。
            ruler_name_key = "sts_name_zong_liangzuo"
            ruler_name = "宗良佐"
            adm, dip, mil = 75, 70, 65
            birth_date = "1298.4.1"
            wife_name_key = "sts_name_zong_wang_shi"
            wife_name = "王夫人"
            wife_birth = "1302.6.1"
            children = [
                ("sts_has_son1", "sts_name_zong_chengzu", "宗承祖", False, "1320.3.8"),
                ("sts_has_son2", "sts_name_zong_chengye", "宗承业", False, "1325.7.16"),
                ("sts_has_daughter1", "sts_name_zong_qingyi", "宗清漪", True, "1329.9.3"),
            ]
        else:
            ruler_name_key = key
            ruler_name = f"{SURNAMES[idx % len(SURNAMES)]}{GIVEN[(idx * 7) % len(GIVEN)]}"
            adm, dip, mil = 30 + idx % 25, 30 + idx % 23, 28 + idx % 27
            birth_date = f"{1290 + idx % 30}.{1 + idx % 12}.{1 + idx % 27}"
            wife_name = f"{SURNAMES[(idx + 5) % len(SURNAMES)]}氏"
            wife_birth = f"{1300 + idx % 10}.{1 + idx % 12}.{1 + idx % 27}"
            children = [(son_key, son_name_key,
                         f"{SURNAMES[idx % len(SURNAMES)]}{GIVEN[(idx * 3 + 11) % len(GIVEN)]}",
                         False, f"{1318 + idx % 8}.{1 + idx % 12}.{1 + idx % 27}")]

        out += [f"\t{ruler_key} = {{", f"\t\tfirst_name = {{ name = {ruler_name_key} }}",
                f"\t\tculture = {culture}", f"\t\treligion = {religion}",
                f"\t\tadm = {adm}", f"\t\tdip = {dip}", f"\t\tmil = {mil}", "\t\tfemale = no",
                f"\t\tbirth_date = {birth_date}", f"\t\tbirth = {birth}", f"\t\ttag = {tag}",
                f"\t\tspouse = {wife_key}", "\t}"]

        out += [f"\t{wife_key} = {{", f"\t\tfirst_name = {{ name = {wife_name_key} }}",
                f"\t\tculture = {culture}", f"\t\treligion = {religion}",
                "\t\tadm = 50", "\t\tdip = 50", "\t\tmil = 50", "\t\tfemale = yes",
                f"\t\tbirth_date = {wife_birth}", f"\t\tbirth = {birth}", f"\t\ttag = {tag}",
                f"\t\tspouse = {ruler_key}", "\t}"]

        for c_key, c_name_key, c_name, c_female, c_birth in children:
            out += [f"\t{c_key} = {{", f"\t\tfirst_name = {{ name = {c_name_key} }}",
                    f"\t\tculture = {culture}", f"\t\treligion = {religion}",
                    f"\t\tadm = {40 + idx % 20}", f"\t\tdip = {40 + idx % 18}",
                    f"\t\tmil = {38 + idx % 22}", f"\t\tfemale = {'yes' if c_female else 'no'}",
                    f"\t\tbirth_date = {c_birth}", f"\t\tbirth = {birth}", f"\t\ttag = {tag}",
                    f"\t\tfather = {ruler_key}", f"\t\tmother = {wife_key}", "\t}"]
            if c_key == "sts_kfe_daughter1":
                # 册后人物使用固定张氏宗族；本地化只写名，避免重复姓氏。
                out.insert(len(out) - 1, "\t\tdynasty = sts_zhang_dynasty")

        loc += [f' {tag}: "{name}"', f' {tag}_ADJ: "{name}"', f' {ruler_name_key}: "{ruler_name}"',
                f' {wife_name_key}: "{wife_name}"']
        for c_key, c_name_key, c_name, _, _ in children:
            # 册后人物的名字由独立 sts_liang_empress 本地化维护，避免重复键。
            if c_key != "sts_kfe_daughter1":
                loc.append(f' {c_name_key}: "{c_name}"')

    for tag, key, name, culture, religion, birth in [
        (SONG, "song", "zhao_bing", "zhongyuan_culture", "sanjiao", "1315.6.1"),
        (DALI, "cdl", "duan_xingzhi", "bai_culture", "mahayana", "1302.3.12"),
    ]:
        out += [f"\tsts_{key}_ruler = {{", f"\t\tfirst_name = {{ name = sts_name_{name} }}", f"\t\tculture = {culture}", f"\t\treligion = {religion}",
                "\t\tadm = 38", "\t\tdip = 44", "\t\tmil = 33", "\t\tfemale = no", f"\t\tbirth_date = {birth}",
                f"\t\tbirth = {'kaifeng' if tag == SONG else 'taihe_dali'}", f"\t\ttag = {tag}", "\t}"]
    out.append("}")
    Path(OUT_CHARS).write_text("\n".join(out) + "\n", encoding="utf-8")
    loc += [' CSO: "宋"', ' CDL: "大理"', ' sts_name_zhao_bing: "赵昺"', ' sts_name_duan_xingzhi: "段兴智"']
    text = read(OUT_LOC).split(" # ---------- 地图生成：国名与君主 ----------")[0].rstrip() + "\n"
    Path(OUT_LOC).write_text(text + "\n".join(loc) + "\n", encoding="utf-8-sig")


def gen_triggers(tags):
    text = "# 万邦之秋：与地图同步生成的北宋省势力名单。\nsts_is_chinese_warlord_tag = {\n\tOR = {\n"
    text += "".join(f"\t\ttag = {tag}\n" for tag in tags) + "\t}\n}\n"
    Path(MOD, "in_game/common/scripted_triggers/sts_warlord_tags.txt").write_text(text, encoding="utf-8-sig")


def gen_diplomacy(deleted):
    lines = []
    for line in read(Path(GAME, "main_menu/setup/1337/12_diplomacy.txt")).splitlines():
        if "dependency =" in line:
            tags = re.findall(r"\b(?:first|second)\s*=\s*(\w+)", uncomment(line))
            if set(tags) & deleted or re.search(r"first = CHI second = CDL\b", line) or re.search(r"first = CHI second = DAI\b", line):
                continue
            if re.search(r"first = CHI second = KOR\b", line):
                line = re.sub(r"subject_type = \w+", "subject_type = tributary", line)
        lines.append(line)
    Path(MOD, "main_menu/setup/1337/12_diplomacy.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
