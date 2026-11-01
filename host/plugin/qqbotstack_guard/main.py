"""QQBotStack guard.

只允许指定群按「@ 机器人 / 包含关键词 / 随机插话」唤醒，其他群一律不回复。
私聊默认也不回复（`private_reply_enabled=false` 时直接停事件）。

配置来自同目录的 config.json（**不入库**，见 config.example.json）：
    allowed_group       允许回复的群号
    private_reply_enabled  是否回复私聊（默认 false）
    keywords            触发关键词（包含即命中）
    random_prob         普通消息的随机插话概率，0 表示关闭
    random_cooldown_sec 随机插话冷却秒数
    idle_reply_prob     接话窗口关闭后，心动值仍高时自己插话的概率
    idle_cooldown_sec   静默期主动接话冷却秒数
    laugh_join_prob     群里笑成一片时跟着接一声的概率
    scope_close_window  跑题时是否直接关窗（默认 false：只扣心动值）
    wake_prefix         指令前缀（保持与 AstrBot 的 wake_prefix 一致）

为什么需要它：
- AstrBot 的 wake_prefix 是**前缀**匹配，表达不了「包含关键词」；
- 会话白名单是精确匹配，表达不了「所有私聊 + 某一个群」。

实现要点：插件的 handler filter 命中后，唤醒阶段只置 `is_wake`，
**不会**置 `is_at_or_wake_command`，所以默认 LLM 不会自动回复。
这里在放行分支上手动置位，让消息继续走完整的默认管线
（人格、上下文、插件都在），而不是自己拼一个 request_llm。

接话窗口：机器人回复后开一个短窗口，窗口内的后续接话先收集，
静默一段时间后统一回一次；第二个人说的内容不同才单独引用回复。
设计见 `docs/DESIGN-FOLLOWUP.md`。
"""

import asyncio
import functools
import json
import os
import random
import re
import shutil
import time
import urllib.parse
from difflib import SequenceMatcher
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image, Json, Plain, Reply
from astrbot.api.star import Context, Star, register
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.star.star import star_map

try:  # Quart is provided by the AstrBot dashboard.
    from quart import jsonify as _quart_jsonify
except Exception:  # noqa: BLE001
    _quart_jsonify = None

# 发送前清理：真人不会在 QQ 里发 Markdown 和一堆 emoji。
# 这是确定性兜底 —— 人格提示词已经要求不用，但模型偶尔仍会漏出来。
_MARKDOWN = re.compile(
    r"\*\*|__|~~|`{1,3}|^\s{0,3}#{1,6}\s+|^\s{0,3}[-*+]\s+|^\s{0,3}>\s+",
    re.MULTILINE,
)
_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF\U00002600-\U000027BF\U0001F1E6-\U0001F1FF"
    "\u2B00-\u2BFF\uFE0F\u200D]"
)
# 模型偶尔会把内部参数标签漏进正文（如 </rfl:parameter>），一律清掉。
_STRAY_TAG = re.compile(r"</?[A-Za-z][A-Za-z0-9_:.-]*(?:\s+[^<>]*)?/?>")
_SPECIAL_TOKEN = re.compile(r"<\|[^>]*\|>")
# 模型偶尔会自续写假对话（<|start|>user<|message|>...）；从第一个标记起整段丢掉。
_FAKE_DIALOG = re.compile(r"<\|(?:start|message|channel|constrain|end|assistant|user|system)\|>")

# Beam 偶尔会把常见英文词夹进中文里（evening / burn out / ok）。
# 角色扮演里这些是最伤「活人感」的，发送前做一次确定性替换。
_DONT_ASK_RE = re.compile(r"你?别(?:问|打听)[^。！？ ]*|别问太多|不让我多说")

_WAKE_BOILERPLATE = re.compile(
    r"你\s*@\s*我了?但没(?:说|讲)|想聊点什么|有什么(?:想|需要).{0,8}帮|需要帮忙|"
    r"随时说.{0,10}我在听"
)

# 纯笑声：不要判成英文，也不要触发走神句。
_LAUGH_ONLY = re.compile(r"(?i)(?:h+a+h*a*|h+h+h+|l+o+l+|lmao+|2{2,}3+|6{3,}|笑死|哈哈哈哈)")
# 模型偶尔会把内部提示块当正文吐出来；发送前整行清掉。
_LEAK_LINE = re.compile(
    r"^\s*(?:\[接话上下文\]|\[本轮说话的人\]|\[名字校准\]|\[接梗\]|\[情绪\]|"
    r"\[插话\]|\[表情标记\]|以上是不同的人|你刚才说[:：]).*$",
    re.MULTILINE,
)
# 上游模型训练时见过「角色参数卡」（<rfl:parameter> 名词段），偶尔会把设定
# 排成一张卡整张吐出来（如「梵铭 二十一岁 伯恩山犬兽人 教堂的神父 …」）。
# 标签本身已被 _STRAY_TAG 剥掉，这里按内容形状认卡：整条回复是一行、
# 五段以上的空格分隔名词段、带年龄段、且命中两个以上身份词。
_CARD_IDENTITY_WORDS = re.compile(
    r"兽人|神父|守护者|容器|火种|别名|一族|教堂|派的首领|掌[律法治愈]|天使|镇狱官|净化部队"
)


def _is_card_dump(text: str) -> bool:
    """整条回复是一张「角色参数卡」而不是说话内容。"""
    body = (text or "").strip()
    if not body or "\n" in body:
        return False
    if any(ch in body for ch in "？吗呢！!"):
        return False
    tokens = re.split(r"[ 　,，、]+", body)
    if len(tokens) < 5:
        return False
    if not any(token.endswith("岁") for token in tokens):
        return False
    return len(set(_CARD_IDENTITY_WORDS.findall(body))) >= 2
# 群里在开玩笑 / 抬杠 / 起哄：给模型一个「接梗」提示，而不是让它讲道理。
BANTER_RE = re.compile(
    r"笑死|哈哈|绷不住|乐死|逗死|逗你|开玩笑|整活|抽象|离谱|逆天|破防|"
    r"急了|就这|无语|小丑|傻|笨|蠢|别装|装什么|嘴硬|不服"
)
# 气头上 / 冲突现场：这种时候绝对不主动插话，也不接梗。
CONFLICT_RE = re.compile(
    r"滚吧|滚开|给我滚|闭嘴|烦死|别烦|去死|傻逼|妈的|气死|你爹|打死|"
    r"想喝血|吵架|别理我|受不了|少来|关你什么事"
)
# 情绪不好：没点他就不插话；点了他就先接人，不玩梗。
NEGATIVE_RE = re.compile(
    r"难过|不开心|郁闷|烦|累死|好累|加班|失眠|想哭|崩溃|生气|吵架|分手|"
    r"辞职|考试|面试|生病|发烧|疼|难受|孤独|压力|没睡好"
)

_ENGLISH_FIXES = (
    (re.compile(r"(?<![A-Za-z])sharpening\s+(?:his|her|the)?\s*sword(?![A-Za-z])", re.I), "磨剑"),
    (re.compile(r"(?<![A-Za-z])wherever\s+he\s+wants\s+to\s+go\s+he\s+just\s+goes(?![A-Za-z])", re.I), "想去哪儿就去哪儿"),
    (re.compile(r"(?<![A-Za-z])sitting\s+in\s+the\s+chair\s+by\s+the\s+fireplace(?![A-Za-z])", re.I), "坐在壁炉边的椅子上"),
    (re.compile(r"(?<![A-Za-z])i\s+don'?t\s+ask\s+where\s+he'?s\s+from(?![A-Za-z])", re.I), "我不问他的来路"),
    (re.compile(r"(?<![A-Za-z])i\s+don'?t\s+need\s+to\s+know\s+everything\s+about\s+everyone(?![A-Za-z])", re.I), "我不需要什么都知道"),
    (re.compile(r"(?<![A-Za-z])that'?s\s+what\s+i\s+think\s+anyway(?![A-Za-z])", re.I), "反正我是这么想的"),
    (re.compile(r"(?<![A-Za-z])teaching\s+me\s+things(?![A-Za-z])", re.I), "教我东西"),
    (re.compile(r"(?<![A-Za-z])sometimes\s+telling\s+stories(?![A-Za-z])", re.I), "有时候讲故事"),
    (re.compile(r"(?<![A-Za-z])\s*telling\s*(?![A-Za-z])", re.I), "讲"),
    (re.compile(r"(?<![A-Za-z])he'?s\s+patient(?![A-Za-z])", re.I), "他有耐心"),
    (re.compile(r"(?<![A-Za-z])\s*excited\s*(?![A-Za-z])", re.I), "兴奋"),
    (re.compile(r"(?<![A-Za-z])\s*mostly\s*(?![A-Za-z])", re.I), "多半"),
    (re.compile(r"(?<![A-Za-z])\s*usually\s*(?![A-Za-z])", re.I), "通常"),
    (re.compile(r"(?<![A-Za-z])\s*sometimes\s*(?![A-Za-z])", re.I), "有时候"),
    (re.compile(r"(?<![A-Za-z])\s*latch\s*(?![A-Za-z])", re.I), "门闩"),
    (re.compile(r"(?<![A-Za-z])\s*patient\s*(?![A-Za-z])", re.I), "有耐心"),
    (re.compile(r"(?<![A-Za-z])\s*stories\s*(?![A-Za-z])", re.I), "故事"),
    (re.compile(r"(?<![A-Za-z])\s*fireplace\s*(?![A-Za-z])", re.I), "壁炉"),
    (re.compile(r"(?<![A-Za-z])\s*sword\s*(?![A-Za-z])", re.I), "剑"),
    (re.compile(r"(?<![A-Za-z])\s*chair\s*(?![A-Za-z])", re.I), "椅子"),
    (re.compile(r"(?<![A-Za-z])\s*he'?s\s*(?![A-Za-z])", re.I), "他是"),
    (re.compile(r"(?<![A-Za-z])\s*she'?s\s*(?![A-Za-z])", re.I), "她是"),
    (re.compile(r"(?<![A-Za-z])\s*his\s*(?![A-Za-z])", re.I), "他的"),
    (re.compile(r"(?<![A-Za-z])\s*her\s*(?![A-Za-z])", re.I), "她的"),
    (re.compile(r"(?<![A-Za-z])\s*he\s*(?![A-Za-z])", re.I), "他"),
    (re.compile(r"(?<![A-Za-z])\s*she\s*(?![A-Za-z])", re.I), "她"),
    (re.compile(r"(?<![A-Za-z])\s*I\s*(?![A-Za-z])", re.I), "我"),
    (re.compile(r"(?<![A-Za-z])\s*you\s*(?![A-Za-z])", re.I), "你"),
    (re.compile(r"(?<![A-Za-z])\s*we\s*(?![A-Za-z])", re.I), "我们"),
    (re.compile(r"(?<![A-Za-z])\s*they\s*(?![A-Za-z])", re.I), "他们"),
    (re.compile(r"(?<![A-Za-z])\s*himself\s*(?![A-Za-z])", re.I), "本人"),
    (re.compile(r"(?<![A-Za-z])\s*it\s*(?![A-Za-z])", re.I), "它"),
    (re.compile(r"(?<![A-Za-z])\s*don'?t\s*(?![A-Za-z])", re.I), "不"),
    (re.compile(r"(?<![A-Za-z])\s*doesn'?t\s*(?![A-Za-z])", re.I), "不"),
    (re.compile(r"(?<![A-Za-z])\s*can'?t\s*(?![A-Za-z])", re.I), "不能"),
    (re.compile(r"(?<![A-Za-z])\s*won'?t\s*(?![A-Za-z])", re.I), "不会"),
    (re.compile(r"(?<![A-Za-z])\s*burn\s+out\s*(?![A-Za-z])", re.I), "烧尽"),
    (re.compile(r"(?<![A-Za-z])\s*burnout\s*(?![A-Za-z])", re.I), "烧尽"),
    (re.compile(r"(?<![A-Za-z])\s*contradiction\s*(?![A-Za-z])", re.I), "死结"),
    (re.compile(r"(?<![A-Za-z])\s*evening\s*(?![A-Za-z])", re.I), "傍晚"),
    (re.compile(r"(?<![A-Za-z])\s*morning\s*(?![A-Za-z])", re.I), "早上"),
    (re.compile(r"(?<![A-Za-z])\s*night\s*(?![A-Za-z])", re.I), "夜里"),
    (re.compile(r"(?<![A-Za-z])\s*afternoon\s*(?![A-Za-z])", re.I), "下午"),
    (re.compile(r"(?<![A-Za-z])\s*okay\s*(?![A-Za-z])", re.I), "好"),
    (re.compile(r"(?<![A-Za-z])\s*ok\s*(?![A-Za-z])", re.I), "好"),
    (re.compile(r"(?<![A-Za-z])\s*sorry\s*(?![A-Za-z])", re.I), "抱歉"),
    (re.compile(r"(?<![A-Za-z])\s*thanks\s*(?![A-Za-z])", re.I), "谢谢"),
    (re.compile(r"(?<![A-Za-z])\s*hello\s*(?![A-Za-z])", re.I), "你好"),
    (re.compile(r"(?<![A-Za-z])\s*hi\s*(?![A-Za-z])", re.I), "你好"),
    (re.compile(r"(?<![A-Za-z])\s*bye\s*(?![A-Za-z])", re.I), "再见"),
    (re.compile(r"(?<![A-Za-z])\s*welcome\s*(?![A-Za-z])", re.I), "欢迎"),
    (re.compile(r"(?<![A-Za-z])\s*please\s*(?![A-Za-z])", re.I), "请"),
    (re.compile(r"(?<![A-Za-z])\s*really\s*(?![A-Za-z])", re.I), "真的"),
    (re.compile(r"(?<![A-Za-z])\s*maybe\s*(?![A-Za-z])", re.I), "也许"),
    (re.compile(r"(?<![A-Za-z])\s*actually\s*(?![A-Za-z])", re.I), "其实"),
    (re.compile(r"(?<![A-Za-z])\s*because\s*(?![A-Za-z])", re.I), "因为"),
    (re.compile(r"(?<![A-Za-z])\s*somewhere\s*(?![A-Za-z])", re.I), "某个地方"),
    (re.compile(r"(?<![A-Za-z])\s*anywhere\s*(?![A-Za-z])", re.I), "任何地方"),
    (re.compile(r"(?<![A-Za-z])\s*everywhere\s*(?![A-Za-z])", re.I), "到处"),
    (re.compile(r"(?<![A-Za-z])\s*nowhere\s*(?![A-Za-z])", re.I), "没有地方"),
    (re.compile(r"(?<![A-Za-z])\s*specifics\s*(?![A-Za-z])", re.I), "具体的事"),
    (re.compile(r"(?<![A-Za-z])\s*specific\s*(?![A-Za-z])", re.I), "具体的"),
    (re.compile(r"(?<![A-Za-z])\s*occasionally\s*(?![A-Za-z])", re.I), "偶尔"),
    (re.compile(r"(?<![A-Za-z])\s*occasional\s*(?![A-Za-z])", re.I), "偶尔"),
    (re.compile(r"(?<![A-Za-z])\s*beyond\s*(?![A-Za-z])", re.I), "再往后"),
    (re.compile(r"(?<![A-Za-z])\s*boring\s*(?![A-Za-z])", re.I), "没意思"),
    (re.compile(r"(?<![A-Za-z])\s*bored\s*(?![A-Za-z])", re.I), "没劲"),
    (re.compile(r"(?<![A-Za-z])\s*kidding\s*(?![A-Za-z])", re.I), "开玩笑"),
    (re.compile(r"(?<![A-Za-z])\s*joke\s*(?![A-Za-z])", re.I), "玩笑"),
    (re.compile(r"(?<![A-Za-z])\s*funny\s*(?![A-Za-z])", re.I), "好笑"),
    (re.compile(r"(?<![A-Za-z])\s*whatever\s*(?![A-Za-z])", re.I), "随便"),
    (re.compile(r"(?<![A-Za-z])\s*weird\s*(?![A-Za-z])", re.I), "怪"),
    (re.compile(r"(?<![A-Za-z])\s*yeah\s*(?![A-Za-z])", re.I), "对"),
    (re.compile(r"(?<![A-Za-z])\s*yep\s*(?![A-Za-z])", re.I), "对"),
    (re.compile(r"(?<![A-Za-z])\s*nope\s*(?![A-Za-z])", re.I), "不"),
    (re.compile(r"(?<![A-Za-z])\s*huh\s*(?![A-Za-z])", re.I), "嗯"),
    # 20261027 实测高频漏词：ears 12 次、rough/stubborn/third/footsteps 各数次。
    (re.compile(r"(?<![A-Za-z])\s*ears\s*(?![A-Za-z])", re.I), "耳朵"),
    (re.compile(r"(?<![A-Za-z])\s*footsteps\s*(?![A-Za-z])", re.I), "脚步声"),
    (re.compile(r"(?<![A-Za-z])\s*stubborn\s*(?![A-Za-z])", re.I), "倔"),
    (re.compile(r"(?<![A-Za-z])\s*rough\s*(?![A-Za-z])", re.I), "糙"),
    (re.compile(r"(?<![A-Za-z])\s*third\s*(?![A-Za-z])", re.I), "第三"),
    (re.compile(r"(?<![A-Za-z])\s*nights\s*(?![A-Za-z])", re.I), "夜里"),
    (re.compile(r"(?<![A-Za-z])\s*tired\s*(?![A-Za-z])", re.I), "累"),
    (re.compile(r"(?<![A-Za-z])\s*afraid\s*(?![A-Za-z])", re.I), "怕"),
    (re.compile(r"(?<![A-Za-z])\s*quiet\s*(?![A-Za-z])", re.I), "安静"),
    (re.compile(r"(?<![A-Za-z])\s*soft\s*(?![A-Za-z])", re.I), "轻"),
)

# 词表盖不住的长尾：回复主体是中文、但仍残留 3 个以上英文字母的词。
# 专有名词 / 缩写 / 群友英文名不算残留，不触发修复。
_LATIN_RUN = re.compile(r"(?<![A-Za-z])([A-Za-z]{3,})(?![A-Za-z])")
_LATIN_ALLOW = re.compile(
    r"^(?i:qq|q群|tts|api|ai|llm|http|https|app|id|ip|kokia|ave|maria|"
    r"napcat|astrbot|zgate|beam|hy\d+|onebot|qqbotstack)$"
)


def _latin_leftover(text: str) -> bool:
    """中文句子里还夹着词表没盖住的英文普通词，需要 LLM 修一轮。"""
    for match in _LATIN_RUN.finditer(text or ""):
        if not _LATIN_ALLOW.match(match.group(1)):
            return True
    return False


def _drop_adjacent_duplicate_lines(text: str) -> str:
    """Beam 偶尔把同一段答两遍，中间只隔一个换行；只去掉紧邻的完全相同行。"""
    out = []
    for line in (item.strip() for item in text.split("\n")):
        if line and out and line == out[-1]:
            continue
        out.append(line)
    return "\n".join(out)


def _drop_repeated_tail(text: str) -> str:
    """Beam 有时把同一条答案连着写两三遍（中间只有空格）；只留第一遍。"""
    chars = []
    index_map = []
    for index, char in enumerate(text):
        if not char.isspace():
            chars.append(char)
            index_map.append(index)
    compact = "".join(chars)
    # 只处理真正整段复读的情况：太短或重复段太短时，可能只是有意的回环/口头禅，
    # 一刀切会把玩笑的第二次重复剪掉。
    if len(compact) < 60:
        return text
    max_size = min(60, len(compact) // 2)
    for size in range(max_size, 23, -1):
        first = compact[:size]
        if not re.search(r"[\u4e00-\u9fff]", first):
            continue
        pos = compact.find(first, size)
        if pos != -1:
            return text[: index_map[pos]].strip()
    return text


def _clean_style(text: str) -> str:
    if not text:
        return text
    cleaned = _MARKDOWN.sub("", text)
    cleaned = _FAKE_DIALOG.split(cleaned, 1)[0]
    cleaned = _SPECIAL_TOKEN.sub("", cleaned)
    cleaned = _STRAY_TAG.sub("", cleaned)
    for pattern, repl in _ENGLISH_FIXES:
        cleaned = pattern.sub(repl, cleaned)
    cleaned = re.sub(r"一百[一二三四五六七八九十百几]+多?岁", "一百多岁", cleaned)
    cleaned = re.sub(r"(?<!\d)120\s*岁", "一百多岁", cleaned)
    cleaned = _drop_repeated_tail(cleaned)
    cleaned = _EMOJI.sub("", cleaned)
    # 清理后可能留下多余空格与空行；QQ 里一个换行就够，不要空一大行。
    cleaned = re.sub(r"\r\n?", "\n", cleaned)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r" *\n *", "\n", cleaned)
    cleaned = re.sub(r"\n{2,}", "\n", cleaned)
    cleaned = cleaned.strip()
    cleaned = _drop_adjacent_duplicate_lines(cleaned)
    cleaned = _LEAK_LINE.sub("", cleaned)
    cleaned = cleaned.strip()
    if _LAUGH_ONLY.fullmatch(cleaned):
        return "哈哈"
    # 「别问 / 别打听」只有在整条回复就是这么一句时才换成弃答；
    # 长句里夹一句卖关子属于语气，不要整条抹平。
    if len(cleaned) <= 30:
        cleaned = _DONT_ASK_RE.sub("这个我不知道", cleaned)
    cleaned = cleaned.replace("他们不是我的事", "这些我也不清楚")
    cleaned = cleaned.replace("不是我的事", "我也不清楚")
    # 只拦「整条回复基本就是客服模板」的情况：模板片段要占大头才替换，
    # 正常接话里顺口带一句「需要帮忙」不该被砍成三个字。
    cover = sum(len(m.group(0)) for m in _WAKE_BOILERPLATE.finditer(cleaned))
    if cleaned and len(cleaned) <= 80 and cover >= len(cleaned) * 0.6:
        return "在 你说"
    return cleaned


# 长文分段：模型习惯用空格断句，不一定打句号。AstrBot 的 segmented_reply
# 只认标点和换行，所以这里在长文里按空格聚成 60 字左右的小段，再插入换行。
# 短回复不处理，避免把日常聊天拆成一地碎句。
def _english_dominant(text: str) -> bool:
    """整条回复几乎全是英文时，用中文走神句兜底。

    笑声（hahaha / lol / 233）不算英文，否则「笑一声」会被判成英文回复。
    """
    body = (text or "").strip()
    if _LAUGH_ONLY.fullmatch(body):
        return False
    latin = len(re.findall(r"[A-Za-z]", body))
    cjk = len(re.findall(r"[一-鿿]", body))
    if cjk >= 2:
        return False
    return latin >= 10 and latin > cjk * 3


LONG_TEXT_SPLIT_THRESHOLD = 60
LONG_TEXT_CHUNK_CHARS = 55


def _split_long_for_qq(text: str) -> str:
    """把长文按空格断句聚成小段，插入换行交给 segmented_reply。

    短于阈值的回复原样返回；单段没有空格的超长句也原样返回，交给标点/换行
    正则去处理，不硬切。
    """
    if len(text) <= LONG_TEXT_SPLIT_THRESHOLD:
        return text
    paragraphs = [p.strip() for p in re.split(r"\n+", text) if p.strip()]
    chunks: list[str] = []
    for paragraph in paragraphs:
        clauses = [c for c in re.split(r"\s+", paragraph) if c]
        if len(clauses) <= 1:
            chunks.append(paragraph)
            continue
        buf = ""
        for clause in clauses:
            if not buf:
                buf = clause
            elif len(buf) + 1 + len(clause) <= LONG_TEXT_CHUNK_CHARS:
                buf += " " + clause
            else:
                chunks.append(buf)
                buf = clause
        if buf:
            chunks.append(buf)
    if len(chunks) <= 1:
        return text
    return "\n".join(chunks)


# 上游全部失败时，AstrBot 会把技术错误当正文发出去。
# 这些文案绝不能进群：既吓人，也把网关/账号细节漏给群友。
_ERROR_TEXT = re.compile(
    r"LLM\s*响应错误|All chat models failed|all upstreams failed|proxy_error|"
    r"InternalServerError|Error code:\s*[45]\d{2}|RateLimitError|"
    r"APIConnectionError|APITimeoutError|EmptyModelOutput|breaker open|"
    r"模型调用失败|请求模型失败",
    re.IGNORECASE,
)

# 兜底台词：模型全挂时用人格化的「走神」接住，而不是复述错误。
# 多准备几条并避免连续重复，否则一眼就能看出是模板。
DEFAULT_ERROR_LINES = (
    "嗯……刚刚好像有些恍神。你再说一遍？",
    "抱歉，我这边刚才走神了。你刚才说什么？",
    "啊，一下子没接住。再说说？",
    "等一下，我脑子刚才空了半拍。你重说一遍？",
    "嗯？我好像漏听了一句。再说一次好吗？",
    "让我缓缓——刚才那句没听清。",
    "刚有点不在状态，你说的什么？",
    "哎，我这会儿有点迟钝。再说一遍吧。",
    "不好意思，刚出了一小会儿神。你讲，我听着。",
    "嗯……刚才那下有点恍惚。你再说一次？",
)


# 夹英文长尾修复：小模型只负责把中文里夹的英文普通词翻成中文。
DEENGLISH_SYSTEM = (
    "你是文字修理工。输入是一段夹了英文单词的中文群聊回复。"
    "只把夹在中文句子里的英文普通词换成贴合语境的中文词，其余文字一律原样"
    "保留，包括换行、空格和标点；英文人名、歌名、专有名词、缩写不要动。"
    "只输出修好后的全文，不要解释，不要加引号。"
)

# 续聊判定器：窗口要关/消息要被忽略时，问一次小模型「他是不是还在跟你说」。
JUDGE_SYSTEM = (
    "你是群聊判定器，只输出一行 JSON，不输出别的。"
    "根据机器人上一句话和群里的近期对话，判断某人最新这句话："
    'to_bot = 这话是不是在跟机器人（群友「神父」）说，而不是在跟群里别人说；'
    "interested = 他是不是还有兴趣跟机器人继续当前这个话题。"
    '只输出 {"to_bot": true, "interested": true} 或 {"to_bot": false, "interested": false}。'
)


# 接话窗口：机器人回复后收集一小段时间内的接话，再统一回一次。
# 第二个人说的内容不同时，模型用这个内部标记另起一段；插件拆出来单独引用发送。
FOLLOWUP_SECOND_MARKER = "<<<SECOND>>>"
IMAGE_HINT_MARKER = "[图片回合]"
FACT_HINT_MARKER = "[查证]"
FACT_QUERY_RE = re.compile(
    r"(叫什么|是谁|长啥样|长什么样|什么意思|查一下|搜一下|"
    r"起个名字|取个名字|起名|取名|真名|本名)"
)
TOOL_HINT_MARKER = "[工具优先]"
NAMED_QUERY_RE = re.compile(
    r"(喜欢|听过|知道|看过|玩过|了解|认识).{0,16}吗|吗.{0,8}(喜欢|听过|知道)"
)
# 纯语气词/短回执：心动值再高也不接，避免「嗯/哦/好」把对话拆成水群。
BACKCHANNEL_RE = re.compile(
    r"^(嗯|哦|噢|好|行|可以|知道了|收到|好吧|行吧|笑死|哈哈+|草|6|666|"
    r"确实|对啊|是啊|真的|谁懂)[。！？!?~…\s]*$"
)
# 机器人刚问「要不要来 / 吃了吗」，用户用短句接住（「可以，就你一个人吗」）。
# 这种句子和 seed 的字面重合很低，但语义上是接着上一句，别让 drift 误杀。
FOLLOWUP_ANSWER_PREFIXES = (
    "可以", "好", "行", "嗯", "对", "是", "那", "我", "没", "不",
    "吃", "喝", "坐", "来", "去",
)
FOLLOWUP_INVITE_CUES = (
    "要不要", "来", "去", "吃", "喝", "坐", "方便", "吗", "？", "?",
    "睡", "聊", "一起",
)

FOLLOWUP_QUESTION_RE = re.compile(
    r"[?？]|什么|怎么|为什么|为啥|如何|吗|呢|哪|谁|多少|是不是|能不能|可不可以"
)

# 机器人的人设是绿海教堂里的神父。群里聊到 AI、游戏、技术、娱乐圈这些
# 他认知范围外的东西时，不接话；除非有人直接点他。
OUT_OF_SCOPE_RE = re.compile(
    r"(?i)(?<![a-z])(?:ai|gpt|chatgpt|claude|llm|token|prompt|agent|api|bug)"
    r"(?![a-z])"
    r"|人工智能|大模型|算法|编程|代码|程序员|"
    r"游戏|打游戏|王者荣耀|原神|英雄联盟|steam|switch|ps5|xbox|"
    r"显卡|cpu|内存条|装机|跑分|电脑配置|手机配置|"
    r"二次元|番剧|动漫|漫画|cosplay|主播|直播|网红|娱乐圈|明星|追星|"
    r"模型|参数|提示词|插件|服务器|接口"
)

# 「他长啥样 / 他这么严格吗」这类代词追问本身没有内容词，bigram 重合度
# 会把它判成跑题；只要窗口里机器人刚提过人，就按相关处理。
PRONOUN_FOLLOWUP_RE = re.compile(
    r"^(?:他|她|它|这人|那人|这位|那位|他们|她们)"
    r"(?:长啥样|长什么样|什么样|是谁|叫啥|叫什么|多大|几岁|在哪|干什么|干啥|"
    r"怎么了|为什么|怎么|是不是|这么|那么|会|有|是|在|呢|啊|呀)"
)

NAME_QUESTION_RE = re.compile(
    r"(我叫什么|我叫啥|我的名字是什么|我的名字是啥|我是谁|"
    r"你记得我叫什么|你记得我的名字|你叫我什么|我叫什么名字)"
)

# 和神父的日子有关的具体东西。命中这些词就不算「跑题」，
# 避免「汤/盐/雪/罐子」这类短句被 bigram 误杀。
IN_SCOPE_RE = re.compile(
    r"神父|小伯|拉贵尔|梵铭|玟德|铭|拉梵|赫尔墨斯|悠塔|犹达斯|卡戎|乌列尔|"
    r"教堂|绿海|火种|圣遗物|灵狐|禁区|钟楼|后院|地下室|圣像|拉斐尔|"
    r"汤|盐|罐子|柴火|草球|雪|风|雨|炉子|碗|桌子|椅子|屋顶|地砖|被子|"
    r"累|难受|开心|难过|饿|冷|热|睡不着|睡|吃|喝|陪|抱|哭|笑|怕|疼"
)

# 这些 bigram 太常见，不能拿来证明「还在聊同一个话题」。
TOPIC_STOP_BIGRAMS = {
    "今天", "明天", "昨天", "现在", "刚才", "最近", "什么", "怎么", "为什么",
    "为啥", "这个", "那个", "一个", "一下", "有点", "我们", "你们", "他们",
    "大家", "群里", "觉得", "就是", "还是", "可以", "真的", "不是", "没有",
    "知道", "时候", "东西", "已经", "因为", "所以", "但是", "如果", "然后",
    "自己", "别人", "这样", "那样",
    # 追问句式：两条不同的事只要都带「你先说清楚」就会被当成复读，
    # 结果把机器人刚说过的话从上下文里删掉（2026-10-28 15:06 实测）。
    "你先", "先说", "说清", "清楚", "具体", "哪个", "哪家", "哪位",
}

@functools.lru_cache(maxsize=1024)
def _normalize_text(text: str) -> str:
    """归一化文本（strip/lower/去空白与标点）。

    纯函数且在复读比对里被逐对重复调用：缓存一份，
    上下文里同一条旧回复整轮只归一一次。返回值是缓存对象，调用方不得修改。
    """
    text = (text or "").strip().lower()
    return re.sub(r"[\s\W_]+", "", text)


def _text_similarity(a: str, b: str) -> float:
    na, nb = _normalize_text(a), _normalize_text(b)
    if not na or not nb:
        return 0.0
    if na == nb:
        return 1.0
    return SequenceMatcher(None, na, nb).ratio()


def _bigram_overlap(a: str, b: str) -> float:
    na, nb = _normalize_text(a), _normalize_text(b)
    if len(na) < 2 or len(nb) < 2:
        return 0.0
    ga = {na[i : i + 2] for i in range(len(na) - 1)}
    gb = {nb[i : i + 2] for i in range(len(nb) - 1)}
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


@functools.lru_cache(maxsize=1024)
def _content_bigrams(text: str) -> set[str]:
    """Bigrams with common conversational filler removed.

    纯函数且在复读比对里逐对重复调用：按原文缓存一份。
    返回值是缓存对象，调用方不得修改（现有调用方只做 & 运算或 set() 拷贝）。
    """
    na = _normalize_text(text)
    return {
        na[i : i + 2]
        for i in range(len(na) - 1)
        if na[i : i + 2] not in TOPIC_STOP_BIGRAMS
    }


def _content_bigram_overlap(a: str, b: str) -> float:
    """Overlap of content bigrams; generic words no longer count as topic."""
    ga, gb = _content_bigrams(a), _content_bigrams(b)
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / min(len(ga), len(gb))


def _message_text(msg) -> str:
    """取一条上下文消息里的纯文本（think / tool 部分不算）。"""
    if not isinstance(msg, dict):
        return ""
    content = msg.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = [
            str(part.get("text") or "")
            for part in content
            if isinstance(part, dict)
            and str(part.get("type") or "text").lower() == "text"
        ]
        return " ".join(p for p in parts if p).strip()
    return ""


def _assistant_texts(contexts) -> list[str]:
    """上下文里机器人说过的纯文本，按时间顺序；带 tool_calls 的空回复跳过。"""
    out = []
    for msg in contexts or []:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        if msg.get("tool_calls"):
            continue
        text = _message_text(msg)
        if len(_normalize_text(text)) >= 4:
            out.append(text)
    return out


def _ratio_ceiling(len_a: int, len_b: int) -> float:
    """SequenceMatcher.ratio() 的数学上界：2*min/(la+lb)。

    ratio = 2M/(la+lb)，而 M（匹配字符数）不可能超过较短边的长度；
    上界低于阈值时可以直接跳过 O(n²) 的真比对，结果等价。
    """
    if not len_a or not len_b:
        return 0.0
    return 2.0 * min(len_a, len_b) / (len_a + len_b)


def _repeat_like(a: str, b: str) -> bool:
    """两条回复是否像同一个模板（用于折叠上下文里的旧复读）。

    短句看相似度或内容 bigram；长句只认近乎逐字。阈值按 2026-10-28 的实际
    复读样本校准：「先喝茶，其他慢慢来」vs「先喝茶，其他再说」bigram 0.67；
    同一话题的两段不同介绍（方大同）sim≈0.45、bigram≈0.18，不会被误杀。
    """
    na, nb = _normalize_text(a), _normalize_text(b)
    if len(na) < 4 or len(nb) < 4:
        return False
    short = max(len(na), len(nb)) <= 40
    threshold = 0.5 if short else 0.85
    # 长度差大到 ratio 上界都够不着阈值时，不必真跑 SequenceMatcher。
    if _ratio_ceiling(len(na), len(nb)) >= threshold:
        if _text_similarity(a, b) >= threshold:
            return True
    return short and _content_bigram_overlap(a, b) >= 0.5


def _repeat_like_strict(a: str, b: str) -> bool:
    """发送前的近重复判定：只拦真正像「换了个尾词」的短句。

    比 _repeat_like 严一点，避免把「同一个话题的正常回答」也送去重说。
    """
    na, nb = _normalize_text(a), _normalize_text(b)
    if len(na) < 6 or len(nb) < 6:
        return False
    short = max(len(na), len(nb)) <= 30
    threshold = 0.6 if short else 0.9
    if _ratio_ceiling(len(na), len(nb)) >= threshold:
        if _text_similarity(a, b) >= threshold:
            return True
    return short and _content_bigram_overlap(a, b) >= 0.55


_QUOTED_BLOCK = re.compile(r"<Quoted Message>\s*(.*?)\s*</Quoted Message>", re.S)

# 这些 bigram 在短回复里反复出现也不值得当成「复读特征」去删历史。
_TICK_STOP = set(TOPIC_STOP_BIGRAMS) | {
    "其他", "慢慢", "以后", "再说", "一句", "两句", "一句", "说了",
    "起来", "下来", "过去", "现在", "然后", "而且", "或者", "还是",
}


def _protected_tokens(worldbook) -> tuple[set[str], set[str]]:
    """世界书里的名字/关键词：涉及设定的重复不能当垫话删掉。

    返回 (bigrams, chars)。名字里的单字也要保护（玟德/梵铭/悠塔…）。
    """
    bigrams, chars = set(), set()
    for entry in worldbook or []:
        if not isinstance(entry, dict):
            continue
        labels = [entry.get("name")] + list(entry.get("keys") or [])
        for label in labels:
            norm = _normalize_text(str(label or ""))
            for i in range(len(norm) - 1):
                bigrams.add(norm[i : i + 2])
        # 单字只从人物名里取：世界书 keys 里有「汤/盐/罐」这类日常物，
        # 一并保护会让真正该收敛的意象永远删不掉。
        for ch in _normalize_text(str(entry.get("name") or "")):
            chars.add(ch)
    return bigrams, chars


# 单字层面的功能词：这些字高频出现不代表同一个意象，不能删历史。
_CHAR_STOP = set(
    "我你他她它你们的地得了吗呢吧啊呀哦嘛哈是不没在有就都也还又很太更最"
    "和与或但而且所以因为如果这那个一下觉得知道时候东西自己别人大家群里"
    "今天明天昨天现在刚才最近慢慢其他以后再说起来去过来着想要能会对给让"
    "把被从到向于先别急啦哪谁前后上下里外中一二三四五六七八九十好对真假"
    "说问话答笑笑哭出声样么怎幾几可只什点之像种坐留杯晚见事清看认度干净"
    "手小长首音听"
)


# 这些单字是动作，不是意象：可以用来判断复读，但不该在提示词里被点名。
_MOTIF_SKIP = set(
    "喝吃睡笑笑哭走跑坐站看听说问答拿给白红黑青蓝绿灰黄紫大小长短高低"
)


def _content_chars(text: str) -> set[str]:
    """短回复里的内容单字（去掉功能词），用来识别「茶/汤/罐子」这类意象。"""
    return {
        ch
        for ch in _normalize_text(text)
        if "\u4e00" <= ch <= "\u9fff" and ch not in _CHAR_STOP
    }


def _strip_repeated_quotes(text: str, bot_texts: list[str]) -> str:
    """把用户消息里「引用机器人上一句」的重复内容去掉。

    群友回复机器人时，AstrBot 会把被引用的原句塞进 user 消息；模型于是在
    用户回合里又看到一遍自己的旧话（2026-10-28 的「先喝茶」有 5 条就是这样
    被反复喂回去的）。只删能确认是机器人自己说过的引用，别人的引用不动。
    """

    if not text or "<Quoted Message>" not in text:
        return text

    def repl(match):
        body = match.group(1)
        body = re.sub(r"^\([^)\n]{0,40}\)\s*[:：]\s*", "", body).strip()
        body = re.sub(r"^[^\n:：]{1,20}[:：]\s*", "", body).strip()
        if len(_normalize_text(body)) < 6:
            return match.group(0)
        for bot_text in bot_texts:
            if _repeat_like_strict(body, bot_text) or body in bot_text:
                return ""
        return match.group(0)

    cleaned = _QUOTED_BLOCK.sub(repl, text)
    return re.sub(r"\n{2,}", "\n", cleaned).strip()


def _has_question_hint(text: str) -> bool:
    return bool(FOLLOWUP_QUESTION_RE.search(text or ""))


def _score_followup_item(item: dict, bot_text: str, last_sender_id: str) -> int:
    """给一条接话打分：点你/引用你最高，其次是与上一句相关、问句、连续性。"""
    text = item.get("text") or ""
    score = 0
    if (
        item.get("is_addressed")
        or item.get("is_at_bot")
        or item.get("is_reply_to_bot")
    ):
        score += 5
    overlap = _bigram_overlap(text, bot_text)
    if overlap > 0:
        score += 1 + min(2, int(overlap * 3))
    if _has_question_hint(text):
        score += 2
    if last_sender_id and item.get("sender_id") == last_sender_id:
        score += 1
    if len(text) >= 8:
        score += 1
    return score


def _is_backchannel(text: str) -> bool:
    body = (text or "").strip()
    if not body:
        return True
    if body.startswith("笑死"):
        return True
    if BACKCHANNEL_RE.match(body):
        return True
    return len(re.sub(r"[\W_]+", "", body, flags=re.UNICODE)) <= 1


def _pick_followup_targets(
    items: list,
    bot_text: str,
    last_sender_id: str,
    related_score: int,
    similarity: float,
) -> dict:
    """选主回复对象与第二个人；两人内容一致时不选第二个人。"""
    scored = [
        (_score_followup_item(item, bot_text, last_sender_id), item)
        for item in items
    ]
    if not scored:
        return {}

    related = [
        (score, item)
        for score, item in scored
        if score >= related_score
        or _bigram_overlap(item.get("text") or "", bot_text) > 0
    ]
    direct_pool = [
        item
        for item in items
        if item.get("is_addressed")
        or item.get("is_at_bot")
        or item.get("is_reply_to_bot")
    ]
    # 直接问你的那条永远优先，不能被「更相关的第二个人」顶掉。
    if direct_pool:
        main_pool = [
            (score, item) for score, item in scored if item in direct_pool
        ]
    else:
        main_pool = related or scored
    main_pool.sort(
        key=lambda pair: (pair[0], pair[1].get("created_at", 0)),
        reverse=True,
    )
    main = main_pool[0][1]

    second = None
    second_pool = [
        (score, item)
        for score, item in scored
        if item.get("sender_id") != main.get("sender_id")
        and not _is_backchannel(item.get("text") or "")
        and _text_similarity(item.get("text") or "", main.get("text") or "")
        < similarity
    ]
    if second_pool:
        second_pool.sort(
            key=lambda pair: (pair[0], pair[1].get("created_at", 0)),
            reverse=True,
        )
        second = second_pool[0][1]
    return {"main": main, "second": second, "has_related": bool(related)}


# 支持的分享链接。QQ 小程序卡片里的短链（b23.tv / v.douyin.com / xhslink.com）
# 也算在内；只用于唤醒与兜底，真正解析交给 parser 插件。
SHARE_URL_RE = re.compile(
    r"https?://(?:[A-Za-z0-9-]+\.)*(?:"
    r"bilibili\.com|b23\.tv|bili2233\.cn|"
    r"douyin\.com|iesdouyin\.com|"
    r"kuaishou\.com|chenzhongtech\.com|"
    r"xiaohongshu\.com|xhslink\.com|xhslink\.cn"
    r")[^\s<>\"'）)】]*",
    re.IGNORECASE,
)

# 点歌 / 聊歌意图。真正的搜索/发歌交给 astrbot_plugin_music 的 LLM Tool；
# 只聊歌不发歌名时，模型可以追问或接话，不强行点歌。
MUSIC_INTENT_RE = re.compile(
    r"("
    r"想听|要听|听一下|听一首|放一首|放首|来一首|来首|点歌|"
    r"这首歌|这首|那首歌|那首|这歌|那歌|"
    r"单曲循环|循环|在听|我听的是|我在听|最近在听|"
    r"推荐.{0,8}歌|有没有.{0,8}歌|什么歌|歌名|BGM|背景音乐|"
    r"歌.{0,6}好听|好听.{0,6}歌|"
    r"《[^》]{1,20}》"
    r")",
    re.IGNORECASE,
)

# 聊视频/内容意图：没有链接时只接话，不假装看过具体内容。
VIDEO_INTENT_RE = re.compile(
    r"("
    r"这个视频|这段视频|那个视频|那段视频|视频好看|视频不错|视频太|"
    r"刷到.{0,8}视频|看了.{0,6}视频|看个视频|分享.{0,6}视频|安利.{0,6}视频|"
    r"这个剪辑|这段剪辑|这个片段|这个短片|这个直播|"
    r"这个番|这部番|这个剧|这部剧|这个电影|这部电影|这个综艺|这个纪录片|"
    r"这个UP|这个博主|这个主播"
    r")",
    re.IGNORECASE,
)

# 歌词意图：查歌词 / 看歌词 / 这首歌怎么唱。调用 query_lyrics_by_name 发歌词图，
# 工具现在会返回一段歌词摘录，模型再据此评论。
LYRICS_INTENT_RE = re.compile(
    r"(歌词|唱词|歌词大意|查歌词|看歌词|这首歌.{0,6}唱|这句.{0,4}词)",
    re.IGNORECASE,
)

# 机器人反问「想听哪首 / 什么歌」后，用户下一句往往只是歌名。
# 这个正则只用来判断「机器人刚才是不是在追问」，不判断用户说了什么。
MEDIA_MUSIC_ASK_RE = re.compile(
    r"(哪首|哪一首|什么歌|歌名|想听什么|听什么|点哪|谁的歌|哪支|哪个歌|"
    r"真名|名字|叫啥|叫什么)",
    re.IGNORECASE,
)
MEDIA_VIDEO_ASK_RE = re.compile(
    r"(什么视频|哪个视频|哪一期|视频名|什么内容|发.{0,6}链接|链接.{0,6}发|哪个up|哪个UP)",
    re.IGNORECASE,
)

SHARE_HINT_MARKER = "[qqbotstack-share-hint]"
MUSIC_HINT_MARKER = "[qqbotstack-music-hint]"
VIDEO_HINT_MARKER = "[qqbotstack-video-hint]"
LYRICS_HINT_MARKER = "[qqbotstack-lyrics-hint]"
FOOD_HINT_MARKER = "[qqbotstack-food-hint]"
API_HINT_MARKER = "[qqbotstack-api-hint]"
ADMIN_HINT_MARKER = "[qqbotstack-admin-hint]"

# 推理块在 OpenAI 兼容协议里的 part 类型 / 字段名。
# Beam（OpenCode）拒绝渲染 reasoning_content，请求前统一剥掉。
_REASONING_PART_TYPES = frozenset({"think", "thinking", "reasoning"})
_REASONING_KEYS = ("reasoning_content", "reasoning")

# 吃什么意图。推荐交给 what_to_eat 插件的数据 + recommend_food 工具，
# 插件自己的自动回复由 qqbotstack_tools 在运行时关掉。
FOOD_INTENT_RE = re.compile(r"(吃什么|吃啥|饿了|吃点什么)", re.IGNORECASE)

# 群管相关词：不负责唤醒，只在已唤醒的轮次提醒模型「写操作没有工具」。
ADMIN_HINT_RE = re.compile(
    r"(禁言|解禁|踢了|踢人|改群名|改头衔|改昵称|改名片|群公告|设精|精华|上管|下管|"
    r"全员禁言|全体禁言)",
    re.IGNORECASE,
)

# qqadmin 的写操作 LLM 工具。need_auth 参数是模型可填的，留着就是绕过权限的口子；
# 这些工具运行时一律停用，群管操作继续走 /禁言、/踢了 这样的命令。
QQADMIN_MUTATING_TOOLS = (
    "llm_set_group_ban",
    "llm_set_group_card",
    "llm_set_group_special_title",
    "llm_set_group_whole_ban",
    "llm_set_group_kick",
    "llm_set_group_block",
    "llm_set_essence_msg",
    "llm_set_group_name",
    "llm_set_group_portrait",
    "llm_send_group_notice",
    "llm_upload_group_file",
    "llm_delete_group_file",
)

# parser 插件读到这个哨兵 whitelist 后会直接跳过自动解析，
# 由本插件的 parse_share_link 工具调用它的 parser 实例来发送。

def _iter_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_strings(value)
    elif isinstance(obj, (list, tuple)):
        for value in obj:
            yield from _iter_strings(value)


def _extract_url_from_text(text: str) -> str | None:
    if not text:
        return None
    match = SHARE_URL_RE.search(text)
    if not match:
        return None
    return match.group(0).rstrip(".,;!?，。；！？、")


def _extract_url_from_json(data) -> str | None:
    """从 QQ 卡片 Json 段里提取跳转 URL（兼容 miniapp / detail_1 / news）。"""
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:
            return _extract_url_from_text(data)
    if not isinstance(data, dict):
        return None

    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    priority_paths = (
        ("miniapp", "legacyUrl"),
        ("miniapp", "pcJumpUrl"),
        ("miniapp", "jumpUrl"),
        ("miniapp", "sourceUrl"),
        ("miniapp", "url"),
        ("detail_1", "qqdocurl"),
        ("detail_1", "jumpUrl"),
        ("detail_1", "url"),
        ("detail_1", "sourceUrl"),
        ("detail_1", "shareUrl"),
        ("detail_1", "targetUrl"),
        ("news", "jumpUrl"),
        ("news", "url"),
        ("news", "sourceUrl"),
        ("news", "shareUrl"),
        ("music", "musicUrl"),
        ("music", "jumpUrl"),
        ("music", "url"),
    )
    for first, second in priority_paths:
        node = meta.get(first)
        if not isinstance(node, dict):
            continue
        value = node.get(second)
        if not isinstance(value, str):
            continue
        cleaned = urllib.parse.unquote(value.replace("\\/", "/"))
        url = _extract_url_from_text(cleaned)
        if url:
            return url

    for value in _iter_strings(data):
        cleaned = urllib.parse.unquote(value.replace("\\/", "/"))
        url = _extract_url_from_text(cleaned)
        if url:
            return url
    return None


def _extract_share_url(event) -> str | None:
    for component in event.get_messages():
        if isinstance(component, Json):
            url = _extract_url_from_json(getattr(component, "data", None))
            if url:
                return url
    return _extract_url_from_text(event.message_str or "")


def _find_plugin(name: str):
    meta = _find_plugin_meta(name)
    if meta is not None and meta.star_cls is not None:
        return meta.star_cls
    return None


def _find_plugin_meta(name: str):
    for metadata in star_map.values():
        if metadata.name == name:
            return metadata
    return None


DEFAULTS = {
    "allowed_group": "",
    "keywords": [],
    "random_prob": 0.0,
    # 下面这些缺省值与 config.example.json / docs 保持一致；
    # 实际运行以实例 config.json 为准。
    "random_cooldown_sec": 180,
    "wake_prefix": "/",
    "routing_enabled": True,
    "model_simple": "Beam",
    "model_complex": "HY3-Free",
    "simple_max_len": 14,
    "error_reply_enabled": True,
    "error_reply_lines": list(DEFAULT_ERROR_LINES),
    "share_wake_enabled": True,
    # 私聊默认不回复：AstrBot 默认会把任何私聊都当唤醒，陌生人可以直接
    # 跟 bot 聊起来。需要私聊功能时再设为 true。
    "private_reply_enabled": False,
    "music_intent_enabled": True,
    "video_intent_enabled": True,
    "video_reply_cooldown_sec": 60,
    "food_intent_enabled": True,
    "food_reply_cooldown_sec": 60,
    "api_intent_enabled": True,
    "api_reply_cooldown_sec": 60,
    "api_allowlist": [
        "看看治愈",
        "讲个笑话",
        "来句诗",
        "讲讲古诗",
        "挑战古诗词",
        "来句情话",
        "毒鸡汤",
        "来碗鸡汤",
        "今日运势",
        "看看动漫",
        "来个头像",
        "电脑壁纸",
        "高清壁纸",
        "bing图",
    ],
    # 模型断路器：被路由的主模型连续失败 N 次就熔断，改走 fallback 模型；
    # 后台按间隔探活，恢复后自动切回。HY4 由 AstrBot 的 agent fallback 链继续兜。
    "breaker_enabled": True,
    "breaker_threshold": 3,
    "breaker_probe_interval_sec": 180.0,
    # 熔断期间直接在 build 阶段把这一轮选成 HY3 的 provider（AstrBot 的
    # selected_provider），避免继续撞 zgate-beam 的 20 秒 source timeout。
    # 留空则退回「只改 req.model」的旧行为。
    "breaker_fallback_provider": "zgate-router",
    # Beam 和 HY3 都熔断时直接选 HY4 的 provider；留空则只靠 fallback 链。
    "breaker_last_provider": "zgate-hy4",
    "model_simple_fallback": "HY3-Free",
    "model_complex_fallback": "HY3-Free",
    # 图片轮次直接交给能看图的模型解码并回复，主文本模型不参与生成。
    # 留空则退回「只给 [图片] 占位、不读图」的策略。
    "model_image": "HY3-Free",
    # Beam（OpenCode 上游）不能渲染 reasoning_content：历史里的 think 块会被
    # AstrBot 转成 reasoning_content 回传，导致每轮 400 prompt_rendering_failed。
    # 请求前把 think part / reasoning_content 从上下文里剥掉。
    "strip_reasoning_from_context": True,
    # 复读治理：Beam 会顺着上下文里自己说过的句子继续写（2026-10-28 实测
    # 「先喝茶」在 5 分钟内被复用 5 次）。请求前折叠近似重复的旧回复；
    # 每轮末尾注入禁复读块；仍然写出近重复的短句时，重说一次。
    "context_dedup_enabled": True,
    "repeat_guard_enabled": True,
    "repeat_regen_enabled": True,
    # 图片轮：主文本模型只看到 [图片] 占位；当前轮图片保留给 model_image 解码，
    # 历史上下文里的 image part 统一替换成 [图片] 文本。设 False 则完全不处理。
    "image_judge_only": True,
    "share_reply_cooldown_sec": 60,
    "followup_enabled": True,
    "followup_window_sec": 300,
    "followup_debounce_sec": 6.0,
    "followup_at_debounce_sec": 1.5,
    "followup_jitter_sec": 1.5,
    "followup_max_messages": 8,
    "followup_min_chars": 2,
    "followup_related_score": 2,
    "followup_similarity": 0.85,
    "followup_second_quote": True,
    "followup_quote_main": False,
    "followup_private": False,
    "followup_ignore_ids": [],
    "followup_max_chain": 10,
    # 续聊判定器：窗口要关/消息要被忽略时，用小模型判断对方是否还在跟你说、
    # 还想不想聊。是就把这条消息当接话收进来，不再靠启发式硬掐。
    "followup_judge_enabled": True,
    "followup_judge_provider_id": "zgate-router",
    "followup_judge_cooldown_sec": 90.0,
    "interest_enabled": True,
    "interest_initial": 70.0,
    "interest_decay_per_min": 1.0,
    "interest_direct_gain": 25.0,
    "interest_related_gain": 6.0,
    "interest_reply_cost": 2.0,
    "interest_unrelated_loss": 8.0,
    "interest_threshold": 20.0,
    "interest_high": 60.0,
    "interest_image_threshold": 50.0,
    "scope_guard_enabled": True,
    "scope_loss": 12.0,
    "scope_min_chars": 6,
    # 跑题只扣心动值、不直接关窗（模块 docstring 与 CHANGELOG 的既定决策）。
    "scope_close_window": False,
    "image_reply_cooldown_sec": 30.0,
    "image_reply_prob": 0.5,
    "media_pending_enabled": True,
    "media_pending_sec": 300,
    "idle_reply_enabled": True,
    "idle_reply_prob": 0.10,
    "idle_cooldown_sec": 180.0,
    "idle_min_interest": 60.0,
    "laugh_join_prob": 0.15,
    "laugh_join_cooldown_sec": 240.0,
    "interject_min_chars": 6,
    "interject_gap_sec": 45.0,
    "interject_window_sec": 30.0,
    "interject_max_msgs": 4,
}

# 出现这些词就按「复杂」处理，交给质量更好的模型。
# AI/命令行这类话题在 Beam 上最容易变成「你先说清楚」（2026-10-28 15:06），
# 所以把它们也划进复杂轮，交给质量模型接。
COMPLEX_HINTS = (
    "为什么", "怎么", "如何", "分析", "解释", "写", "代码", "方案", "评价",
    "推荐", "总结", "翻译", "对比", "原因", "帮我", "是不是", "能不能",
    "喜欢", "介绍", "关系", "世界", "设定", "故事", "以前", "过去",
    "知道吗", "听过", "看过", "玩过", "了解", "认识",
    "复读", "重复",
    "cli", "命令行", "终端", "模型", "提示词", "ai", "gemini", "claude",
    "gpt", "deepseek", "openai", "api", "token", "额度", "中转", "反代",
    "封号", "订阅", "部署", "显卡",
)

# ASCII 提示词的单词边界匹配（避免 ai 命中 said、api 命中 rapid）。
# 每次 LLM 请求都要跑一遍，正则在模块加载时编译好，不再靠 re 内部缓存。
_COMPLEX_ASCII_RE = {
    hint: re.compile(r"(?<![a-z0-9])" + re.escape(hint) + r"(?![a-z0-9])")
    for hint in COMPLEX_HINTS
    if hint.isascii()
}


def _has_complex_hint(text: str) -> bool:
    """ASCII 提示词按单词边界匹配（避免 ai 命中 said、api 命中 rapid）。"""
    low = (text or "").lower()
    for hint in COMPLEX_HINTS:
        if hint.isascii():
            if _COMPLEX_ASCII_RE[hint].search(low):
                return True
        elif hint in low:
            return True
    return False

# 世界书：按关键词命中后注入设定，常驻条目每轮都注入。
# 单轮注入有上限，避免把上下文塞爆、也避免设定抢了人格的声音。
# 上一轮还在生成时到达的消息：先缓存，当前回复发完后再等一小段，
# 把同一批合并成一条，避免一条消息触发一次生成。
LATE_DEBOUNCE_SEC = 2.0


def _late_item(event, text: str, has_image: bool) -> dict:
    sender_id = str(event.get_sender_id() or "")
    name = ""
    try:
        name = str(event.get_sender_name() or "")
    except Exception:  # noqa: BLE001
        name = ""
    return {
        "sender_id": sender_id,
        "sender_name": name or sender_id or "群友",
        "text": (text or "").strip(),
        "has_image": bool(has_image),
    }


def _format_late_items(items: list[dict]) -> str:
    lines: list[str] = []
    last_name = ""
    for item in items[:8]:
        name = str(item.get("sender_name") or item.get("sender_id") or "群友")
        body = str(item.get("text") or "").strip()
        if item.get("has_image"):
            body = (body + " [图片]").strip() if body else "[图片]"
        if not body:
            continue
        if name != last_name:
            lines.append(f"{name}：{body}")
            last_name = name
        else:
            lines.append(body)
    if not lines:
        return ""
    note = (
        "（下面的「名字：内容」只是给你看的记录格式。"
        "回复时不要写名字前缀，也不要按人名分行逐条回，"
        "用一两句话接住其中一件事就行。）"
    )
    # 说明放在记录前面：超过 1200 字被截断时，先丢记录而不是格式要求。
    return ("以下是不同人的连续发言（不要串人）：\n" + note + "\n" + "\n".join(lines))[:1200]


LORE_MAX_ENTRIES = 2
LORE_MAX_CHARS = 1400
LORE_HEADER = "\n\n[以下是你所知道的设定，用于保持世界观一致；不要原文复述，也不要解释它从哪来]\n"

# 代词追问（「他长啥样」「她后来呢」）本身不含人名，世界书会漏命中。
# 这种情况下把上一轮机器人回复一起拿来取词，别让模型只能自己编。
PRONOUN_HINTS = ("他", "她", "它", "这人", "那人", "这个", "那个", "其")


def _lore_match_text(
    text: str, bot_text: str = "", topic_text: str = ""
) -> str:
    text = (text or "").strip()
    if any(hint in text for hint in PRONOUN_HINTS):
        extra = " ".join(
            part[-240:]
            for part in (str(bot_text or ""), str(topic_text or ""))
            if part.strip()
        )
        if extra:
            text = (text + " " + extra).strip()
    return text


def _load_config() -> dict:
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
    conf = dict(DEFAULTS)
    try:
        with open(path, encoding="utf-8") as fh:
            conf.update(json.load(fh))
    except FileNotFoundError:
        logger.warning(f"[qqbotstack_guard] config.json not found at {path}")
    except (OSError, ValueError) as exc:
        logger.error(f"[qqbotstack_guard] failed to read config.json: {exc}")
    return conf


def _load_worldbook() -> list:
    """读同目录的 worldbook.json。缺失或损坏时返回空表，不影响其他功能。"""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "worldbook.json")
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        entries = data.get("entries", data) if isinstance(data, dict) else data
        return [e for e in entries if isinstance(e, dict) and e.get("content")]
    except FileNotFoundError:
        return []
    except (OSError, ValueError) as exc:
        logger.error(f"[qqbotstack_guard] failed to read worldbook.json: {exc}")
        return []


@register(
    "qqbotstack_guard",
    "M.Venn",
    "只允许指定群按 @ / 关键词 / 随机插话唤醒；分享、点歌、聊天、吃什么、API 小功能走 LLM 工具并接人格回复",
    "1.6.40",
)
class QQBotStackGuard(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        conf = _load_config()
        self.allowed_group = str(conf.get("allowed_group") or "").strip()
        self.keywords = tuple(k for k in conf.get("keywords") or [] if k)
        self.random_prob = float(conf.get("random_prob") or 0.0)
        self.random_cooldown_sec = int(conf.get("random_cooldown_sec") or 300)
        self.wake_prefix = str(conf.get("wake_prefix") or "/")
        self.routing_enabled = bool(conf.get("routing_enabled", True))
        self.model_simple = str(conf.get("model_simple") or "")
        self.model_complex = str(conf.get("model_complex") or "")
        self.simple_max_len = int(conf.get("simple_max_len") or 14)
        self.error_reply_enabled = bool(conf.get("error_reply_enabled", True))
        self.error_reply_lines = [
            str(line) for line in (conf.get("error_reply_lines") or []) if line
        ]
        self._last_error_line: str | None = None
        self.share_wake_enabled = bool(conf.get("share_wake_enabled", True))
        self.private_reply_enabled = bool(
            conf.get("private_reply_enabled", False)
        )
        self.music_intent_enabled = bool(conf.get("music_intent_enabled", True))
        self.video_intent_enabled = bool(conf.get("video_intent_enabled", True))
        self.video_reply_cooldown_sec = int(
            conf.get("video_reply_cooldown_sec") or 60
        )
        self.food_intent_enabled = bool(conf.get("food_intent_enabled", True))
        self.food_reply_cooldown_sec = int(
            conf.get("food_reply_cooldown_sec") or 60
        )
        self.api_intent_enabled = bool(conf.get("api_intent_enabled", True))
        self.api_reply_cooldown_sec = int(
            conf.get("api_reply_cooldown_sec") or 60
        )
        self.api_allowlist = tuple(
            str(x).strip() for x in (conf.get("api_allowlist") or []) if str(x).strip()
        )
        self._api_wake_names = None
        self._api_wake_re_obj = None
        self.breaker_enabled = bool(conf.get("breaker_enabled", True))
        self.breaker_threshold = int(conf.get("breaker_threshold") or 3)
        self.breaker_probe_interval_sec = float(
            conf.get("breaker_probe_interval_sec") or 180.0
        )
        self.breaker_fallback_provider = str(
            conf.get("breaker_fallback_provider") or ""
        )
        self.breaker_last_provider = str(conf.get("breaker_last_provider") or "")
        self.model_simple_fallback = str(conf.get("model_simple_fallback") or "")
        self.model_complex_fallback = str(conf.get("model_complex_fallback") or "")
        self.model_image = str(conf.get("model_image") or "")
        self.strip_reasoning_from_context = bool(
            conf.get("strip_reasoning_from_context", True)
        )
        self.image_judge_only = bool(conf.get("image_judge_only", True))
        self._breaker_fails: dict[str, int] = {}
        self._breaker_open_models: set[str] = set()
        self._breaker_provider_ok = False
        self._breaker_last_ok = False
        self._probe_providers: dict[str, object] = {}
        self._probe_task: asyncio.Task | None = None
        self.share_reply_cooldown_sec = int(
            conf.get("share_reply_cooldown_sec") or 60
        )
        self._last_random_at = 0.0
        self._share_seen: dict[str, float] = {}
        self._last_video_chat: dict[str, float] = {}
        self._last_food_reply: dict[str, float] = {}
        self._last_api_reply: dict[str, float] = {}
        self._admin_tools_down: set[str] = set()
        self._admin_tools_check_at = 0.0
        self.followup_enabled = bool(conf.get("followup_enabled", True))
        self.followup_window_sec = float(conf.get("followup_window_sec") or 45)
        self.followup_debounce_sec = float(
            conf.get("followup_debounce_sec") or 6.0
        )
        self.followup_at_debounce_sec = float(
            conf.get("followup_at_debounce_sec") or 1.5
        )
        self.followup_jitter_sec = float(conf.get("followup_jitter_sec") or 1.5)
        self.followup_max_messages = int(conf.get("followup_max_messages") or 8)
        self.followup_min_chars = int(conf.get("followup_min_chars") or 2)
        self.followup_related_score = int(conf.get("followup_related_score") or 2)
        self.followup_similarity = float(conf.get("followup_similarity") or 0.85)
        self.followup_second_quote = bool(conf.get("followup_second_quote", True))
        self.followup_quote_main = bool(conf.get("followup_quote_main", False))
        self.followup_private = bool(conf.get("followup_private", False))
        self.followup_ignore_ids = {
            str(x) for x in (conf.get("followup_ignore_ids") or []) if x
        }
        self.followup_max_chain = int(conf.get("followup_max_chain") or 3)
        self.interest_enabled = bool(conf.get("interest_enabled", True))
        self.interest_initial = float(conf.get("interest_initial") or 70.0)
        self.interest_decay_per_min = float(
            conf.get("interest_decay_per_min") or 1.0
        )
        self.interest_direct_gain = float(conf.get("interest_direct_gain") or 25.0)
        self.interest_related_gain = float(conf.get("interest_related_gain") or 6.0)
        self.interest_reply_cost = float(conf.get("interest_reply_cost") or 2.0)
        self.interest_unrelated_loss = float(
            conf.get("interest_unrelated_loss") or 8.0
        )
        self.interest_threshold = float(conf.get("interest_threshold") or 20.0)
        self.interest_high = float(conf.get("interest_high") or 60.0)
        self.interest_image_threshold = float(
            conf.get("interest_image_threshold") or 50.0
        )
        self.scope_guard_enabled = bool(conf.get("scope_guard_enabled", True))
        self.scope_loss = float(conf.get("scope_loss") or 12.0)
        self.scope_min_chars = int(conf.get("scope_min_chars") or 6)
        self.scope_close_window = bool(conf.get("scope_close_window", True))
        self.image_reply_cooldown_sec = float(
            conf.get("image_reply_cooldown_sec") or 30.0
        )
        self.image_reply_prob = min(
            1.0, max(0.0, float(conf.get("image_reply_prob") or 0.5))
        )
        self._last_image_reply: dict[str, float] = {}
        self.followup_judge_enabled = bool(
            conf.get("followup_judge_enabled", True)
        )
        self.followup_judge_provider_id = str(
            conf.get("followup_judge_provider_id") or "zgate-router"
        )
        self.followup_judge_cooldown_sec = float(
            conf.get("followup_judge_cooldown_sec") or 90.0
        )
        self._judge_last_at: dict[str, float] = {}
        self._judge_wakes: dict[str, list[float]] = {}
        self.media_pending_enabled = bool(conf.get("media_pending_enabled", True))
        self.media_pending_sec = float(conf.get("media_pending_sec") or 180)
        # 静默期主动接话：窗口早就关了、也没人点他，但心动值还在，就按概率
        # 自己插一句。没有这条，非 @ 的消息只能等 3% 的随机插话。
        self.idle_reply_enabled = bool(conf.get("idle_reply_enabled", True))
        self.idle_reply_prob = min(
            1.0, max(0.0, float(conf.get("idle_reply_prob") or 0.12))
        )
        self.idle_cooldown_sec = float(conf.get("idle_cooldown_sec") or 120.0)
        self.idle_min_interest = float(conf.get("idle_min_interest") or 60.0)
        self._last_idle_at = 0.0
        # 群里笑成一片时偶尔跟着笑一声；只作为接话条目，不单独刷屏。
        self.laugh_join_prob = min(
            1.0, max(0.0, float(conf.get("laugh_join_prob") or 0.15))
        )
        self.laugh_join_cooldown_sec = float(
            conf.get("laugh_join_cooldown_sec") or 240.0
        )
        self._last_laugh_at = 0.0
        # 入场判断：机器人刚说过话、群里正多人在聊、对方在气头上时，
        # 都不该主动插话。
        self.interject_min_chars = int(conf.get("interject_min_chars") or 6)
        self.interject_gap_sec = float(conf.get("interject_gap_sec") or 45.0)
        self.interject_window_sec = float(conf.get("interject_window_sec") or 30.0)
        self.interject_max_msgs = int(conf.get("interject_max_msgs") or 4)
        self._last_bot_send_at = 0.0
        self._recent_msgs: dict[str, list[tuple[float, str, bool]]] = {}
        self._followup: dict[str, dict] = {}
        self.context_dedup_enabled = bool(
            conf.get("context_dedup_enabled", True)
        )
        self.repeat_guard_enabled = bool(conf.get("repeat_guard_enabled", True))
        self.repeat_regen_enabled = bool(conf.get("repeat_regen_enabled", True))
        # 真正发出去的最近回复（上下文折叠后仍要能判断「这句是不是刚说过」）。
        self._recent_bot_texts: dict[str, list[str]] = {}
        self._interest_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "interest.json"
        )
        self._interest_saved: dict[str, dict] = self._load_interest()
        self._interest_saved_at = 0.0
        self._late_buffer: dict[str, list[dict]] = {}
        self._late_waiter: dict[str, AstrMessageEvent] = {}
        self._pending_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "pending_media.json"
        )
        self._pending_media: dict[str, dict] = self._load_pending_media()
        self.worldbook = _load_worldbook()
        logger.info(
            f"[qqbotstack_guard] group={self.allowed_group} "
            f"keywords={list(self.keywords)} prob={self.random_prob} "
            f"lore={len(self.worldbook)} share={self.share_wake_enabled} "
            f"music={self.music_intent_enabled} video={self.video_intent_enabled} "
            f"food={self.food_intent_enabled} api={self.api_intent_enabled}"
            f"/{len(self.api_allowlist)} "
            f"followup={self.followup_enabled} window={self.followup_window_sec} "
            f"pending={self.media_pending_enabled}/{self.media_pending_sec} "
            f"idle={self.idle_reply_prob}/{self.idle_cooldown_sec:.0f}s"
            f"/{self.idle_min_interest:.0f} "
            f"laugh={self.laugh_join_prob}/{self.laugh_join_cooldown_sec:.0f}s "
            f"scope_close={self.scope_close_window} "
            f"breaker={self.breaker_enabled}/{self.breaker_threshold} "
            f"breaker_provider={self.breaker_fallback_provider or '-'} "
            f"breaker_last={self.breaker_last_provider or '-'} "
            f"strip_reasoning={self.strip_reasoning_from_context} "
            f"dedup={self.context_dedup_enabled} "
            f"repeat={self.repeat_guard_enabled}/{self.repeat_regen_enabled} "
            f"image_judge_only={self.image_judge_only} "
            f"image_prob={self.image_reply_prob:.2f} "
            f"judge={self.followup_judge_enabled}/{self.followup_judge_provider_id}"
            f"/{self.followup_judge_cooldown_sec:.0f}s "
            f"model={self.model_simple or '-'}/{self.model_complex or '-'} "
            f"model_image={self.model_image or '-'} "
            f"fallback={self.model_simple_fallback or '-'}/{self.model_complex_fallback or '-'} "
            f"ffmpeg={shutil.which('ffmpeg')} ffprobe={shutil.which('ffprobe')}"
        )
        self._register_status_page()

    def _register_status_page(self) -> None:
        try:
            self.context.register_web_api(
                "/qqbotstack_guard/status",
                self.page_status,
                ["GET"],
                "Guard runtime status",
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[qqbotstack_guard] register status page failed: {exc}")

    async def page_status(self):
        """Read-only runtime snapshot for views/status/index.html."""
        if _quart_jsonify is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        group_id = self.allowed_group
        state = self._followup.get(group_id) if group_id else None
        now = time.time()
        window = None
        if state:
            deadline = float(state.get("window_deadline") or 0)
            window = {
                "open": bool(deadline and now < deadline),
                "remaining_sec": max(0, int(deadline - now)) if deadline else 0,
                "interest": round(self._interest_value(state, now), 1),
                "chain": int(state.get("chain") or 0),
                "generating": bool(state.get("generating")),
                "bot_len": len(str(state.get("bot_text") or "")),
            }
        plugins = {
            name: _find_plugin(name) is not None
            for name in (
                "astrbot_plugin_parser",
                "astrbot_plugin_music",
                "astrbot_plugin_apis",
                "astrbot_plugin_what_to_eat",
                "astrbot_plugin_meme_manager",
                "qqbotstack_worldbook",
                "qqbotstack_memechance",
                "qqbotstack_tools",
                "qqbotstack_people",
            )
        }
        data = {
            "allowed_group": group_id,
            "keywords": list(self.keywords),
            "random_prob": self.random_prob,
            "random_cooldown_sec": self.random_cooldown_sec,
            "followup": {
                "enabled": self.followup_enabled,
                "window_sec": self.followup_window_sec,
                "current": window,
            },
            "routing": {
                "enabled": self.routing_enabled,
                "simple": self.model_simple,
                "complex": self.model_complex,
                "image": self.model_image,
                "simple_fallback": self.model_simple_fallback,
                "complex_fallback": self.model_complex_fallback,
            },
            "breaker": {
                "enabled": self.breaker_enabled,
                "open": self._beam_open(),
                "fail_count": self._model_fails(self.model_simple),
                "threshold": self.breaker_threshold,
                "probe_interval_sec": self.breaker_probe_interval_sec,
                "fallback_provider": self.breaker_fallback_provider,
                "provider_ready": self._breaker_provider_ok,
                "last_provider": self.breaker_last_provider,
                "last_provider_ready": self._breaker_last_ok,
                "models": {
                    model: {
                        "open": model in self._breaker_open_models,
                        "fail_count": self._model_fails(model),
                    }
                    for model in self._monitored_models()
                },
            },
            "features": {
                "share": self.share_wake_enabled,
                "music": self.music_intent_enabled,
                "video": self.video_intent_enabled,
                "food": self.food_intent_enabled,
                "api": self.api_intent_enabled,
                "takeover_parser": bool(getattr(_find_plugin("qqbotstack_tools"), "takeover_parser", False)),
                "takeover_apis": bool(getattr(_find_plugin("qqbotstack_tools"), "takeover_apis", False)),
                "takeover_food": bool(getattr(_find_plugin("qqbotstack_tools"), "takeover_food", False)),
                "strip_reasoning": self.strip_reasoning_from_context,
                "image_judge_only": self.image_judge_only,
            },
            "plugins": plugins,
            "worldbook_fallback_entries": len(self.worldbook),
        }
        return _quart_jsonify({"ok": True, "data": data})

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        """所有插件加载完后立刻关掉 parser 自动解析，避免第一条消息抢跑。"""
        self._ensure_tools_takeover()
        await self._ensure_admin_tools()
        logger.info(
            f"[qqbotstack_guard] delegation "
            f"tools={_find_plugin('qqbotstack_tools') is not None} "
            f"people={_find_plugin('qqbotstack_people') is not None} "
            f"worldbook={_find_plugin('qqbotstack_worldbook') is not None}"
        )
        self._install_breaker()
        if (
            self.breaker_enabled
            and self._probe_providers
            and self._probe_task is None
        ):
            self._probe_task = asyncio.create_task(self._probe_loop())

    # ---------------- 模型断路器 ----------------

    def _install_breaker(self) -> None:
        """给主模型和第一 fallback 的 provider 各包一层计数器。

        AstrBot 的 agent fallback 只在单次请求内切换（Beam 挂了当轮切 HY3），
        guard 每轮仍会把模型名改成 Beam，等于每轮都先撞一次挂掉的上游。
        这里按模型分别计数：连续失败 N 次就把该模型标成不可用，后续 agent
        请求立即返回 err（不再等满 source timeout），交给 runner 的 fallback
        链；后台探活恢复后自动解除。
        """
        if not self.breaker_enabled:
            return
        if not self.model_simple_fallback and not self.model_complex_fallback:
            logger.warning(
                "[qqbotstack_guard] breaker enabled but no fallback model set; skipped"
            )
            return
        targets = set(self._monitored_models())
        for provider in self.context.get_all_providers():
            provider_id = str(provider.provider_config.get("id", "") or "")
            if provider_id and provider_id == self.breaker_fallback_provider:
                self._breaker_provider_ok = True
            if provider_id and provider_id == self.breaker_last_provider:
                self._breaker_last_ok = True
            try:
                model = provider.get_model()
            except Exception:  # noqa: BLE001
                continue
            if model not in targets:
                continue
            if getattr(provider, "_qqbotstack_breaker", False):
                # 热重载后 provider 还是旧对象：拿回原始方法重新包一层，
                # 否则计数闭包会指向已经卸载的旧插件实例。
                orig_text_chat = getattr(
                    provider, "_qqbotstack_orig_text_chat", None
                )
                if orig_text_chat is None:
                    continue
            else:
                orig_text_chat = provider.text_chat

            async def counted_text_chat(*args, _orig=orig_text_chat, _model=model, **kwargs):
                # 同一个 provider 会被 guard 改 model（图片轮次走 HY3），
                # 只统计真正发给被监控模型的请求，避免别的模型的失败误触发熔断。
                effective = kwargs.get("model") or _model
                if (
                    effective == _model
                    and _model in self._breaker_open_models
                    and "contexts" in kwargs
                ):
                    # agent 请求：立即失败，让 runner 直接切下一个 provider。
                    # 后台插件（只传 prompt，不传 contexts）保持原样，避免
                    # 返回 err 破坏它们的解析。
                    logger.info(f"[qqbotstack_guard] skip {_model}: breaker open")
                    return self._breaker_skip_response(_model)
                try:
                    response = await _orig(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    if effective == _model:
                        self._note_model_failure(_model, exc)
                    raise
                if effective == _model:
                    self._note_model_success(_model)
                return response

            provider.text_chat = counted_text_chat
            provider._qqbotstack_breaker = True
            provider._qqbotstack_orig_text_chat = orig_text_chat
            self._probe_providers[model] = provider
            logger.info(f"[qqbotstack_guard] breaker watching model={model}")
        if self.breaker_fallback_provider and not self._breaker_provider_ok:
            logger.warning(
                f"[qqbotstack_guard] breaker fallback provider "
                f"{self.breaker_fallback_provider} not found; model override only"
            )
        if self.breaker_last_provider and not self._breaker_last_ok:
            logger.warning(
                f"[qqbotstack_guard] breaker last provider "
                f"{self.breaker_last_provider} not found; both-open uses HY3"
            )

    def _monitored_models(self) -> list[str]:
        """需要独立计数的模型：主模型 + 第一 fallback（去重保序）。"""
        models: list[str] = []
        for model in (
            self.model_simple,
            self.model_complex,
            self.model_simple_fallback,
            self.model_complex_fallback,
        ):
            if model and model not in models:
                models.append(model)
        return models

    def _beam_open(self) -> bool:
        open_models = getattr(self, "_breaker_open_models", None) or set()
        return any(
            model in open_models
            for model in (
                getattr(self, "model_simple", ""),
                getattr(self, "model_complex", ""),
            )
            if model
        )

    def _fallback_model(self) -> str:
        return getattr(self, "model_simple_fallback", "") or getattr(
            self, "model_complex_fallback", ""
        )

    def _fallback_open(self) -> bool:
        model = self._fallback_model()
        open_models = getattr(self, "_breaker_open_models", None) or set()
        return bool(model) and model in open_models

    def _model_fails(self, model: str) -> int:
        fails = getattr(self, "_breaker_fails", None) or {}
        return int(fails.get(model, 0))

    @staticmethod
    def _breaker_skip_response(model: str):
        """熔断模型的即时失败响应。runner 会把它当成 err 并切下一个 provider。"""
        try:
            from astrbot.core.provider.entities import LLMResponse
        except Exception:  # noqa: BLE001
            raise RuntimeError(f"{model} breaker open")
        return LLMResponse(
            role="err",
            completion_text=f"LLM 响应错误：{model} breaker open",
        )

    @staticmethod
    def _is_countable_failure(exc: Exception) -> bool:
        """只把「上游不可用」计入熔断。

        4xx（429 除外）是请求内容/参数问题：换模型可能有用，但探活只发纯
        `ping`，永远复现不了这类错误，计入就会变成「开了又关」的抖动。
        5xx / 429 / 超时 / 连接错误 / 未知异常都算。
        """
        status = getattr(exc, "status_code", None)
        if status is None:
            status = getattr(getattr(exc, "response", None), "status_code", None)
        if status is not None:
            try:
                code = int(status)
            except (TypeError, ValueError):
                return True
            if 400 <= code < 500 and code != 429:
                return False
        return True

    def _note_model_failure(self, model: str, exc: Exception) -> None:
        if not self._is_countable_failure(exc):
            logger.debug(
                f"[qqbotstack_guard] {model} failure ignored "
                f"(non-retryable {type(exc).__name__}): {str(exc)[:120]}"
            )
            return
        reason = str(exc)[:160] or type(exc).__name__
        if model in self._breaker_open_models:
            logger.warning(
                f"[qqbotstack_guard] breaker open, {model} still failing: {reason}"
            )
            return
        count = self._model_fails(model) + 1
        self._breaker_fails[model] = count
        if count >= self.breaker_threshold:
            self._breaker_open_models.add(model)
            logger.warning(
                f"[qqbotstack_guard] breaker OPEN after {count}x {model} failures "
                f"({reason}); skip it, probe every "
                f"{self.breaker_probe_interval_sec:.0f}s"
            )
        else:
            logger.warning(
                f"[qqbotstack_guard] {model} failure "
                f"{count}/{self.breaker_threshold}: {reason}"
            )

    def _note_model_success(self, model: str) -> None:
        if not self._model_fails(model) and model not in self._breaker_open_models:
            return
        if model in self._breaker_open_models:
            self._breaker_open_models.discard(model)
            logger.info(f"[qqbotstack_guard] breaker CLOSE: {model} recovered")
        self._breaker_fails[model] = 0

    async def _probe_loop(self) -> None:
        """熔断期间定时探活；成功时自动解除对应模型的熔断。"""
        try:
            while True:
                await asyncio.sleep(self.breaker_probe_interval_sec)
                for model, provider in list(self._probe_providers.items()):
                    if model not in self._breaker_open_models:
                        continue
                    orig = getattr(provider, "_qqbotstack_orig_text_chat", None)
                    if orig is None:
                        continue
                    try:
                        await orig(
                            prompt="ping",
                            session_id=None,
                            request_max_retries=1,
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.info(
                            f"[qqbotstack_guard] breaker probe {model}: still down "
                            f"({str(exc)[:120]})"
                        )
                    else:
                        self._note_model_success(model)
        except asyncio.CancelledError:  # noqa: PERF203
            pass

    def _apply_breaker_provider(self, event) -> None:
        """熔断期间在 build 阶段直接选下一个 provider。

        Beam 熔断 → zgate-router（HY3）；Beam 和 HY3 都熔断 → zgate-hy4。
        这样连 source timeout 都不用等，直接走健康的那一层。
        """
        if not getattr(self, "breaker_enabled", False):
            return
        if not self._beam_open():
            return
        target = ""
        if (
            self._fallback_open()
            and getattr(self, "breaker_last_provider", "")
            and getattr(self, "_breaker_last_ok", False)
        ):
            target = self.breaker_last_provider
        elif getattr(self, "breaker_fallback_provider", "") and getattr(
            self, "_breaker_provider_ok", False
        ):
            target = self.breaker_fallback_provider
        if not target:
            return
        try:
            event.set_extra("selected_provider", target)
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[qqbotstack_guard] set selected_provider failed: {exc}")

    # priority=100：必须先于 parser 插件执行。否则 parser 会先自动发媒体，
    # AstrBot 的 _has_send_oper 门槛会让默认 LLM 直接跳过，人格接话就没了。
    @filter.event_message_type(filter.EventMessageType.GROUP_MESSAGE, priority=100)
    async def guard(self, event: AstrMessageEvent):
        group_id = str(event.get_group_id() or "")
        if not self.allowed_group or group_id != self.allowed_group:
            event.stop_event()
            return

        self._apply_breaker_provider(event)

        # 媒体工具插件负责 parser/apis/what_to_eat 的运行时接管。
        self._ensure_tools_takeover()
        # 每个群常驻一份状态：窗口关了也留住心动值和话题，重启后从 interest.json 恢复。
        self._ensure_state(group_id)
        # qqadmin 写操作工具的停用按分钟级重查，插件热重载后也能补上。
        if time.time() - self._admin_tools_check_at >= 60.0:
            self._admin_tools_check_at = time.time()
            await self._ensure_admin_tools()

        text = event.message_str or ""
        sender_id = str(event.get_sender_id() or "")
        self_id = str(event.get_self_id() or "")
        if text.strip() in ("/忘记我", "／忘记我"):
            await self._people_forget(sender_id)
            event.stop_event()
            yield event.plain_result(
                "好，我这边关于你的名字和聊天记录清掉了。偏好记忆用 /忘记 再清一次。"
            )
            return
        if (
            sender_id
            and sender_id != self_id
            and sender_id not in self.followup_ignore_ids
        ):
            # 每条群消息都记名字簿和历史发言；独立文件，不进 DB / 日志。
            await self._people_remember(event, group_id)
            self._track_recent(
                group_id, sender_id, self._is_addressed(event, text)
            )

        components = event.get_messages()
        has_image = any(isinstance(c, Image) for c in components)

        # 接话窗口：机器人刚回完，窗口内的普通文本先收集，不逐条回。
        state = self._followup.get(group_id)
        if state and state.get("generating"):
            if time.time() > state.get("generating_until", 0):
                # 模型/发送异常时不要永久卡在 generating。
                state["generating"] = False
                state["generating_until"] = 0
            elif not self._is_special_message(event, text):
                sender_id = str(event.get_sender_id() or "")
                self_id = str(event.get_self_id() or "")
                is_direct = self._is_addressed(event, text)
                interest = self._interest_value(state) if state else 0.0
                image_ok = bool(has_image) and (
                    is_direct or interest >= self.interest_image_threshold
                )
                text_ok = (
                    not has_image
                    and bool(text.strip())
                    and (is_direct or len(text) >= self.followup_min_chars)
                )
                if (
                    self.followup_enabled
                    and sender_id
                    and sender_id != self_id
                    and sender_id not in self.followup_ignore_ids
                    and (image_ok or text_ok)
                ):
                    # 上一轮还没生成完：先缓存，等它发完后把同一批 late 合并成一次。
                    logger.info(
                        f"[followup] defer late group={group_id} "
                        f"sender={sender_id} len={len(text)} image={has_image}"
                    )
                    buf = self._late_buffer.setdefault(group_id, [])
                    if len(buf) < self.followup_max_messages:
                        buf.append(_late_item(event, text, has_image))
                    waiter = self._late_waiter.get(group_id)
                    # 图片优先做载体，保证图片本身不丢；否则第一个 late 事件做载体。
                    if waiter is None or (has_image and waiter is not event):
                        self._late_waiter[group_id] = event
                        deadline = time.time() + 45
                        while time.time() < deadline:
                            current = self._followup.get(group_id)
                            if not current or not current.get("generating"):
                                break
                            await asyncio.sleep(0.4)
                        # 当前回复发完后，再收一小段，把同一轮后续消息并进来。
                        await asyncio.sleep(LATE_DEBOUNCE_SEC)
                        if self._late_waiter.get(group_id) is not event:
                            # 已被更晚的图片事件接管，别重复发。
                            event.stop_event()
                            return
                        items = self._late_buffer.pop(group_id, [])
                        self._late_waiter.pop(group_id, None)
                        for late_item in items:
                            try:
                                self._people_bump(late_item.get("sender_id") or "", 1)
                            except Exception:
                                pass
                        combined = _format_late_items(items)
                        if combined:
                            event.message_str = combined
                            event.set_extra(
                                "qqbotstack_followup_text", combined
                            )
                        if has_image:
                            event.set_extra("qqbotstack_image_turn", True)
                        logger.info(
                            f"[followup] late release group={group_id} "
                            f"items={len(items)} image={has_image} "
                            f"len={len(combined)}"
                        )
                        event.is_at_or_wake_command = True
                        return
                    event.stop_event()
                    return
                event.stop_event()
                return

        # 图片 / 表情包：以前在随机插话分支被直接吞掉，模型根本没机会看见。
        # 直接 @/叫他，或窗口中心动值还高时，放行给 LLM；AstrBot 会自动把
        # 无 image 模态的 Beam 切到 HY3/HY4。
        if (
            has_image
            and not self._is_special_message(event, text)
            and not _extract_share_url(event)
        ):
            now = time.time()
            addressed = self._is_addressed(event, text)
            window_open = bool(
                state and float(state.get("window_deadline") or 0) > now
            )
            interest = self._interest_value(state) if state else 0.0
            image_ok = addressed or (
                window_open
                and interest >= self.interest_image_threshold
                and now - self._last_image_reply.get(group_id, 0.0)
                >= self.image_reply_cooldown_sec
                and random.random() < self.image_reply_prob
            )
            if image_ok:
                if not text.strip():
                    event.message_str = "[图片]"
                event.set_extra("qqbotstack_image_turn", True)
                if state and not addressed:
                    self._add_interest(
                        state, self.interest_related_gain, "image-followup"
                    )
                self._last_image_reply[group_id] = now
                event.is_at_or_wake_command = True
                logger.info(
                    f"[image] wake group={group_id} addressed={addressed} "
                    f"interest={interest:.1f} window={window_open} "
                    f"prob={self.image_reply_prob:.2f}"
                )
                return
            if state:
                value = self._add_interest(
                    state, -self.interest_unrelated_loss, "image-ignored"
                )
                if value < self.interest_threshold:
                    state["window_deadline"] = 0
            event.stop_event()
            return

        if self.followup_enabled:
            sender_id = str(event.get_sender_id() or "")
            self_id = str(event.get_self_id() or "")
            if sender_id == self_id or sender_id in self.followup_ignore_ids:
                event.stop_event()
                return
            if await self._followup_candidate(event, group_id):
                await self._handle_followup(event, group_id)
                return
            if event.get_extra("qqbotstack_interest_ignored"):
                event.stop_event()
                return
            if (
                state
                and float(state.get("window_deadline") or 0) <= time.time()
                and text.strip()
                and not self._is_special_message(event, text)
                and await self._judge_maybe_wake(
                    event, state, group_id, text.strip(), "closed"
                )
            ):
                # 判定器说对方还在跟你说话：重开窗口，当接话处理。
                state["window_deadline"] = time.time() + self.followup_window_sec
                logger.info(
                    f"[followup] judge reopen group={group_id} "
                    f"sender={event.get_sender_name()}"
                )
                await self._handle_followup(event, group_id)
                return
            if state and self._is_special_message(event, text):
                # 指令 / 分享 / 点歌 / 聊视频：取消还没触发的接话窗口，
                # 但保留心动值，别让它跟着窗口一起清零。
                state["window_deadline"] = 0.0
                state["items"] = []
                self._save_interest()

        # 反问后的待答意图：机器人刚问「哪首 / 什么歌 / 什么视频」，
        # 用户下一句只回歌名/视频名时，即使过了接话窗口也要唤醒 LLM。
        if self.media_pending_enabled:
            sender_id = str(event.get_sender_id() or "")
            self_id = str(event.get_self_id() or "")
            is_direct = self._has_at_bot(event, self_id) or self._has_reply_to_bot(
                event, self_id
            )
            has_keyword = any(keyword in text for keyword in self.keywords)
            if self._is_special_message(event, text):
                self._clear_pending_media(group_id, [sender_id])
            else:
                pending_kind = self._take_pending_media(group_id, [sender_id])
                if pending_kind:
                    self._mark_pending_media(event, pending_kind)
                    if not is_direct and not has_keyword:
                        event.is_at_or_wake_command = True
                        logger.info(
                            f"[media-pending] answer group={group_id} "
                            f"sender={sender_id} kind={pending_kind}"
                        )
                        return
                    # @/关键词：不 return，让下面的原链路唤醒；
                    # music/video hint 已经挂在 event 上。

        # 指令（"/" 开头）交给默认管线，唤醒阶段已置位
        if self.wake_prefix and text.startswith(self.wake_prefix):
            return

        # 分享链接 / QQ 小程序卡片：唤醒 LLM，由 parse_share_link 工具解析发送。
        if self.share_wake_enabled:
            share_url = _extract_share_url(event)
            if share_url:
                now = time.time()
                key = f"{group_id}:{share_url}"
                if now - self._share_seen.get(key, 0.0) < self.share_reply_cooldown_sec:
                    event.stop_event()
                    return
                self._share_seen[key] = now
                if len(self._share_seen) > 200:
                    for old_key, _ in sorted(
                        self._share_seen.items(), key=lambda item: item[1]
                    )[:100]:
                        self._share_seen.pop(old_key, None)
                event.set_extra("qqbotstack_share_url", share_url)
                # 小程序卡片只有 Json 段，message_str 为空；AstrBot 的 LLM 阶段会把
                # 「无文本且无图片」的消息当空消息跳过，这里补上链接文本。
                if not text.strip():
                    event.message_str = share_url
                event.is_at_or_wake_command = True
                parsed = urllib.parse.urlsplit(share_url)
                safe_url = f"{parsed.netloc}{parsed.path}"[:100]
                logger.info(f"[qqbotstack_guard] share wake: {safe_url}")
                return

        # 歌词意图：唤醒 LLM，由音乐插件的 query_lyrics_by_name 发歌词图并返回摘录，
        # 模型拿到摘录后再评论，不只是一张图。
        if self.music_intent_enabled and text and LYRICS_INTENT_RE.search(text):
            event.set_extra("qqbotstack_lyrics_intent", True)
            event.is_at_or_wake_command = True
            logger.info("[qqbotstack_guard] lyrics intent wake")
            return

        # 自然语言点歌/聊歌意图：唤醒 LLM，由点歌插件的 play_song_by_name 工具发卡片。
        if self.music_intent_enabled and text and MUSIC_INTENT_RE.search(text):
            event.set_extra("qqbotstack_music_intent", True)
            if VIDEO_INTENT_RE.search(text):
                event.set_extra("qqbotstack_video_intent", True)
            event.is_at_or_wake_command = True
            logger.info("[qqbotstack_guard] music intent wake")
            return

        # 聊视频/内容意图：没有链接时只接话，不假装看过；带链接时上面的分享分支优先。
        if self.video_intent_enabled and text and VIDEO_INTENT_RE.search(text):
            now = time.time()
            if now - self._last_video_chat.get(group_id, 0.0) < self.video_reply_cooldown_sec:
                event.stop_event()
                return
            self._last_video_chat[group_id] = now
            event.set_extra("qqbotstack_video_intent", True)
            event.is_at_or_wake_command = True
            logger.info("[qqbotstack_guard] video chat intent wake")
            return

        # 吃什么：唤醒 LLM，由 recommend_food 工具出推荐，不让 what_to_eat 插件抢答。
        if self.food_intent_enabled and text and FOOD_INTENT_RE.search(text):
            now = time.time()
            if now - self._last_food_reply.get(group_id, 0.0) < self.food_reply_cooldown_sec:
                event.stop_event()
                return
            self._last_food_reply[group_id] = now
            event.set_extra("qqbotstack_food_intent", True)
            event.is_at_or_wake_command = True
            logger.info("[qqbotstack_guard] food intent wake")
            return

        # API 小功能：白名单关键词直接唤醒，由 fetch_api 工具取内容发送。
        api_re = self._api_wake_re()
        if (
            self.api_intent_enabled
            and api_re is not None
            and text
            and api_re.search(text)
        ):
            now = time.time()
            if now - self._last_api_reply.get(group_id, 0.0) < self.api_reply_cooldown_sec:
                event.stop_event()
                return
            self._last_api_reply[group_id] = now
            event.set_extra("qqbotstack_api_intent", api_re.search(text).group(0))
            event.is_at_or_wake_command = True
            logger.info("[qqbotstack_guard] api intent wake")
            return

        # 关键词：包含即可
        if any(keyword in text for keyword in self.keywords):
            event.is_at_or_wake_command = True
            return

        # @ 机器人 或 引用机器人的消息
        self_id = str(event.get_self_id())
        for component in components:
            if isinstance(component, At) and str(getattr(component, "qq", "")) == self_id:
                event.is_at_or_wake_command = True
                return
            if (
                isinstance(component, Reply)
                and str(getattr(component, "sender_id", "")) == self_id
            ):
                event.is_at_or_wake_command = True
                return

        # 随机插话只针对纯文本消息。
        # 图片、纯表情、空文本一律不随机 —— 否则会出现「答非所问」：
        # 主模型不认图，它只会回一句"我看不到这张图"，看起来像 bug。
        if has_image or not text.strip():
            event.stop_event()
            return

        # 静默期主动接话：窗口已经关了、也没人点他，但心动值还在。
        # 以前这里只剩 random_prob（3%），所以「不 @ 不叫关键词」几乎等于哑巴。
        now = time.time()
        if getattr(self, "idle_reply_enabled", False) and not self._is_special_message(event, text):
            idle_state = self._followup.get(group_id) or self._ensure_state(group_id)
            idle_interest = self._interest_value(idle_state)
            if (
                idle_interest >= self.idle_min_interest
                and now - self._last_idle_at >= self.idle_cooldown_sec
                and random.random() < self.idle_reply_prob
            ):
                ok, why = self._interject_allowed(
                    event, group_id, text, idle_state
                )
                if not ok:
                    logger.info(
                        f"[interest] skip idle group={group_id} reason={why} "
                        f"text={text[:30]!r}"
                    )
                else:
                    self._last_idle_at = now
                    self._add_interest(
                        idle_state, self.interest_related_gain, "idle-wake"
                    )
                    event.set_extra("qqbotstack_interject", True)
                    event.is_at_or_wake_command = True
                    logger.info(
                        f"[interest] idle wake group={group_id} "
                        f"value={idle_interest:.1f} text={text[:30]!r}"
                    )
                    return

        # 随机插话（带冷却，避免连续刷屏）
        if (
            self.random_prob > 0
            and now - self._last_random_at >= self.random_cooldown_sec
            and random.random() < self.random_prob
        ):
            random_state = self._followup.get(group_id) or self._ensure_state(
                group_id
            )
            ok, why = self._interject_allowed(
                event, group_id, text, random_state
            )
            if not ok:
                logger.info(
                    f"[qqbotstack_guard] skip random group={group_id} "
                    f"reason={why} text={text[:30]!r}"
                )
            else:
                self._last_random_at = now
                event.set_extra("qqbotstack_interject", True)
                logger.info(
                    f"[qqbotstack_guard] random reply triggered in group "
                    f"{group_id} text={text[:30]!r}"
                )
                event.is_at_or_wake_command = True
                return

        event.stop_event()

    def _is_special_message(self, event: AstrMessageEvent, text: str) -> bool:
        """指令、分享、点歌、聊视频走原链路，不进入接话收集。"""
        if self.wake_prefix and text.startswith(self.wake_prefix):
            return True
        if _extract_share_url(event):
            return True
        if self.music_intent_enabled and text and LYRICS_INTENT_RE.search(text):
            return True
        if self.music_intent_enabled and text and MUSIC_INTENT_RE.search(text):
            return True
        if self.video_intent_enabled and text and VIDEO_INTENT_RE.search(text):
            return True
        if self.food_intent_enabled and text and FOOD_INTENT_RE.search(text):
            return True
        api_re = self._api_wake_re()
        if self.api_intent_enabled and api_re is not None and text and api_re.search(text):
            return True
        return False

    @staticmethod
    def _has_at_bot(event: AstrMessageEvent, self_id: str) -> bool:
        return any(
            isinstance(component, At)
            and str(getattr(component, "qq", "")) == self_id
            for component in event.get_messages()
        )

    @staticmethod
    def _has_reply_to_bot(event: AstrMessageEvent, self_id: str) -> bool:
        return any(
            isinstance(component, Reply)
            and str(getattr(component, "sender_id", "")) == self_id
            for component in event.get_messages()
        )

    def _is_addressed(self, event: AstrMessageEvent, text: str) -> bool:
        """@ / 引用机器人 / 叫他的名字，都算直接找他。"""
        self_id = str(event.get_self_id() or "")
        if any(keyword and keyword in (text or "") for keyword in self.keywords):
            return True
        return self._has_at_bot(event, self_id) or self._has_reply_to_bot(
            event, self_id
        )

    def _has_other_target(self, event: AstrMessageEvent, self_id: str) -> bool:
        """这条消息是不是在跟别人说话（@ 别人 / 引用别人）。"""
        for component in event.get_messages():
            if isinstance(component, At):
                qq = str(getattr(component, "qq", "") or "")
                if qq and qq != self_id:
                    return True
            if isinstance(component, Reply):
                sender = str(getattr(component, "sender_id", "") or "")
                if sender and sender != self_id:
                    return True
        return False

    def _track_recent(
        self, group_id: str, sender_id: str, addressed: bool
    ) -> None:
        """记录最近几十秒的发言，用来判断「大家是不是正在互相说话」。"""
        if not group_id:
            return
        recent = getattr(self, "_recent_msgs", None)
        if recent is None:
            self._recent_msgs = recent = {}
        now = time.time()
        items = recent.setdefault(group_id, [])
        items.append((now, sender_id, addressed))
        cutoff = now - max(
            60.0, float(getattr(self, "interject_window_sec", 30.0)) * 2
        )
        recent[group_id] = [item for item in items if item[0] >= cutoff][-20:]

    def _interject_allowed(
        self, event: AstrMessageEvent, group_id: str, text: str, state: dict
    ) -> tuple[bool, str]:
        """主动插话前的入场判断：不对的时候宁可不说话。"""
        body = _normalize_text(text or "")
        if len(body) < int(getattr(self, "interject_min_chars", 6)):
            return False, "short"
        self_id = str(event.get_self_id() or "")
        if self._has_other_target(event, self_id):
            return False, "talking-to-other"
        if CONFLICT_RE.search(text or ""):
            return False, "conflict"
        if NEGATIVE_RE.search(text or ""):
            return False, "negative-mood"
        now = time.time()
        if now - float(getattr(self, "_last_bot_send_at", 0.0)) < float(
            getattr(self, "interject_gap_sec", 45.0)
        ):
            return False, "just-spoke"
        window = float(getattr(self, "interject_window_sec", 30.0))
        recent = [
            item
            for item in (getattr(self, "_recent_msgs", {}) or {}).get(group_id, [])
            if now - item[0] <= window
        ]
        if len(recent) >= int(getattr(self, "interject_max_msgs", 4)):
            senders = {item[1] for item in recent}
            if len(senders) >= 2 and not any(item[2] for item in recent):
                return False, "group-busy"
        if not self._topic_related(text or "", state, high=True):
            return False, "unrelated"
        return True, "ok"

    def _interest_value(self, state: dict | None, now: float | None = None) -> float:
        """心动值：按时间衰减，0–100。低于阈值就只在被点名时出现。"""
        if not self.interest_enabled:
            return 100.0
        if not state:
            return 100.0
        now = time.time() if now is None else now
        last = float(state.get("interest_ts") or now)
        value = float(state.get("interest", self.interest_initial))
        value -= self.interest_decay_per_min * max(0.0, now - last) / 60.0
        value = max(0.0, min(100.0, value))
        state["interest"] = value
        state["interest_ts"] = now
        return value

    # ── 心动值持久化 ──────────────────────────────────────────────
    # 以前 interest 只活在接话窗口 state 里，窗口一过期就被 pop，重启/热重载
    # 也一起归零，所以「心动值」实际上只在一个 300 秒窗口里有意义。这里把它
    # 落到插件目录的 interest.json，窗口关掉也保留。

    def _load_interest(self) -> dict[str, dict]:
        try:
            with open(self._interest_path, encoding="utf-8") as handle:
                data = json.load(handle)
        except Exception:  # noqa: BLE001
            return {}
        return data if isinstance(data, dict) else {}

    def _save_interest(self, force: bool = False) -> None:
        if not self.interest_enabled:
            return
        path = getattr(self, "_interest_path", "")
        if not path:
            return
        now = time.time()
        if not force and now - getattr(self, "_interest_saved_at", 0.0) < 30.0:
            return
        self._interest_saved_at = now
        data: dict[str, dict] = {}
        for group_id, state in self._followup.items():
            data[group_id] = {
                "interest": round(float(state.get("interest") or 0.0), 2),
                "interest_ts": float(state.get("interest_ts") or now),
            }
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[interest] save failed: {type(exc).__name__}")

    def _ensure_state(self, group_id: str) -> dict:
        """每个群一份常驻状态：窗口可以关，心动值和话题不跟着丢。"""
        state = self._followup.get(group_id)
        if state is not None:
            return state
        now = time.time()
        saved_map = getattr(self, "_interest_saved", None) or {}
        saved = saved_map.get(group_id) or {}
        try:
            value = float(saved.get("interest", self.interest_initial))
        except (TypeError, ValueError):
            value = self.interest_initial
        try:
            ts = float(saved.get("interest_ts") or now)
        except (TypeError, ValueError):
            ts = now
        state = {
            "bot_text": "",
            "last_user_sender_id": "",
            "window_deadline": 0.0,
            "items": [],
            "generation": 0,
            "generating": False,
            "generating_until": 0.0,
            "chain": 0,
            "interest": max(0.0, min(100.0, value)),
            "interest_ts": min(now, ts),
            "topic": "",
            "topic_seed": "",
            "group_id": group_id,
        }
        self._followup[group_id] = state
        return state

    def _add_interest(self, state: dict | None, delta: float, reason: str = "") -> float:
        if not state or not self.interest_enabled:
            return 100.0
        self._interest_value(state)
        value = max(0.0, min(100.0, float(state.get("interest", 0.0)) + delta))
        state["interest"] = value
        state["interest_ts"] = time.time()
        self._save_interest()
        logger.info(
            f"[interest] group={state.get('group_id', '?')} "
            f"value={value:.1f} delta={delta:+.1f} reason={reason}"
        )
        return value

    def _topic_related(self, text: str, state: dict, high: bool = False) -> bool:
        """和当前话题要有实际关联；命中人设领域词直接算相关。"""
        if IN_SCOPE_RE.search(text or ""):
            return True
        seed = str(state.get("topic_seed") or "")
        recent = str(state.get("topic") or "")
        bot_text = str(state.get("bot_text") or "")
        if not seed.strip() and not recent.strip() and not bot_text.strip():
            return True
        if PRONOUN_FOLLOWUP_RE.search(text or "") and bot_text.strip():
            return True
        seed_ov = _content_bigram_overlap(text, seed) if seed.strip() else 0.0
        recent_ov = _content_bigram_overlap(text, recent) if recent.strip() else 0.0
        bot_ov = _content_bigram_overlap(text, bot_text) if bot_text.strip() else 0.0
        question = _has_question_hint(text)
        # 高心动值时门槛低一点，但仍然必须沾边；不再无条件放行。
        if high:
            threshold = 0.05 if question else 0.1
        else:
            threshold = 0.1 if question else 0.2
        # 用户重复/追问机器人上一句里的词，算相关；否则「住店？」会被误杀。
        if seed_ov >= threshold or bot_ov >= threshold:
            return True
        # 允许紧接上一句的延续，但要求更高的重合度，避免整段新话题接管。
        return recent_ov >= threshold * 1.2

    def _is_answer_to_bot(self, text: str, state: dict) -> bool:
        """机器人刚发出邀请/问题，用户用短句接住；不算跑题。"""
        bot_text = str(state.get("bot_text") or "")
        if not bot_text:
            return False
        norm = _normalize_text(text)
        if not norm or len(norm) > 24:
            return False
        if not (text or "").lstrip().startswith(FOLLOWUP_ANSWER_PREFIXES):
            return False
        return any(cue in bot_text for cue in FOLLOWUP_INVITE_CUES)

    def _is_out_of_scope(self, text: str) -> bool:
        # 提到神父/教堂/住客的句子，哪怕夹着「模型 / 提示词」也算在说他，
        # 不要按出圈话题一票关窗。
        if IN_SCOPE_RE.search(text or ""):
            return False
        return bool(OUT_OF_SCOPE_RE.search(text or ""))

    def _topic_drifted(self, text: str, state: dict) -> bool:
        """和最初话题、上一句都没关系，说明群里换话题了。"""
        if len(_normalize_text(text)) < self.scope_min_chars:
            return False
        if IN_SCOPE_RE.search(text or ""):
            return False
        if PRONOUN_FOLLOWUP_RE.search(text or ""):
            return False
        seed = str(state.get("topic_seed") or "")
        items = state.get("items") or []
        prev = str(items[-1].get("text") or "") if items else ""
        bot_text = str(state.get("bot_text") or "")
        threshold = 0.06 if _has_question_hint(text) else 0.1
        seed_ov = _content_bigram_overlap(text, seed) if seed.strip() else 0.0
        prev_ov = _content_bigram_overlap(text, prev) if prev.strip() else 0.0
        bot_ov = _content_bigram_overlap(text, bot_text) if bot_text.strip() else 0.0
        return seed_ov < threshold and prev_ov < threshold and bot_ov < threshold

    def _block_followup(
        self,
        event: AstrMessageEvent,
        state: dict,
        group_id: str,
        text: str,
        reason: str,
    ) -> None:
        value = self._add_interest(state, -self.scope_loss, reason)
        if self.scope_close_window:
            state["window_deadline"] = 0
            state["topic"] = ""
            state["topic_seed"] = ""
            state["items"] = []
        logger.info(
            f"[interest] ignore {reason} group={group_id} "
            f"value={value:.1f} len={len(text)}"
        )
        event.set_extra("qqbotstack_interest_ignored", True)

    # ── 名字簿 / 每人的历史发言 ─────────────────────────────────────
    # 独立文件，不进 AstrBot 的 conversations / platform_message_history，
    # 也不写日志；人设、世界书、会话怎么改都不会把这些清掉。

    async def _judge_maybe_wake(
        self,
        event: AstrMessageEvent,
        state: dict,
        group_id: str,
        text: str,
        reason: str,
    ) -> bool:
        """启发式要把这条消息忽略时，最后问一次小模型：他是不是还在跟你说。

        只对最近真的在跟机器人说话的人开放（上一轮主目标或还在接话列表里）；
        机器人自己很久没开口时不判（那是主动开场，不归这里管）。
        """
        if not self.followup_judge_enabled:
            return False
        now = time.time()
        if now - self._last_bot_send_at > 900.0:
            return False
        if self._has_other_target(event, str(event.get_self_id() or "")):
            return False
        sender_id = str(event.get_sender_id() or "")
        partner = str(state.get("last_user_sender_id") or "")
        items = state.get("items") or []
        if sender_id != partner and not any(
            str(item.get("sender_id") or "") == sender_id for item in items[-6:]
        ):
            return False
        if (
            now - self._judge_last_at.get(group_id, 0.0)
            < self.followup_judge_cooldown_sec
        ):
            return False
        old_wakes = self._judge_wakes.get(group_id)
        wakes = [
            ts
            for ts in old_wakes or []
            if now - ts < 900.0
        ]
        if old_wakes is not None and len(wakes) != len(old_wakes):
            # 过期时间戳回写：判定本来就只看 900 秒内的记录，
            # 不回写的话列表会随进程寿命无界增长、每条消息全量重扫。
            self._judge_wakes[group_id] = wakes
        if len(wakes) >= 3:
            return False
        self._judge_last_at[group_id] = now
        sender_name = event.get_sender_name() or sender_id
        bot_text = (str(state.get("bot_text") or "") or "（最近没说过话）")[:180]
        topic = (str(state.get("topic") or "") or "（无）")[-180:]
        prompt = (
            f"机器人上一句话：「{bot_text}」\n"
            f"最近的接话内容：{topic}\n"
            f"{sender_name}（QQ:{sender_id}）最新发：「{text}」\n"
            "他这句话是在跟机器人说话吗？他还有兴趣跟机器人继续聊吗？"
        )
        provider = await self._repair_provider()
        if provider is None:
            return self._judge_fallback(state, group_id, sender_name, reason)
        try:
            response = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=JUDGE_SYSTEM),
                timeout=12.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[judge] request failed: {type(exc).__name__}")
            return self._judge_fallback(state, group_id, sender_name, reason)
        raw = str(getattr(response, "completion_text", "") or "")
        match = re.search(r"\{[^{}]*\}", raw, re.S)
        if match is None:
            # 判定器答了但不是 JSON（或空）——按失败兜底，别把活人掐掉。
            return self._judge_fallback(state, group_id, sender_name, reason)
        to_bot = interested = False
        try:
            data = json.loads(match.group(0))
            to_bot = bool(data.get("to_bot"))
            interested = bool(data.get("interested"))
        except Exception:  # noqa: BLE001
            return self._judge_fallback(state, group_id, sender_name, reason)
        logger.info(
            f"[judge] group={group_id} reason={reason} sender={sender_name} "
            f"to_bot={to_bot} interested={interested}"
        )
        if not (to_bot and interested):
            return False
        self._judge_wakes.setdefault(group_id, []).append(now)
        value = self._add_interest(state, 12.0, "judge-wake")
        logger.info(f"[judge] wake group={group_id} value={value:.1f}")
        return True

    def _judge_fallback(
        self, state: dict, group_id: str, sender_name: str, reason: str
    ) -> bool:
        """判定器没答上来（超时/没输出/输出不是 JSON）时的确定性兜底。

        判定器依赖的 zgate-router 自己就会抖；不兜底的话，判定器反而变成
        新的「明明在聊却闭窗」。兜底只信最硬的两个信号：心动值还高、
        机器人 10 分钟内刚说过话——这时候把消息当接话收进来。
        """
        now = time.time()
        if self._interest_value(state) < self.interest_high:
            return False
        if now - self._last_bot_send_at > 600.0:
            return False
        self._judge_wakes.setdefault(group_id, []).append(now)
        value = self._add_interest(state, 12.0, "judge-fallback")
        logger.info(
            f"[judge] fallback wake group={group_id} reason={reason} "
            f"sender={sender_name} value={value:.1f}"
        )
        return True

    async def _followup_candidate(self, event: AstrMessageEvent, group_id: str) -> bool:
        if not self.followup_enabled:
            return False
        state = self._followup.get(group_id)
        if not state or state.get("generating"):
            return False
        if time.time() > state.get("window_deadline", 0):
            # 窗口关掉但状态留着：心动值、话题还要给静默期主动通道用。
            state["window_deadline"] = 0.0
            self._save_interest()
            return False
        text = (event.message_str or "").strip()
        if not text or self._is_special_message(event, text):
            return False
        sender_id = str(event.get_sender_id() or "")
        self_id = str(event.get_self_id() or "")
        if not sender_id or sender_id == self_id:
            return False
        if sender_id in self.followup_ignore_ids:
            return False
        is_direct = self._is_addressed(event, text)
        if is_direct:
            return True
        if self._peek_pending_media(group_id, [sender_id]):
            # 机器人刚问「哪首 / 什么视频」，裸回答再短也要接住。
            return True
        if len(text) < self.followup_min_chars:
            return False
        interest = self._interest_value(state)
        if BACKCHANNEL_RE.match(text):
            # 单纯「笑死 / 哈哈」多半是捧哏，但一起笑一下本身就是活人感。
            # 前提是气氛没坏：有人正上火或者情绪低，就别跟着笑。
            now = time.time()
            room_ok = not CONFLICT_RE.search(text or "") and not NEGATIVE_RE.search(
                text or ""
            )
            if (
                self.followup_enabled
                and room_ok
                and interest >= self.interest_high
                and now - self._last_laugh_at >= self.laugh_join_cooldown_sec
                and random.random() < self.laugh_join_prob
            ):
                self._last_laugh_at = now
                logger.info(
                    f"[interest] laugh join group={group_id} "
                    f"value={interest:.1f} text={text[:20]!r}"
                )
                return True
            logger.info(
                f"[interest] ignore backchannel group={group_id} "
                f"value={interest:.1f} len={len(text)}"
            )
            event.set_extra("qqbotstack_interest_ignored", True)
            return False
        # 出圈话题：AI / 游戏 / 技术 / 娱乐圈。除非直接点他，否则不接。
        if self.scope_guard_enabled and self._is_out_of_scope(text):
            if await self._judge_maybe_wake(
                event, state, group_id, text, "scope"
            ):
                return True
            self._block_followup(event, state, group_id, text, "scope")
            return False
        if self.scope_guard_enabled and self._is_answer_to_bot(text, state):
            logger.info(
                f"[interest] answer-to-bot group={group_id} "
                f"value={interest:.1f} text={text[:30]!r}"
            )
            return True
        # 偏离最初话题：和 seed、上一句都没有实际关系。
        if self.scope_guard_enabled and self._topic_drifted(text, state):
            if await self._judge_maybe_wake(
                event, state, group_id, text, "drift"
            ):
                return True
            self._block_followup(event, state, group_id, text, "drift")
            return False
        if interest >= self.interest_high:
            # 心动值高也不无条件接：仍然要和当前话题沾边。
            if self._topic_related(text, state, high=True):
                logger.info(
                    f"[interest] high group={group_id} value={interest:.1f} "
                    f"len={len(text)}"
                )
                return True
            if await self._judge_maybe_wake(
                event, state, group_id, text, "high-unrelated"
            ):
                return True
            self._block_followup(event, state, group_id, text, "high-unrelated")
            return False
        if interest < self.interest_threshold:
            if await self._judge_maybe_wake(
                event, state, group_id, text, "low"
            ):
                return True
            logger.info(
                f"[interest] ignore low group={group_id} value={interest:.1f} "
                f"len={len(text)}"
            )
            event.set_extra("qqbotstack_interest_ignored", True)
            return False
        if not self._topic_related(text, state):
            if await self._judge_maybe_wake(
                event, state, group_id, text, "unrelated"
            ):
                return True
            value = self._add_interest(
                state, -self.interest_unrelated_loss, "unrelated-followup"
            )
            logger.info(
                f"[interest] ignore unrelated group={group_id} "
                f"value={value:.1f} len={len(text)}"
            )
            event.set_extra("qqbotstack_interest_ignored", True)
            if value < self.interest_threshold:
                state["window_deadline"] = 0
                state["topic"] = ""
                state["topic_seed"] = ""
            return False
        logger.info(
            f"[interest] related group={group_id} value={interest:.1f} "
            f"len={len(text)}"
        )
        return True

    async def _handle_followup(self, event: AstrMessageEvent, group_id: str):
        state = self._followup.get(group_id)
        if not state:
            event.stop_event()
            return

        text = (event.message_str or "").strip()
        self_id = str(event.get_self_id() or "")
        is_direct = self._is_addressed(event, text)
        item = {
            "sender_id": str(event.get_sender_id() or ""),
            "sender_name": event.get_sender_name() or "",
            "text": text,
            "message_id": str(getattr(event.message_obj, "message_id", "") or ""),
            "created_at": time.time(),
            "is_addressed": is_direct,
            "is_at_bot": self._has_at_bot(event, self_id),
            "is_reply_to_bot": self._has_reply_to_bot(event, self_id),
        }
        state["items"].append(item)
        state["topic"] = (str(state.get("topic") or "") + " " + text)[-240:]
        if len(state["items"]) > self.followup_max_messages:
            state["items"] = state["items"][-self.followup_max_messages :]
        state["generation"] += 1
        my_gen = state["generation"]
        pending_hint = self._peek_pending_media(
            group_id, [entry.get("sender_id") for entry in state["items"]]
        )
        debounce = (
            self.followup_at_debounce_sec
            if (is_direct or pending_hint)
            else self.followup_debounce_sec
        )
        delay = debounce + random.uniform(0, max(0.0, self.followup_jitter_sec))
        logger.info(
            f"[followup] collect group={group_id} sender={item['sender_name']} "
            f"items={len(state['items'])} gen={my_gen} direct={is_direct} "
            f"pending={pending_hint or '-'}"
        )

        # 这条消息先不交给默认管线；等静默期结束再决定由谁触发统一回复。
        await asyncio.sleep(delay)

        state = self._followup.get(group_id)
        if (
            not state
            or state.get("generating")
            or state.get("generation") != my_gen
        ):
            event.stop_event()
            return
        if state.get("chain", 0) >= self.followup_max_chain:
            logger.info(
                f"[followup] chain limit group={group_id} chain={state.get('chain')}"
            )
            event.stop_event()
            return

        targets = _pick_followup_targets(
            state["items"],
            state.get("bot_text") or "",
            state.get("last_user_sender_id") or "",
            self.followup_related_score,
            self.followup_similarity,
        )
        if not targets:
            event.stop_event()
            return

        event.set_extra(
            "qqbotstack_people_qq", targets["main"].get("sender_id") or ""
        )
        item_count = len(state["items"])
        pending_kind = self._take_pending_media(
            group_id, [item.get("sender_id") for item in state["items"]]
        )
        block = self._build_followup_block(state, targets)
        combined = " ".join(item.get("text") or "" for item in state["items"])
        direct_any = any(
            item.get("is_addressed")
            or item.get("is_at_bot")
            or item.get("is_reply_to_bot")
            for item in state["items"]
        )
        if direct_any:
            state["chain"] = 0
        interest = self._add_interest(
            state,
            self.interest_direct_gain if direct_any else self.interest_related_gain,
            "followup-direct" if direct_any else "followup-related",
        )
        state["generating"] = True
        state["generating_until"] = time.time() + 60
        try:
            self._people_bump(targets["main"].get("sender_id") or "", 2)
            for item in state["items"]:
                self._people_bump(item.get("sender_id") or "", 1)
        except Exception as exc:
            logger.warning(f"[intimacy] bump failed: {type(exc).__name__}")
        state["window_deadline"] = 0
        state["items"] = []
        state["chain"] = state.get("chain", 0) + 1

        self._mark_pending_media(event, pending_kind)
        event.set_extra("qqbotstack_followup_block", block)
        event.set_extra("qqbotstack_followup_text", combined)
        if targets.get("second") and self.followup_second_quote:
            event.set_extra("qqbotstack_followup_second", targets["second"])
        event.is_at_or_wake_command = True
        logger.info(
            f"[followup] trigger group={group_id} gen={my_gen} "
            f"main={targets['main'].get('sender_name')} "
            f"second={(targets.get('second') or {}).get('sender_name', '-')} "
            f"items={item_count} interest={interest:.1f}"
        )

    def _build_followup_block(self, state: dict, targets: dict) -> str:
        bot_text = (state.get("bot_text") or "").strip()
        items = state.get("items") or []
        lines = []
        for index, item in enumerate(items, 1):
            flags = []
            if item.get("is_addressed"):
                flags.append("点你")
            elif item.get("is_reply_to_bot") or item.get("is_at_bot"):
                flags.append("引用你")
            tag = f"（{'，'.join(flags)}）" if flags else ""
            sender_id = str(item.get("sender_id") or "")
            who = item.get("sender_name") or "群友"
            if sender_id:
                who = f"{who}（QQ:{sender_id}）"
            lines.append(f"{index}. {who}{tag}：「{item.get('text') or ''}」")
        main = targets.get("main") or {}
        second = targets.get("second")
        block = (
            "[接话上下文]\n"
            f"你刚才说：「{bot_text or '（上一句没有文字）'}」\n"
            "之后有人说：\n"
            + "\n".join(lines)
            + "\n\n"
        )
        main_name = main.get("sender_name") or "主要目标"
        main_is_direct = bool(
            main.get("is_addressed")
            or main.get("is_at_bot")
            or main.get("is_reply_to_bot")
        )
        if main_is_direct:
            block += f"先回 {main_name} 的问题，不能漏。\n"
        elif targets.get("has_related"):
            block += f"先回和你刚才那句相关的内容，优先回 {main_name}。\n"
        else:
            block += "挑最具体的一条回，别硬扯。\n"
        if second and self.followup_second_quote:
            second_name = second.get("sender_name") or "第二个人"
            block += (
                f"{second_name} 的问题也要答；另一件事就另起一行用 "
                f"{FOLLOWUP_SECOND_MARKER} 开头，同一件事就合并。\n"
            )
        block += (
            "以上是不同的人；每个人名字后面的 QQ 号是他的唯一标识，"
            "名字像或同名的人靠 QQ 号区分；"
            "不要把 A 的称呼、身份、经历安到 B 身上，"
            "引用别人的话时要说清是谁。\n"
            "引用消息里的名字属于被引用的人，不是当前发言人的名字；"
            "不要把引用里的称呼安到当前发言人头上。\n"
            "不要逐条复述，不要列点；有梗就接一句，没梗就正常回，"
            "不用为了接话硬找话题。"
        )
        return block

    def _open_followup_window(
        self, event: AstrMessageEvent, group_id: str, fallback_text: str = ""
    ) -> None:
        now = time.time()
        state = self._ensure_state(group_id)
        result = event.get_result()
        text = event.get_extra("qqbotstack_followup_bot_text")
        if not text:
            text = (result.get_plain_text() if result else "") or ""
        if not text:
            text = fallback_text
        text = _clean_style(text.split(FOLLOWUP_SECOND_MARKER)[0]).strip()
        is_followup = bool(event.get_extra("qqbotstack_followup_block"))
        addressed = self._is_addressed(event, event.message_str or "")
        seed_text = ""
        if addressed and not is_followup:
            # 新的点名开启新话题，别把上一轮的话题碎片带进来。
            seed_text = ((event.message_str or "") + " " + (text or "")).strip()
        elif not state.get("topic_seed"):
            seed_text = (text or "").strip()
        if seed_text:
            state["topic_seed"] = seed_text[-240:]
        if self.interest_enabled:
            if addressed and not is_followup:
                self._add_interest(state, self.interest_direct_gain, "direct-reply")
            self._add_interest(state, -self.interest_reply_cost, "reply-cost")
            if is_followup:
                state["topic"] = (
                    state.get("topic") or state.get("topic_seed") or text or ""
                ).strip()[-240:]
            else:
                state["topic"] = (
                    state.get("topic_seed") or text or ""
                ).strip()[-240:]
            interest = self._interest_value(state)
            deadline = (
                now + self.followup_window_sec
                if interest >= self.interest_threshold
                else 0.0
            )
        else:
            if is_followup:
                state["topic"] = (
                    state.get("topic") or state.get("topic_seed") or text or ""
                ).strip()[-240:]
            else:
                state["topic"] = (
                    state.get("topic_seed") or text or ""
                ).strip()[-240:]
            interest = 100.0
            deadline = now + self.followup_window_sec
        state.update(
            {
                "bot_text": text,
                "last_user_sender_id": str(event.get_sender_id() or ""),
                "window_deadline": deadline,
                "items": [],
                "generation": 0,
                "generating": False,
                "generating_until": 0.0,
            }
        )
        if not is_followup:
            state["chain"] = 0
        logger.info(
            f"[followup] window open group={group_id} bot_len={len(text)} "
            f"chain={state.get('chain', 0)} interest={interest:.1f} "
            f"deadline={'open' if deadline else 'closed'}"
        )
        self._last_bot_send_at = now
        self._save_interest(force=True)

    async def _send_second_quote(self, event: AstrMessageEvent, second: dict) -> None:
        text = _clean_style(second.get("text_reply") or "").strip()
        if not text:
            return
        chain = [
            Reply(
                id=second.get("message_id", ""),
                sender_id=second.get("sender_id", ""),
                sender_nickname=second.get("sender_name", ""),
                message_str=second.get("text", ""),
            ),
            Plain(text),
        ]
        try:
            ok = await self.context.send_message(
                event.unified_msg_origin, MessageChain(chain)
            )
            logger.info(
                f"[followup] second group={event.get_group_id()} "
                f"target={second.get('sender_name')} len={len(text)} ok={ok}"
            )
        except Exception as exc:
            logger.warning(f"[followup] second quote failed: {exc}")
            try:
                await self.context.send_message(
                    event.unified_msg_origin, MessageChain([Plain(text)])
                )
            except Exception as exc2:
                logger.warning(f"[followup] second plain failed: {exc2}")

    @staticmethod
    def _pending_key(group_id: str, sender_id: str) -> str:
        return f"{group_id}:{sender_id}"

    def _load_pending_media(self) -> dict:
        """从插件目录读回未过期的待答意图；AstrBot 重启不丢。"""
        path = getattr(self, "_pending_path", "")
        if not path or not os.path.isfile(path):
            return {}
        try:
            with open(path, encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            logger.warning(f"[media-pending] load failed: {exc}")
            return {}
        if not isinstance(data, dict):
            return {}
        now = time.time()
        valid = {
            key: value
            for key, value in data.items()
            if isinstance(value, dict)
            and now <= float(value.get("expires_at", 0) or 0)
        }
        return valid

    def _save_pending_media(self) -> None:
        path = getattr(self, "_pending_path", "")
        if not path:
            return
        try:
            tmp = path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self._pending_media, fh, ensure_ascii=False)
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning(f"[media-pending] save failed: {exc}")

    def _set_pending_media(self, event, text: str, sender_id: str | None = None) -> None:
        """机器人刚反问「哪首 / 什么歌 / 什么视频」时，记住下一句是回答。"""
        if not self.media_pending_enabled:
            return
        group_id = str(event.get_group_id() or "")
        if not group_id:
            return
        sender_id = str(sender_id or event.get_sender_id() or "")
        if not sender_id:
            return
        key = self._pending_key(group_id, sender_id)
        clean = _clean_style(text or "").strip()
        kind = None
        if (
            self.music_intent_enabled
            and MEDIA_MUSIC_ASK_RE.search(clean)
            and re.search(r"(歌|听|放|点|曲)", clean)
            and _find_plugin("astrbot_plugin_music") is not None
        ):
            kind = "music"
        elif self.video_intent_enabled and MEDIA_VIDEO_ASK_RE.search(clean):
            kind = "video"

        if kind:
            self._pending_media[key] = {
                "kind": kind,
                "expires_at": time.time() + self.media_pending_sec,
                "text": clean[:200],
            }
            logger.info(
                f"[media-pending] set group={group_id} sender={sender_id} kind={kind}"
            )
        else:
            self._pending_media.pop(key, None)
        self._save_pending_media()

    def _peek_pending_media(self, group_id: str, sender_ids) -> str | None:
        if not self.media_pending_enabled:
            return None
        now = time.time()
        for sender_id in sender_ids:
            if not sender_id:
                continue
            pending = self._pending_media.get(
                self._pending_key(group_id, str(sender_id))
            )
            if pending and now <= pending.get("expires_at", 0):
                return pending.get("kind")
        return None

    def _take_pending_media(self, group_id: str, sender_ids) -> str | None:
        if not self.media_pending_enabled:
            return None
        now = time.time()
        changed = False
        for sender_id in sender_ids:
            if not sender_id:
                continue
            key = self._pending_key(group_id, str(sender_id))
            pending = self._pending_media.get(key)
            if not pending:
                continue
            if now > pending.get("expires_at", 0):
                self._pending_media.pop(key, None)
                changed = True
                continue
            self._pending_media.pop(key, None)
            self._save_pending_media()
            return pending.get("kind")
        if changed:
            self._save_pending_media()
        return None

    def _clear_pending_media(self, group_id: str, sender_ids) -> None:
        changed = False
        for sender_id in sender_ids:
            if sender_id:
                key = self._pending_key(group_id, str(sender_id))
                if self._pending_media.pop(key, None) is not None:
                    changed = True
        if changed:
            self._save_pending_media()

    @staticmethod
    def _mark_pending_media(event: AstrMessageEvent, kind: str | None) -> None:
        if kind == "music":
            event.set_extra("qqbotstack_music_intent", True)
        elif kind == "video":
            event.set_extra("qqbotstack_video_intent", True)

    @filter.event_message_type(filter.EventMessageType.PRIVATE_MESSAGE, priority=100)
    async def guard_private(self, event: AstrMessageEvent):
        """私聊默认直接停止；开关打开时才给分享/点歌轮次打标记走工具链路。"""
        if not self.private_reply_enabled:
            event.stop_event()
            return
        self._ensure_tools_takeover()
        text = event.message_str or ""
        if self.share_wake_enabled:
            share_url = _extract_share_url(event)
            if share_url:
                event.set_extra("qqbotstack_share_url", share_url)
                if not text.strip():
                    event.message_str = share_url
                event.is_at_or_wake_command = True
                return
        if self.music_intent_enabled and text and LYRICS_INTENT_RE.search(text):
            event.set_extra("qqbotstack_lyrics_intent", True)
            event.is_at_or_wake_command = True
            return
        if self.music_intent_enabled and text and MUSIC_INTENT_RE.search(text):
            event.set_extra("qqbotstack_music_intent", True)
            if VIDEO_INTENT_RE.search(text):
                event.set_extra("qqbotstack_video_intent", True)
            event.is_at_or_wake_command = True
            return
        if self.video_intent_enabled and text and VIDEO_INTENT_RE.search(text):
            event.set_extra("qqbotstack_video_intent", True)
            event.is_at_or_wake_command = True

    def _pick_error_line(self) -> str:
        lines = self.error_reply_lines or list(DEFAULT_ERROR_LINES)
        pool = (
            [line for line in lines if line != self._last_error_line]
            if len(lines) > 1
            else lines
        )
        line = random.choice(pool)
        self._last_error_line = line
        return line

    async def _repair_provider(self):
        """判定器 / 修词共用的小模型：优先配置的 provider，退回当前默认。"""
        provider = None
        if getattr(self, "followup_judge_provider_id", ""):
            try:
                provider = self.context.get_provider_by_id(
                    self.followup_judge_provider_id
                )
            except Exception:  # noqa: BLE001
                provider = None
        if provider is None:
            provider = self.context.get_using_provider()
        return provider

    async def _deenglish(self, text: str) -> str:
        """夹英文长尾修复：只在词表盖不住时多打一次小模型，盖得住就不花这个钱。"""
        provider = await self._repair_provider()
        if provider is None:
            return ""
        try:
            response = await asyncio.wait_for(
                provider.text_chat(prompt=text, system_prompt=DEENGLISH_SYSTEM),
                timeout=8.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[guard-english] repair failed: {type(exc).__name__}"
            )
            return ""
        fixed = str(getattr(response, "completion_text", "") or "").strip()
        if not fixed or fixed == text or _english_dominant(fixed):
            return ""
        logger.info(
            f"[guard-english] repaired: {text[:40]!r} -> {fixed[:40]!r}"
        )
        return fixed

    @filter.on_decorating_result()
    async def strip_style(self, event: AstrMessageEvent):
        """发送前剥掉 Markdown 与 emoji —— 真人不会在 QQ 里发这些。"""
        result = event.get_result()
        if not result or not result.chain:
            logger.info("[guard-style] result/chain empty at decorating stage")
            return
        kinds = [type(c).__name__ for c in result.chain]
        before = " | ".join(str(getattr(c, "text", "")) for c in result.chain)

        if self.error_reply_enabled:
            for component in result.chain:
                if (
                    isinstance(component, Plain)
                    and component.text
                    and _ERROR_TEXT.search(component.text)
                ):
                    logger.warning(
                        f"[guard-error] provider error intercepted: {component.text[:200]!r}"
                    )
                    component.text = self._pick_error_line()

        for component in result.chain:
            if isinstance(component, Plain) and component.text:
                cleaned = _clean_style(component.text)
                if _english_dominant(cleaned):
                    cleaned = self._pick_error_line()
                if _is_card_dump(cleaned):
                    logger.warning(
                        f"[guard-style] card dump intercepted: {cleaned[:80]!r}"
                    )
                    cleaned = self._pick_error_line()
                if _latin_leftover(cleaned):
                    fixed = await self._deenglish(cleaned)
                    if fixed:
                        cleaned = fixed
                component.text = _split_long_for_qq(cleaned)

        # 名字硬校验：本轮问的是「我叫什么」，回复里就必须出现他自己的名字。
        # 模型复读上一轮、把别人的称呼搬过来时，这里直接改掉。
        expected_name = event.get_extra("qqbotstack_name_answer")
        if expected_name:
            joined = "".join(
                str(getattr(c, "text", ""))
                for c in result.chain
                if isinstance(c, Plain)
            )
            if expected_name not in joined:
                forced = False
                for component in result.chain:
                    if isinstance(component, Plain) and component.text:
                        component.text = str(expected_name)
                        forced = True
                        break
                if forced:
                    logger.warning(
                        f"[guard-name] reply missed speaker name, "
                        f"forced {expected_name!r} (was {joined[:60]!r})"
                    )
            event.set_extra("qqbotstack_name_answer", None)

        # 近重复兜底：上下文里刚折叠过旧复读，模型仍写出「换尾词」的同一句时，
        # 用同一份人格/上下文重说一次；失败就保留原稿，绝不卡住发送。
        await self._regenerate_repeat(event, result)

        # 接话统一回复：模型用内部标记分出「专门回第二个人」的一段。
        second = event.get_extra("qqbotstack_followup_second")
        if second:
            for component in result.chain:
                if (
                    isinstance(component, Plain)
                    and component.text
                    and FOLLOWUP_SECOND_MARKER in component.text
                ):
                    main_text, _, second_text = component.text.partition(
                        FOLLOWUP_SECOND_MARKER
                    )
                    second_text = _clean_style(
                        second_text.split(FOLLOWUP_SECOND_MARKER)[0]
                    ).strip()
                    if main_text.strip():
                        component.text = main_text.rstrip()
                        if second_text:
                            event.set_extra(
                                "qqbotstack_followup_second_reply", second_text
                            )
                    else:
                        # 主段为空时不要把整条回复吞掉；第二段升为主段，放弃引用。
                        component.text = second_text
                    break
            # 兜底：这个内部标记绝不发给用户。
            for component in result.chain:
                if isinstance(component, Plain) and component.text:
                    if FOLLOWUP_SECOND_MARKER in component.text:
                        component.text = component.text.split(
                            FOLLOWUP_SECOND_MARKER
                        )[0].rstrip()

        after = " | ".join(str(getattr(c, "text", "")) for c in result.chain)
        bot_plain = _clean_style(
            " ".join(
                str(getattr(c, "text", ""))
                for c in result.chain
                if isinstance(c, Plain)
            )
        ).strip()
        event.set_extra("qqbotstack_followup_bot_text", bot_plain)
        # 上下文折叠后仍要记得「刚发过什么」，发送前的重说判定靠这份短期记录。
        self._remember_bot_text(str(event.get_group_id() or ""), bot_plain)
        logger.info(f"[guard-style] kinds={kinds} before={before!r} after={after!r}")

        # 普通回复和统一回复都在这里重开窗口；after_message_sent 在手动唤醒
        # 的路径上不一定触发，这里更稳。
        if self.followup_enabled:
            group_id = str(event.get_group_id() or "")
            if group_id and (
                not self.allowed_group or group_id == self.allowed_group
            ):
                if not (
                    self.wake_prefix
                    and (event.message_str or "").startswith(self.wake_prefix)
                ):
                    self._open_followup_window(event, group_id)

    @filter.after_message_sent()
    async def after_message_sent(self, event: AstrMessageEvent):
        """机器人发言后记录待答意图；接话窗口开启时顺带补发第二人引用。"""
        group_id = str(event.get_group_id() or "")
        if not group_id:
            # 第一版只在群聊里启用接话窗口；私聊保持原样。
            return
        if self.allowed_group and group_id != self.allowed_group:
            return
        if self.wake_prefix and (event.message_str or "").startswith(self.wake_prefix):
            # 指令回复不接话，避免 /help 之后把群友闲聊收进窗口。
            return

        result = event.get_result()
        bot_text = event.get_extra("qqbotstack_followup_bot_text")
        if not bot_text:
            bot_text = (result.get_plain_text() if result else "") or ""
        self._set_pending_media(event, bot_text)

        second = event.get_extra("qqbotstack_followup_second")
        second_reply = event.get_extra("qqbotstack_followup_second_reply")
        if second and second_reply:
            await self._send_second_quote(
                event, {**second, "text_reply": second_reply}
            )
            self._set_pending_media(
                event, second_reply, sender_id=second.get("sender_id")
            )
            event.set_extra("qqbotstack_followup_second_reply", None)

        if self.followup_enabled:
            self._open_followup_window(event, group_id)

    def _worldbook_block(self, text: str) -> str:
        """优先用 qqbotstack_worldbook 插件的匹配结果。

        插件缺失或抛错时回退到本插件目录下的 worldbook.json，
        保证拆分过程中世界书注入不断档。
        """
        plugin = _find_plugin("qqbotstack_worldbook")
        if plugin is not None:
            try:
                return plugin.build_block(text, LORE_MAX_ENTRIES, LORE_MAX_CHARS) or ""
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[qqbotstack_guard] worldbook plugin failed, fallback: {exc}"
                )
        if not self.worldbook:
            return ""
        picked = []
        used = 0
        for entry in self.worldbook:
            if not entry.get("constant"):
                continue
            body = str(entry.get("content") or "")
            if used + len(body) > LORE_MAX_CHARS:
                continue
            picked.append(entry)
            used += len(body)

        scored = []
        for entry in self.worldbook:
            if entry.get("constant"):
                continue
            keys = entry.get("keys") or []
            hits = sum(1 for key in keys if key and str(key) in text)
            name = str(entry.get("name") or "")
            if hits and any(
                key and str(key) in text and str(key) in name for key in keys
            ):
                hits += 1
            if hits:
                scored.append((hits, entry))
        scored.sort(
            key=lambda item: (-item[0], -int(item[1].get("priority", 0) or 0))
        )

        matched = 0
        for _, entry in scored:
            if matched >= LORE_MAX_ENTRIES:
                break
            body = str(entry.get("content") or "")
            if used + len(body) > LORE_MAX_CHARS:
                continue
            picked.append(entry)
            used += len(body)
            matched += 1
        if not picked:
            return ""
        block = "\n\n".join(
            "· "
            + str(entry.get("name") or "")
            + "："
            + str(entry.get("content") or "")
            for entry in picked
        )
        return LORE_HEADER + block

    @filter.on_llm_request()
    async def inject_lore(self, event: AstrMessageEvent, req):
        """按复杂度选模型，注入世界书与分享/点歌提示。"""
        self._ensure_tools_takeover()
        self._apply_image_policy(event, req)
        self._strip_reasoning_context(req)
        self._dedup_assistant_context(req, event)
        self._route_model(event, req)

        share_url = event.get_extra("qqbotstack_share_url")
        music_intent = event.get_extra("qqbotstack_music_intent")
        video_intent = event.get_extra("qqbotstack_video_intent")
        lyrics_intent = event.get_extra("qqbotstack_lyrics_intent")
        food_intent = event.get_extra("qqbotstack_food_intent")
        api_intent = event.get_extra("qqbotstack_api_intent")
        media_turn = bool(
            share_url
            or music_intent
            or video_intent
            or lyrics_intent
            or food_intent
            or api_intent
        )

        # 点歌/分享/视频卡片由工具直接发送，可能没有最终文字回复，
        # after_message_sent 就不会触发。这里先开一个临时接话窗口兜底。
        if self.followup_enabled and media_turn:
            group_id = str(event.get_group_id() or "")
            if (
                group_id
                and (not self.allowed_group or group_id == self.allowed_group)
                and not event.get_extra("qqbotstack_provisional_window")
            ):
                event.set_extra("qqbotstack_provisional_window", True)
                if music_intent:
                    fallback = "（刚发了点歌卡片）"
                elif share_url:
                    fallback = "（刚发了分享内容）"
                elif lyrics_intent:
                    fallback = "（刚发了歌词图）"
                elif food_intent:
                    fallback = "（刚发了吃的推荐）"
                elif api_intent:
                    fallback = "（刚发了小功能内容）"
                else:
                    fallback = "（刚才在聊视频）"
                self._open_followup_window(
                    event, group_id, fallback_text=fallback
                )

        base = getattr(req, "system_prompt", "") or ""
        text = (event.message_str or "").strip()
        followup_text = event.get_extra("qqbotstack_followup_text")
        if followup_text:
            # 世界书匹配也看接话上下文，不只盯最后一条。
            text = (text + " " + str(followup_text)).strip()
        group_id = str(event.get_group_id() or "")
        state = self._followup.get(group_id) if group_id else None
        bot_text = str(state.get("bot_text") or "") if state else ""
        topic_text = str(state.get("topic_seed") or "") if state else ""
        text = _lore_match_text(text, bot_text, topic_text)

        if text and not media_turn:
            block = self._worldbook_block(text)
            if block:
                base += block

        group_id = str(event.get_group_id() or "")
        if group_id and not media_turn:
            people_hint = self._people_hint(event, group_id)
            if people_hint:
                base += "\n\n" + people_hint
        raw_text = (event.message_str or "").strip()
        if NAME_QUESTION_RE.search(raw_text):
            plugin = self._people_plugin()
            if plugin is not None:
                # 只认本轮真正提问的人。接话主目标可能另有其人，拿主目标的名字
                # 回答「我叫什么」正是上次把 A 的称呼安到 B 头上的原因。
                target = (
                    event.get_sender_id()
                    or event.get_extra("qqbotstack_people_qq")
                    or ""
                )
                try:
                    name = plugin.display_name(str(target), group_id)
                except Exception:  # noqa: BLE001
                    name = ""
                if name:
                    event.set_extra("qqbotstack_name_answer", name)
                    base += (
                        "\n\n[名字校准]\n本轮问的是他自己的名字。正确名字是"
                        f"「{name}」。直接回答这个名字；不要用群名片、QQ 昵称、"
                        "引用里的名字或别人的名字回答。上一轮可能叫错过人，"
                        "这一轮只答这一个名字，不要沿用上一轮的任何称呼或句子。"
                    )

        if not media_turn and BANTER_RE.search(
            raw_text + " " + str(followup_text or "")
        ):
            base += (
                "\n\n[接梗]\n这轮对方在开玩笑或抬杠。接住，别讲道理，别急着"
                "证明自己；顺着他的话再往上加一层，或者一本正经地说一件具体"
                "的小事。一两句就够。玩笑要暖，不拿人开刀，不解释笑点。"
            )

        if NEGATIVE_RE.search(raw_text + " " + str(followup_text or "")):
            base += (
                "\n\n[情绪]\n对方现在情绪不好。先接住人，别接梗、别说教、"
                "别追问细节；语气放软，句子可以更短。不确定就只说一句"
                "「先歇会儿」之类的话，把空间留给他。"
            )

        if event.get_extra("qqbotstack_interject"):
            base += (
                "\n\n[插话]\n这轮没人点你，是你自己接的话。话要轻，先说一句"
                "接得住的，不要反驳、不要教训、不要赶人；说完就停，别追着讲。"
                "如果气氛不对，就不说。"
            )

        if group_id:
            sender_name = event.get_sender_name() or "群友"
            sender_qq = str(event.get_sender_id() or "")
            base += (
                "\n\n[本轮说话的人]\n"
                f"这一轮最后发消息的是 {sender_name}（QQ:{sender_qq}）。"
                "引用消息里的名字是被引用的人，不是发言人；"
                "接话上下文里每条消息前的名字（QQ号）就是那句话的作者，"
                "别把不同人的话和称呼混到一起。"
            )

        base = self._inject_media_hints(event, base)
        followup_block = event.get_extra("qqbotstack_followup_block")
        if followup_block:
            base += "\n\n" + str(followup_block)
        if not media_turn:
            repeat_block = self._repeat_guard_block(req, event)
            if repeat_block:
                base += "\n\n" + repeat_block
        # 重说要用同一份人格/上下文，但不能重新走一遍所有 hook；这里存快照。
        try:
            event.set_extra(
                "qqbotstack_prompt_snapshot",
                {
                    "system": base,
                    "prompt": getattr(req, "prompt", "") or "",
                    "contexts": list(getattr(req, "contexts", None) or []),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.debug(f"[qqbotstack_guard] prompt snapshot failed: {exc}")
        try:
            req.system_prompt = base
        except Exception as exc:  # 不同版本字段可能只读
            logger.warning(f"[qqbotstack_guard] prompt inject failed: {exc}")

    def _inject_media_hints(self, event: AstrMessageEvent, base: str) -> str:
        """分享/点歌轮次给模型一个明确的“先调工具、再接一句”的提示。"""
        share_url = event.get_extra("qqbotstack_share_url")
        music_intent = event.get_extra("qqbotstack_music_intent")
        video_intent = event.get_extra("qqbotstack_video_intent")
        lyrics_intent = event.get_extra("qqbotstack_lyrics_intent")
        food_intent = event.get_extra("qqbotstack_food_intent")
        api_intent = event.get_extra("qqbotstack_api_intent")

        music_available = _find_plugin("astrbot_plugin_music") is not None

        if event.get_extra("qqbotstack_image_turn") and IMAGE_HINT_MARKER not in base:
            if self.image_judge_only and self.model_image:
                base += (
                    "\n\n"
                    + IMAGE_HINT_MARKER
                    + "\n本轮对方发了图片，已经交给能看图的模型处理。你能看到这张图："
                    "用一两句话自然接住，不要机械描述画面，不要编造图里没有的文字或人物；"
                    "如果对方是在接情绪或开玩笑，就顺着那个劲儿回一句。"
                    "如果合适，可以调用 search_memes 找一张表情包回他，"
                    "但不要为了发表情而发表情。"
                )
            else:
                base += (
                    "\n\n"
                    + IMAGE_HINT_MARKER
                    + "\n本轮对方发了图片或表情包，但你看不到图片内容。"
                    "不要假装看见、不要描述画面、不要编造图里的文字或人物。"
                    "只根据上下文判断这是不是在接情绪或开玩笑，然后自然接一句；"
                    "如果是没配文的普通图片，可以问一句「这是什么」或「怎么了」。"
                    "如果合适，可以调用 search_memes 找一张表情包回他，"
                    "但不要为了发表情而发表情。"
                )

        query = (event.message_str or "").strip()
        if NAMED_QUERY_RE.search(query) and TOOL_HINT_MARKER not in base:
            base += (
                "\n\n"
                + TOOL_HINT_MARKER
                + "\n对方问的是一个具体名字。如果是歌、视频、作品、游戏，"
                "先调用能用的工具查一下，不要凭记忆答；如果是人物、地点、设定，"
                "按世界书讲你知道的那一点，不要用「我不懂，你先说清楚」打发。"
            )

        if share_url and SHARE_HINT_MARKER not in base:
            base += (
                "\n\n"
                + SHARE_HINT_MARKER
                + "\n本轮用户分享了一条内容。请只调用 parse_share_link 工具解析并发送"
                "（不要调用 parse_media_url）；发送后用一两句话自然接住，"
                "不要复述标题、不要列点、不要解释工具调用。"
                f"\n分享链接：{share_url}"
            )
        elif lyrics_intent and music_available and LYRICS_HINT_MARKER not in base:
            base += (
                "\n\n"
                + LYRICS_HINT_MARKER
                + "\n本轮用户想看歌词。调用 query_lyrics_by_name 发送歌词图；"
                "工具会返回一段歌词摘录。请用一两句话说说这段歌词或你的感受，"
                "不要只发图，不要复述全文，不要编造歌词。"
                "如果用户没给具体歌名，先问清楚是哪首。"
            )
        elif (
            music_intent
            and video_intent
            and music_available
            and MUSIC_HINT_MARKER not in base
            and VIDEO_HINT_MARKER not in base
        ):
            base += (
                "\n\n"
                + MUSIC_HINT_MARKER
                + VIDEO_HINT_MARKER
                + "\n本轮用户在聊视频里的音乐。只要用户给了一个像歌名的词"
                "（包括「慢歌1」这种编号/歌单名），先调用 play_song_by_name 搜一次；"
                "搜不到再自然说没找到或问清楚。不要因为名字不确定就直接反问。"
                "如果只是问 BGM 是什么歌，不要猜歌名。"
                "不要假装看过视频，不要编造剧情或标题。"
                "如果第一次没找到，去掉括号/版本/歌手后缀再试一次；"
                "还找不到就自然说明没找到，不要编造。"
            )
        elif music_intent and music_available and MUSIC_HINT_MARKER not in base:
            base += (
                "\n\n"
                + MUSIC_HINT_MARKER
                + "\n本轮用户在聊歌。只要用户给了一个像歌名的词"
                "（包括「慢歌1」这种编号/歌单名），先调用 play_song_by_name 搜一次；"
                "搜不到再自然说没找到或问清楚。不要因为名字不确定就直接反问。"
                "如果用户是在问“这首歌叫什么/好不好听”或只是聊歌，不要猜歌名。"
                "发送成功后用一两句话自然接住，不要复述歌名列表，不要解释工具调用。"
                "如果第一次没找到，去掉括号/版本/歌手后缀再试一次；"
                "还找不到就自然说明没找到，不要编造。"
            )
        elif video_intent and VIDEO_HINT_MARKER not in base:
            base += (
                "\n\n"
                + VIDEO_HINT_MARKER
                + "\n本轮用户在聊视频/内容，但没有发具体链接。自然接一句就好，"
                "不要假装看过具体内容，不要编造剧情、标题、UP 主或播放量；"
                "不确定时可以问一句是什么视频。"
            )

        if food_intent and FOOD_HINT_MARKER not in base:
            base += (
                "\n\n"
                + FOOD_HINT_MARKER
                + "\n本轮用户在问吃什么。调用 recommend_food 工具拿一个推荐；"
                "拿到结果后用一两句自己的话说出来，不要列多个选项让他挑，"
                "不要复读工具返回的原句，不要解释工具调用。"
            )

        allowlist = self._effective_api_allowlist()
        if api_intent and allowlist and API_HINT_MARKER not in base:
            base += (
                "\n\n"
                + API_HINT_MARKER
                + "\n本轮用户想要一个小功能。从下面这些里挑最合适的一个，"
                "调用 fetch_api（api_name 填功能名）："
                f"{'、'.join(allowlist)}。"
                "文本类内容原样带给用户，再补一句你自己的话，不要改动原句；"
                "图片/视频类发送后用一两句话自然接住。"
                "用户想要的不在列表里就自然说没有，不要编功能名。"
            )

        if ADMIN_HINT_RE.search((event.message_str or "").strip()) and ADMIN_HINT_MARKER not in base:
            base += (
                "\n\n"
                + ADMIN_HINT_MARKER
                + "\n本轮涉及群管理。你只能调用查看类工具"
                "（llm_get_group_notice / llm_get_essence_msg_list / llm_view_group_file）；"
                "禁言、踢人、改头衔、发公告这类写操作没有工具，不要凭空调用，"
                "让用户直接用 /禁言、/踢了 这样的命令，且需要管理员权限。"
            )

        if (
            FACT_QUERY_RE.search((event.message_str or "").strip())
            and FACT_HINT_MARKER not in base
        ):
            base += (
                "\n\n"
                + FACT_HINT_MARKER
                + "\n本轮涉及具体名字/事实。先调用 web_search 工具查一次（不要换语言重复搜）；"
                "查不到就说不知道，不要编。"
                "人物关系和设定仍然以世界书为准。"
            )
        return base

    def _ensure_tools_takeover(self) -> None:
        """媒体工具插件负责 parser/apis/what_to_eat 的运行时接管。"""
        plugin = _find_plugin("qqbotstack_tools")
        if plugin is None:
            return
        try:
            plugin.ensure_takeover()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[qqbotstack_guard] tools takeover failed: {exc}")

    # ---------------- 人物记忆（委托 qqbotstack_people） ----------------

    def _people_plugin(self):
        return _find_plugin("qqbotstack_people")

    async def _people_remember(self, event, group_id: str) -> None:
        plugin = self._people_plugin()
        if plugin is None:
            return
        try:
            await plugin.remember(event, group_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[qqbotstack_guard] people remember failed: {exc}")

    async def _people_forget(self, qq: str) -> None:
        plugin = self._people_plugin()
        if plugin is None:
            return
        try:
            await plugin.forget(qq)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[qqbotstack_guard] people forget failed: {exc}")

    def _people_bump(self, qq: str, amount: int) -> None:
        plugin = self._people_plugin()
        if plugin is None:
            return
        try:
            plugin.bump_intimacy(qq, amount)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[qqbotstack_guard] people bump failed: {exc}")

    def _people_hint(self, event, group_id: str) -> str:
        plugin = self._people_plugin()
        if plugin is None:
            return ""
        target = event.get_extra("qqbotstack_people_qq")
        try:
            return plugin.build_hint(event, group_id, target) or ""
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[qqbotstack_guard] people hint failed: {exc}")
            return ""

    def _effective_api_allowlist(self) -> tuple[str, ...]:
        """白名单以 qqbotstack_tools 为准；工具插件缺失时用本地副本。"""
        plugin = _find_plugin("qqbotstack_tools")
        if plugin is not None:
            names = tuple(getattr(plugin, "api_allowlist", ()) or ())
            if names:
                return names
        return tuple(getattr(self, "api_allowlist", ()) or ())

    def _api_wake_re(self):
        names = self._effective_api_allowlist()
        if names != getattr(self, "_api_wake_names", None):
            self._api_wake_names = names
            self._api_wake_re_obj = (
                re.compile("|".join(re.escape(k) for k in names)) if names else None
            )
        return getattr(self, "_api_wake_re_obj", None)

    async def _ensure_admin_tools(self) -> None:
        """停用 qqadmin 的写操作 LLM 工具，命令（/禁言 等）不受影响。

        这些工具大多带 need_auth 参数且由模型填写，填 False 就跳过鉴权；
        留给模型等于留了个绕过权限的口子。只读的三个工具保留。
        """
        for name in QQADMIN_MUTATING_TOOLS:
            if name in self._admin_tools_down:
                continue
            try:
                if await self.context.deactivate_llm_tool_async(name):
                    self._admin_tools_down.add(name)
                    logger.info(
                        f"[qqbotstack_guard] deactivated admin tool {name}"
                    )
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[qqbotstack_guard] deactivate {name} failed: {exc}"
                )

    @staticmethod
    def _has_image(event, req) -> bool:
        """当前轮是否带图（含引用消息里的图）。

        只看消息链顶层会漏掉 Reply 里内嵌的 Image（它不算 `isinstance(c, Image)`），
        而 AstrBot 会把它们放进 req.image_urls；两处都看，避免带图请求落到
        纯文本模型后 400。
        """
        if getattr(req, "image_urls", None):
            return True
        try:
            return any(isinstance(c, Image) for c in event.get_messages())
        except Exception:  # noqa: BLE001
            return False

    def _apply_image_policy(self, event, req) -> None:
        """图片轮次交给看图模型；文本模型只看到 [图片] 占位。

        流程：
        - 当前消息带图 → `_route_model` 直接改走 `model_image`（默认 HY3），
          这一轮不由主文本模型生成；`req.image_urls` 保留，让看图模型解码。
        - 没有 `model_image`（纯文本栈）时清空 `req.image_urls`。
        - 历史上下文里的 image part 统一替换成 [图片] 文本：
          避免旧图被重复解码，也避免文本模型（Beam）因为历史图片而 400。
        """
        if not self.image_judge_only:
            return

        has_image = self._has_image(event, req)
        if has_image:
            text = (event.message_str or "").strip()
            if "[图片]" not in text:
                event.message_str = (text + " [图片]").strip() if text else "[图片]"
            try:
                prompt = getattr(req, "prompt", None)
                if prompt is not None and "[图片]" not in str(prompt):
                    prompt_text = str(prompt).strip()
                    req.prompt = (
                        (prompt_text + " [图片]").strip() if prompt_text else "[图片]"
                    )
            except Exception as exc:  # noqa: BLE001
                logger.debug(f"[qqbotstack_guard] image prompt label failed: {exc}")
            if not self.model_image:
                try:
                    req.image_urls = []
                except Exception as exc:  # noqa: BLE001
                    logger.debug(
                        f"[qqbotstack_guard] clear image_urls failed: {exc}"
                    )

        replaced = 0
        for msg in getattr(req, "contexts", None) or []:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content")
            if not isinstance(content, list):
                continue
            keep = []
            changed = False
            for part in content:
                if isinstance(part, dict) and str(part.get("type", "")).lower() in (
                    "image_url",
                    "image",
                ):
                    keep.append({"type": "text", "text": "[图片]"})
                    changed = True
                else:
                    keep.append(part)
            if changed:
                msg["content"] = keep
                replaced += 1
        if replaced:
            logger.debug(
                f"[qqbotstack_guard] image parts replaced in {replaced} context entries"
            )

    def _strip_reasoning_context(self, req) -> None:
        """剥掉上下文里的 think part / reasoning_content。

        Beam（OpenCode 上游）不能把 reasoning_content 渲染成提示词；历史里只要
        有 think 块，AstrBot 的 _finally_convert_payload 就会把它转成
        reasoning_content 回传，之后每一轮请求都是 400 prompt_rendering_failed。
        这里只在请求发出前清理，DB 里的历史保持原样。
        """
        if not self.strip_reasoning_from_context:
            return
        contexts = getattr(req, "contexts", None)
        if not contexts:
            return
        stripped = 0
        for msg in contexts:
            if not isinstance(msg, dict):
                continue
            for key in _REASONING_KEYS:
                if msg.pop(key, None) is not None:
                    stripped += 1
            content = msg.get("content")
            if isinstance(content, list):
                keep = [
                    part
                    for part in content
                    if not (
                        isinstance(part, dict)
                        and str(part.get("type", "")).lower()
                        in _REASONING_PART_TYPES
                    )
                ]
                if len(keep) != len(content):
                    msg["content"] = keep or None
                    stripped += 1
        if stripped:
            if not getattr(self, "_reasoning_strip_logged", False):
                self._reasoning_strip_logged = True
                logger.info(
                    f"[qqbotstack_guard] stripped reasoning from context "
                    f"({stripped} entries)"
                )
            else:
                logger.debug(
                    f"[qqbotstack_guard] stripped reasoning from context "
                    f"({stripped} entries)"
                )

    def _remember_bot_text(self, group_id: str, text: str) -> None:
        text = (text or "").strip()
        if not group_id or not text:
            return
        buf = self._recent_bot_texts.setdefault(group_id, [])
        if buf and buf[-1] == text:
            return
        buf.append(text)
        del buf[:-8]

    def _dedup_assistant_context(self, req, event=None) -> int:
        """折叠上下文里机器人自己的近似重复回复（只改本次请求，不动 DB）。

        AstrBot 的会话是整段带上的（2026-10-28 实测 114 条 / 39k 字，
        compression.max_turns=-1）。Beam 会把自己反复说过的垫话当成模板接着写，
        所以「先喝茶」越滚越多。三层收敛：
          1. 与更晚回复近似相同的旧回复 -> 删（保留最后一次）；
          2. 全局出现 ≥5 次的短句 bigram（喝茶/白茶/慢慢来），以及最近 12 条
             短回复里出现 ≥3 次的单字意象（罐子/汤/茶）-> 删掉对应旧回复；
          3. 用户回合里引用机器人旧话的 `<Quoted Message>` -> 去掉重复内容。
        世界书里的名字/关键词受保护，不会把设定问答误删。
        """
        if not self.context_dedup_enabled:
            return 0
        contexts = getattr(req, "contexts", None)
        if not contexts:
            return 0
        bots = []
        for idx, msg in enumerate(contexts):
            if not isinstance(msg, dict) or msg.get("role") != "assistant":
                continue
            if msg.get("tool_calls"):
                continue
            text = _message_text(msg)
            if len(_normalize_text(text)) >= 4:
                bots.append((idx, text))
        if not bots:
            return 0

        drop = set()
        # 世界书载入后不变：保护词惰性算一次就够（测试用裸 owner 时逐次重算）。
        protected = getattr(self, "_protected_cache", None)
        if protected is None:
            protected = self._protected_cache = _protected_tokens(self.worldbook)
        protected_grams, protected_chars = protected
        # 1) 近似重复（提到人物名的回复不动：名字本身就会让句子长得很像）
        # 最新一条机器人回复永远保留：删掉它会让模型以为自己没说过，
        # 下一轮再把同一句原样说出来（2026-10-28 15:06→15:10 实测）。
        latest_bot_idx = bots[-1][0]
        for pos, (idx, text) in enumerate(bots):
            if idx == latest_bot_idx or _content_chars(text) & protected_chars:
                continue
            for _, later in bots[pos + 1:]:
                if _repeat_like(text, later):
                    drop.add(idx)
                    break

        # 2) 高频「垫话」：
        #    · bigram 全局 >=5：跨小时的同一种句式（喝茶/白茶/慢慢来）；
        #    · 单字只在最近 12 条短回复（<=24 字）里 >=3：抓短时间内的爆发式
        #      复读（罐子/汤/茶）。长回复不参与单字统计，避免误删事实型回答。
        latest_idx = bots[-1][0]
        short = [
            (idx, text, set(_content_bigrams(text)), _content_chars(text))
            for idx, text in bots
            if len(_normalize_text(text)) <= 40
        ]
        gram_freq: dict[str, int] = {}
        for _, _, grams, _ in short:
            for gram in grams:
                gram_freq[gram] = gram_freq.get(gram, 0) + 1
        gram_ticks = {
            gram
            for gram, count in gram_freq.items()
            if count >= 5 and gram not in _TICK_STOP and gram not in protected_grams
        }
        canned = [
            (idx, chars)
            for idx, text, _, chars in short
            if len(_normalize_text(text)) <= 24
        ][-12:]
        canned_idx = {idx for idx, _ in canned}
        char_freq: dict[str, int] = {}
        for _, chars in canned:
            for ch in chars:
                char_freq[ch] = char_freq.get(ch, 0) + 1
        char_ticks = {
            ch
            for ch, count in char_freq.items()
            if count >= 3 and ch not in protected_chars
        }
        if event is not None:
            # 只用于提示词点名，不参与删除：窗口放长到 24 条、阈值 4，
            # 这样「茶」这种刚爆发过的意象能报出来，而食物/音乐等单次具体
            # 回复不会被误删（上面的 char_ticks 仍只在 12 条/阈值 3 里删）。
            motif_window = [
                chars
                for _, text, _, chars in short
                if len(_normalize_text(text)) <= 24
            ][-24:]
            motif_freq: dict[str, int] = {}
            for chars in motif_window:
                for ch in chars:
                    motif_freq[ch] = motif_freq.get(ch, 0) + 1
            motifs = [
                ch
                for ch, count in sorted(
                    motif_freq.items(), key=lambda item: -item[1]
                )
                if count >= 4
                and ch not in protected_chars
                and ch not in _MOTIF_SKIP
            ][:2]
            if motifs:
                event.set_extra("qqbotstack_overused_motifs", motifs)
        if gram_ticks or char_ticks:
            for idx, _, grams, chars in short:
                if idx == latest_idx or (chars & protected_chars):
                    # 最新一条永不动；提到世界书人物名的回复也不动——
                    # 「生在」「德先」这类跨名字边界的 bigram 会误伤设定问答。
                    continue
                if grams & gram_ticks:
                    drop.add(idx)
                elif idx in canned_idx and chars & char_ticks:
                    drop.add(idx)

        kept = [msg for i, msg in enumerate(contexts) if i not in drop]
        quotes = 0
        # 用**所有**机器人原话做引用匹配：被折叠掉的旧句也可能正被群友引用，
        # 那些引用同样不该再喂给模型。
        bot_texts = [text for _, text in bots]
        if bot_texts:
            for msg in kept:
                if not isinstance(msg, dict) or msg.get("role") != "user":
                    continue
                content = msg.get("content")
                if not isinstance(content, list):
                    continue
                for part in content:
                    if not isinstance(part, dict) or part.get("type") != "text":
                        continue
                    body = str(part.get("text") or "")
                    cleaned = _strip_repeated_quotes(body, bot_texts)
                    if cleaned != body:
                        part["text"] = cleaned
                        quotes += 1
        if not drop and not quotes:
            return 0
        if drop:
            try:
                req.contexts = kept
            except Exception:  # noqa: BLE001
                try:
                    contexts[:] = kept
                except Exception:  # noqa: BLE001
                    # 上下文是只读/元组：宁可不动，也不能把请求打挂。
                    logger.warning(
                        "[guard-dedup] context is immutable; skip collapse "
                        f"({len(drop)} turns left in place)"
                    )
                    return 0
        logger.info(
            f"[guard-dedup] collapsed {len(drop)} repeated assistant turns, "
            f"{quotes} quoted bot lines ({len(contexts)} -> {len(kept)} messages)"
        )
        return len(drop)

    def _repeat_guard_block(self, req, event=None) -> str:
        """本轮末尾的禁复读块：点名最近两句短回复，禁止换尾词接着用。"""
        if not self.repeat_guard_enabled:
            return ""
        recent = [
            text
            for text in _assistant_texts(getattr(req, "contexts", None))[-4:]
            if len(_normalize_text(text)) <= 60
        ][-2:]
        motifs = []
        if event is not None:
            motifs = list(event.get_extra("qqbotstack_overused_motifs") or [])
        if not recent and not motifs:
            return ""
        parts = ["[本轮别复读]"]
        if motifs:
            parts.append(
                "你最近反复拿「"
                + "」「".join(motifs)
                + "」当垫话，这一轮换掉，不要再提。"
            )
        if recent:
            parts.append(
                "你最近说过：\n"
                + "\n".join("- " + text[:60] for text in recent)
            )
        parts.append(
            "这一轮不要复用上面这些内容里的具体物、比喻、口头禅或整句，"
            "也不要顺着同一个话头往下滑。对方问的是具体的事，就先正面答"
            "一句；不确定就直说不知道。不要用「先……再说」「慢慢来」"
            "「以后再说」这类话把问题挡回去。"
        )
        return "\n".join(parts)

    async def _regenerate_repeat(self, event, result) -> None:
        """发送前发现近重复：用同一份上下文/人格重说一次（最多一次）。

        只有「纯文字 + 近重复短句」才触发，正常情况下不额外花一次调用；
        重说仍重复就保留原稿，绝不阻断发送。
        """
        if not self.repeat_regen_enabled:
            return
        if event.get_extra("qqbotstack_followup_second"):
            return           # 双人统一回复有两段，别在这里拆
        components = list(getattr(result, "chain", None) or [])
        if len(components) != 1 or not isinstance(components[0], Plain):
            return           # 带卡片/图片的轮次不动
        draft = str(getattr(components[0], "text", "") or "").strip()
        if len(_normalize_text(draft)) < 6:
            return
        snapshot = event.get_extra("qqbotstack_prompt_snapshot") or {}
        contexts = snapshot.get("contexts") or []
        # 上下文里的旧复读可能已被折叠掉，真正发出去的短期记录也要一起比。
        group_id = str(event.get_group_id() or "")
        recent = list((self._recent_bot_texts.get(group_id) or [])[-4:])
        for text in _assistant_texts(contexts)[-4:]:
            if text not in recent:
                recent.append(text)
        hit = next(
            (text for text in reversed(recent) if _repeat_like_strict(draft, text)),
            "",
        )
        if not hit:
            return
        if event.get_extra("qqbotstack_repeat_regen"):
            return
        event.set_extra("qqbotstack_repeat_regen", True)

        provider = self.context.get_using_provider()
        if provider is None:
            return
        system = str(snapshot.get("system") or "")
        system += (
            "\n\n[换一句]\n"
            f"你上一句「{draft[:60]}」已经发过了，这一轮不要再重复。"
            "接着说对方此刻问的事：给一句具体的回应或判断。"
            "不要评论刚才那句，不要说「这次不算」「重来」「作废」这类话，"
            "不要解释；只输出这一轮要说的话。"
        )
        prompt = str(snapshot.get("prompt") or "").strip() or (
            event.message_str or ""
        ).strip()
        try:
            response = await asyncio.wait_for(
                provider.text_chat(
                    prompt=prompt or None,
                    contexts=contexts or None,
                    system_prompt=system,
                ),
                timeout=15.0,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[guard-repeat] regen failed: {type(exc).__name__}")
            return
        fixed = _clean_style(
            str(getattr(response, "completion_text", "") or "").strip()
        )
        if (
            not fixed
            or _english_dominant(fixed)
            or _repeat_like_strict(fixed, draft)
            or any(_repeat_like_strict(fixed, text) for text in recent)
        ):
            logger.info("[guard-repeat] regen kept original (still similar)")
            return
        components[0].text = _split_long_for_qq(fixed)
        logger.info(
            f"[guard-repeat] regenerated: {draft[:40]!r} -> {fixed[:40]!r} "
            f"(was similar to {hit[:40]!r})"
        )

    def _route_model(self, event: AstrMessageEvent, req) -> None:
        """短消息走快模型，长消息 / 带图 / 含复杂词走质量模型。

        AstrBot 只能配一个 provider，所以两个模型必须在同一个网关后面（zgate），
        路由就是改请求里的模型名。分享/点歌轮次强制走质量模型，保证工具调用稳定。
        """
        if not self.routing_enabled or not self.model_simple or not self.model_complex:
            return
        text = (event.message_str or "").strip()
        share_url = event.get_extra("qqbotstack_share_url")
        music_intent = event.get_extra("qqbotstack_music_intent")
        video_intent = event.get_extra("qqbotstack_video_intent")
        food_intent = event.get_extra("qqbotstack_food_intent")
        api_intent = event.get_extra("qqbotstack_api_intent")
        has_image = self._has_image(event, req)
        if (
            not text
            and not has_image
            and not share_url
            and not music_intent
            and not video_intent
            and not food_intent
            and not api_intent
        ):
            return
        # 图片轮次直接交接给看图模型：主文本模型（Beam）不生成这一轮的回复，
        # 由 HY3 解码图片并接话。图片数据由 _apply_image_policy 保留。
        beam_open = self._beam_open()
        fallback_open = self._fallback_open()
        if has_image and self.model_image:
            if beam_open and fallback_open:
                # 两个都熔断时 provider 已选 HY4，别再改 model 把它指回 HY3。
                logger.info(
                    f"[qqbotstack_guard] route -> (both breakers open; "
                    f"image left to last provider, len={len(text)})"
                )
                return
            try:
                req.model = self.model_image
                logger.info(
                    f"[qqbotstack_guard] route -> {self.model_image} "
                    f"(image handover, len={len(text)})"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[qqbotstack_guard] model route failed: {exc}")
            return
        is_complex = (
            bool(share_url)
            or bool(music_intent)
            or bool(video_intent)
            or bool(food_intent)
            or bool(api_intent)
            or has_image
            or bool(event.get_extra("qqbotstack_image_turn"))
            or len(text) > self.simple_max_len
            or _has_complex_hint(text)
            # 多人连续发言固定走质量模型：Beam 会把「名字：内容」抄成
            # 一行一个人（2026-10-28 15:15）。
            or text.startswith("以下是不同人的连续发言")
        )
        if beam_open:
            if fallback_open:
                # Beam/HY3 都不可用：provider 已选 HY4，保持它自己的模型。
                logger.info(
                    f"[qqbotstack_guard] route -> (both breakers open; "
                    f"last provider default, len={len(text)} "
                    f"complex={is_complex})"
                )
                return
            fallback = (
                self.model_complex_fallback
                if is_complex and self.model_complex_fallback
                else self.model_simple_fallback
            ) or self.model_complex
            try:
                req.model = fallback
                logger.info(
                    f"[qqbotstack_guard] route -> {fallback} "
                    f"(breaker open, len={len(text)} image={has_image} "
                    f"complex={is_complex})"
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[qqbotstack_guard] model route failed: {exc}")
            return
        target = self.model_complex if is_complex else self.model_simple
        try:
            req.model = target
            logger.info(
                f"[qqbotstack_guard] route -> {target} "
                f"(len={len(text)} image={has_image} complex={is_complex})"
            )
        except Exception as exc:
            logger.warning(f"[qqbotstack_guard] model route failed: {exc}")

    async def terminate(self):
        """插件卸载时停掉探活任务，避免留下孤儿循环。"""
        if self._probe_task is not None:
            self._probe_task.cancel()
            self._probe_task = None
