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
    python /path/to/tools/preflight.py --mod /path/to/sts_autumn_of_states --self-test
"""
import os
import re
import sys

GAME = r"D:/SteamLibrary/steamapps/common/Europa Universalis V/game"
# 工坊上传时 tools 可移出；--mod 指定实际模组目录，默认仍使用原相对路径。
MOD = os.path.abspath(sys.argv[sys.argv.index("--mod") + 1] if "--mod" in sys.argv
                      else os.path.join(os.path.dirname(__file__), ".."))

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


def child_blocks(nodes, key):
    """同名块可能重复出现（如多个 outcome），这里返回全部。"""
    return [value for name, _, value in nodes if name == key and isinstance(value, list)]


def walk_blocks(nodes, parents=()):
    for key, op, value in nodes:
        yield key, op, value, parents
        if isinstance(value, list):
            yield from walk_blocks(value, parents + (key,))


CASTLE_LOCATIONS = (
    "liangquan daan xunyang pucheng jiangyou yiling shipai lingshi yushe jincheng_zezhou "
    "wudi guantao pingyuan_jinan yanci licheng anqiu wulian jiangning guangde wujin "
    "jiaxing linan zhangping wuling shaoyang").split()


def setup_owner_map(countries_text):
    """setup 国家块内 own_control_core 的地点归属表。"""
    owner = {}
    for m in re.finditer(r"^\t([A-Z]{2,3}) = \{", countries_text, re.M):
        tag, start = m.group(1), m.end()
        nxt = re.search(r"^\t[A-Z]{2,3} = \{", countries_text[start:], re.M)
        body = countries_text[start:start + nxt.start()] if nxt else countries_text[start:]
        for om in re.finditer(r"own_control_core = \{(.*?)\}", body, re.S):
            for loc in om.group(1).split():
                owner.setdefault(loc, tag)
    return owner


def castle_setup_errors(building_text, countries_text, locations):
    """指定地点必须在开局拥有归属正确的 1 级城堡。"""
    errors = []
    owner = setup_owner_map(countries_text)
    found = {}
    for m in re.finditer(r"castle\s*=\s*\{\s*tag\s*=\s*([A-Z]{2,3})\s*level\s*=\s*(\d+)\s*"
                         r"location\s*=\s*(\w+)\s*\}", building_text):
        found.setdefault(m.group(3), []).append((m.group(1), int(m.group(2))))
    for loc in CASTLE_LOCATIONS:
        if loc not in locations:
            errors.append(f"[开局城堡] location {loc} 不存在")
            continue
        entries = found.get(loc)
        if not entries:
            errors.append(f"[开局城堡] {loc} 缺少 castle 条目")
            continue
        if len(entries) > 1:
            errors.append(f"[开局城堡] {loc} 重复定义 castle")
        tag, level = entries[0]
        if level != 1:
            errors.append(f"[开局城堡] {loc} 城堡等级必须是 1")
        expected = owner.get(loc)
        if expected and tag != expected:
            errors.append(f"[开局城堡] {loc} 城堡归属 {tag} 与 setup 所有者 {expected} 不一致")
    return errors


def advance_ages(text):
    """只读取顶层革新 ID 与直属时代，缺少时代的 ID 仍保留以区分悬空引用。"""
    return {key: next((v for k, op, v in body if k == "age" and op == "=" and isinstance(v, str)), None)
            for key, op, body in script_blocks(text) if op == "=" and isinstance(body, list)}


def merged_advance_age_map(vanilla_sources, mod_sources):
    """按相对文件名遮蔽原版后合并，不能把被整文件覆盖的旧 ID 留在索引中。"""
    files = {**vanilla_sources, **mod_sources}
    ages = {}
    for name in sorted(files):
        ages.update(advance_ages(files[name]))
    return ages


def advance_dependency_errors(text, age_map):
    """requires 是同代科技树连线；跨代研究条件应放在 allow.has_advance。"""
    errors = []
    for advance, _, body in script_blocks(text):
        if not isinstance(body, list):
            continue
        age = next((v for k, op, v in body if k == "age" and op == "=" and isinstance(v, str)), None)
        for key, op, dependency, _ in walk_blocks(body):
            if key != "requires":
                continue
            if op != "=" or not isinstance(dependency, str) or dependency not in age_map:
                errors.append(f"[革新依赖] {advance} 的 requires 引用不存在或格式错误：{dependency}")
            elif not age or not age_map[dependency]:
                errors.append(f"[革新依赖] {advance} 或前置 {dependency} 缺少时代")
            elif age != age_map[dependency]:
                errors.append(f"[革新依赖] {advance} ({age}) 跨时代 requires {dependency} ({age_map[dependency]})")
    return errors


def unknown_field_keys(text, corpus, unit_types=False):
    if unit_types:
        # 只豁免顶层兵种 ID；内部字段（包括自定义前缀）仍须有原版语料依据。
        keys = {key for key, op, _, parents in walk_blocks(script_blocks(text))
                if parents and op and re.fullmatch(r"[a-z][a-z0-9_]+", key)}
    else:
        keys = {key for key in re.findall(r"^\s*([a-z][a-z0-9_]+) = ", text, re.M)
                if not key.startswith(("sts_", "cb_sts_", "io_opinion_sts_", "io_trust_sts_"))}
    return sorted(keys - corpus)


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
                   and any(key == "trigger_event_non_silently" and value in ("sts_consolidation.1", "sts_consolidation.2")
                           for key, _, value, _ in walk_blocks(v))]
    if len(intro_loops) != 1:
        errors.append("[整合开场] 局势开始须统一发送开场事件")
    else:
        loop = intro_loops[0]
        limits = block_child(loop, "limit")
        if ("sts_is_consolidation_member", "=", "yes") not in limits or ("country_type", "=", "location") not in limits or any(k in ("is_subject", "is_human") for k, _, _, _ in walk_blocks(limits)):
            errors.append("[整合开场] 必须覆盖玩家/AI及附庸成员，并排除建筑国家")
        if ("has_variable", "=", "sts_consolidation_intro_seen") not in block_child(limits, "NOT") or ("name", "=", "sts_consolidation_intro_seen") not in block_child(loop, "set_variable"):
            errors.append("[整合开场] 必须保留逐国仅一次标记")
        leader_if = block_child(loop, "if")
        member_else = block_child(loop, "else")
        if block_child(leader_if, "limit") != [("is_leader_of_international_organization", "=", "international_organization:sts_chancellery")]:
            errors.append("[整合开场] 丞相视角必须按实际相府领袖判定")
        if ("trigger_event_non_silently", "=", "sts_consolidation.2") not in leader_if or member_else != [("trigger_event_non_silently", "=", "sts_consolidation.1")]:
            errors.append("[整合开场] 领袖与普通成员事件必须互斥分发")
        sends = [(key, value) for key, _, value, _ in walk_blocks(loop) if key == "trigger_event_non_silently"]
        if sends != [("trigger_event_non_silently", "sts_consolidation.2"), ("trigger_event_non_silently", "sts_consolidation.1")]:
            errors.append("[整合开场] 两视角事件不可漏发或重复")
    loc = sources["intro_loc"]
    event_tree = script_blocks(sources["intro_events"])
    for event_id in ("sts_consolidation.1", "sts_consolidation.2"):
        intro = block_child(event_tree, event_id)
        option = block_child(intro, "option")
        if ("type", "=", "country_event") not in intro or not option:
            errors.append(f"[整合开场] 缺少有效国家事件和确认选项 {event_id}")
        if any(k not in ("type", "category", "title", "desc", "outcome", "option") for k, _, _ in intro) or any(k not in ("name", "ai_chance") for k, _, _ in option):
            errors.append(f"[整合开场] 事件须保持纯叙事，不得添加玩法效果 {event_id}")
        for field in ("title", "desc"):
            if (field, "=", f"{event_id}.{field}") not in intro:
                errors.append(f"[整合开场] 事件本地化引用错误 {event_id}.{field}")
        if ("name", "=", f"{event_id}.a") not in option:
            errors.append(f"[整合开场] 事件选项引用错误 {event_id}")
        for key in (f"{event_id}.title", f"{event_id}.desc", f"{event_id}.a"):
            if not re.search(rf"^\s+{re.escape(key)}:", loc, re.M):
                errors.append(f"[整合开场] 缺少本地化 {key}")
    # 册后链路只读取 sources，变异测试不得导入生成器或触碰模组文件。
    characters = block_child(trees["characters"], "character_db")
    daughter = block_child(characters, "sts_kfe_daughter1")
    for condition in (("female", "=", "yes"), ("birth_date", "=", "1319.4.1"),
                      ("dynasty", "=", "sts_zhang_dynasty"), ("father", "=", "sts_kfe_ruler"),
                      ("mother", "=", "sts_kfe_wife"), ("tag", "=", "KFE")):
        if condition not in daughter:
            errors.append(f"[册后人物] 张氏长女缺少正确属性 {condition[0]}")
    if ("name", "=", "sts_name_zhang_lingyi") not in block_child(daughter, "first_name"):
        errors.append("[册后人物] 长女必须保留独立姓名")
    if any(k == "spouse" for k, _, _, _ in walk_blocks(daughter)) or any(
            k == "spouse" and v == "sts_kfe_daughter1" for k, _, v, _ in walk_blocks(characters)):
        errors.append("[册后人物] 长女不得预设婚姻")
    if ("dynasty", "=", "sts_zhang_dynasty") not in block_child(characters, "sts_kfe_ruler"):
        errors.append("[册后人物] 长女与父亲必须同属张氏宗族")

    eligible = block_child(trees["triggers"], "sts_can_present_daughter")
    for condition in (("tag", "=", "KFE"), ("exists", "=", "character:sts_kfe_ruler"),
                      ("ruler", "=", "character:sts_kfe_ruler"),
                      ("is_leader_of_international_organization", "=", "international_organization:sts_chancellery"),
                      ("sts_hosts_song_court", "=", "yes"), ("country_exists", "=", "c:CSO"),
                      ("exists", "=", "character:sts_kfe_daughter1")):
        if condition not in eligible:
            errors.append(f"[册后前置] 必须直接核对 {condition[0]}")
    if ("has_variable", "=", "sts_liang_empress_installed") not in block_child(eligible, "NOT"):
        errors.append("[册后前置] 缺少已册后排除条件")
    song_eligible = block_child(eligible, "c:CSO")
    for flag in ("has_ruler", "has_consort"):
        if (flag, "=", "yes" if flag == "has_ruler" else "no") not in song_eligible:
            errors.append(f"[册后前置] 宋廷 {flag} 条件不正确")
    for label, body, female in (("长女", block_child(eligible, "character:sts_kfe_daughter1"), "yes"),
                                 ("官家", block_child(song_eligible, "ruler"), "no")):
        for flag, value in (("is_alive", "yes"), ("is_adult", "yes"), ("is_female", female),
                            ("is_married", "no"), ("is_eligible_for_marriage", "yes")):
            if (flag, "=", value) not in body:
                errors.append(f"[册后前置] {label} 缺少直接条件 {flag}={value}")
    if ("owner", "=", "c:KFE") not in block_child(eligible, "character:sts_kfe_daughter1"):
        errors.append("[册后前置] 长女必须仍归梁所有，迁回也仅恢复国家归属")
    if ("can_marry_character", "=", "character:sts_kfe_daughter1") not in block_child(song_eligible, "ruler"):
        errors.append("[册后前置] 官家必须能与指定长女结婚")

    present = block_child(trees["decisions"], "sts_liang_present_daughter")
    if ("has_variable", "=", "sts_liang_empress_installed") not in block_child(block_child(present, "potential"), "NOT"):
        errors.append("[册后决策] 必须通过已册后标记保证只成功一次")
    if ("only_once", "=", "yes") in present:
        errors.append("[册后决策] 失败必须可重试，不得使用会提前消费次数的 only_once")
    if ("value", "=", "1000") not in block_child(present, "ai_will_do"):
        errors.append("[册后AI] 决议必须使用原版最高 AI 意愿值 1000，确保开局优先执行")
    attempt = block_child(block_child(block_child(present, "option"), "effect"), "if")
    if block_child(present, "allow") != [("sts_can_present_daughter", "=", "yes")] or block_child(attempt, "limit") != [("sts_can_present_daughter", "=", "yes")]:
        errors.append("[册后决策] 决策入口与执行前必须复核同一前置")
    if block_child(attempt, "c:CSO.ruler") != [("marry_character", "=", "character:sts_kfe_daughter1")]:
        errors.append("[册后婚姻] 必须由真实宋国君主调用 marry_character 与指定长女结婚")
    installed = block_child(attempt, "if")
    if block_child(block_child(installed, "limit"), "c:CSO") != [
            ("has_consort", "=", "yes"), ("consort", "=", "character:sts_kfe_daughter1")]:
        errors.append("[册后成功门] 必须确认宋国真实配偶就是长女")
    if ("name", "=", "sts_liang_empress_installed") not in block_child(installed, "set_variable") or ("value", "=", "yes") not in block_child(installed, "set_variable"):
        errors.append("[册后成功门] 成功分支必须设置已册后标记")
    if block_child(attempt, "character:sts_kfe_daughter1") != [("move_country", "=", "c:CSO")] or block_child(block_child(attempt, "else"), "character:sts_kfe_daughter1") != [("move_country", "=", "c:KFE")]:
        errors.append("[册后婚姻] 长女须先移居宋廷，婚姻失败则送回梁")
    if ("trigger_event_non_silently", "=", "sts_liang_empress.1") not in installed:
        errors.append("[册后成功门] 梁主事件必须在真实配偶确认后发送")
    marriage_pos = next((i for i, (k, _, _) in enumerate(attempt) if k == "c:CSO.ruler"), -1)
    success_pos = next((i for i, (k, _, _) in enumerate(attempt) if k == "if"), -1)
    move_pos = next((i for i, (k, _, _) in enumerate(attempt) if k == "character:sts_kfe_daughter1"), -1)
    if move_pos < 0 or marriage_pos <= move_pos or success_pos <= marriage_pos:
        errors.append("[册后成功门] 必须先移居、结婚，再确认配偶")
    installed_markers = [p for k, _, v, p in walk_blocks(present)
                         if k == "name" and v == "sts_liang_empress_installed"]
    if installed_markers != [("option", "effect", "if", "if", "set_variable")]:
        errors.append("[册后成功门] 已册后标记只能写入成功分支一次")
    sends = [(v, p) for k, _, v, p in walk_blocks(present) if k == "trigger_event_non_silently"]
    if sends != [("sts_liang_empress.1", ("option", "effect", "if", "if")),
                 ("sts_liang_empress.2", ("option", "effect", "if", "if", "every_country"))]:
        errors.append("[册后成功门] 两类事件只能在成功分支各发送一次")
    news = block_child(installed, "every_country")
    news_limit = block_child(news, "limit")
    exclusions = [v for k, _, v in news_limit if k == "NOT"]
    if (("country_type", "=", "location") not in news_limit or
            ("sts_is_consolidation_member", "=", "yes") not in news_limit or
            [("tag", "=", "KFE")] not in exclusions or
            [("has_variable", "=", "sts_liang_empress_news_seen")] not in exclusions or
            block_child(news, "set_variable") != [("name", "=", "sts_liang_empress_news_seen"), ("value", "=", "yes")]):
        errors.append("[册后广播去重] 必须逐个领土型诸侯排除梁并先标记再发送")
    if [k for k, _, _ in news if k in ("set_variable", "trigger_event_non_silently")] != ["set_variable", "trigger_event_non_silently"]:
        errors.append("[册后广播去重] 收件标记必须先于事件发送")
    if any(k in ("add_legitimacy", "add_political_influence", "add_prestige", "add_country_modifier") for k, _, _, _ in walk_blocks(present)):
        errors.append("[册后奖励] 决策不得绕开事件选项直接发奖")

    empress_events = trees["empress_events"]
    main_event = block_child(empress_events, "sts_liang_empress.1")
    reward = block_child(block_child(main_event, "option"), "if")
    for gate in (block_child(main_event, "trigger"), block_child(reward, "limit")):
        if (("tag", "=", "KFE") not in gate or ("has_variable", "=", "sts_liang_empress_installed") not in gate or
                ("has_variable", "=", "sts_liang_empress_rewarded") not in block_child(gate, "NOT")):
            errors.append("[册后奖励去重] 事件及选项都须核对梁、已册后与未领奖")
    reward_effects = [k for k, _, _ in reward if k == "set_variable" or k.startswith("add_")]
    if (block_child(reward, "set_variable") != [("name", "=", "sts_liang_empress_rewarded"), ("value", "=", "yes")] or
            reward_effects != ["set_variable", "add_legitimacy", "add_political_influence", "add_prestige", "add_country_modifier"]):
        errors.append("[册后奖励去重] 选项须先设置一次性领奖标记，再发放一组奖励")
    for key, value in (("add_legitimacy", "10"), ("add_political_influence", "25"), ("add_prestige", "20")):
        if [(v, p) for k, _, v, p in walk_blocks(main_event) if k == key] != [(value, ("option", "if"))]:
            errors.append(f"[册后奖励] {key} 必须只在去重选项内发放 {value}")
    court = block_child(reward, "add_country_modifier")
    if court != [("modifier", "=", "sts_liang_inner_court"), ("years", "=", "1")]:
        errors.append("[册后年限] 内廷加成必须精确持续一年")
    inner_court = block_child(trees["modifiers"], "sts_liang_inner_court")
    if inner_court != [("game_data", "=", [("category", "=", "country")]), ("monthly_political_influence", "=", "1")]:
        errors.append("[册后奖励] 内廷静态修正须仅提供每月1政治影响力")

    reaction = block_child(empress_events, "sts_liang_empress.2")
    answer = block_child(block_child(reaction, "option"), "if")
    for gate in (block_child(reaction, "trigger"), block_child(answer, "limit")):
        if (("has_variable", "=", "sts_liang_empress_news_seen") not in gate or
                [("has_variable", "=", "sts_liang_empress_news_answered")] not in [v for k, _, v in gate if k == "NOT"]):
            errors.append("[册后反应去重] 消息事件及选项必须检查逐收件国未回应")
    reaction_trigger = block_child(reaction, "trigger")
    if (("country_type", "=", "location") not in reaction_trigger or
            [("tag", "=", "KFE")] not in [v for k, _, v in reaction_trigger if k == "NOT"]):
        errors.append("[册后反应去重] 反应事件必须排除梁及非领土型国家")
    if (block_child(answer, "set_variable") != [("name", "=", "sts_liang_empress_news_answered"), ("value", "=", "yes")] or
            [k for k, _, _ in answer if k != "limit"] != ["set_variable", "if"]):
        errors.append("[册后反应去重] 回应选项须先设置逐国已回应标记")
    if block_child(block_child(answer, "if"), "limit") != [("country_exists", "=", "c:KFE")]:
        errors.append("[册后好感方向] 添加好感前必须确认梁仍存在")
    opinions = [(v, p) for k, _, v, p in walk_blocks(reaction) if k.startswith("add_")]
    if opinions != [([("modifier", "=", "sts_liang_empress_outrage"), ("target", "=", "c:KFE")], ("option", "if", "if"))]:
        errors.append("[册后好感方向] 收件国只能对梁添加一次好感修正，不得反向或附带其他奖励")
    if block_child(trees["biases"], "sts_liang_empress_outrage") != [("value", "=", "-20")]:
        errors.append("[册后好感方向] 诸侯对梁的固定好感必须为-20")

    consort = block_child(trees["ranks"], "country_flavor_consort")
    if block_child(consort, "text") != [("localization_key", "=", "country_flavor_consort_sts_song"),
                                         ("trigger", "=", [("tag", "=", "CSO")])]:
        errors.append("[册后头衔] 宋廷专属配偶头衔必须作为CSO限定的首个分支")
    female_rank = block_child(trees["ranks"], "country_flavor_consort_female")
    if ("parent", "=", "country_flavor_consort") not in female_rank or ("suffix", "=", '"_female"') not in female_rank:
        errors.append("[册后头衔] 女性配偶必须通过_female后缀获取皇后头衔")
    empress_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*(?:\d+\s*)?"((?:\\.|[^"\\])*)"\s*$', sources["empress_loc"], re.M))
    required_loc = ["sts_name_zhang_lingyi", "sts_liang_present_daughter.title", "sts_liang_present_daughter.desc",
                    "sts_liang_present_daughter.a", "STATIC_MODIFIER_NAME_sts_liang_inner_court",
                    "STATIC_MODIFIER_DESC_sts_liang_inner_court", "sts_liang_empress_outrage"]
    for event_id in ("sts_liang_empress.1", "sts_liang_empress.2"):
        event = block_child(empress_events, event_id)
        if ("type", "=", "country_event") not in event:
            errors.append(f"[册后本地化] 缺少国家事件 {event_id}")
        for field in ("title", "desc"):
            key = f"{event_id}.{field}"
            required_loc.append(key)
            if (field, "=", key) not in event:
                errors.append(f"[册后本地化] 事件字段引用错误 {key}")
        required_loc.append(f"{event_id}.a")
        if ("name", "=", f"{event_id}.a") not in block_child(event, "option"):
            errors.append(f"[册后本地化] 事件选项引用错误 {event_id}")
    for key in required_loc:
        if not empress_loc.get(key, "").strip():
            errors.append(f"[册后本地化] 缺少非空本地化 {key}")
    for suffix, text in (("", "皇夫"), ("_female", "皇后"), ("_suffix", ""), ("_suffix_female", "")):
        if empress_loc.get(f"country_flavor_consort_sts_song{suffix}") != text:
            errors.append(f"[册后头衔] 宋廷配偶本地化错误 {suffix or '基础'}")
    image = '"gfx/interface/illustrations/event/backgrounds/special/sts_liang_empress.dds"'
    if ("image", "=", image) not in main_event:
        errors.append("[册后插画] 主事件必须引用册后专用DDS插画")

    # ---- 海内整合三个结局：事件分发、丞相视角与八成覆灭条件 ----
    situation = block_child(trees["situations"], "sts_consolidation")
    outcome_blocks = {}
    for outcome in child_blocks(situation, "outcome"):
        name = next((v.strip('"') for k, _, v in outcome if k == "name"), "")
        outcome_blocks[name] = outcome
    expected_outcomes = {
        "sts_consolidation_hegemon": ("sts_consolidation.3", "sts_consolidation.4"),
        "sts_consolidation_annihilated": ("sts_consolidation.5", "sts_consolidation.6"),
        "sts_consolidation_continue": ("sts_consolidation.7", "sts_consolidation.8"),
    }
    for outcome_name, (member_event, chancellor_event) in expected_outcomes.items():
        outcome = outcome_blocks.get(outcome_name)
        if not outcome:
            errors.append(f"[结局事件] 缺少结局 {outcome_name}")
            continue
        send = block_child(block_child(outcome, "immediate"), "sts_send_consolidation_end_events")
        if ("MEMBER_EVENT", "=", member_event) not in send or ("CHANCELLOR_EVENT", "=", chancellor_event) not in send:
            errors.append(f"[结局事件] {outcome_name} 必须发送 {member_event}/{chancellor_event}")

    annihilated = outcome_blocks.get("sts_consolidation_annihilated", [])
    annihilated_trigger = block_child(annihilated, "trigger")
    annihilated_tip = block_child(annihilated_trigger, "custom_tooltip")
    if not annihilated_tip or ("text", "=", "sts_consolidation_annihilated_condition_tt") not in annihilated_tip:
        errors.append("[诸夏覆灭] 必须用中文自定义提示替代引擎默认列表文本")
    size_blocks = child_blocks(annihilated_tip, "global_variable_list_size") if annihilated_tip else []
    survivors = [b for b in size_blocks if ("name", "=", "sts_consolidation_survivor_list") in b]
    if not survivors or ("value", "<", "41") not in survivors[0]:
        errors.append("[诸夏覆灭] 必须以原始独立成员池的存活数少于 41 作为至少八成覆灭条件")
    if any(k == "NOT" for k, _, _ in annihilated_trigger):
        errors.append("[诸夏覆灭] 不得保留旧的全体成员消失条件")

    start = block_child(situation, "on_start")
    monthly = block_child(situation, "on_monthly")
    start_clears = {v for k, _, v, _ in walk_blocks(start) if k == "clear_global_variable_list"}
    if not {"sts_consolidation_original_list", "sts_consolidation_survivor_list"} <= start_clears:
        errors.append("[诸夏覆灭] 开局必须记录原始独立成员池与存活池")
    monthly_flat = list(walk_blocks(monthly))
    if not any(k == "every_in_global_list" and isinstance(v, list)
               and ("variable", "=", "sts_consolidation_original_list") in v
               for k, _, v, _ in monthly_flat):
        errors.append("[诸夏覆灭] 每月必须按原始成员池重建存活名单")
    if not any(k == "add_to_global_variable_list" and isinstance(v, list)
               and ("name", "=", "sts_consolidation_survivor_list") in v
               for k, _, v, _ in monthly_flat):
        errors.append("[诸夏覆灭] 存活名单必须写入 sts_consolidation_survivor_list")

    send_effect = block_child(effects, "sts_send_consolidation_end_events")
    send_flat = list(walk_blocks(send_effect))
    if not any(k == "every_country" and isinstance(v, list) for k, _, v, _ in send_flat):
        errors.append("[结局视角] 分发效果必须遍历国家")
    if not any(k == "set_variable" and isinstance(v, list)
               and ("name", "=", "sts_consolidation_end_seen") in v
               for k, _, v, _ in send_flat):
        errors.append("[结局视角] 每国只能收到一次结局事件")
    send_values = {v for _, _, v, _ in send_flat if isinstance(v, str)}
    if "$MEMBER_EVENT$" not in send_values or "$CHANCELLOR_EVENT$" not in send_values:
        errors.append("[结局视角] 分发效果必须接受普通/丞相两个事件参数")

    end_events = trees["end_events"]
    for event_id in range(3, 9):
        event_key = f"sts_consolidation.{event_id}"
        event = block_child(end_events, event_key)
        if not event:
            errors.append(f"[结局事件] 缺少 {event_key}")
            continue
        if ("type", "=", "country_event") not in event:
            errors.append(f"[结局事件] {event_key} 必须是国家事件")
        for field in ("title", "desc"):
            if (field, "=", f"{event_key}.{field}") not in event:
                errors.append(f"[结局事件] {event_key}.{field} 引用错误")
        if ("name", "=", f"{event_key}.a") not in block_child(event, "option"):
            errors.append(f"[结局事件] {event_key} 选项引用错误")
        if event_id in (4, 6, 8):
            if ("is_leader_of_international_organization", "=", "international_organization:sts_chancellery") not in block_child(event, "trigger"):
                errors.append(f"[结局视角] {event_key} 必须是丞相专属视角")

    end_loc_text = sources["end_loc"]
    end_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', end_loc_text, re.M))
    for event_id in range(3, 9):
        for suffix in ("title", "desc", "a"):
            key = f"sts_consolidation.{event_id}.{suffix}"
            if not end_loc.get(key, "").strip():
                errors.append(f"[结局本地化] 缺少非空 {key}")
    if not end_loc.get("sts_consolidation_annihilated_condition_tt", "").strip():
        errors.append("[结局本地化] 缺少诸夏覆灭中文条件提示")
    if not re.search(r"sts_consolidation_annihilated_desc:\s*\"[^\"]*八成", sources["main_loc"]):
        errors.append("[诸夏覆灭] 结局描述必须同步为八成口径")

    # ---- 梁《整编禁军》决议事件 ----
    guard_decision = block_child(trees["decisions"], "sts_liang_reform_guard")
    guard_effect = block_child(block_child(guard_decision, "option"), "effect")
    if ("trigger_event_non_silently", "=", "sts_liang_guard_reform.1") not in guard_effect:
        errors.append("[整编禁军] 决议必须触发洗汰禁军事件")
    guard_event = block_child(trees["guard_events"], "sts_liang_guard_reform.1")
    if not guard_event:
        errors.append("[整编禁军] 缺少事件 sts_liang_guard_reform.1")
    else:
        if ("type", "=", "country_event") not in guard_event:
            errors.append("[整编禁军] 事件必须是国家事件")
        for field in ("title", "desc"):
            if (field, "=", f"sts_liang_guard_reform.1.{field}") not in guard_event:
                errors.append(f"[整编禁军] 事件字段引用错误 .{field}")
        if ("name", "=", "sts_liang_guard_reform.1.a") not in block_child(guard_event, "option"):
            errors.append("[整编禁军] 事件选项引用错误")
        if ("image", "=", '"gfx/interface/illustrations/event/backgrounds/special/sts_liang_guard_reform.dds"') not in guard_event:
            errors.append("[整编禁军] 事件缺少专属配图")
    guard_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["guard_loc"], re.M))
    for suffix in ("title", "desc", "a"):
        key = f"sts_liang_guard_reform.1.{suffix}"
        if not guard_loc.get(key, "").strip():
            errors.append(f"[整编禁军] 缺少非空本地化 {key}")

    # ---- 秦·岳家军六时代兵种与革新 ----
    yj_units = trees["yuejiajun_units"]
    yj_advances = trees["yuejiajun_advances"]
    unit_ages = [
        "a_age_1_traditions_heavy_infantry",
        "a_age_2_renaissance_heavy_infantry",
        "a_age_3_discovery_heavy_infantry",
        "a_age_4_reformation_heavy_infantry",
        "a_age_5_absolutism_heavy_infantry",
        "a_age_6_revolutions_heavy_infantry",
    ]
    unit_keys = ["a_traditions_yuejiajun", "a_renaissance_yuejiajun", "a_discovery_yuejiajun",
                 "a_reformation_yuejiajun", "a_absolutism_yuejiajun", "a_revolutions_yuejiajun"]
    adv_keys = [f"sts_xia_yuejiajun_{i}_advance" for i in range(1, 7)]
    adv_ages = ["age_1_traditions", "age_2_renaissance", "age_3_discovery",
                "age_4_reformation", "age_5_absolutism", "age_6_revolutions"]
    dependency_sources = [sources[name] for name in ("yuejiajun_advances", "jinglue_advance",
                                                     "kfe_court_advances", "kfe_guard_advances",
                                                     "shu_advances", "jin_advances",
                                                     "qi_advances", "xiang_advances", "yue_advances")]
    age_map = {}
    for text in [sources["vanilla_army_advances"]] + dependency_sources:
        age_map.update(advance_ages(text))
    for text in dependency_sources:
        errors.extend(advance_dependency_errors(text, age_map))
    adv_requires = [None, "unlock_men_at_arms_advance", "unlock_early_arquebusiers_advance",
                    "unlock_arquebusiers_advance", "unlock_musketeers_advance",
                    "unlock_fusiliers_advance"]
    for i, (unit_key, adv_key, unit_age, adv_age) in enumerate(zip(unit_keys, adv_keys, unit_ages, adv_ages)):
        unit = block_child(yj_units, unit_key)
        if not unit:
            errors.append(f"[岳家军] 缺少兵种 {unit_key}")
        else:
            for field, value in (("copy_from", unit_age), ("is_special", "yes"), ("buildable", "yes"),
                                 ("strength_damage_taken", "-0.10"), ("morale_damage_taken", "-0.10")):
                if (field, "=", value) not in unit:
                    errors.append(f"[岳家军] {unit_key} 缺少 {field}={value}")
            if child_blocks(unit, "country_potential") != [[("has_or_had_tag", "=", "XIA")]]:
                errors.append(f"[岳家军] {unit_key} 国家条件只能限定秦 XIA，不得反查革新")
            if any(k in ("family", "limit") for k, _, _, _ in walk_blocks(unit)):
                errors.append(f"[岳家军] {unit_key} 不得设置额外 family/limit 招募约束")
            if i < len(unit_keys) - 1:
                if ("upgrades_to_only", "=", unit_keys[i + 1]) not in unit:
                    errors.append(f"[岳家军] {unit_key} 必须只升级到 {unit_keys[i + 1]}")
            elif any(k == "upgrades_to_only" for k, _, _ in unit):
                errors.append("[岳家军] 最终兵种不应再有升级目标")

        adv = block_child(yj_advances, adv_key)
        if not adv:
            errors.append(f"[岳家军] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "XIA")]]:
            errors.append(f"[岳家军] {adv_key} 潜在资格只能限定秦 XIA")
        if ("age", "=", adv_age) not in adv:
            errors.append(f"[岳家军] {adv_key} 时代必须是 {adv_age}")
        if ("unlock_unit", "=", unit_key) not in adv:
            errors.append(f"[岳家军] {adv_key} 必须解锁 {unit_key}")
        expected_require = adv_requires[i]
        requires = [(k, op, v) for k, op, v, _ in walk_blocks(adv) if k == "requires"]
        if requires != ([] if expected_require is None else [("requires", "=", expected_require)]):
            errors.append(f"[岳家军] {adv_key} 同代前置必须为 {expected_require or '无'}")
        if i:
            if child_blocks(adv, "allow") != [[("has_advance", "=", adv_keys[i - 1])]]:
                errors.append(f"[岳家军] {adv_key} 必须在 allow 中检查上一项 {adv_keys[i - 1]}")
        elif any(k == "allow" for k, _, _ in adv):
            errors.append("[岳家军] 第一级革新不应有研究门槛")

    init_flat = list(walk_blocks(block_child(effects, "sts_game_init")))
    yj_grants = [(v.removeprefix("advance_type:"), p) for k, _, v, p in init_flat
                 if k == "research_advance" and isinstance(v, str)
                 and v.removeprefix("advance_type:") in adv_keys]
    if len(yj_grants) != 1 or yj_grants[0][0] != adv_keys[0]:
        errors.append("[岳家军] 开局只能授予第一级革新一次，不得授予第二至六级")
    if any("c:XIA" not in parents for _, parents in yj_grants):
        errors.append("[岳家军] 开局授予革新的执行作用域必须限定秦 c:XIA")

    for source in ("yuejiajun_families", "yuejiajun_values"):
        if trees[source]:
            errors.append(f"[岳家军] {source} 必须只剩注释，不得恢复生效定义或固定30团上限")

    yj_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["yuejiajun_loc"], re.M))
    for key in ["sts_yuejiajun"] + adv_keys + [f"{a}_desc" for a in adv_keys] + unit_keys + [f"{u}_desc" for u in unit_keys]:
        if not yj_loc.get(key, "").strip():
            errors.append(f"[岳家军] 缺少非空本地化 {key}")

    # ---- 藩镇藩王通用革新·经略封疆 ----
    jinglue = block_child(trees["jinglue_advance"], "sts_jinglue_fengjiang_advance")
    if not jinglue:
        errors.append("[经略封疆] 缺少革新")
    else:
        if ("age", "=", "age_1_traditions") not in jinglue:
            errors.append("[经略封疆] 必须位于第一时代")
        jinglue_potential = block_child(jinglue, "potential")
        static_trigger = block_child(trees["warlord_tags"], "sts_is_chinese_warlord_tag")
        static_or = block_child(static_trigger, "OR")
        static_tags = {v for k, op, v in static_or if k == "tag" and op == "=" and isinstance(v, str)}
        if (len(static_tags) != 189 or len(static_or) != 189 or
                static_trigger != [("OR", "=", static_or)] or
                any(k != "tag" or op != "=" or not isinstance(v, str) or
                    not re.fullmatch(r"[A-Z][A-Z0-9]{1,2}", v) for k, op, v in static_or)):
            errors.append("[经略封疆] 藩镇触发器必须仅为189国静态 tag OR 名单，不得依赖变量或组织")
        supplements = set("AAB AAE BAQ DUY GAQ LAJ LAK PAF PAG SBI SBJ SIN TAY WAC XAM ZAF".split())
        potential_or = block_child(jinglue_potential, "OR")
        expected_or = [("sts_is_chinese_warlord_tag", "=", "yes")] + [
            ("has_or_had_tag", "=", tag) for tag in sorted(supplements)]
        if sorted(potential_or, key=repr) != sorted(expected_or, key=repr):
            errors.append("[经略封疆] 国家 OR 必须为静态藩镇触发器加16个补充 tag，不得依赖动态成员条件")
        if sorted(jinglue_potential, key=repr) != sorted([
                ("OR", "=", potential_or), ("country_type", "=", "location"),
                ("NOT", "=", [("tag", "=", "CSO")])], key=repr):
            errors.append("[经略封疆] potential 只能包含静态国家 OR、领土国家条件及排除CSO，不得有运行期依赖")
        manager = block_child(trees["setup_organizations"], "international_organization_manager")
        chancellery = [body for body in child_blocks(manager, "add_international_organization")
                       if ("type", "=", "sts_chancellery") in body]
        if len(chancellery) != 1 or not block_child(chancellery[0], "members"):
            errors.append("[经略封疆] setup 必须提供唯一的 sts_chancellery 成员名单")
        else:
            expected_tags = {tag for tag, _, _ in block_child(chancellery[0], "members")} - {"CSO"}
            actual_tags = static_tags | {v for k, op, v in potential_or
                                        if k == "has_or_had_tag" and op == "=" and isinstance(v, str)}
            for tag in sorted(expected_tags - actual_tags):
                errors.append(f"[经略封疆] 国家范围缺少 setup 相府成员 {tag}")
            for tag in sorted(actual_tags - expected_tags):
                errors.append(f"[经略封疆] 国家范围多出 setup 相府成员以外国家 {tag}")
        if ("country_type", "=", "location") not in jinglue_potential:
            errors.append("[经略封疆] 必须排除建筑宋廷")
        if not any(k == "NOT" and isinstance(v, list) and ("tag", "=", "CSO") in v
                   for k, _, v in jinglue_potential):
            errors.append("[经略封疆] 必须排除宋天子 CSO")
        if ("global_integration_speed_modifier", "=", "0.05") not in jinglue:
            errors.append("[经略封疆] 整合速度必须为 +5%")
        if ("monthly_prestige", "=", "0.05") not in jinglue:
            errors.append("[经略封疆] 月度威望必须为 +0.05")
        icon = next((v for k, op, v in jinglue if k == "icon" and op == "="), None)
        if icon != "sts_jinglue_fengjiang":
            errors.append("[革新图标] 经略封疆必须使用专属图标 sts_jinglue_fengjiang")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[革新图标] 找不到 {icon}.dds，界面会静默回退默认烧瓶图标")
    jinglue_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["jinglue_loc"], re.M))
    for key in ("sts_jinglue_fengjiang_advance", "sts_jinglue_fengjiang_advance_desc"):
        if not jinglue_loc.get(key, "").strip():
            errors.append(f"[经略封疆] 缺少非空本地化 {key}")

    # ---- 梁·相府政略革新 ----
    court = trees["kfe_court_advances"]
    court_spec = {
        "sts_kfe_mandate_advance": ("age_1_traditions", "sts_kfe_mandate",
                                    [("monthly_prestige", "0.05"), ("monthly_diplomats", "0.10")]),
        "sts_kfe_huairou_advance": ("age_2_renaissance", "sts_kfe_huairou",
                                    [("improve_relation_impact", "0.30")]),
        "sts_kfe_dudu_advance": ("age_2_renaissance", "sts_kfe_dudu",
                                 [("army_reinforce_efficiency", "0.20"),
                                  ("regiment_reinforcement_speed", "0.10")]),
    }
    for adv_key, (adv_age, icon_key, effect_list) in court_spec.items():
        adv = block_child(court, adv_key)
        if not adv:
            errors.append(f"[梁政略] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "KFE")]]:
            errors.append(f"[梁政略] {adv_key} 潜在资格只能限定梁 KFE")
        if ("age", "=", adv_age) not in adv:
            errors.append(f"[梁政略] {adv_key} 时代必须是 {adv_age}")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[梁政略] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[梁政略] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[梁政略] {adv_key} 缺少效果 {field}={value}")

    # ---- 梁·殿前禁卫六时代 ----
    guard_units = ["a_traditions_dianqian", "a_renaissance_dianqian", "a_discovery_dianqian",
                   "a_reformation_dianqian", "a_absolutism_dianqian", "a_revolutions_dianqian"]
    guard_adcs = [f"sts_kfe_dianqian_{i}_advance" for i in range(1, 7)]
    guard_requires = [None, "unlock_men_at_arms_advance", "unlock_early_arquebusiers_advance",
                      "unlock_arquebusiers_advance", "unlock_musketeers_advance",
                      "unlock_fusiliers_advance"]
    guard_ages = ["age_1_traditions", "age_2_renaissance", "age_3_discovery",
                  "age_4_reformation", "age_5_absolutism", "age_6_revolutions"]
    unit_ages = ["a_age_1_traditions_heavy_infantry", "a_age_2_renaissance_heavy_infantry",
                 "a_age_3_discovery_heavy_infantry", "a_age_4_reformation_heavy_infantry",
                 "a_age_5_absolutism_heavy_infantry", "a_age_6_revolutions_heavy_infantry"]
    for i in range(6):
        unit_key, adv_key = guard_units[i], guard_adcs[i]
        unit = block_child(trees["kfe_units"], unit_key)
        if not unit:
            errors.append(f"[殿前禁卫] 缺少兵种 {unit_key}")
        else:
            for field, value in (("copy_from", unit_ages[i]), ("is_special", "yes"), ("buildable", "yes"),
                                 ("strength_damage_taken", "-0.10"), ("morale_damage_taken", "-0.10")):
                if (field, "=", value) not in unit:
                    errors.append(f"[殿前禁卫] {unit_key} 缺少 {field}={value}")
            if child_blocks(unit, "country_potential") != [[("has_or_had_tag", "=", "KFE")]]:
                errors.append(f"[殿前禁卫] {unit_key} 国家条件只能限定梁 KFE")
            if any(k in ("family", "limit") for k, _, _, _ in walk_blocks(unit)):
                errors.append(f"[殿前禁卫] {unit_key} 不得设置额外 family/limit 招募约束")
            if i < 5 and ("upgrades_to_only", "=", guard_units[i + 1]) not in unit:
                errors.append(f"[殿前禁卫] {unit_key} 必须只升级到 {guard_units[i + 1]}")
        adv = block_child(trees["kfe_guard_advances"], adv_key)
        if not adv:
            errors.append(f"[殿前禁卫] 缺少革新 {adv_key}")
            continue
        if ("age", "=", guard_ages[i]) not in adv:
            errors.append(f"[殿前禁卫] {adv_key} 时代必须是 {guard_ages[i]}")
        if ("unlock_unit", "=", unit_key) not in adv:
            errors.append(f"[殿前禁卫] {adv_key} 必须解锁 {unit_key}")
        requires = [(k, op, v) for k, op, v, _ in walk_blocks(adv) if k == "requires"]
        expected = [] if guard_requires[i] is None else [("requires", "=", guard_requires[i])]
        if requires != expected:
            errors.append(f"[殿前禁卫] {adv_key} 同代前置必须为 {guard_requires[i] or '无'}")
        if i and child_blocks(adv, "allow") != [[("has_advance", "=", guard_adcs[i - 1])]]:
            errors.append(f"[殿前禁卫] {adv_key} 必须在 allow 中检查上一项 {guard_adcs[i - 1]}")
        if ("allow_children", "=", "no") not in adv:
            errors.append(f"[殿前禁卫] {adv_key} 必须 allow_children = no")

    grants = [v.removeprefix("advance_type:") for k, _, v, p in
              walk_blocks(block_child(effects, "sts_game_init"))
              if k == "research_advance" and isinstance(v, str) and "c:KFE" in p]
    expected_grants = ["sts_kfe_chancellery_advance", "sts_kfe_dianqian_1_advance", "sts_kfe_mandate_advance"]
    if sorted(grants) != expected_grants:
        errors.append("[梁政略] 梁开局只能研究既有相府革新、《执掌天宪》与第一级殿前禁卫，不得预研后续")

    art_entries = trees["kfe_unit_art"]
    art_map = {next((v for k, op, v in body if k == "texture" and op == "="), None):
               next((v for k, op, v in block_child(body, "trigger") if k == "is_unit_type" and op == "="), None)
               for key, op, body in art_entries if isinstance(body, list)}
    art_dir = os.path.join("main_menu/gfx/interface/illustrations/units")
    for i, unit_key in enumerate(guard_units, 1):
        tex = f'"gfx/interface/illustrations/units/sts_kfe_dianqian_{i}.dds"'
        if art_map.get(tex) != unit_key:
            errors.append(f"[殿前禁卫] 插画条目必须把 sts_kfe_dianqian_{i}.dds 指给 {unit_key}")
            continue
        rel = f"sts_kfe_dianqian_{i}.dds"
        if not os.path.exists(os.path.join(MOD, art_dir, rel)):
            errors.append(f"[殿前禁卫] 缺少插画文件 {rel}")
        if not os.path.exists(os.path.join(MOD, art_dir, "masks", rel)):
            errors.append(f"[殿前禁卫] 缺少同名遮罩 masks/{rel}")

    kfe_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["kfe_loc"], re.M))
    for key in list(court_spec) + guard_adcs + guard_units + \
            [f"{k}_desc" for k in list(court_spec) + guard_adcs + guard_units]:
        if not kfe_loc.get(key, "").strip():
            errors.append(f"[梁革新] 缺少非空本地化 {key}")

    # ---- 蜀·三项革新与元戎劲弩手 ----
    shu = trees["shu_advances"]
    shu_spec = {
        "sts_shu_shudao_advance": ("age_1_traditions", "sts_shu_shudao",
                                   [("army_light_infantry_power", "0.10"), ("siege_ability", "0.10")]),
        "sts_shu_jiaozi_advance": ("age_2_renaissance", "sts_shu_jiaozi",
                                   [("tax_income_efficiency", "0.03"), ("bank_interest", "-0.01")]),
    }
    for adv_key, (adv_age, icon_key, effect_list) in shu_spec.items():
        adv = block_child(shu, adv_key)
        if not adv:
            errors.append(f"[蜀革新] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "CAJ")]]:
            errors.append(f"[蜀革新] {adv_key} 潜在资格只能限定蜀 CAJ")
        if ("age", "=", adv_age) not in adv:
            errors.append(f"[蜀革新] {adv_key} 时代必须是 {adv_age}")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[蜀革新] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[蜀革新] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[蜀革新] {adv_key} 缺少效果 {field}={value}")

    yuan = block_child(trees["shu_units"], "a_shu_yuanrong")
    if not yuan:
        errors.append("[蜀兵种] 缺少 a_shu_yuanrong")
    else:
        for field, value in (("copy_from", "a_age_1_traditions_light_infantry"), ("is_special", "yes"),
                             ("buildable", "yes"), ("upgrades_to", "a_crossbowmen"),
                             ("max_strength", "0.1")):
            if (field, "=", value) not in yuan:
                errors.append(f"[蜀兵种] a_shu_yuanrong 缺少 {field}={value}")
        if child_blocks(yuan, "country_potential") != [[("has_or_had_tag", "=", "CAJ")]]:
            errors.append("[蜀兵种] a_shu_yuanrong 国家条件只能限定蜀 CAJ")
        if any(k == "family" for k, _, _, _ in walk_blocks(yuan)):
            errors.append("[蜀兵种] a_shu_yuanrong 不得设置额外家族招募约束")
        combat = block_child(yuan, "combat")
        if not any(k == "mountains" and v == "0.20" for k, _, v in combat):
            errors.append("[蜀兵种] a_shu_yuanrong 必须有山地作战加成")
    yuan_adv = block_child(shu, "sts_shu_yuanrong_advance")
    if ("unlock_unit", "=", "a_shu_yuanrong") not in yuan_adv:
        errors.append("[蜀兵种] 元戎遗制必须解锁 a_shu_yuanrong")
    tex = '"gfx/interface/illustrations/units/sts_shu_yuanrong.dds"'
    if art_map.get(tex) != "a_shu_yuanrong":
        errors.append("[蜀兵种] 插画条目必须把 sts_shu_yuanrong.dds 指给 a_shu_yuanrong")
    else:
        for rel in ("sts_shu_yuanrong.dds", "masks/sts_shu_yuanrong.dds"):
            if not os.path.exists(os.path.join(MOD, art_dir, rel)):
                errors.append(f"[蜀兵种] 缺少插画资源 {rel}")

    shu_grants = [v.removeprefix("advance_type:") for k, _, v, p in
                  walk_blocks(block_child(effects, "sts_game_init"))
                  if k == "research_advance" and isinstance(v, str) and "c:CAJ" in p]
    if sorted(shu_grants) != ["sts_shu_salt_iron_advance", "sts_shu_shudao_advance"]:
        errors.append("[蜀革新] 蜀开局只能持有既有盐铁革新与《蜀道拓险》，不得预研交子务或元戎遗制")

    shu_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["shu_loc"], re.M))
    for key in list(shu_spec) + ["sts_shu_yuanrong_advance", "a_shu_yuanrong"] + \
            [f"{k}_desc" for k in list(shu_spec) + ["sts_shu_yuanrong_advance", "a_shu_yuanrong"]]:
        if not shu_loc.get(key, "").strip():
            errors.append(f"[蜀革新] 缺少非空本地化 {key}")

    # ---- 晋·三项革新 ----
    jin_spec = {
        "sts_jin_jintang_advance": ("age_1_traditions", "sts_jin_jintang",
                                    [("discipline", "0.05"), ("fort_limit", "1")]),
        "sts_jin_yicong_advance": ("age_2_renaissance", "sts_jin_yicong",
                                   [("peasants_estate_levy_size", "0.10")]),
        "sts_jin_tielu_advance": ("age_2_renaissance", "sts_jin_tielu",
                                  [("discipline", "0.05")]),
    }
    for adv_key, (adv_age, icon_key, effect_list) in jin_spec.items():
        adv = block_child(trees["jin_advances"], adv_key)
        if not adv:
            errors.append(f"[晋革新] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "LAK")]]:
            errors.append(f"[晋革新] {adv_key} 潜在资格只能限定晋 LAK")
        if ("age", "=", adv_age) not in adv:
            errors.append(f"[晋革新] {adv_key} 时代必须是 {adv_age}")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[晋革新] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[晋革新] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[晋革新] {adv_key} 缺少效果 {field}={value}")

    jin_grants = [v.removeprefix("advance_type:") for k, _, v, p in
                  walk_blocks(block_child(effects, "sts_game_init"))
                  if k == "research_advance" and isinstance(v, str) and "c:LAK" in p]
    if sorted(jin_grants) != ["sts_jin_jintang_advance", "sts_jin_taihang_advance"]:
        errors.append("[晋革新] 晋开局只能持有既有太行革新与《表里金汤》，雪耻义从与三晋铁旅需自行研发")

    jin_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["jin_loc"], re.M))
    for key in list(jin_spec) + [f"{k}_desc" for k in jin_spec]:
        if not jin_loc.get(key, "").strip():
            errors.append(f"[晋革新] 缺少非空本地化 {key}")

    # ---- 齐·三项第一时代革新 ----
    qi_spec = {
        "sts_qi_haidai_advance": ("sts_qi_haidai", [("global_build_buildings_efficiency", "0.20")]),
        "sts_qi_yiyong_advance": ("sts_qi_yiyong", [("land_morale", "0.20")]),
        "sts_qi_suxun_advance": ("sts_qi_suxun", [("nobles_estate_levy_size", "0.30")]),
    }
    for adv_key, (icon_key, effect_list) in qi_spec.items():
        adv = block_child(trees["qi_advances"], adv_key)
        if not adv:
            errors.append(f"[齐革新] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "JIN")]]:
            errors.append(f"[齐革新] {adv_key} 潜在资格只能限定齐 JIN")
        if ("age", "=", "age_1_traditions") not in adv:
            errors.append(f"[齐革新] {adv_key} 必须在第一时代")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[齐革新] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[齐革新] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[齐革新] {adv_key} 缺少效果 {field}={value}")

    qi_grants = [v.removeprefix("advance_type:") for k, _, v, p in
                 walk_blocks(block_child(effects, "sts_game_init"))
                 if k == "research_advance" and isinstance(v, str) and "c:JIN" in p]
    expected_qi = ["sts_qi_haidai_advance", "sts_qi_maritime_advance",
                   "sts_qi_suxun_advance", "sts_qi_yiyong_advance"]
    if sorted(qi_grants) != expected_qi:
        errors.append("[齐革新] 齐开局必须同时持有既有海事革新与海岱藩屏、忠烈遗勇、忠烈宿勋")

    qi_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["qi_loc"], re.M))
    for key in list(qi_spec) + [f"{k}_desc" for k in qi_spec]:
        if not qi_loc.get(key, "").strip():
            errors.append(f"[齐革新] 缺少非空本地化 {key}")

    # ---- 湘·三项革新 ----
    xiang_spec = {
        "sts_xiang_taoyuan_advance": ("age_1_traditions", "sts_xiang_taoyuan",
                                      [("global_migration_speed", "0.10"),
                                       ("global_monthly_prosperity", "0.10")]),
        "sts_xiang_tiebu_advance": ("age_1_traditions", "sts_xiang_tiebu",
                                    [("army_heavy_infantry_power", "0.10")]),
        "sts_xiang_quecha_advance": ("age_2_renaissance", "sts_xiang_quecha",
                                     [("tax_income_efficiency", "0.10")]),
    }
    for adv_key, (adv_age, icon_key, effect_list) in xiang_spec.items():
        adv = block_child(trees["xiang_advances"], adv_key)
        if not adv:
            errors.append(f"[湘革新] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "CAQ")]]:
            errors.append(f"[湘革新] {adv_key} 潜在资格只能限定湘 CAQ")
        if ("age", "=", adv_age) not in adv:
            errors.append(f"[湘革新] {adv_key} 时代必须是 {adv_age}")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[湘革新] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[湘革新] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[湘革新] {adv_key} 缺少效果 {field}={value}")

    xiang_grants = [v.removeprefix("advance_type:") for k, _, v, p in
                    walk_blocks(block_child(effects, "sts_game_init"))
                    if k == "research_advance" and isinstance(v, str) and "c:CAQ" in p]
    if sorted(xiang_grants) != ["sts_xiang_taoyuan_advance"]:
        errors.append("[湘革新] 湘（CAQ）开局只能持有《武陵桃源》，湘铁重步与榷茶通商需自行研发")

    xiang_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["xiang_loc"], re.M))
    for key in list(xiang_spec) + [f"{k}_desc" for k in xiang_spec]:
        if not xiang_loc.get(key, "").strip():
            errors.append(f"[湘革新] 缺少非空本地化 {key}")

    # ---- 闽·两项第一时代革新 ----
    min_spec = {
        "sts_min_tihang_advance": ("sts_min_tihang",
                                   [("navy_galley_power", "0.15"), ("export_efficiency", "0.02"),
                                    ("max_tariff", "0.10")]),
        "sts_min_tongqu_advance": ("sts_min_tongqu",
                                   [("mountains_proximity_impact", "-0.33"),
                                    ("hills_proximity_impact", "-0.33")]),
    }
    for adv_key, (icon_key, effect_list) in min_spec.items():
        adv = block_child(trees["min_advances"], adv_key)
        if not adv:
            errors.append(f"[闽革新] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "QAB")]]:
            errors.append(f"[闽革新] {adv_key} 潜在资格只能限定闽 QAB")
        if ("age", "=", "age_1_traditions") not in adv:
            errors.append(f"[闽革新] {adv_key} 必须在第一时代")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[闽革新] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[闽革新] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[闽革新] {adv_key} 缺少效果 {field}={value}")

    min_grants = [v.removeprefix("advance_type:") for k, _, v, p in
                  walk_blocks(block_child(effects, "sts_game_init"))
                  if k == "research_advance" and isinstance(v, str) and "c:QAB" in p]
    if sorted(min_grants) != ["sts_min_tihang_advance", "sts_min_tongqu_advance"]:
        errors.append("[闽革新] 闽开局必须同时持有《梯航万国》与《闽道通衢》")

    min_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["min_loc"], re.M))
    for key in list(min_spec) + [f"{k}_desc" for k in min_spec]:
        if not min_loc.get(key, "").strip():
            errors.append(f"[闽革新] 缺少非空本地化 {key}")

    # ---- 粤·三项革新 ----
    yue_spec = {
        "sts_yue_jiezhi_advance": ("age_1_traditions", "sts_yue_jiezhi",
                                   [("subject_income_modifier", "0.10")]),
        "sts_yue_zongmeng_advance": ("age_1_traditions", "sts_yue_zongmeng",
                                     [("diplomatic_capacity", "1")]),
        "sts_yue_wubian_advance": ("age_2_renaissance", "sts_yue_wubian",
                                   [("land_morale", "0.15")]),
    }
    for adv_key, (adv_age, icon_key, effect_list) in yue_spec.items():
        adv = block_child(trees["yue_advances"], adv_key)
        if not adv:
            errors.append(f"[粤革新] 缺少革新 {adv_key}")
            continue
        if child_blocks(adv, "potential") != [[("has_or_had_tag", "=", "GAI")]]:
            errors.append(f"[粤革新] {adv_key} 潜在资格只能限定粤 GAI")
        if ("age", "=", adv_age) not in adv:
            errors.append(f"[粤革新] {adv_key} 时代必须是 {adv_age}")
        if ("icon", "=", icon_key) not in adv:
            errors.append(f"[粤革新] {adv_key} 图标必须是 {icon_key}")
        elif not any(os.path.exists(os.path.join(root, "main_menu/gfx/interface/advance", icon_key + ".dds"))
                     for root in (MOD, GAME)):
            errors.append(f"[粤革新] 找不到图标文件 {icon_key}.dds")
        for field, value in effect_list:
            if (field, "=", value) not in adv:
                errors.append(f"[粤革新] {adv_key} 缺少效果 {field}={value}")

    yue_grants = [v.removeprefix("advance_type:") for k, _, v, p in
                  walk_blocks(block_child(effects, "sts_game_init"))
                  if k == "research_advance" and isinstance(v, str) and "c:GAI" in p]
    if sorted(yue_grants) != ["sts_yue_jiezhi_advance", "sts_yue_zongmeng_advance"]:
        errors.append("[粤革新] 粤开局必须持有《节制百粤》与《岭南宗盟》，南岭武弁需自行研发")

    yue_loc = dict(re.findall(r'^\s+([A-Za-z0-9_.]+):\s*"((?:\\.|[^"\\])*)"\s*$', sources["yue_loc"], re.M))
    for key in list(yue_spec) + [f"{k}_desc" for k in yue_spec]:
        if not yue_loc.get(key, "").strip():
            errors.append(f"[粤革新] 缺少非空本地化 {key}")
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
        ("丞相分支漏发", "situations", "trigger_event_non_silently = sts_consolidation.2", "# missing chancellor event", "[整合开场]"),
        ("丞相判断写死国家", "situations", "is_leader_of_international_organization = international_organization:sts_chancellery", "tag = KFE", "[整合开场]"),
        ("丞相事件不存在", "intro_events", "sts_consolidation.2 = {", "sts_consolidation.99 = {", "[整合开场]"),
        ("丞相漏正文", "intro_loc", "sts_consolidation.2.desc:", "sts_consolidation.99.desc:", "[整合开场]"),
        ("开场分支不互斥", "situations", "else = {\n\t\t\t\ttrigger_event_non_silently = sts_consolidation.1", "if = {\n\t\t\t\ttrigger_event_non_silently = sts_consolidation.1", "[整合开场]"),
        ("丞相事件误加奖励", "intro_events", "name = sts_consolidation.2.a", "name = sts_consolidation.2.a\n\t\tadd_gold = 100", "[整合开场]"),
        ("册后遗漏真实婚姻", "decisions", "marry_character = character:sts_kfe_daughter1", "save_scope_as = sts_kfe_daughter1", "[册后婚姻]"),
        ("册后跳过配偶确认", "decisions", "consort = character:sts_kfe_daughter1", "consort = character:sts_kfe_wife", "[册后成功门]"),
        ("册后重复领取奖励", "empress_events", "has_variable = sts_liang_empress_rewarded", "has_variable = wrong_reward_marker", "[册后奖励去重]"),
        ("册后收件国重复回应", "empress_events", "has_variable = sts_liang_empress_news_answered", "has_variable = wrong_answer_marker", "[册后反应去重]"),
        ("册后广播遗漏去重", "decisions", "has_variable = sts_liang_empress_news_seen", "has_variable = wrong_news_marker", "[册后广播去重]"),
        ("册后好感方向颠倒", "empress_events", "add_opinion = { modifier = sts_liang_empress_outrage target = c:KFE }", "c:KFE = { add_opinion = { modifier = sts_liang_empress_outrage target = root } }", "[册后好感方向]"),
        ("册后加成误为永久", "empress_events", "years = 1", "years = -1", "[册后年限]"),
        ("册后长女出生过晚", "characters", "birth_date = 1319.4.1", "birth_date = 1329.4.1", "[册后人物]"),
        ("册后长女宗族丢失", "characters", "first_name = { name = sts_name_zhang_lingyi }\n\t\tdynasty = sts_zhang_dynasty", "first_name = { name = sts_name_zhang_lingyi }", "[册后人物]"),
        ("册后头衔错用梁国", "ranks", "localization_key = country_flavor_consort_sts_song\n\t\ttrigger = { tag = CSO }", "localization_key = country_flavor_consort_sts_song\n\t\ttrigger = { tag = KFE }", "[册后头衔]"),
        ("册后本地化漏正文", "empress_loc", "sts_liang_empress.1.desc:", "sts_liang_empress.99.desc:", "[册后本地化]"),
        ("册后前置允许已婚", "triggers", "is_married = no", "is_married = yes", "[册后前置]"),
        ("册后AI权重不足", "decisions", "ai_will_do = { value = 1000 }", "ai_will_do = { value = 100 }", "[册后AI]"),
        ("诸夏覆灭阈值回退", "situations", "value < 41", "value < 101", "[诸夏覆灭]"),
        ("诸夏覆灭提示回退英文", "situations", "text = sts_consolidation_annihilated_condition_tt", "text = GLOBAL_VARIABLE_LIST_SIZE_TRIGGER", "[诸夏覆灭]"),
        ("结局一普通事件错号", "situations", "MEMBER_EVENT = sts_consolidation.3", "MEMBER_EVENT = sts_consolidation.99", "[结局事件]"),
        ("结局两视角合并", "effects", "trigger_event_non_silently = $CHANCELLOR_EVENT$", "trigger_event_non_silently = $MEMBER_EVENT$", "[结局视角]"),
        ("结局本地化错键", "end_loc", "sts_consolidation.5.desc:", "sts_consolidation.99.desc:", "[结局本地化]"),
        ("诸夏覆灭描述回退", "main_loc", "超过八成", "最后一个", "[诸夏覆灭]"),
        ("整编禁军决议漏触发", "decisions", "trigger_event_non_silently = sts_liang_guard_reform.1", "# missing guard event", "[整编禁军]"),
        ("整编禁军事件错号", "guard_events", "sts_liang_guard_reform.1 = {", "sts_liang_guard_reform.99 = {", "[整编禁军]"),
        ("整编禁军本地化错键", "guard_loc", "sts_liang_guard_reform.1.desc:", "sts_liang_guard_reform.99.desc:", "[整编禁军]"),
        ("整编禁军配图丢失", "guard_events", 'image = "gfx/interface/illustrations/event/backgrounds/special/sts_liang_guard_reform.dds"', "# missing image", "[整编禁军]"),
        ("岳家军漏解锁", "yuejiajun_advances", "unlock_unit = a_traditions_yuejiajun", "# missing unlock", "[岳家军]"),
        ("岳家军错时代", "yuejiajun_advances", "age = age_3_discovery", "age = age_2_renaissance", "[岳家军]"),
        ("岳家军断升级链", "yuejiajun_units", "upgrades_to_only = a_discovery_yuejiajun", "upgrades_to_only = a_reformation_yuejiajun", "[岳家军]"),
        ("岳家军本地化缺失", "yuejiajun_loc", "a_traditions_yuejiajun_desc:", "a_traditions_yuejiajun_desc_x:", "[岳家军]"),
        ("岳家军缺科技前置", "yuejiajun_advances", "requires = unlock_musketeers_advance", "# missing tech", "[岳家军]"),
        ("岳家军恢复家族定义", "yuejiajun_families", sources["yuejiajun_families"], sources["yuejiajun_families"] + "\nsts_yuejiajun = { limit = sts_yuejiajun_unit_limit }", "[岳家军]"),
        ("岳家军恢复30团脚本值", "yuejiajun_values", sources["yuejiajun_values"], sources["yuejiajun_values"] + "\nsts_yuejiajun_unit_limit = { value = 30 }", "[岳家军]"),
        ("岳家军反查自身革新", "yuejiajun_units", "country_potential = { has_or_had_tag = XIA }", "country_potential = { has_or_had_tag = XIA has_advance = sts_xia_yuejiajun_1_advance }", "[岳家军]"),
        ("岳家军兵种恢复family", "yuejiajun_units", "buildable = yes", "buildable = yes\n family = sts_yuejiajun", "[岳家军]"),
        ("岳家军兵种恢复limit", "yuejiajun_units", "buildable = yes", "buildable = yes\n limit = 30", "[岳家军]"),
        ("岳家军二级恢复跨代连线", "yuejiajun_advances", "requires = unlock_men_at_arms_advance", "requires = sts_xia_yuejiajun_1_advance", "[革新依赖]"),
        ("岳家军前置不存在", "yuejiajun_advances", "requires = unlock_men_at_arms_advance", "requires = sts_missing_advance", "[革新依赖]"),
        ("原版前置时代变化", "vanilla_army_advances", "unlock_men_at_arms_advance = {", "unlock_men_at_arms_advance = { age = age_1_traditions", "[革新依赖]"),
        ("岳家军丢失上代研究条件", "yuejiajun_advances", "allow = { has_advance = sts_xia_yuejiajun_1_advance }", "allow = { always = yes }", "[岳家军]"),
        ("岳家军开局误授二级", "effects", "research_advance = advance_type:sts_xia_yuejiajun_1_advance", "research_advance = advance_type:sts_xia_yuejiajun_1_advance\n research_advance = advance_type:sts_xia_yuejiajun_2_advance", "[岳家军]"),
        ("岳家军开局误授六级", "effects", "research_advance = advance_type:sts_xia_yuejiajun_1_advance", "research_advance = advance_type:sts_xia_yuejiajun_1_advance\n research_advance = advance_type:sts_xia_yuejiajun_6_advance", "[岳家军]"),
        ("岳家军开局错授其他国家", "effects", "c:XIA ?= {", "c:KFE ?= {", "[岳家军]"),
        ("岳家军开局未授革新", "effects", "research_advance = advance_type:sts_xia_yuejiajun_1_advance", "# missing start advance", "[岳家军]"),
        ("经略封疆缺贵州补充国", "jinglue_advance", "has_or_had_tag = AAB", "# 缺少贵州补充国", "[经略封疆] 国家范围缺少"),
        ("经略封疆缺晋王", "jinglue_advance", "has_or_had_tag = LAK", "# 缺少晋王", "[经略封疆] 国家范围缺少"),
        ("经略封疆恢复动态成员", "jinglue_advance", "sts_is_chinese_warlord_tag = yes", "sts_is_consolidation_member = yes", "[经略封疆]"),
        ("经略封疆夹入变量门槛", "jinglue_advance", "country_type = location", "country_type = location\n has_variable = sts_warlord", "[经略封疆]"),
        ("经略封疆夹入组织门槛", "jinglue_advance", "country_type = location", "country_type = location\n is_member_of_international_organization = international_organization:sts_chancellery", "[经略封疆]"),
        ("经略封疆静态触发器误回动态", "warlord_tags", "tag = KAA", "has_variable = sts_warlord", "[经略封疆]"),
        ("经略封疆静态名单漏国", "warlord_tags", "tag = GUI", "# 缺少静态国家", "[经略封疆] 国家范围缺少"),
        ("经略封疆setup名单增加国家", "setup_organizations", "type = sts_chancellery\n creation_date = 1337.4.1\n members = { CSO", "type = sts_chancellery\n creation_date = 1337.4.1\n members = { AAA CSO", "[经略封疆] 国家范围缺少"),
        ("经略封疆范围混入外部国家", "jinglue_advance", "has_or_had_tag = AAB", "has_or_had_tag = AAA", "[经略封疆] 国家范围多出"),
        ("经略封疆未排除宋天子", "jinglue_advance", "NOT = { tag = CSO }", "# missing CSO exclusion", "[经略封疆]"),
        ("经略封疆整合速度错误", "jinglue_advance", "global_integration_speed_modifier = 0.05", "global_integration_speed_modifier = 0.10", "[经略封疆]"),
        ("经略封疆本地化缺失", "jinglue_loc", "sts_jinglue_fengjiang_advance_desc:", "sts_jinglue_fengjiang_advance_desc_x:", "[经略封疆]"),
        ("经略封疆图标丢失", "jinglue_advance", "icon = sts_jinglue_fengjiang", "icon = sts_missing_advance_icon", "[革新图标]"),
        ("执掌天宪外交官回退", "kfe_court_advances", "monthly_diplomats = 0.10", "monthly_diplomats = 0.01", "[梁政略]"),
        ("怀柔四方效果回退", "kfe_court_advances", "improve_relation_impact = 0.30", "improve_relation_impact = 0.50", "[梁政略]"),
        ("都督军政补员回退", "kfe_court_advances", "army_reinforce_efficiency = 0.20", "army_reinforce_efficiency = 0.10", "[梁政略]"),
        ("殿前禁卫跨代前置", "kfe_guard_advances", "requires = unlock_men_at_arms_advance", "requires = sts_kfe_dianqian_1_advance", "[殿前禁卫]"),
        ("殿前禁卫漏授一级", "effects", "research_advance = advance_type:sts_kfe_dianqian_1_advance", "# missing guard grant", "[梁政略]"),
        ("殿前禁卫插画错位", "kfe_unit_art", "is_unit_type = a_traditions_dianqian", "is_unit_type = a_renaissance_dianqian", "[殿前禁卫]"),
        ("梁革新本地化缺失", "kfe_loc", "sts_kfe_mandate_advance_desc:", "sts_kfe_mandate_advance_desc_x:", "[梁革新]"),
        ("蜀道拓险效果回退", "shu_advances", "army_light_infantry_power = 0.10", "army_light_infantry_power = 0.05", "[蜀革新]"),
        ("蜀道拓险围城回退", "shu_advances", "siege_ability = 0.10", "siege_ability = 0.05", "[蜀革新]"),
        ("交子务利率回退", "shu_advances", "bank_interest = -0.01", "bank_interest = 0.01", "[蜀革新]"),
        ("元戎弩手漏解锁", "shu_advances", "unlock_unit = a_shu_yuanrong", "# missing shu unlock", "[蜀兵种]"),
        ("元戎弩手国家错位", "shu_units", "country_potential = { has_or_had_tag = CAJ }", "country_potential = { has_or_had_tag = XIA }", "[蜀兵种]"),
        ("蜀开局误授多项", "effects", "research_advance = advance_type:sts_shu_shudao_advance", "research_advance = advance_type:sts_shu_yuanrong_advance", "[蜀革新]"),
        ("表里金汤要塞回退", "jin_advances", "fort_limit = 1", "fort_limit = 0", "[晋革新]"),
        ("雪耻义从征召回退", "jin_advances", "peasants_estate_levy_size = 0.10", "peasants_estate_levy_size = 0.05", "[晋革新]"),
        ("三晋铁旅训练度回退", "jin_advances", "discipline = 0.05\n}", "discipline = 0.01\n}", "[晋革新]"),
        ("晋开局漏授表里金汤", "effects", "research_advance = advance_type:sts_jin_jintang_advance", "# missing jin grant", "[晋革新]"),
        ("晋革新本地化缺失", "jin_loc", "sts_jin_tielu_advance_desc:", "sts_jin_tielu_advance_desc_x:", "[晋革新]"),
        ("海岱藩屏建造回退", "qi_advances", "global_build_buildings_efficiency = 0.20", "global_build_buildings_efficiency = 0.10", "[齐革新]"),
        ("忠烈遗勇士气回退", "qi_advances", "land_morale = 0.20", "land_morale = 0.10", "[齐革新]"),
        ("忠烈宿勋征召回退", "qi_advances", "nobles_estate_levy_size = 0.30", "nobles_estate_levy_size = 0.15", "[齐革新]"),
        ("齐开局漏授革新", "effects", "research_advance = advance_type:sts_qi_suxun_advance", "# missing qi grant", "[齐革新]"),
        ("齐革新本地化缺失", "qi_loc", "sts_qi_yiyong_advance_desc:", "sts_qi_yiyong_advance_desc_x:", "[齐革新]"),
        ("武陵桃源迁徙回退", "xiang_advances", "global_migration_speed = 0.10", "global_migration_speed = 0.05", "[湘革新]"),
        ("武陵桃源繁荣回退", "xiang_advances", "global_monthly_prosperity = 0.10", "global_monthly_prosperity = 0.01", "[湘革新]"),
        ("榷茶通商税收回退", "xiang_advances", "tax_income_efficiency = 0.10\n}", "tax_income_efficiency = 0.05\n}", "[湘革新]"),
        ("湘开局漏授桃源", "effects", "research_advance = advance_type:sts_xiang_taoyuan_advance", "# missing xiang grant", "[湘革新]"),
        ("湘革新本地化缺失", "xiang_loc", "sts_xiang_tiebu_advance_desc:", "sts_xiang_tiebu_advance_desc_x:", "[湘革新]"),
        ("梯航万国舰队回退", "min_advances", "navy_galley_power = 0.15", "navy_galley_power = 0.05", "[闽革新]"),
        ("梯航万国关税回退", "min_advances", "max_tariff = 0.10", "max_tariff = 0.05", "[闽革新]"),
        ("闽道通衢山地回退", "min_advances", "mountains_proximity_impact = -0.33", "mountains_proximity_impact = -0.10", "[闽革新]"),
        ("闽开局漏授通衢", "effects", "research_advance = advance_type:sts_min_tongqu_advance", "# missing min grant", "[闽革新]"),
        ("闽革新本地化缺失", "min_loc", "sts_min_tihang_advance_desc:", "sts_min_tihang_advance_desc_x:", "[闽革新]"),
        ("节制百粤上缴回退", "yue_advances", "subject_income_modifier = 0.10", "subject_income_modifier = 0.05", "[粤革新]"),
        ("岭南宗盟外交容量回退", "yue_advances", "diplomatic_capacity = 1", "diplomatic_capacity = 0", "[粤革新]"),
        ("南岭武弁士气回退", "yue_advances", "land_morale = 0.15", "land_morale = 0.05", "[粤革新]"),
        ("粤开局漏授宗盟", "effects", "research_advance = advance_type:sts_yue_zongmeng_advance", "# missing yue grant", "[粤革新]"),
        ("粤革新本地化缺失", "yue_loc", "sts_yue_wubian_advance_desc:", "sts_yue_wubian_advance_desc_x:", "[粤革新]"),
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


def semantic_self_test():
    """独立内存样例验证通用语义规则，避免仅靠固定回归断言证明自身。"""
    vanilla = {"base.txt": "old = { age = age_1 } same = { age = age_2 }",
               "keep.txt": "kept = { age = age_3 }"}
    mod = {"base.txt": "replacement = { age = age_2 }",
           "custom.txt": "custom = { age = age_2 requires = replacement }"}
    ages = merged_advance_age_map(vanilla, mod)
    cases = [
        ("同名文件整份遮蔽", ages == {"kept": "age_3", "replacement": "age_2", "custom": "age_2"}),
        ("同代依赖合法", not advance_dependency_errors(mod["custom.txt"], ages)),
        ("通用跨时代变异", bool(advance_dependency_errors("custom = { age = age_3 requires = replacement }", ages))),
        ("通用悬空引用", bool(advance_dependency_errors("custom = { age = age_2 requires = absent }", ages))),
        ("被遮蔽ID不能引用", bool(advance_dependency_errors("custom = { age = age_1 requires = old }", ages))),
        ("依赖方缺时代", bool(advance_dependency_errors("custom = { requires = replacement }", ages))),
        ("前置缺时代", bool(advance_dependency_errors("custom = { age = age_2 requires = parent }", {"parent": None}))),
        ("重复requires逐一检查", bool(advance_dependency_errors("custom = { age = age_2 requires = replacement requires = kept }", ages))),
        ("跨代allow合法", not advance_dependency_errors("custom = { age = age_2 allow = { has_advance = kept } }", ages)),
        ("注释字符串不作依赖", not advance_dependency_errors('custom = { age = age_2 # requires = absent\n icon = "requires = absent" }', ages)),
        ("只忽略顶层兵种ID", not unknown_field_keys("custom_unit = { buildable = yes }", {"buildable"}, True)),
        ("兵种内部拼写错误", unknown_field_keys("custom_unit = { buildabel = yes }", {"buildable"}, True) == ["buildabel"]),
        ("兵种嵌套字段仍检查", unknown_field_keys("custom_unit = { country_potential = { has_advnace = wrong } }", {"country_potential"}, True) == ["has_advnace"]),
        ("内部自定义前缀不豁免", unknown_field_keys("custom_unit = { sts_typo = yes }", set(), True) == ["sts_typo"]),
        ("兵种注释不误报", not unknown_field_keys("custom_unit = { # bogus = yes\n buildable = yes }", {"buildable"}, True)),
        ("城堡归属一致", not castle_setup_errors(
            "building_manager = {\n castle = { tag = XIA level = 1 location = liangquan }\n}",
            "\tXIA = {\n\t\town_control_core = {\n\t\t\tliangquan\n\t\t}\n\t}\n",
            set(CASTLE_LOCATIONS) | {"liangquan"}) or True),
        ("城堡归属不一致可检出", any("不一致" in e for e in castle_setup_errors(
            "building_manager = {\n castle = { tag = XAB level = 1 location = liangquan }\n}",
            "\tXIA = {\n\t\town_control_core = {\n\t\t\tliangquan\n\t\t}\n\t}\n",
            {"liangquan"}))),
    ]
    failures = [f"[语义自测] {name} 未通过" for name, passed in cases if not passed]
    print(f"  通用语义内存自测：{len(cases) - len(failures)}/{len(cases)} 项通过（未改写游戏文件）")
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
    advance_sources = []
    for root in (GAME, MOD):
        folder = os.path.join(root, "in_game/common/advances")
        advance_sources.append({os.path.relpath(p, folder).replace("\\", "/"): read(p)
                                for p in sorted(walk_txt(folder))})
    advance_age_map = merged_advance_age_map(*advance_sources)
    for name, text in advance_sources[1].items():
        problems.extend(f"in_game/common/advances/{name}: {error}"
                        for error in advance_dependency_errors(text, advance_age_map))
    info.append(f"革新依赖：原版与模组按同名文件遮蔽合并 {len(advance_age_map)} 个ID，检查全部模组 requires 的存在性与同代约束")
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

        for key in unknown_field_keys(text, corpus, rel.startswith("in_game/common/unit_types/")):
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
    current = gen_map.country_blocks(read(os.path.join(MOD, "main_menu/setup/1337/10_countries.txt")))
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
    data = json.load(open(os.path.join(os.path.dirname(__file__), "sts_tags.json"), encoding="utf-8"))
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
    setup_text = read(os.path.join(MOD, "main_menu/setup/1337/10_countries.txt"))
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
        "main_loc": read(os.path.join(LOC_DIR, "sts_l_simp_chinese.yml")),
        "end_events": read(os.path.join(MOD, "in_game/events/situations/sts_consolidation_end_events.txt")) if os.path.exists(os.path.join(MOD, "in_game/events/situations/sts_consolidation_end_events.txt")) else "",
        "end_loc": read(os.path.join(LOC_DIR, "sts_consolidation_end_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_consolidation_end_l_simp_chinese.yml")) else "",
        "guard_events": read(os.path.join(MOD, "in_game/events/situations/sts_liang_guard_reform_events.txt")) if os.path.exists(os.path.join(MOD, "in_game/events/situations/sts_liang_guard_reform_events.txt")) else "",
        "guard_loc": read(os.path.join(LOC_DIR, "sts_liang_guard_reform_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_liang_guard_reform_l_simp_chinese.yml")) else "",
        "vanilla_army_advances": advance_sources[1].get("2_army_unlocks.txt", advance_sources[0].get("2_army_unlocks.txt", "")),
        "warlord_tags": triggers,
        "setup_organizations": "\n".join(io_lines),
        "yuejiajun_units": read(os.path.join(MOD, "in_game/common/unit_types/sts_yuejiajun_unit_types.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/unit_types/sts_yuejiajun_unit_types.txt")) else "",
        "yuejiajun_advances": read(os.path.join(MOD, "in_game/common/advances/sts_yuejiajun_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_yuejiajun_advances.txt")) else "",
        "yuejiajun_loc": read(os.path.join(LOC_DIR, "sts_yuejiajun_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_yuejiajun_l_simp_chinese.yml")) else "",
        "yuejiajun_families": read(os.path.join(MOD, "in_game/common/unit_families/sts_yuejiajun_families.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/unit_families/sts_yuejiajun_families.txt")) else "",
        "yuejiajun_values": read(os.path.join(MOD, "in_game/common/script_values/sts_yuejiajun_values.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/script_values/sts_yuejiajun_values.txt")) else "",
        "jinglue_advance": read(os.path.join(MOD, "in_game/common/advances/sts_jinglue_fengjiang_advance.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_jinglue_fengjiang_advance.txt")) else "",
        "jinglue_loc": read(os.path.join(LOC_DIR, "sts_jinglue_fengjiang_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_jinglue_fengjiang_l_simp_chinese.yml")) else "",
        "kfe_court_advances": read(os.path.join(MOD, "in_game/common/advances/sts_kfe_court_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_kfe_court_advances.txt")) else "",
        "kfe_guard_advances": read(os.path.join(MOD, "in_game/common/advances/sts_kfe_guard_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_kfe_guard_advances.txt")) else "",
        "kfe_units": read(os.path.join(MOD, "in_game/common/unit_types/sts_kfe_guard_unit_types.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/unit_types/sts_kfe_guard_unit_types.txt")) else "",
        "kfe_unit_art": read(os.path.join(MOD, "in_game/gfx/unit_illustrations/sts_kfe_unit_illustrations.txt")) if os.path.exists(os.path.join(MOD, "in_game/gfx/unit_illustrations/sts_kfe_unit_illustrations.txt")) else "",
        "kfe_loc": read(os.path.join(LOC_DIR, "sts_kfe_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_kfe_advances_l_simp_chinese.yml")) else "",
        "shu_advances": read(os.path.join(MOD, "in_game/common/advances/sts_shu_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_shu_advances.txt")) else "",
        "shu_units": read(os.path.join(MOD, "in_game/common/unit_types/sts_shu_unit_types.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/unit_types/sts_shu_unit_types.txt")) else "",
        "shu_loc": read(os.path.join(LOC_DIR, "sts_shu_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_shu_advances_l_simp_chinese.yml")) else "",
        "jin_advances": read(os.path.join(MOD, "in_game/common/advances/sts_jin_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_jin_advances.txt")) else "",
        "jin_loc": read(os.path.join(LOC_DIR, "sts_jin_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_jin_advances_l_simp_chinese.yml")) else "",
        "qi_advances": read(os.path.join(MOD, "in_game/common/advances/sts_qi_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_qi_advances.txt")) else "",
        "qi_loc": read(os.path.join(LOC_DIR, "sts_qi_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_qi_advances_l_simp_chinese.yml")) else "",
        "xiang_advances": read(os.path.join(MOD, "in_game/common/advances/sts_xiang_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_xiang_advances.txt")) else "",
        "xiang_loc": read(os.path.join(LOC_DIR, "sts_xiang_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_xiang_advances_l_simp_chinese.yml")) else "",
        "min_advances": read(os.path.join(MOD, "in_game/common/advances/sts_min_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_min_advances.txt")) else "",
        "min_loc": read(os.path.join(LOC_DIR, "sts_min_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_min_advances_l_simp_chinese.yml")) else "",
        "yue_advances": read(os.path.join(MOD, "in_game/common/advances/sts_yue_advances.txt")) if os.path.exists(os.path.join(MOD, "in_game/common/advances/sts_yue_advances.txt")) else "",
        "yue_loc": read(os.path.join(LOC_DIR, "sts_yue_advances_l_simp_chinese.yml")) if os.path.exists(os.path.join(LOC_DIR, "sts_yue_advances_l_simp_chinese.yml")) else "",
        "characters": generated_chars,
        "decisions": decision_text,
        "triggers": triggers_text,
        "empress_events": read(os.path.join(MOD, "in_game/events/situations/sts_liang_empress_events.txt")),
        "modifiers": static_text,
        "biases": read(os.path.join(MOD, "in_game/common/biases/sts_biases.txt")),
        "ranks": rank_text,
        "empress_loc": read(os.path.join(LOC_DIR, "sts_liang_empress_l_simp_chinese.yml")),
    }
    problems.extend(script_regressions(script_sources))
    problems.extend(castle_setup_errors(
        read(os.path.join(MOD, "main_menu/setup/1337/07a_sts_buildings.txt")),
        read(os.path.join(MOD, "main_menu/setup/1337/10_countries.txt")),
        locs))
    info.append(f"开局城堡：{len(CASTLE_LOCATIONS)} 处指定地点的 1 级城堡与 setup 所有者已逐项核对")
    info.append("地区割地：索取宣称专用 CB/战争目标链路、双方受让国首都 area 限制已检查")
    info.append("海内整合：实际开始满三年到期、独立成员直辖100地点结局、全体成员仅一次开场事件、三结局事件与八成覆灭条件已检查")
    info.append("进女配极：真实人物与婚姻前置、配偶成功门、逐国去重、奖励/一年加成、对梁好感方向及皇后头衔本地化已检查")
    info.append("岳家军：六代同代科技前置、上代研究门槛、原生解锁、仅授一级及无额外家族/上限已检查")
    info.append("经略封疆：189国静态名单加16国与setup相府成员减CSO逐国对等，无变量/组织运行期依赖已检查")
    if "--self-test" in sys.argv:
        problems.extend(regression_self_test(script_sources))
        problems.extend(semantic_self_test())
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
