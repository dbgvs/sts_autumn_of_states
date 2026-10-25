# -*- coding: utf-8 -*-
"""
万邦之秋 / Autumn of Ten Thousand States
生成器：从原版复制并注入中华文化与头衔规则

为什么必须"同名覆盖"：
    EU5 对重复键只认第一个加载的定义，原版先加载，模组后加载会被丢弃。
    所以覆盖某个键，必须用与原版**同名**的文件把整个文件遮蔽掉。

产出：
    in_game/common/customizable_localization/country_name_construction.txt
    in_game/common/customizable_localization/00_customizable_localization.txt

用法（游戏更新后重跑）：
    python tools/gen_custom_loc.py
"""
import os

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
CL = os.path.join(GAME, "in_game/common/customizable_localization")
OUT = os.path.join(MOD, "in_game/common/customizable_localization")

# ---------------- 1. 国名构造 ----------------
CN_NAME_BRANCH = """	# ===== 万邦之秋：中华文化圈不使用欧洲爵位后缀 =====
	text = {
		localization_key = sts_cn_name_empire
		trigger = {
			culture = { has_culture_group = culture_group:chinese_group }
			country_rank = country_rank:rank_empire
		}
	}
	text = {
		localization_key = sts_cn_name_plain
		trigger = {
			culture = { has_culture_group = culture_group:chinese_group }
		}
	}
"""

# ---------------- 2. 统治者头衔 ----------------
CN_RULER_BRANCH = """	# ===== 万邦之秋：中华文化圈的地方藩帅（文本/提示用） =====
	text = {
		localization_key = sts_cn_ruler_chancellor
		trigger = { has_ruler = yes tag = KFE }
	}
	text = {
		localization_key = sts_cn_ruler_emperor
		trigger = { has_ruler = yes tag = CSO }
	}
	text = {
		localization_key = sts_cn_ruler_xuanfushi
		trigger = {
			has_ruler = yes
			capital ?= { area = area:guizhou_area }
		}
	}
	text = {
		localization_key = sts_cn_ruler_duchy
		trigger = {
			has_ruler = yes
			culture = { has_culture_group = culture_group:chinese_group }
			country_rank = country_rank:rank_duchy
		}
	}
	text = {
		localization_key = sts_cn_ruler_county
		trigger = {
			has_ruler = yes
			culture = { has_culture_group = culture_group:chinese_group }
			country_rank = country_rank:rank_county
		}
	}
	text = {
		localization_key = sts_cn_ruler_kingdom
		trigger = {
			has_ruler = yes
			OR = {
				culture = { has_culture_group = culture_group:chinese_group }
				tag = LAK
			}
			country_rank = country_rank:rank_kingdom
		}
	}
"""

# ---------------- 3. 宋代官制头衔（country_flavor 才是角色面板的来源） ----------------
CN_RANK_BRANCH = """	# ===== 万邦之秋：宋代官制头衔 =====
	# 角色面板走 country_flavor -> country_flavor_ruler_male，
	# 不是 GetRulerOrRegentTitle；必须放在原版 rank_duchy / rank_kingdom 之前。
	text = {
		localization_key = rank_duchy_sts_chancellor
		trigger = { tag = KFE }
	}
	text = {
		localization_key = rank_duchy_sts_son_of_heaven
		trigger = { tag = CSO }
	}
	# 贵州土司：宣抚使
	text = {
		localization_key = rank_duchy_sts_xuanfushi
		trigger = {
			country_rank_is_duchy = yes
			capital ?= { area = area:guizhou_area }
		}
	}
	# 藩王：亲王
	text = {
		localization_key = rank_kingdom_sts_fanwang
		trigger = {
			country_rank_is_kingdom = yes
			OR = {
				culture = { has_culture_group = culture_group:chinese_group }
				has_reform = government_reform:three_departments_system
				tag = LAK
			}
		}
	}
	# 普通藩镇：节度使
	text = {
		localization_key = rank_duchy_sts_jiedushi
		trigger = {
			country_rank_is_duchy = yes
			OR = {
				culture = { has_culture_group = culture_group:chinese_group }
				has_reform = government_reform:three_departments_system
			}
		}
	}
	# 县级藩镇：刺史
	text = {
		localization_key = rank_county_sts_cishi
		trigger = {
			country_rank_is_county = yes
			OR = {
				culture = { has_culture_group = culture_group:chinese_group }
				has_reform = government_reform:three_departments_system
			}
		}
	}
"""


def gen_country_names():
    src = os.path.join(CL, "country_name_construction.txt")
    text = open(src, encoding="utf-8-sig").read()
    head = "country_name_construction = {\n\ttype = country\n"
    if not text.startswith(head.strip()):
        raise SystemExit("country_name_construction 头部结构变了，需要更新生成器")
    body = text[len(head):]
    out = "country_name_construction = {\n\ttype = country\n\n" + CN_NAME_BRANCH + body
    p = os.path.join(OUT, "country_name_construction.txt")
    open(p, "w", encoding="utf-8-sig").write(out)
    print("生成", p, len(out.split("\n")), "行")


def gen_ruler_titles():
    src = os.path.join(CL, "00_customizable_localization.txt")
    lines = open(src, encoding="utf-8-sig").read().split("\n")

    # 两个键都要注入：面板用的可能是 GetRulerOrRegentTitle，而不是 GetRulerOrHeirTitle
    for key in ["GetRulerOrHeirTitle = {", "GetRulerOrRegentTitle = {"]:
        start = next((i for i, l in enumerate(lines) if l.startswith(key)), None)
        if start is None:
            raise SystemExit(f"00_customizable_localization 里找不到 {key}")
        t = next((i for i in range(start, start + 6) if lines[i].strip() == "type = country"), None)
        if t is None:
            raise SystemExit(f"{key} 结构变了")
        lines[t + 1:t + 1] = CN_RULER_BRANCH.split("\n")
    out = "\n".join(lines)
    p = os.path.join(OUT, "00_customizable_localization.txt")
    open(p, "w", encoding="utf-8-sig").write(out)
    print("生成", p, len(lines), "行")


def gen_country_ranks():
    src = os.path.join(CL, "country_ranks.txt")
    lines = open(src, encoding="utf-8-sig").read().split("\n")

    start = next((i for i, l in enumerate(lines) if l.startswith("country_flavor = {")), None)
    if start is None:
        raise SystemExit("country_ranks 里找不到 country_flavor")
    t = next((i for i in range(start, start + 6) if lines[i].strip() == "type = country"), None)
    if t is None:
        raise SystemExit("country_flavor 结构变了")
    lines[t + 1:t + 1] = CN_RANK_BRANCH.split("\n")

    out = "\n".join(lines)
    p = os.path.join(OUT, "country_ranks.txt")
    open(p, "w", encoding="utf-8-sig").write(out)
    print("生成", p, len(lines), "行")


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    gen_country_names()
    gen_ruler_titles()
    gen_country_ranks()
