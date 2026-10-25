# -*- coding: utf-8 -*-
"""生成宋廷静态建筑落座文件。

MODE = "a"：新增 07a_sts_buildings.txt，仅含 building_manager 块。
          原版 13_religion.txt 证明 setup 顶层块可跨文件合并。
MODE = "b"：整份复制原版 07_cities_and_buildings.txt 并插入宋廷，
          作为跨文件合并不生效时的回退。
"""
import os
from pathlib import Path

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT_A = os.path.join(MOD, "main_menu/setup/1337/07a_sts_buildings.txt")
VANILLA_07 = os.path.join(GAME, "main_menu/setup/1337/07_cities_and_buildings.txt")
OUT_B = os.path.join(MOD, "main_menu/setup/1337/07_cities_and_buildings.txt")

MODE = "a"
LINES = [
    "\tsts_song_court = { tag = CSO level = 1 location = kaifeng }",
    "\tsts_chancellery_palace = { tag = KFE level = 1 location = kaifeng }",
    "\tsts_imperial_guard_camp = { tag = KFE level = 1 location = kaifeng }",
]
LINE = "\n".join(LINES)


def write_no_bom(path, text):
    assert not text.startswith("\ufeff")
    Path(path).write_text(text, encoding="utf-8", newline="\n")
    raw = Path(path).read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf"), "setup 文件不能带 BOM"
    assert raw.count(b"{") == raw.count(b"}"), "括号不平衡：" + path


def build_a():
    text = "building_manager = {\n" + LINE + "\n}\n"
    write_no_bom(OUT_A, text)
    # 回退文件若存在，删除，避免同时加载两份宋廷
    if os.path.exists(OUT_B):
        os.remove(OUT_B)
    print("输出", OUT_A)
    return OUT_A


def build_b():
    text = Path(VANILLA_07).read_text(encoding="utf-8-sig")
    # 找 building_manager 块，插入到它的最后一个右括号前
    start = text.find("building_manager = {")
    if start < 0:
        raise SystemExit("原版 07 找不到 building_manager")
    depth = 0
    end = None
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end is None:
        raise SystemExit("building_manager 块未闭合")
    text = text[:end] + LINE + "\n" + text[end:]
    write_no_bom(OUT_B, text)
    if os.path.exists(OUT_A):
        os.remove(OUT_A)
    print("输出", OUT_B)
    return OUT_B


def main():
    return build_a() if MODE == "a" else build_b()


if __name__ == "__main__":
    main()
