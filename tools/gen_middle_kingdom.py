# -*- coding: utf-8 -*-
"""
万邦之秋 / Autumn of Ten Thousand States
生成器：改天朝（middle_kingdom）的三处设置

原版天朝：
  · 领袖是从领袖国君主里取的角色（leader_type = character，头衔「皇帝」）
  · 没有 has_buildings（不能挂靠建筑）

本模组要加的三样：
  1. has_buildings = yes        —— 让天朝可以挂靠建筑
  2. disband_if_no_leader = no  —— 一时找不到领袖也不解散（照幕府）
  3. special_statuses_implemented 补上「天子」「藩镇」
     —— 不声明的话，效果里的 add_special_status 会被引擎直接忽略

领袖仍保持原版的「角色」类型：宋是天子，天朝领袖就该是宋的皇帝。

产出：
    in_game/common/international_organizations/middle_kingdom.txt

用法：
    python tools/gen_middle_kingdom.py
"""
import os

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
SRC = os.path.join(GAME, "in_game/common/international_organizations/middle_kingdom.txt")
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(MOD, "in_game/common/international_organizations/middle_kingdom.txt")

ANCHOR = "\thas_leader_country = yes\n"
INJECT = "\thas_leader_country = yes\n\thas_buildings = yes\n\tdisband_if_no_leader = no\n"

STATUS_OLD = "\tspecial_statuses_implemented = {\n\t\tcelestial_governor\n\t}"
STATUS_NEW = (
    "\tspecial_statuses_implemented = {\n"
    "\t\tcelestial_governor\n"
    "\t\tsts_son_of_heaven\n"
    "\t\tsts_warlord_state\n"
    "\t}"
)


def main():
    lines = open(SRC, encoding="utf-8-sig").read().split("\n")
    if not any(l.strip() == "has_leader_country = yes" for l in lines):
        raise SystemExit("middle_kingdom.txt 结构变了，找不到 has_leader_country")

    text = "\n".join(lines)
    if "has_buildings = yes" not in text:
        text = text.replace(ANCHOR, INJECT, 1)

    if "sts_son_of_heaven" not in text:
        if STATUS_OLD not in text:
            raise SystemExit("找不到 special_statuses_implemented 块")
        text = text.replace(STATUS_OLD, STATUS_NEW, 1)

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8-sig") as f:
        f.write(text)
    print("生成", OUT, len(text.split("\n")), "行")
    for k in ("has_buildings", "disband_if_no_leader", "sts_son_of_heaven", "leader_type"):
        print(f"  {k}:", text.count(k))


if __name__ == "__main__":
    main()
