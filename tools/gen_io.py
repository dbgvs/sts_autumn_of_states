# -*- coding: utf-8 -*-
"""
万邦之秋 / Autumn of Ten Thousand States
生成器：把宋与藩镇写进国际组织的成员表

原版 1337 剧本里：
  · 中华（middle_kingdom）的领袖是元，成员里没有宋与藩镇
  · 三教（sanjiao）国家本应加入儒/道宗派，但新生势力不在名单里

做法：整份复制 15_international_organizations.txt，改写两个块后同名覆盖。
（EU5 对重复键只认第一个，必须同名遮蔽）

用法：
    python tools/gen_io.py
"""
import os
import re

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
SRC = os.path.join(GAME, "main_menu/setup/1337/15_international_organizations.txt")
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(MOD, "main_menu", "setup", "1337", "15_international_organizations.txt")

OUR_TAGS = []  # 从本次地图的 sts_tags.json 读取，不保留三国测试版名单。

import json as _json
_TAGS = _json.load(open(os.path.join(os.path.dirname(__file__), "sts_tags.json"), encoding="utf-8"))
CHINESE = _TAGS["chinese"]
GUIZHOU = _TAGS.get("guizhou", [])
SONG = "CSO"
OUR_TAGS = [SONG] + CHINESE
# 丞相府成员 = 宋 + 汉地藩镇 + 贵州土司；天朝仍只含宋、汉地藩镇与大理。
CHANC_TAGS = [SONG] + _TAGS.get("chancellery", CHINESE)
KAIFENG = _TAGS["kaifeng"]
DELETED = set(_TAGS.get("deleted", []))


def block_spans(lines):
    """返回每个 add_international_organization 块的 (start, end)"""
    spans = []
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("add_international_organization"):
            depth = 0
            start = i
            for j in range(i, len(lines)):
                depth += lines[j].count("{") - lines[j].count("}")
                if depth == 0 and j > start:
                    spans.append((start, j))
                    i = j
                    break
        i += 1
    return spans


def block_type(lines, s, e):
    for k in range(s, min(e, s + 5)):
        m = re.match(r"\s*type = (\w+)", lines[k])
        if m:
            return m.group(1)
    return None


def rewrite_members(lines, s, e, add_tags, remove_tags=()):
    """把成员表重写成一行：保留原有（去掉 remove_tags）+ 追加 add_tags"""
    mstart = None
    for k in range(s, e):
        if re.match(r"\s*members = \{", lines[k]):
            mstart = k
            break
    if mstart is None:
        return False

    depth = 0
    mend = None
    for k in range(mstart, e + 1):
        depth += lines[k].count("{") - lines[k].count("}")
        if depth == 0:
            mend = k
            break
    if mend is None:
        return False

    body = " ".join(l.split("#", 1)[0] for l in lines[mstart:mend + 1])
    body = body.split("{", 1)[1].rsplit("}", 1)[0]
    tokens = [t for t in body.split() if t and t not in remove_tags]

    seen = set(tokens)
    for t in add_tags:
        if t not in seen:
            tokens.append(t)
            seen.add(t)

    indent = lines[mstart][: len(lines[mstart]) - len(lines[mstart].lstrip())]
    merged = []
    for i in range(0, len(tokens), 12):
        merged.append(indent + "\t" + " ".join(tokens[i:i + 12]))
    lines[mstart:mend + 1] = [indent + "members = {"] + merged + [indent + "}"]

    # 如果注释被吃掉了，补一行说明
    return True


def yunnan_tags():
    """首都落在云南（大理/云南两区）的国家 —— 它们是元旧属，现改附大理，不该算天朝成员"""
    defs = os.path.join(GAME, "in_game/map_data/definitions.txt")
    yn, cur = set(), None
    for line in open(defs, encoding="utf-8-sig"):
        code = line.split("#", 1)[0]
        st = code.strip()
        if st.startswith("dali_area = {") or st.startswith("yunnan_area = {"):
            cur = True
        elif cur and st.startswith("}") and code.startswith("\t\t\t}"):
            cur = None
        elif cur and "_province = {" in st:
            yn.update(st.split("{", 1)[1].replace("}", "").split())
    out = set()
    path = os.path.join(MOD, "main_menu/setup/1337/10_countries.txt")
    tag = None
    for line in open(path, encoding="utf-8"):
        m = re.match(r"^\t([A-Z][A-Z0-9]{2}) = \{", line)
        if m:
            tag = m.group(1)
        m2 = re.match(r"^\t\tcapital = (\w+)", line)
        if m2 and tag and m2.group(1) in yn:
            out.add(tag)
    out.discard("CDL")
    return out


def main():
    lines = open(SRC, encoding="utf-8-sig").read().split("\n")
    spans = block_spans(lines)
    print(f"共 {len(spans)} 个国际组织块")

    hit_mk = hit_conf = 0
    # 逆序处理，避免改动行号影响前面的块
    for s, e in reversed(spans):
        t = block_type(lines, s, e)
        if t == "middle_kingdom":
            # 天朝领袖永久空置：注释掉原版/原生成的 leader 行
            for k in range(s, e):
                if re.match(r"\s*leader = ", lines[k]):
                    indent = lines[k][: len(lines[k]) - len(lines[k].lstrip())]
                    lines[k] = f"{indent}# 天朝领袖空置（宋不再是天朝领袖）"
            # 天朝含所有丞相府藩镇（汉地 + 贵州 + 山西南）+ 大理；宋只留相府天子。
            chunk = "\n".join(lines[s:e + 1])
            member_body = re.search(r"members\s*=\s*\{([^{}]*)\}", chunk, re.S).group(1)
            drop = tuple(re.findall(r"\b[A-Z][A-Z0-9]{1,2}\b", member_body))
            if rewrite_members(lines, s, e, _TAGS.get("chancellery", CHINESE) + ["CDL"], remove_tags=drop):
                hit_mk += 1
        elif t == "sect":
            chunk = "\n".join(lines[s:e + 1])
            if "confucianism_policy" in chunk:
                if rewrite_members(lines, s, e, OUR_TAGS, remove_tags=DELETED):
                    hit_conf += 1

    # ---- 追加丞相府实例 ----
    spans2 = block_spans(lines)
    mk_end = None
    for s2, e2 in spans2:
        if block_type(lines, s2, e2) == "middle_kingdom":
            mk_end = e2
            break
    if mk_end is None:
        raise SystemExit("找不到 middle_kingdom 块，无法插入丞相府")
    block = [
        "",
        "\tadd_international_organization = {",
        "\t\ttype = sts_chancellery",
        "\t\tcreation_date = 1337.4.1",
        # 成员必须写在 leader 前面，否则报 leader isn't a member
        "\t\tmembers = { " + " ".join(CHANC_TAGS) + " }",
        f"\t\tleader = {KAIFENG}",
        "\t}",
    ]
    lines[mk_end + 1:mk_end + 1] = block

    text = "\n".join(lines)
    text = text.replace("\t\tcelestial_governor = {\n\t\t\tKOR\n\t\t}", "\t\tcelestial_governor = {\n\t\t}")
    # 并国后同步清理各宗派/其他组织的成员和特殊地位，不让旧实体日一退会。
    text = re.sub(r"\b[A-Z][A-Z0-9]{1,2}\b", lambda m: "" if m.group(0) in DELETED else m.group(0), text)
    lines = text.split("\n")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"改写 middle_kingdom: {hit_mk} 个（领袖空置）")
    print(f"改写 儒学宗派: {hit_conf} 个")
    print("输出", OUT, len(lines), "行")
    print("BOM:", open(OUT, "rb").read(3) == b"\xef\xbb\xbf")


if __name__ == "__main__":
    main()
