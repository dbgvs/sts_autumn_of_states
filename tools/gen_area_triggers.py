# -*- coding: utf-8 -*-
"""
万邦之秋 / Autumn of Ten Thousand States
生成器：从地图数据生成「完整控制任意一个地区」的脚本触发器

山东、河北、燕南只是例子 —— 实际应该对中华范围内的每一个 area
都做一次判定，只要完整控制其中任意一个就算达标。

数据来源：in_game/map_data/definitions.txt
    continent { region { area { province { location... } } } }

产出：
    in_game/common/scripted_triggers/sts_areas.txt

用法（地图变动后重跑）：
    python tools/gen_area_triggers.py
"""
import os
import re

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
DEFS = os.path.join(GAME, "in_game/map_data/definitions.txt")
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(MOD, "in_game/common/scripted_triggers/sts_areas.txt")

# 只看中华范围内的 region
TARGET_REGIONS = [
    "north_china_region",
    "south_china_region",
    "east_china_region",
    "west_china_region",
]


def parse_areas():
    """按大括号层级取出 region -> [area]"""
    raw = open(DEFS, encoding="utf-8-sig").read()
    raw = "\n".join(l.split("#", 1)[0] for l in raw.split("\n"))

    region = None
    depth_region = None
    depth = 0
    areas = {}

    for line in raw.split("\n"):
        opened = re.match(r"\s*(\w+) = \{", line)
        if opened:
            key = opened.group(1)
            depth += 1
            if key in TARGET_REGIONS:
                region = key
                depth_region = depth
                areas.setdefault(region, [])
            elif region and key.endswith("_area") and depth_correct(depth, depth_region):
                areas[region].append(key)
        depth += line.count("{") - (1 if opened else 0)
        depth -= line.count("}")
        if region and depth < depth_region:
            region = None
            depth_region = None
    return areas


def depth_correct(depth, depth_region):
    return depth_region is not None and depth == depth_region + 1


def simple_parse():
    """按行解析，用大括号深度确定 region / area 的层级"""
    raw = open(DEFS, encoding="utf-8-sig").read()
    clean = "\n".join(l.split("#", 1)[0] for l in raw.split("\n"))

    areas = {}
    depth = 0
    cur_region = None
    reg_depth = 0

    for line in clean.split("\n"):
        m = re.match(r"\s*(\w+) = \{", line)
        opens = line.count("{")
        closes = line.count("}")

        if m:
            key = m.group(1)
            new_depth = depth + 1
            if key in TARGET_REGIONS:
                cur_region = key
                reg_depth = new_depth
                areas.setdefault(key, [])
            elif cur_region and key.endswith("_area") and new_depth == reg_depth + 1:
                areas[cur_region].append(key)

        depth += opens - closes
        if cur_region and depth < reg_depth:
            cur_region = None

    return areas


def main():
    areas = simple_parse()
    all_areas = []
    for r in TARGET_REGIONS:
        lst = areas.get(r, [])
        print(f"{r}: {len(lst)} 个地区")
        all_areas.extend(lst)

    all_areas = sorted(set(all_areas))
    print(f"合计 {len(all_areas)} 个地区")

    lines = [
        "# 由 tools/gen_area_triggers.py 生成，请勿手改",
        "# 完整控制中华范围内任意一个地区（含附属国）即算达成",
        "",
        "sts_controls_any_whole_area = {",
        "\tcustom_tooltip = {",
        "\t\ttext = sts_controls_any_whole_area_tt",
        "\t\tOR = {",
    ]
    for a in all_areas:
        lines.append(f"\t\tsts_controls_entire_area = {{ AREA = area:{a} }}")
    lines.append("\t\t}")
    lines.append("\t}")
    lines.append("}")
    lines.append("")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig") as f:
        f.write("\n".join(lines))
    print("输出", OUT)


if __name__ == "__main__":
    main()
