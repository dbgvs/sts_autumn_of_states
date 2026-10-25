# -*- coding: utf-8 -*-
"""
万邦之秋 / Autumn of Ten Thousand States
生成器：整份复制原版 in_game/setup/countries/east_asia.txt，只删掉 CSO（宋）
块里的 is_historic = yes。

为什么必须整份同名覆盖：
    EU5 遇到重复键只认第一个。要让 mod 里的 CSO 定义生效，就不能只写一个
    CSO 块，必须同名覆盖整份文件。is_historic = yes 会让宋被当成"危机事件
    释放"的历史国家，宋在本 mod 里是建筑国家，所以要去掉这一行。

产出：
    in_game/setup/countries/east_asia.txt（同名覆盖）

用法（每次游戏更新后重跑一次）：
    python tools/gen_country_defs.py
"""
import os

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
SRC = os.path.join(GAME, "in_game/setup/countries/east_asia.txt")
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(MOD, "in_game/setup/countries/east_asia.txt")

TAG = "CSO"
DROP = "is_historic = yes"


def find_block(lines, tag):
    """找顶格的 `tag = {` 块，返回 (起始行, 结束行)，花括号配平；找不到返回 None"""
    start = None
    for i, line in enumerate(lines):
        if line.startswith(tag + " = {"):
            start = i
            break
    if start is None:
        return None
    depth = 0
    for i in range(start, len(lines)):
        code = lines[i].split("#", 1)[0]
        depth += code.count("{") - code.count("}")
        if depth == 0:
            return start, i
    return None


def main():
    raw = open(SRC, "rb").read()
    has_bom = raw.startswith(b"\xef\xbb\xbf")
    enc = "utf-8-sig" if has_bom else "utf-8"

    # newline="" —— 换行符原样保留（\r\n 或 \n 都不动）
    with open(SRC, "r", encoding=enc, newline="") as f:
        text = f.read()
    lines = text.splitlines(keepends=True)

    span = find_block(lines, TAG)
    if span is None:
        raise SystemExit(f"找不到顶格的 {TAG} = {{ 块：{SRC} 结构与预期不符")
    s, e = span

    hit = None
    for i in range(s, e + 1):
        if lines[i].strip().startswith(DROP):
            hit = i
            break
    if hit is None:
        raise SystemExit(f"{TAG} 块（第 {s + 1}-{e + 1} 行）里没有 {DROP}，结构与预期不符")

    removed = lines[hit]
    del lines[hit]

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding=enc, newline="") as f:
        f.write("".join(lines))

    print("原版文件带 BOM:", has_bom)
    print(f"删除第 {hit + 1} 行原文:", repr(removed))
    print("输出:", OUT)
    print("输出行数:", len(lines))


if __name__ == "__main__":
    main()
