# -*- coding: utf-8 -*-
"""
万邦之秋 / Autumn of Ten Thousand States
预检脚本：在开游戏之前，把明显会静默失败的问题挑出来。

检查项：
  1. 花括号 / 引号平衡
  2. setup 文件 BOM（必须无）、脚本文件 BOM（必须有）
  3. location:xxx 是否真实存在
  4. tag / c:XXX 是否有国家定义
  5. 脚本里用到的 key = { 是否在原版语料里出现过（抓拼写错误）
  6. 我们引用的本地化 key 是否都有文本

用法：
    python tools/preflight.py
"""
import os
import re
import sys

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
MOD = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

OWN_TAGS = set()  # 必须存在实际国家定义，不能用白名单伪造存在。
OWN_LOC_KEYS = set()

# 本地化文件里我们自己定义的 key（含独立界面文件，避免只查一个文件）
LOC_DIR = os.path.join(MOD, "main_menu/localization/simp_chinese")
LOC_FILES = [os.path.join(LOC_DIR, f) for f in sorted(os.listdir(LOC_DIR)) if f.endswith(".yml")]


def read(p):
    return open(p, encoding="utf-8-sig").read()


def walk_txt(root):
    for dp, _, fs in os.walk(root):
        for f in fs:
            if f.endswith(".txt"):
                yield os.path.join(dp, f)


def vanilla_corpus():
    """原版所有脚本里出现过的 token 集合 + effect/trigger 文档键"""
    words = set()
    for p in walk_txt(os.path.join(GAME, "in_game")):
        words.update(re.findall(r"[a-z][a-z0-9_]+", read(p)))
    for p in walk_txt(os.path.join(GAME, "main_menu")):
        words.update(re.findall(r"[a-z][a-z0-9_]+", read(p)))
    return words


def vanilla_locations():
    """地点模板为权威来源，避免把省块的属性误当地点。"""
    text = read(os.path.join(GAME, "in_game/map_data/location_templates.txt"))
    return set(re.findall(r"^(\w+)\s*=\s*\{", text, re.M))


def vanilla_tags():
    # 同名模组文件遮蔽原版；国家名本地化和 setup 块都不能代替国家定义。
    paths = {}
    for root in (GAME, MOD):
        folder = os.path.join(root, "in_game/setup/countries")
        for p in walk_txt(folder):
            paths[os.path.relpath(p, folder)] = p
    tags = set()
    for p in paths.values():
        tags.update(re.findall(r"^([A-Z][A-Z0-9]{1,2})\s*=\s*\{", read(p), re.M))
    return tags


def script_blocks(text):
    """轻量括号树：只处理本轮回归所需的 key/operator/value，忽略注释和字符串内容。"""
    tokens = re.findall(r'"(?:\\.|[^"\\])*"|#[^\n]*|[{}]|\?=|!=|>=|<=|=|>|<|[^\s{}=!?<>]+', text)
    tokens = [t for t in tokens if not t.startswith("#")]

    def parse(pos):
        nodes = []
        while pos < len(tokens) and tokens[pos] != "}":
            # rgb { ... }、列表等匿名块也需完整消费，不能误把其右括号当父块结束。
            if tokens[pos] == "{":
                value, pos = parse(pos + 1)
                nodes.append(("__anonymous_block__", "", value))
                continue
            key = tokens[pos]
            if pos + 2 < len(tokens) and tokens[pos + 1] in ("=", "?=", "!=", ">=", "<=", ">", "<"):
                op, value = tokens[pos + 1:pos + 3]
                pos += 3
                if value == "{":
                    value, pos = parse(pos)
                nodes.append((key, op, value))
            else:
                nodes.append((key, "", ""))
                pos += 1
        return nodes, pos + (pos < len(tokens) and tokens[pos] == "}")

    return parse(0)[0]


def block_child(nodes, key):
    return next((value for name, _, value in nodes if name == key and isinstance(value, list)), [])


def walk_blocks(nodes, parents=()):
    for key, op, value in nodes:
        yield key, op, value, parents
        if isinstance(value, list):
            yield from walk_blocks(value, parents + (key,))


def script_regressions(sources):
    """本模组回归约束，不冒充完整的引擎语义验证器；可用内存变异测试。"""
    errors = []
    trees = {name: script_blocks(text) for name, text in sources.items() if name != "gui"}
    actions, effects, hooks, events = (trees[name] for name in ("actions", "effects", "hooks", "events"))

    for key, _, value, parents in walk_blocks(actions):
        if key in ("ai_prerequisite", "ai_prerequisite_after_potential") and isinstance(value, list):
            if any(re.search(r"\bscope:\w+", name) or
                   (isinstance(item, str) and re.search(r"\bscope:\w+", item))
                   for name, _, item, _ in walk_blocks(value)):
                errors.append(f"[AI前置] {parents[0]} 的 {key} 提前引用命名作用域")
    for source in ("actions", "effects", "hooks"):
        for key, _, value, _ in walk_blocks(trees[source]):
            if key == "has_special_status_in_international_organization" and isinstance(value, list):
                if not any(name == "international_organization" for name, _, _ in value):
                    errors.append(f"[组织身份] {source} 的特殊身份检查缺少 international_organization")

    for hook, handler in (("on_war_declared", "sts_on_chancellery_member_attacked"),
                          ("on_rejected_call_to_arms", "sts_on_chancellery_defense_refused")):
        body = block_child(hooks, hook)
        if block_child(body, "effect") or not any(name == handler for name, _, _ in block_child(body, "on_actions")):
            errors.append(f"[钩子追加] {hook} 必须追加 {handler}，不得替换原版 effect")
    attacked = block_child(hooks, "sts_on_chancellery_member_attacked")
    for key, _, value, parents in walk_blocks(attacked):
        if key == "NOT" and parents and parents[-1] == "leader_country":
            errors.append("[相府援助] leader_country 效果内有裸 NOT，必须包入 if.limit")
    hook_flat = list(walk_blocks(attacked))
    if not any(k == "international_organization_has_policy" and v == "policy:sts_fanwang_levy_policy"
               for k, _, v, _ in hook_flat):
        errors.append("[相府援助] 藩王援助缺少组织联防法律条件")
    if not any(k == "can_join_as_defender" for k, _, _, _ in hook_flat):
        errors.append("[相府援助] 缺少加入防御方资格筛选")

    for event in ("sts_defense_levy.1", "sts_defense_levy.2"):
        options = [v for k, _, v in block_child(events, event) if k == "option" and isinstance(v, list)]
        if len(options) != 2:
            errors.append(f"[援助权重] {event} 必须保留两个选项")
        for option in options:
            chance = block_child(option, "ai_chance")
            opinions = [(v, p) for k, _, v, p in walk_blocks(chance) if k == "opinion" and isinstance(v, list)]
            if len(opinions) != 1 or ("target", "=", "scope:sts_attacked_member") not in opinions[0][0] or len(opinions[0][1]) != 1:
                errors.append(f"[援助好感] {event} 必须直接检查响应国对受援国的好感")
            if ("base", "=", "50") not in chance:
                errors.append(f"[援助权重] {event} 基础权重不再是 50")
        if options and not any(k == "can_join_as_defender" for k, _, _, _ in walk_blocks(block_child(options[0], "trigger"))):
            errors.append(f"[相府援助] {event} 缺少选项参战资格复核")

    init = block_child(effects, "sts_game_init")
    if any(k == "female" for k, _, _, _ in walk_blocks(init)):
        errors.append("[宗族] 初始化条件不得使用 female，角色触发器应为 is_female")
    hate = block_child(effects, "sts_spread_emperor_hate")
    if ("save_scope_as", "=", "sts_emperor_host") not in hate:
        errors.append("[年度敌意] 缺少挟天子国家命名作用域")
    hate_flat = list(walk_blocks(hate))
    if any(k == "root" or v == "root" for k, _, v, _ in hate_flat):
        errors.append("[年度敌意] 不得把局势 root 当作挟天子国")
    if sum(k == "target" and v == "scope:sts_emperor_host" for k, _, v, _ in hate_flat) != 10:
        errors.append("[年度敌意] 十级敌意目标必须全部指向挟天子国家")

    header = block_child(effects, "sts_update_warring_header")
    header_flat = list(walk_blocks(header))
    for variable in ("sts_chancellor_character", "sts_strongest_fanwang_country", "sts_strongest_fanwang_character"):
        if not any(k == "remove_variable" and v == variable for k, _, v, _ in header_flat):
            errors.append(f"[局势头像] 更新前未清理 {variable}")
    for scope in ("sts_chancellor_country", "sts_chancellor_character", "sts_strongest_fanwang_character"):
        if ("clear_saved_scope", "=", scope) not in header:
            errors.append(f"[局势头像] 未清理临时作用域 {scope}")
    if sum(k == "is_alive" and v == "yes" for k, _, v, _ in header_flat) < 2:
        errors.append("[局势头像] 两个人物都必须通过存活检查")
    gui = sources["gui"]
    if gui.count("Character.IsAlive") < 2 or "visible = \"[Or(" not in gui:
        errors.append("[局势头像] GUI 必须独立保护两个存活人物，不能只由丞相控制整个头部")

    promote = block_child(actions, "sts_promote_to_jiedushi")
    if not any(k == "target_flag" and v == "recipient" for k, _, v, _ in walk_blocks(promote)):
        errors.append("[节度使] situation 行动缺少 recipient 选择")
    mandate = block_child(actions, "sts_receive_mandate")
    for k, _, _, parents in walk_blocks(block_child(mandate, "effect")):
        if k == "is_member_of_international_organization" and "international_organization:middle_kingdom" in parents:
            after_io = parents[parents.index("international_organization:middle_kingdom") + 1:]
            if not any(p in ("scope:actor", "c:CSO") for p in after_io):
                errors.append("[受禅] 天朝 IO 中的成员条件必须进入国家作用域")
    restore = block_child(actions, "sts_return_government")
    restore_effect = block_child(restore, "effect")
    actor = block_child(restore_effect, "scope:actor")
    song = block_child(restore_effect, "c:CSO")
    if ("add_political_influence", "=", "-50") not in actor or any(k == "annex_country" for k, _, _, _ in walk_blocks(actor)):
        errors.append("[奉还] 费用须在旧国吞并前支付，吞并不得留在旧 actor 块中")
    if ("add_prestige", "=", "150") not in song or ("add_legitimacy", "=", "30") not in song:
        errors.append("[奉还] 威望与正统奖励必须给宋")
    ai = block_child(restore, "ai_will_do")
    if ("value", "=", "-1000") not in ai or not any(k == "has_variable" and v == "sts_ai_restore_song" for k, _, v, _ in walk_blocks(ai)):
        errors.append("[奉还设计] 必须保留普通 AI 禁用及指定 AI 开关")
    types = script_blocks(sources["types"])
    for status in ("sts_son_of_heaven", "sts_fanwang_state", "sts_warlord_state"):
        for suffix, flag in (("can_participate_in_parliament", "boolean"), ("agenda_impact", "percent")):
            name = f"{status}_{suffix}"
            body = block_child(types, name)
            if (flag, "=", "yes") not in body or ("category", "=", "internationalorganization") not in block_child(body, "game_data"):
                errors.append(f"[身份配套类型] {name} 缺失或类型/分类不正确")
    if block_child(script_blocks(sources["prices"]), "sts_claim_cb_price"):
        errors.append("[废弃价格] 不得恢复已停用的固定 30 金 sts_claim_cb_price")
    claim = block_child(actions, "sts_claim_cb")
    if not any(k == "type" and v == "casus_belli:cb_sts_consolidation_claim" for k, _, v, _ in walk_blocks(block_child(claim, "effect"))):
        errors.append("[地区割地] 索取宣称必须授予专用地区征服CB")
    cb = block_child(script_blocks(sources["claim_cb"]), "cb_sts_consolidation_claim")
    if ("war_goal_type", "=", "sts_consolidation_claim_wargoal") not in cb:
        errors.append("[地区割地] 专用CB必须连接独立战争目标")
    if ("area", "=", "scope:actor.capital.area") not in block_child(cb, "province"):
        errors.append("[地区割地] 专用CB目标省份必须在首都area内")
    goal = block_child(script_blocks(sources["wargoals"]), "sts_consolidation_claim_wargoal")
    if ("type", "=", "take_province") not in goal or ("ticking_war_score", "=", "0.5") not in goal:
        errors.append("[地区割地] 必须保持原版征服省份目标和累计分")
    for side in ("attacker", "defender"):
        allowed = block_child(block_child(goal, side), "allowed_locations")
        checks = [(k, op, v) for k, op, v, _ in walk_blocks(allowed) if k != "custom_tooltip" and k != "text"]
        if checks != [("scope:location.area", "=", "scope:winner.capital.area")]:
            errors.append(f"[地区割地] {side} 必须仅允许受让国当前首都area内割地")
    if ("conquer_cost", "=", "0.75") not in block_child(goal, "attacker") or ("subjugate_cost", "=", "0.75") not in block_child(goal, "attacker"):
        errors.append("[地区割地] 原版征服省份成本不得改变")
    consolidation = block_child(script_blocks(sources["situations"]), "sts_consolidation")
    outcomes = {next((v.strip('"') for k, _, v in body if k == "name"), ""): body
                for k, _, body in consolidation if k == "outcome" and isinstance(body, list)}
    expiry = block_child(outcomes.get("sts_consolidation_continue", []), "trigger")
    elapsed = block_child(expiry, "situation:sts_consolidation")
    if ("years_since_situation_start", ">=", "3") not in elapsed or any(k == "current_date" for k, _, _, _ in walk_blocks(expiry)):
        errors.append("[三年整合] 到期必须按实际局势开始满三年计算")
    hegemon = block_child(block_child(outcomes.get("sts_consolidation_hegemon", []), "trigger"), "any_country")
    for condition in (("sts_is_consolidation_member", "=", "yes"), ("is_subject", "=", "no"), ("num_locations", ">=", "100")):
        if condition not in hegemon:
            errors.append("[三年整合] 霸主须为独立成员且直辖地点>=100")
            break
    start = block_child(consolidation, "on_start")
    intro_loops = [v for k, _, v in start if k == "every_country" and isinstance(v, list)
                   and ("trigger_event_non_silently", "=", "sts_consolidation.1") in v]
    if len(intro_loops) != 1:
        errors.append("[整合开场] 局势开始须统一发送开场事件")
    else:
        loop = intro_loops[0]
        limits = block_child(loop, "limit")
        if ("sts_is_consolidation_member", "=", "yes") not in limits or ("country_type", "=", "location") not in limits or any(k in ("is_subject", "is_human") for k, _, _, _ in walk_blocks(limits)):
            errors.append("[整合开场] 必须覆盖玩家/AI及附庸成员，并排除建筑国家")
        if ("has_variable", "=", "sts_consolidation_intro_seen") not in block_child(limits, "NOT") or ("name", "=", "sts_consolidation_intro_seen") not in block_child(loop, "set_variable"):
            errors.append("[整合开场] 必须保留逐国仅一次标记")
    intro = block_child(script_blocks(sources["intro_events"]), "sts_consolidation.1")
    if ("type", "=", "country_event") not in intro or not block_child(intro, "option"):
        errors.append("[整合开场] 缺少有效国家事件和确认选项")
    loc = sources["intro_loc"]
    for key in ("sts_consolidation.1.title", "sts_consolidation.1.desc", "sts_consolidation.1.a"):
        if not re.search(rf"^\s+{re.escape(key)}:", loc, re.M):
            errors.append(f"[整合开场] 缺少本地化 {key}")
    return errors


def regression_self_test(sources):
    """仅在内存重新注入已知旧错，不改写游戏文件。"""
    status_match = re.search(r"has_special_status_in_international_organization\s*=\s*\{[^{}]*\}", sources["hooks"])
    status_block = status_match.group(0) if status_match else "missing_status_injection_point"
    cases = [
        ("早期AI作用域", "actions", "ai_prerequisite = {", "ai_prerequisite = { scope:actor = { is_subject = no }", "[AI前置]"),
        ("特殊身份缺组织", "hooks", status_block, "has_special_status_in_international_organization = { type = special_status:sts_fanwang_state }", "[组织身份]"),
        ("援助好感反向", "events", "opinion = { target = scope:sts_attacked_member value > 0 }", "scope:sts_attacked_member = { opinion = { target = root value > 0 } }", "[援助好感]"),
        ("年度敌意目标root", "effects", "target = scope:sts_emperor_host", "target = root", "[年度敌意]"),
        ("头像缺变量清理", "effects", "remove_variable = sts_chancellor_character", "# missing variable cleanup", "[局势头像]"),
        ("头像缺scope清理", "effects", "clear_saved_scope = sts_chancellor_country", "# missing scope cleanup", "[局势头像]"),
        ("奉还奖励留旧国", "actions", "\t\t\tadd_prestige = 150\n\t\t\tadd_legitimacy = 30", "\t\t\tscope:sts_old_chancellor = { add_prestige = 150 add_legitimacy = 30 }", "[奉还]"),
        ("奉还丢失费用", "actions", "save_scope_as = sts_old_chancellor\n\t\t\tc:CSO = { save_scope_as = sts_song_emperor }\n\t\t\tadd_political_influence = -50", "save_scope_as = sts_old_chancellor\n\t\t\tc:CSO = { save_scope_as = sts_song_emperor }", "[奉还]"),
        ("宣战钩子覆盖", "hooks", "on_war_declared = {", "on_war_declared = { effect = { sts_game_init = yes }", "[钩子追加]"),
        ("拒援钩子覆盖", "hooks", "on_rejected_call_to_arms = {", "on_rejected_call_to_arms = { effect = { sts_game_init = yes }", "[钩子追加]"),
        ("宗族female旧写法", "effects", "is_female = no", "female = no", "[宗族]"),
        ("GUI失去存活检查", "gui", "Character.IsAlive", "Character.IsValid", "[局势头像]"),
        ("缺身份配套类型", "types", "sts_son_of_heaven_can_participate_in_parliament", "removed_type", "[身份配套类型]"),
        ("恢复废弃价格", "prices", sources["prices"], "sts_claim_cb_price = { gold = 30 }", "[废弃价格]"),
        ("误用通用征服CB", "actions", "type = casus_belli:cb_sts_consolidation_claim", "type = casus_belli:cb_conquer_province", "[地区割地]"),
        ("断开独立战争目标", "claim_cb", "war_goal_type = sts_consolidation_claim_wargoal", "war_goal_type = conquer_province", "[地区割地]"),
        ("CB丢失地区条件", "claim_cb", "area = scope:actor.capital.area", "always = yes", "[地区割地]"),
        ("进攻方丢失割地限制", "wargoals", "scope:location.area = scope:winner.capital.area", "always = yes", "[地区割地]"),
        ("地区被误改为大区", "wargoals", "scope:location.area = scope:winner.capital.area", "scope:location.region = scope:winner.capital.region", "[地区割地]"),
        ("防守方丢失割地限制", "wargoals", "defender = {\n\t\tallowed_locations = {", "defender = {\n\t\tdisabled_locations = {", "[地区割地]"),
        ("整合恢复十年", "situations", "years_since_situation_start >= 3", "years_since_situation_start >= 10", "[三年整合]"),
        ("霸主恢复三百", "situations", "num_locations >= 100", "num_locations >= 300", "[三年整合]"),
        ("开场漏发事件", "situations", "trigger_event_non_silently = sts_consolidation.1", "# missing intro event", "[整合开场]"),
        ("开场重复发送", "situations", "has_variable = sts_consolidation_intro_seen", "has_variable = wrong_marker", "[整合开场]"),
        ("开场事件不存在", "intro_events", "sts_consolidation.1 = {", "sts_consolidation.99 = {", "[整合开场]"),
        ("开场漏正文", "intro_loc", "sts_consolidation.1.desc:", "sts_consolidation.99.desc:", "[整合开场]"),
    ]
    failures = []
    baseline = script_regressions(sources)
    if baseline:
        return ["[变异自测] 基线不是无错误状态"] + baseline
    for name, source, old, new, expected in cases:
        if old not in sources[source]:
            failures.append(f"[变异自测] {name} 未找到注入位置")
            continue
        mutated = dict(sources)
        mutated[source] = mutated[source].replace(old, new, 1)
        caught = script_regressions(mutated)
        if not any(error.startswith(expected) for error in caught):
            failures.append(f"[变异自测] {name} 未被预期规则捕获")
    print(f"  内存变异回归：{len(cases) - len(failures)}/{len(cases)} 项通过（未改写游戏文件）")
    return failures


def main():
    problems = []
    info = []

    # ---- 1/2. 逐文件检查 ----
    for dp, _, fs in os.walk(MOD):
        for f in sorted(fs):
            if not f.endswith((".txt", ".yml", ".gui")):
                continue
            if not os.path.relpath(dp, MOD).replace("\\", "/").startswith(("in_game", "main_menu")):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, MOD).replace("\\", "/")
            raw = open(p, "rb").read()
            has_bom = raw.startswith(b"\xef\xbb\xbf")
            is_setup = rel.startswith("main_menu/setup/1337/")
            is_gui = rel.endswith(".gui")
            if (is_setup or is_gui) and has_bom:
                problems.append(f"[BOM] {rel} 不应带 BOM")
            if not (is_setup or is_gui) and not has_bom:
                problems.append(f"[BOM] {rel} 缺少 BOM")
            text = read(p)
            # 外国建筑必须四选一，否则引擎每月清理（error.log: "is foreign but lacks either ..."）
            if "/building_types/" in "/" + rel:
                for m in re.finditer(r"^(\w+) = \{(.*?)^\}", text, re.S | re.M):
                    body = m.group(2)
                    if re.search(r"^\s*is_foreign = yes", body, re.M) and not re.search(
                        r"^\s*(stronger_power_projection = yes|need_good_relation = yes|"
                        r"own_or_overlord_relation_needed = \w+|international_organization_link = \w+)",
                        body, re.M):
                        problems.append(f"[外国建筑] {rel}: {m.group(1)} 是 is_foreign 但缺少四选一的立足条件")
            depth, instr, bad = 0, False, None
            for i, ch in enumerate(text):
                if ch == '"':
                    instr = not instr
                if instr:
                    continue
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth < 0:
                        bad = i
                        break
            if depth or bad is not None or instr:
                problems.append(f"[语法] {rel} 括号/引号不平衡 depth={depth}")

    # ---- 2.5 顶层块之后不能有游离内容 ----
    for dp, _, fs in os.walk(os.path.join(MOD, "main_menu/setup")):
        for f in fs:
            if not f.endswith(".txt"):
                continue
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, MOD).replace("\\", "/")
            depth, closed_at = 0, None
            for idx, line in enumerate(read(p).split("\n"), 1):
                depth += line.count("{") - line.count("}")
                # 记录最后一次回到顶层的行（文件可能有多个顶层块）
                if depth == 0 and idx > 1 and line.strip().endswith("}"):
                    closed_at = idx
            if closed_at:
                after = read(p).split("\n")[closed_at:]
                junk = [l for l in after if l.strip() and not l.strip().startswith("#")]
                if junk:
                    problems.append(
                        f"[结构] {rel} 第 {closed_at} 行之后还有 {len(junk)} 行内容在顶层块之外，"
                        f"不会被解析（例：{junk[0].strip()[:40]}）")

    # ---- 3/4/5. 语义检查 ----
    locs = vanilla_locations()
    tags = vanilla_tags() | OWN_TAGS
    corpus = vanilla_corpus()
    formable_tags = set()
    for p in walk_txt(os.path.join(GAME, "in_game/common/formable_countries")):
        formable_tags.update(re.findall(r"^\ttag\s*=\s*([A-Z][A-Z0-9]{1,2})\b", read(p), re.M))
    reference_tags = tags | formable_tags

    for p in walk_txt(MOD):
        rel = os.path.relpath(p, MOD).replace("\\", "/")
        # setup 里是原版文件的整体副本，里面的引用由原版保证，不做语义检查
        if rel.startswith("main_menu/setup/") or not rel.startswith(("in_game/", "main_menu/")):
            continue
        # country_ranks 是整份原版覆盖文件，含原版所有 tag；只校验生成器/自定义部分
        if rel == "in_game/common/customizable_localization/country_ranks.txt":
            continue
        text = read(p)
        for loc in re.findall(r"location:([a-z0-9_]+)", text):
            if loc not in locs:
                problems.append(f"[地名] {rel}: location:{loc} 不存在")
        for m in re.findall(r"\bc:([A-Z][A-Z0-9]{1,2})\b", text):
            if m not in reference_tags:
                problems.append(f"[国家] {rel}: c:{m} 没有国家定义")
        for m in re.findall(r"\btag = ([A-Z][A-Z0-9]{1,2})\b", text):
            if m not in reference_tags:
                problems.append(f"[国家] {rel}: tag = {m} 没有国家定义")

        # key = { ... } 形式的字段名，检查是否在原版语料里出现过
        for key in set(re.findall(r"^\s*([a-z][a-z0-9_]+) = ", text, re.M)):
            if key.startswith(("sts_", "cb_sts_", "io_opinion_sts_", "io_trust_sts_")):
                continue
            if key not in corpus:
                problems.append(f"[未知字段] {rel}: `{key} =` 原版从未出现，可能是拼错或版本已改")

    # ---- 内容模板检查：静态修正 / 法律位置 / 建筑作用域 / 决策 tags ----
    mod_defs = read(os.path.join(GAME, "main_menu/common/modifier_type_definitions/00_modifier_types.txt"))
    mod_category = {}
    for m in re.finditer(r"^([a-z_]+)=\{\n(.*?)^\}", mod_defs, re.M | re.S):
        cat = re.search(r"category\s*=\s*(\w+)", m.group(2))
        mod_category[m.group(1)] = cat.group(1) if cat else ""
    static_path = os.path.join(MOD, "in_game/common/static_modifiers/sts_modifiers.txt")
    if os.path.exists(static_path):
        static_text = read(static_path)
        for m in re.finditer(r"^(\w+) = \{(.*?)^\}", static_text, re.M | re.S):
            name, body = m.group(1), m.group(2)
            if "game_data" not in body:
                problems.append(f"[静态修正] {name}: 缺少 game_data = {{ category = country }}")
            for key in re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*=", body, re.M):
                if key == "game_data":
                    continue
                if key == "category":
                    continue
                if key not in mod_category:
                    problems.append(f"[静态修正] {name}: 未知修正键 {key}")
                elif mod_category[key] == "location":
                    problems.append(f"[静态修正] {name}: {key} 是 location 键，不能用于国家静态修正")
    setup_text = read(os.path.join(MOD, "main_menu/setup/1337/10_countries.txt"))
    if re.search(r"^\t\tlaws\s*=\s*\{", setup_text, re.M):
        problems.append("[法律] setup 中 laws 位于国家层级，必须在 government = { } 内")
    for tag in ("KFE", "XIA", "JIN", "DAD", "CAJ", "LAK", "YAF", "XAF", "XAB", "HAS"):
        block = re.search(rf"^\t{tag} = \{{(.*?)^\t\}}", setup_text, re.M | re.S)
        if not block:
            problems.append(f"[法律] {tag} 缺少国家块")
        elif "\t\t\tlaws = {" not in block.group(1):
            problems.append(f"[法律] {tag} 的 laws 不在 government 内")
    building_path = os.path.join(MOD, "in_game/common/building_types/sts_liang_buildings.txt")
    if os.path.exists(building_path):
        building_text = read(building_path)
        for m in re.finditer(r"(?<!_)\bmodifier = \{(.*?)\}", building_text, re.S):
            body = m.group(1)
            for key in re.findall(r"^\s*([a-z_][a-z0-9_]*)\s*=", body, re.M):
                if key in ("gold_to_building_owner", "manpower_to_building_owner", "can_recruit_regiment_in_this_location"):
                    continue
                problems.append(f"[建筑] modifier 中出现非 location 键 {key}，应移到 capital_country_modifier")
            limit = re.search(r"manpower_to_building_owner\s*=\s*([0-9.]+)", body)
            if limit and float(limit.group(1)) > 0.00125:
                problems.append("[建筑] manpower_to_building_owner 超过引擎上限 0.00125")
    decision_path = os.path.join(MOD, "in_game/common/decisions/sts_liang_decisions.txt")
    if os.path.exists(decision_path):
        decision_text = read(decision_path)
        for m in re.finditer(r"^(\w+) = \{(.*?)^\}", decision_text, re.M | re.S):
            if "tags = { KFE }" not in m.group(2):
                problems.append(f"[决策] {m.group(1)} 缺少 tags = {{ KFE }}")

    # ---- 宋代官制头衔：country_flavor 必须包含分支，本地化必须有 _ruler_male ----
    rank_path = os.path.join(MOD, "in_game/common/customizable_localization/country_ranks.txt")
    ui_loc_path = os.path.join(MOD, "main_menu/localization/simp_chinese/sts_ui_l_simp_chinese.yml")
    if not os.path.exists(rank_path) or not os.path.exists(ui_loc_path):
        problems.append("[头衔] country_ranks.txt 或 sts_ui 本地化缺失")
    else:
        rank_text, ui_loc = read(rank_path), read(ui_loc_path)
        for key in ("rank_duchy_sts_jiedushi", "rank_kingdom_sts_fanwang",
                    "rank_county_sts_cishi", "rank_duchy_sts_xuanfushi",
                    "rank_duchy_sts_chancellor", "rank_duchy_sts_son_of_heaven"):
            if f"localization_key = {key}" not in rank_text:
                problems.append(f"[头衔] country_ranks 缺少 {key} 分支")
            if f"{key}:" not in ui_loc:
                problems.append(f"[头衔] 缺少 {key} 基础本地化")
            if f"{key}_ruler_male:" not in ui_loc:
                problems.append(f"[头衔] 缺少 {key}_ruler_male 本地化")

    from prince_data import PRINCES
    adv_path = os.path.join(MOD, "in_game/common/advances/sts_prince_advances.txt")
    law_path = os.path.join(MOD, "in_game/common/laws/sts_prince_laws.txt")
    prince_loc_path = os.path.join(MOD, "main_menu/localization/simp_chinese/sts_prince_l_simp_chinese.yml")
    if not os.path.exists(adv_path) or not os.path.exists(law_path) or not os.path.exists(prince_loc_path):
        problems.append("[内容] 八国 advance/法律/本地化生成文件缺失，请先运行 tools/gen_prince_content.py")
    else:
        adv_text, law_text, prince_loc = read(adv_path), read(law_path), read(prince_loc_path)
        for tag, data in PRINCES.items():
            ak = data["advance"]["key"]
            lk = data["law"]["key"]
            if ak not in adv_text:
                problems.append(f"[内容] {tag} 缺少 advance {ak}")
            if lk not in law_text:
                problems.append(f"[内容] {tag} 缺少法律 {lk}")
            if ak not in prince_loc or lk not in prince_loc:
                problems.append(f"[内容] {tag} advance/法律缺少本地化")
            law_block = re.search(rf"^{lk} = \{{(.*?)^\}}", law_text, re.M | re.S)
            if law_block:
                policies = [p for p in re.findall(r"^\t(\w+) = \{", law_block.group(1), re.M)
                            if p not in ("unique", "law_category", "law_gov_group", "law_country_group",
                                         "potential", "allow", "locked")]
                if len(policies) != 3:
                    problems.append(f"[内容] {tag} 法律政策数 {len(policies)}，应为 3")
            adv_block = re.search(rf"^{ak} = \{{(.*?)^\}}", adv_text, re.M | re.S)
            if adv_block:
                mods = [k for k in re.findall(r"^\t([a-z_]+) = ", adv_block.group(1), re.M)
                        if k not in ("age", "icon", "content_priority", "potential")]
                if not 3 <= len(mods) <= 5:
                    problems.append(f"[内容] {tag} advance 修正数 {len(mods)}，应为 3-5")

    # ---- 地图完整性：三种归属、setup 实体、人物、组织都交叉核对 ----
    import json
    import gen_map
    from collections import Counter
    base = gen_map.country_blocks(read(gen_map.V_COUNTRIES))
    current = gen_map.country_blocks(read(gen_map.OUT_COUNTRIES))
    old_own, new_own = gen_map.ownership(base), gen_map.ownership(current)
    lost = sorted(set(old_own) - set(new_own))
    added = sorted(set(new_own) - set(old_own))
    for loc in lost:
        problems.append(f"[白地] 原版有主地点 {loc} 在模组中无主，原主 {old_own[loc]}")
    for loc in added:
        problems.append(f"[殖民地] 原版无主地点 {loc} 被新认领")
    for loc, owners in new_own.items():
        if len(owners) > 1:
            problems.append(f"[重复归属] {loc}: {owners}")
    for tag in sorted(set(current) - tags):
        problems.append(f"[国家] setup 国家 {tag} 缺实际定义")
    chars = set()
    char_root = os.path.join(GAME, "main_menu/setup/1337")
    for root in (char_root, os.path.join(MOD, "main_menu/setup/1337")):
        for p in walk_txt(root):
            chars.update(re.findall(r"^\t([a-z][a-z0-9_]+)\s*=\s*\{", read(p), re.M))
    generated_chars = read(os.path.join(MOD, "main_menu/setup/1337/05_sts_characters.txt"))
    for match in re.finditer(r"^\t(sts_\w+_ruler)\s*=\s*\{(.*?)^\t\}", generated_chars, re.M | re.S):
        born = re.search(r"\bbirth\s*=\s*(\w+)", match.group(2))
        if not born or born.group(1) not in locs:
            problems.append(f"[人物] {match.group(1)} 缺少有效出生地点")
    data = json.load(open(os.path.join(MOD, "tools/sts_tags.json"), encoding="utf-8"))
    for tag in data["all"] + ["CSO", "CDL"]:
        block = current.get(tag, "")
        for ruler in re.findall(r"\bruler\s*=\s*(sts_\w+)", block):
            if ruler not in chars:
                problems.append(f"[人物] {tag} 引用不存在的 {ruler}")
        cap = re.search(r"\bcapital\s*=\s*(\w+)", block)
        if cap and "type = building" not in block and tag not in new_own.get(cap.group(1), []):
            problems.append(f"[首都] {tag} 不拥有 {cap.group(1)}")
    for tag, block in current.items():
        cap = re.search(r"\bcapital\s*=\s*(\w+)", gen_map.uncomment(block))
        if cap and tag in old_own.get(cap.group(1), []) and tag not in new_own.get(cap.group(1), []):
            if any(tag in owners for owners in new_own.values()):
                problems.append(f"[首都] {tag} 失去原首都 {cap.group(1)} 却未迁都")
    setup_text = read(gen_map.OUT_COUNTRIES)
    setup_tags = [t for t, _, _ in gen_map.block_spans(setup_text.splitlines())]
    if len(setup_tags) != len(set(setup_tags)):
        problems.append("[国家] setup 有重复国家块")
    diplomacy = read(os.path.join(MOD, "main_menu/setup/1337/12_diplomacy.txt"))
    for first, second in re.findall(r"dependency\s*=\s*\{\s*first\s*=\s*(\w+)\s+second\s*=\s*(\w+)", diplomacy):
        if first not in current or second not in current:
            problems.append(f"[外交] 附属关系 {first}-{second} 引用缺失的 setup 国家")
    triggers = read(os.path.join(MOD, "in_game/common/scripted_triggers/sts_warlord_tags.txt"))
    trigger_tags = re.findall(r"\btag = ([A-Z][A-Z0-9]{1,2})\b", triggers)
    if Counter(trigger_tags) != Counter(data["chinese"]):
        problems.append("[名单] 藩镇触发器与本次地图 tag 不同步")
    io_lines = read(os.path.join(MOD, "main_menu/setup/1337/15_international_organizations.txt")).splitlines()
    import gen_io
    for start, end in gen_io.block_spans(io_lines):
        kind = gen_io.block_type(io_lines, start, end)
        if kind not in ("middle_kingdom", "sts_chancellery"):
            continue
        block = "\n".join(io_lines[start:end + 1])
        member = re.search(r"members\s*=\s*\{([^{}]*)\}", block, re.S)
        members = set(member.group(1).split())
        expected = set(data["chinese"])
        if kind == "middle_kingdom":
            expected = set(data.get("chancellery", data["chinese"])) | {"CDL"}
        else:
            expected = set(data.get("chancellery", data["chinese"])) | {"CSO"}
        if members != expected:
            problems.append(f"[组织] {kind} 成员不同步：多余 {sorted(members - expected)} 缺少 {sorted(expected - members)}")
        leader_match = re.search(r"\bleader\s*=\s*(\w+)", block)
        if kind == "middle_kingdom":
            if leader_match:
                problems.append(f"[组织] middle_kingdom 应无领袖，却写了 {leader_match.group(1)}")
        elif not leader_match:
            problems.append("[组织] sts_chancellery 缺少领袖")
        elif leader_match.group(1) not in members:
            problems.append(f"[组织] {kind} 领袖 {leader_match.group(1)} 不在成员内")
    regions = gen_map.parse_definitions()
    taiwan = {x for ls in regions["east_china_region"]["taiwan_area"].values() for x in ls}
    if taiwan & set(new_own):
        problems.append("[殖民地] 中国台湾被认领，必须保持原版无主状态")
    tibet = {x for ps in regions["tibet_region"].values() for ls in ps.values() for x in ls}
    if any("CHI" in new_own.get(x, []) for x in tibet):
        problems.append("[领土] 元仍在西藏持有地点")
    if not re.search(r"\bcapital = dadu\b", current["CHI"]):
        problems.append("[首都] 元未定都大都")
    effects = read(os.path.join(MOD, "in_game/common/scripted_effects/sts_effects.txt"))
    actions = read(os.path.join(MOD, "in_game/common/generic_actions/sts_actions.txt"))
    triggers_text = read(os.path.join(MOD, "in_game/common/scripted_triggers/sts_triggers.txt"))
    situations = read(os.path.join(MOD, "in_game/common/situations/sts_situations.txt"))
    if "sts_declare_kingdom_b" in actions:
        problems.append("[宋廷] 称王 B 已废弃，仍存在于 actions")
    if "sts_hosts_song_court" not in triggers_text:
        problems.append("[宋廷] 缺少触发器 sts_hosts_song_court")
    if actions.count("sts_hosts_song_court") < 3:
        problems.append("[宋廷] 称王 A/C、自领丞相、受禅未全部改用宋廷判定")
    if "location:kaifeng.owner" in actions or "location:kaifeng.owner" in situations:
        problems.append("[宋廷] actions/situations 仍写死 location:kaifeng.owner")
    # 建筑国家必须在 setup 的 building_manager 里有落座建筑，否则首月即消亡
    built = set()
    for name in ("07_cities_and_buildings.txt", "07a_sts_buildings.txt"):
        for root in (MOD, GAME):
            path = os.path.join(root, "main_menu/setup/1337", name)
            if not os.path.exists(path):
                continue
            for m in re.finditer(r"^\s*\w+\s*=\s*\{\s*tag\s*=\s*([A-Z][A-Z0-9]{1,2})\b", read(path), re.M):
                built.add((name, m.group(1)))
    built_tags = {tag for _, tag in built}
    for tag, block in current.items():
        if "type = building" in block and tag not in built_tags and tag != "YMT":
            problems.append(f"[宋廷] 建筑国家 {tag} 在 07/07a 中没有建筑")
    seven_a = os.path.join(MOD, "main_menu/setup/1337/07a_sts_buildings.txt")
    if not os.path.exists(seven_a) or "sts_song_court = { tag = CSO level = 1 location = kaifeng }" not in read(seven_a):
        problems.append("[宋廷] 07a 缺少开封宋廷落座条目")
    info.append(f"地图：原版有主 {len(old_own)}；模组有主 {len(new_own)}；遗漏 {len(lost)}；新增认领 {len(added)}")
    info.append(f"中国台湾 {len(taiwan)} 地点保持无主；元在西藏 0 地点；元首都大都")
    info.append(f"藩镇：{len(data['chinese'])} 家，触发器/国家/人物/组织已交叉核对")

    # ---- 索取宣称 AI 回归：前置阶段没有命名作用域，地域约束不得丢失 ----
    claim_match = re.search(r"^sts_claim_cb = \{(.*?)^\}", actions, re.M | re.S)
    if not claim_match:
        problems.append("[索取宣称] 缺少 sts_claim_cb 行动")
    else:
        claim = claim_match.group(1)
        # 原版 generic_actions/readme.txt：ai_prerequisite 只有 root 国家，
        # actor/recipient/target 等命名作用域尚未建立。
        clean_claim = re.sub(r'"(?:\\.|[^"\\])*"|#[^\n]*', "", claim)
        for gate in re.finditer(r"\bai_prerequisite(?:_after_potential)?\s*=\s*\{", clean_claim):
            start, depth = gate.end(), 1
            end = start
            while end < len(clean_claim) and depth:
                depth += (clean_claim[end] == "{") - (clean_claim[end] == "}")
                end += 1
            if re.search(r"\bscope:\w+", clean_claim[start:end - 1]):
                problems.append("[索取宣称] AI 前置检查引用命名 scope，必须直接用执行国家/root")
        if not re.search(r"\barea\s*=\s*scope:actor\.capital\.area\b", clean_claim):
            problems.append("[索取宣称] 丢失首都所在地区 area 限制")
        if not re.search(r"any_location_in_province\s*=\s*\{\s*is_neighbor_of\s*=\s*scope:actor\s*\}", clean_claim):
            problems.append("[索取宣称] 丢失目标省份与本国相邻限制")
        list_path = os.path.join(MOD, "in_game/common/generic_action_ai_lists/sts_consolidation_list.txt")
        if not os.path.exists(list_path) or not re.search(r"\bactions\s*=\s*\{\s*sts_claim_cb\s*\}", read(list_path)):
            problems.append("[索取宣称] 缺少专用 AI 行动分组登记")
        info.append("索取宣称：AI 前置作用域、首都 area、相邻限制及行动分组已检查")

    # ---- 运行期缺陷回归：覆盖日志暴露但通用 token 检查无法识别的问题 ----
    script_sources = {
        "actions": actions,
        "effects": effects,
        "hooks": read(os.path.join(MOD, "in_game/common/on_action/sts_on_actions.txt")),
        "events": read(os.path.join(MOD, "in_game/events/situations/sts_defense_levy_events.txt")),
        "gui": read(os.path.join(MOD, "in_game/gui/panels/situation/sts_warring_states.gui")),
        "types": read(os.path.join(MOD, "main_menu/common/modifier_type_definitions/sts_modifier_types.txt")) if os.path.exists(os.path.join(MOD, "main_menu/common/modifier_type_definitions/sts_modifier_types.txt")) else "",
        "prices": read(os.path.join(MOD, "in_game/common/prices/sts_prices.txt")),
        "claim_cb": read(os.path.join(MOD, "in_game/common/casus_belli/sts_consolidation_claim.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/casus_belli/sts_consolidation_claim.txt")) else "",
        "wargoals": read(os.path.join(MOD, "in_game/common/wargoals/sts_wargoals.txt")),
        "situations": situations,
        "intro_events": read(os.path.join(MOD, "in_game/events/situations/sts_consolidation_events.txt")) if os.path.exists(os.path.join(MOD, "in_game/events/situations/sts_consolidation_events.txt")) else "",
        "intro_loc": read(ui_loc_path),
    }
    problems.extend(script_regressions(script_sources))
    info.append("地区割地：索取宣称专用 CB/战争目标链路、双方受让国首都 area 限制已检查")
    info.append("海内整合：实际开始满三年到期、独立成员直辖100地点结局、全体成员仅一次开场事件已检查")
    if "--self-test" in sys.argv:
        problems.extend(regression_self_test(script_sources))
    info.append("脚本回归：钩子追加、组织身份及配套类型、全部 AI 前置、援助好感、年度敌意、奉还奖励及头像清理已检查")

    # ---- 5.5 每个局势必须有同名 GUI 面板 ----
    sit_dir = os.path.join(MOD, "in_game/common/situations")
    gui_dir = os.path.join(MOD, "in_game/gui/panels/situation")
    for f in os.listdir(sit_dir):
        if not f.endswith(".txt"):
            continue
        for key in re.findall(r"^([a-z][a-z0-9_]+) = \{", read(os.path.join(sit_dir, f)), re.M):
            if not os.path.exists(os.path.join(gui_dir, key + ".gui")):
                problems.append(f"[GUI] 局势 {key} 缺少 gui/panels/situation/{key}.gui，面板会是空白")

    # ---- 5.6 覆盖原版键必须用同名文件 ----
    import collections
    vanilla_owner = {}
    for sub in ["customizable_localization", "situations", "generic_actions", "casus_belli"]:
        d = os.path.join(GAME, "in_game/common", sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".txt"):
                continue
            for k in re.findall(r"^([a-z][a-z0-9_]+) = \{", read(os.path.join(d, f)), re.M):
                vanilla_owner.setdefault(k, f)
    for sub in ["customizable_localization", "situations", "generic_actions", "casus_belli"]:
        d = os.path.join(MOD, "in_game/common", sub)
        if not os.path.isdir(d):
            continue
        for f in os.listdir(d):
            if not f.endswith(".txt"):
                continue
            for k in re.findall(r"^([a-z][a-z0-9_]+) = \{", read(os.path.join(d, f)), re.M):
                if k in vanilla_owner and vanilla_owner[k] != f:
                    problems.append(
                        f"[覆盖] {sub}/{f} 里的键 {k} 与原版 {vanilla_owner[k]} 重名，"
                        f"必须改成同名文件才能生效")

    # ---- 6. 本地化 ----
    defined = set()
    for p in LOC_FILES:
        for line in read(p).split("\n"):
            m = re.match(r"\s+([A-Za-z0-9_.]+):", line)
            if m:
                defined.add(m.group(1))
    # 我们脚本里出现的、看起来像 loc key 的键
    need = set()
    for p in walk_txt(MOD):
        text = read(p)
        need.update(re.findall(r'name = "(sts_[a-z0-9_]+)"', text))
        need.update(re.findall(r'desc = "(sts_[a-z0-9_]+)"', text))
        need.update(re.findall(r'text = "(sts_[a-z0-9_]+)"', text))
        need.update(re.findall(r"_tt\b", text) and [])
    for k in sorted(need):
        if k not in defined:
            problems.append(f"[本地化] 缺少 {k}")
    for k in ("sts_move_song_court", "sts_move_song_court_desc",
              "STATIC_MODIFIER_NAME_sts_relocated_court",
              "STATIC_MODIFIER_DESC_sts_relocated_court",
              "sts_court_relocated"):
        if k not in defined:
            problems.append(f"[本地化] 缺少 {k}")

    # ---- 输出 ----
    print(f"检查完成：{len(problems)} 个问题\n")
    for message in info:
        print(" ", message)
    for x in problems:
        print(" ✗", x)
    if not problems:
        print(" ✓ 全部通过")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
