# 万邦之秋 / Autumn of Ten Thousand States

EU5 架空历史剧本模组 · 0.1.0

## 设定

靖康之变后，南宋反推北方，收复北宋故土，又在蒙古崛起时守住了国祚。
但王朝活得太久，也就烂得太透。1337 年，中原已经裂成 189 个藩镇，
宋天子还坐在开封，只是没人再听他的诏书。北方的大元仍压着河朔与大都。

## 适配版本

**Europa Universalis V 1.4.\***

必须新开档。旧存档不会读取新的 setup、宗族、旗帜与地图颜色。

## 核心内容

- 宋为静态建筑国家，无领土，宋廷固定在开封；梁（KFE）控制开封与丞相府。
- 189 个藩镇；除梁与 12 个特殊藩王外，普通藩镇一省一国、公爵级节度使。
- 13 个特殊势力：梁、秦、齐、莱、蜀、晋、吴、楚、汉、越、闽、粤、湘。
- 群雄割据（1337 开局）与海内整合（1337.4.4 后）两场局势。
- 丞相府三栏、防御法、求援与拒绝惩罚、讨贼诏、定贼臣、自领丞相、迁移天子。
- 称王、受禅、称帝三条升级路线。
- 原版红巾军局势禁用，元境反抗由绿巾军承接。
- 固定宗族、固定旗帜、中华朝堂背景、藩王地图配色区分。
- AI 会称王、整合附庸、使用索取宣称。

## 结构

```text
.metadata/                              模组信息 + 缩略图
main_menu/setup/1337/10_countries.txt   开局国家与地块
main_menu/setup/1337/04_sts_dynasties.txt 固定宗族
main_menu/setup/1337/05_sts_characters.txt 开局角色
main_menu/localization/simp_chinese/     中文本地化
main_menu/common/coat_of_arms/           藩王固定旗帜
main_menu/gfx/                           局势背景与图标
in_game/setup/countries/                 国家颜色/文化/宗教定义
in_game/common/situations/               群雄割据、海内整合
in_game/common/generic_actions/          称王/整合/索取宣称等行动
in_game/common/scripted_effects/         开局初始化、丞相府逻辑
in_game/common/scripted_triggers/        藩镇与天朝判定
in_game/gui/country_header.gui           中华朝堂背景
tools/                                   生成器与预检脚本
docs/                                    开发参考
```

## 开游戏前

```bash
python tools/preflight.py
```

当前应输出：

```text
检查完成：0 个问题
藩镇：189
有主地点：13576
```

## 发布说明

- 版本：0.1.0
- 支持游戏：1.4.*
- 语言：简体中文
- 不建议与其他修改中国 setup、藩镇、天朝、丞相府或朝堂 UI 的模组混用。
- 开局规则若把 AI 性格设为随机，会覆盖秦/楚/闽/粤/湘的固定性格。
- 完整创意工坊介绍见 `outputs/sts_workshop_description_gemini_20261024.txt`。
