# -*- coding: utf-8 -*-
"""从 prince_data.py 生成八国 advance / 法律 / 本地化。"""
import re
from pathlib import Path

from prince_data import PRINCES

GAME = Path(r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game")
MOD = Path(__file__).resolve().parent.parent
MOD_DB = GAME / "main_menu/common/modifier_type_definitions/00_modifier_types.txt"
OUT_ADV = MOD / "in_game/common/advances/sts_prince_advances.txt"
OUT_LAW = MOD / "in_game/common/laws/sts_prince_laws.txt"
OUT_LOC = MOD / "main_menu/localization/simp_chinese/sts_prince_l_simp_chinese.yml"


def fmt(value):
    if isinstance(value, int):
        return str(value)
    text = f"{value:.4f}".rstrip("0").rstrip(".")
    return text if text not in ("", "-0") else "0"


def modifier_keys():
    text = MOD_DB.read_text(encoding="utf-8-sig")
    return set(re.findall(r"^\s*([a-z_]+)\s*=\s*\{", text, re.M))


def check_mods(owner, mods, valid):
    for key, value in mods:
        if key not in valid:
            raise ValueError(f"{owner}: 未知修正键 {key}")


def render_advances():
    valid = modifier_keys()
    out = ["# 万邦之秋：八国藩王国家增益（由 tools/gen_prince_content.py 生成）", ""]
    for tag, data in PRINCES.items():
        a = data["advance"]
        check_mods(f"{tag}/advance", a["mods"], valid)
        out += [
            f"{a['key']} = {{",
            "\tage = age_1_traditions",
            f"\ticon = {a['icon']}",
            "\tcontent_priority = 1000",
            f"\tpotential = {{ has_or_had_tag = {tag} }}",
        ]
        for key, value in a["mods"]:
            out.append(f"\t{key} = {fmt(value)}")
        out += ["}", ""]
    OUT_ADV.write_text("\n".join(out), encoding="utf-8-sig")


def render_laws():
    valid = modifier_keys()
    out = ["# 万邦之秋：八国藩王法律（由 tools/gen_prince_content.py 生成）", ""]
    for tag, data in PRINCES.items():
        law = data["law"]
        if len(law["policies"]) != 3:
            raise ValueError(f"{tag}: 法律必须 3 政策")
        if sum(1 for p in law["policies"] if p["key"] == law["default"]) != 1:
            raise ValueError(f"{tag}: 默认政策缺失或重复")
        out += [
            f"{law['key']} = {{",
            "\tunique = yes",
            f"\tlaw_category = {law['category']}",
            "\tlaw_gov_group = monarchy",
            f"\tlaw_country_group = {tag}",
            f"\tpotential = {{ has_or_had_tag = {tag} }}",
            "\tallow = { always = yes }",
            "",
        ]
        for policy in law["policies"]:
            check_mods(f"{tag}/{policy['key']}", policy["mods"], valid)
            out += [f"\t{policy['key']} = {{", "\t\tcountry_modifier = {"]
            for key, value in policy["mods"]:
                out.append(f"\t\t\t{key} = {fmt(value)}")
            out.append("\t\t}")
            if policy.get("estates"):
                out.append("\t\testate_preferences = { " + " ".join(policy["estates"]) + " }")
            bias = 20 if policy["key"] == law["default"] else -10
            out += [
                "\t\twants_this_policy_bias = {",
                "\t\t\tadd = {",
                '\t\t\t\tdesc = "DIPLOREASON_BASE"',
                f"\t\t\t\tvalue = {bias}",
                "\t\t\t}",
                "\t\t}",
                "\t\tyears = 2",
                "\t}",
            ]
        out += ["}", ""]
    OUT_LAW.write_text("\n".join(out), encoding="utf-8-sig")


def render_loc():
    out = ["l_simp_chinese:"]
    for _, data in PRINCES.items():
        a = data["advance"]
        out += [f" {a['key']}: \"{a['name']}\"", f" {a['key']}_desc: \"{a['desc']}\""]
        law = data["law"]
        out += [f" {law['key']}: \"{law['name']}\"", f" {law['key']}_desc: \"{law['desc']}\""]
        for policy in law["policies"]:
            out += [f" {policy['key']}: \"{policy['name']}\"", f" {policy['key']}_desc: \"{policy['desc']}\""]
    OUT_LOC.write_text("\n".join(out) + "\n", encoding="utf-8-sig")


def main():
    OUT_ADV.parent.mkdir(parents=True, exist_ok=True)
    render_advances()
    render_laws()
    render_loc()
    print(f"advance {len(PRINCES)} 条；法律 {len(PRINCES)} 部；政策 {sum(len(v['law']['policies']) for v in PRINCES.values())} 条")
    print(OUT_ADV)
    print(OUT_LAW)
    print(OUT_LOC)


if __name__ == "__main__":
    main()
