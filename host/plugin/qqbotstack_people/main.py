"""QQBotStack people memory plugin.

Two layers:
  - raw buffer: recent messages per QQ (short, used as extraction input)
  - long-term: LLM-extracted profile + facts table (topic / summary / tags / time)

Guard calls remember() for every group message and build_hint() for injection.
Extraction runs in a background task (default every 180s, only when there are
>=4 new messages), so it never adds an LLM round-trip to a reply.

Data: plugin_data/qqbotstack_people/people/<qq>.json
WebUI page: views/people/index.html
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
import uuid
from difflib import SequenceMatcher
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star, StarTools, register

try:  # Quart is provided by the AstrBot dashboard.
    from quart import jsonify as _quart_jsonify, request as _quart_request
except Exception:  # noqa: BLE001
    _quart_jsonify = None
    _quart_request = None

PLUGIN_NAME = "qqbotstack_people"

INTIMACY_STAGES = (
    (120, "家人"),
    (80, "再近一步的人"),
    (50, "无话不谈的人"),
    (30, "好朋友"),
    (15, "朋友"),
    (5, "熟人"),
    (0, "刚认识"),
)

NAME_REPORT_RE = re.compile(
    r"(?:我(?:的名字)?叫|我的名字是|你可以叫我|叫我)"
    r"\s*([\u4e00-\u9fa5A-Za-z0-9_.·\-]{2,20})"
)
RECALL_RE = re.compile(r"记得|以前|上次|之前|我说过|我跟你说过|还记得")
_NAME_STOP = {
    "什么", "啥", "谁", "干嘛", "做什么", "干什么", "一声", "一下", "名字",
    "我", "你", "他", "她", "它", "叫", "什么吗", "什么名字", "啥名字",
    "什么什么", "怎么", "怎样",
}
_NAME_REJECT_TOKENS = ("什么", "啥", "谁", "怎么", "怎样", "吗", "呢")
_NAME_TITLE_TOKENS = (
    "陛下", "女王", "大人", "主人", "老板", "爸爸", "妈妈", "爹", "娘",
)

EXTRACT_SYSTEM = (
    "你是记忆整理器。只输出一个 JSON 对象，不要解释、不要 Markdown 代码块。"
    '格式：{"profile":"一句画像（不超过60字，没有就空字符串）",'
    '"facts":[{"topic":"2-8字话题","summary":"不超过80字","tags":["标签"]}]}'
)

DEFAULTS = {
    "people_memory_enabled": True,
    "people_address_prob": 0.25,
    "people_address_cooldown_sec": 300.0,
    "people_history_max": 80,
    "people_history_chars": 200,
    "people_history_ttl_days": 180,
    "people_history_inject": 3,
    "people_recall_max": 6,
    "intimacy_daily_cap": 20,
    "extract_enabled": True,
    "extract_interval_sec": 180.0,
    "extract_min_messages": 4,
    "extract_max_messages": 30,
    "extract_cooldown_sec": 120.0,
    "extract_provider_id": "zgate-router",
    "extract_timeout_sec": 60.0,
    "extract_max_facts_per_call": 3,
    "fact_max": 50,
    "fact_ttl_days": 180,
    "fact_inject": 5,
    "raw_keep_after_extract": 3,
}


def _intimacy_stage(points) -> str:
    try:
        value = int(points or 0)
    except (TypeError, ValueError):
        value = 0
    for threshold, name in INTIMACY_STAGES:
        if value >= threshold:
            return name
    return "刚认识"


def _intimacy_line(name: str, days: int, points: int, stage: str) -> str:
    return (
        f"[关系]\n正在和你说话的是「{name}」。你们认识 {days} 天，互动 {points} 次，"
        f"现在的关系是「{stage}」。"
        "有人问「我们是什么关系」，就按这个阶段、用你自己的话说；"
        "不要报数字，不要生硬复述这段话，也不要因为阶段低就冷淡。"
    )


def _extract_reported_name(text: str) -> str:
    match = NAME_REPORT_RE.search(text or "")
    if not match:
        return ""
    name = re.split(r"[，。！？、,.!?;；:：\s]", match.group(1), 1)[0].strip()
    name = name.strip("吧啊呀哦嘛呢哈 ")
    if not name or name in _NAME_STOP or len(name) < 2 or len(name) > 20:
        return ""
    if any(token in name for token in _NAME_REJECT_TOKENS):
        return ""
    if any(token in name for token in _NAME_TITLE_TOKENS):
        return ""
    return name
    return name


def _person_display_name(person: dict, group_id: str = "") -> str:
    preferred = str(person.get("preferred_name") or "").strip()
    if preferred:
        return preferred
    groups = person.get("groups") or {}
    info = groups.get(group_id) if isinstance(groups, dict) else None
    if isinstance(info, dict):
        card = str(info.get("card") or "").strip()
        if card:
            return card
        nickname = str(info.get("nickname") or "").strip()
        if nickname:
            return nickname
    for key in ("last_card", "last_nickname"):
        value = str(person.get(key) or "").strip()
        if value:
            return value
    aliases = person.get("aliases") or []
    return str(aliases[-1]).strip() if aliases else ""


def _parse_extraction(text: str) -> dict | None:
    """Parse the model output into {"profile": str, "facts": [...]}."""
    if not text:
        return None
    cleaned = re.sub(
        r"^```(?:json)?|```$", "", text.strip(), flags=re.MULTILINE
    ).strip()
    data = None
    try:
        data = json.loads(cleaned)
    except (ValueError, TypeError):
        data = None
    if data is None:
        candidates = []
        for open_ch, close_ch in (("[", "]"), ("{", "}")):
            start = cleaned.find(open_ch)
            end = cleaned.rfind(close_ch)
            if start != -1 and end > start:
                candidates.append((start, cleaned[start : end + 1]))
        candidates.sort(key=lambda item: item[0])
        for _, blob in candidates:
            try:
                data = json.loads(blob)
                break
            except (ValueError, TypeError):
                continue
    if data is None:
        return None
    if isinstance(data, list):
        data = {"profile": "", "facts": data}
    if not isinstance(data, dict):
        return None
    profile = str(data.get("profile") or "").strip()[:200]
    raw_facts = data.get("facts")
    if not isinstance(raw_facts, list):
        raw_facts = []
    facts = []
    for item in raw_facts[:5]:
        if not isinstance(item, dict):
            continue
        topic = str(item.get("topic") or "").strip()[:20]
        summary = str(item.get("summary") or "").strip()[:120]
        if not topic or not summary:
            continue
        tags = []
        for tag in item.get("tags") or []:
            tag = str(tag).strip()[:12]
            if tag and tag not in tags:
                tags.append(tag)
        facts.append({"topic": topic, "summary": summary, "tags": tags[:4]})
    return {"profile": profile, "facts": facts}


def _load_config(path: Path) -> dict:
    conf = dict(DEFAULTS)
    try:
        with path.open(encoding="utf-8") as fh:
            conf.update(json.load(fh))
    except FileNotFoundError:
        logger.warning(f"[{PLUGIN_NAME}] config.json not found, using defaults")
    except (OSError, ValueError) as exc:
        logger.error(f"[{PLUGIN_NAME}] failed to read config.json: {exc}")
    return conf


@register(
    PLUGIN_NAME,
    "M.Venn",
    "人物记忆：按 QQ 记称呼、历史与亲密度；后台用模型把聊天整理成要点表格",
    "1.1.1",
)
class PeoplePlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._config_path = Path(__file__).resolve().parent / "config.json"
        conf = _load_config(self._config_path)
        self.enabled = bool(conf.get("people_memory_enabled", True))
        self.address_prob = float(conf.get("people_address_prob") or 0.25)
        self.address_cooldown_sec = float(
            conf.get("people_address_cooldown_sec") or 300.0
        )
        self.history_max = int(conf.get("people_history_max") or 80)
        self.history_chars = int(conf.get("people_history_chars") or 200)
        self.history_ttl_days = int(conf.get("people_history_ttl_days") or 180)
        self.history_inject = int(conf.get("people_history_inject") or 3)
        self.recall_max = int(conf.get("people_recall_max") or 6)
        self.intimacy_daily_cap = int(conf.get("intimacy_daily_cap") or 20)
        self.extract_enabled = bool(conf.get("extract_enabled", True))
        self.extract_interval_sec = float(conf.get("extract_interval_sec") or 180.0)
        self.extract_min_messages = int(conf.get("extract_min_messages") or 4)
        self.extract_max_messages = int(conf.get("extract_max_messages") or 30)
        self.extract_cooldown_sec = float(conf.get("extract_cooldown_sec") or 120.0)
        self.extract_provider_id = str(conf.get("extract_provider_id") or "")
        self.extract_timeout_sec = float(conf.get("extract_timeout_sec") or 60.0)
        self.extract_max_facts_per_call = int(
            conf.get("extract_max_facts_per_call") or 3
        )
        self.fact_max = int(conf.get("fact_max") or 50)
        self.fact_ttl_days = int(conf.get("fact_ttl_days") or 180)
        self.fact_inject = int(conf.get("fact_inject") or 5)
        self.raw_keep_after_extract = int(conf.get("raw_keep_after_extract") or 3)
        self._dir: Path | None = None
        self._locks: dict[str, asyncio.Lock] = {}
        self._last_named: dict[tuple[str, str], float] = {}
        # 人档读缓存：qq -> ((mtime_ns, size), person dict)。
        # 只省「读盘 + 解析 + prune」，写入仍是每次落盘（写穿），
        # 崩溃一致性、外部改动（mtime 变化即失效）与原来一致。
        self._person_cache: dict[str, tuple[tuple[int, int], dict]] = {}
        self._person_cache_cap = 64
        # 整理循环用：上次「没有新消息」检查时的文件 mtime，未变化就不再读盘。
        self._extract_stat: dict[str, int] = {}
        self._extract_task: asyncio.Task | None = None
        self._register_routes()
        logger.info(
            f"[{PLUGIN_NAME}] loaded enabled={self.enabled} "
            f"extract={self.extract_enabled}/{self.extract_interval_sec:.0f}s "
            f"provider={self.extract_provider_id or 'default'}"
        )

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        if self.extract_enabled and self._extract_task is None:
            self._extract_task = asyncio.create_task(self._extract_loop())

    async def terminate(self):
        if self._extract_task is not None:
            self._extract_task.cancel()
            self._extract_task = None

    # ---------------- storage ----------------

    def _ensure_dir(self) -> Path | None:
        if not self.enabled:
            return None
        if self._dir is not None:
            return self._dir
        try:
            path = Path(StarTools.get_data_dir(PLUGIN_NAME)) / "people"
            path.mkdir(parents=True, exist_ok=True)
            self._dir = path
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] init failed: {type(exc).__name__}")
            self.enabled = False
            return None
        return self._dir

    def _person_path(self, qq: str) -> Path | None:
        if not self.enabled or not qq.isdigit():
            return None
        if not (5 <= len(qq) <= 12):
            return None
        root = self._ensure_dir()
        return (root / f"{qq}.json") if root else None

    def _person_lock(self, qq: str) -> asyncio.Lock:
        lock = self._locks.get(qq)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[qq] = lock
        return lock

    @staticmethod
    def _empty_person(qq: str) -> dict:
        now = time.time()
        return {
            "qq": qq,
            "preferred_name": "",
            "last_card": "",
            "last_nickname": "",
            "aliases": [],
            "first_seen": now,
            "last_seen": now,
            "groups": {},
            "messages": [],
            "profile": {"summary": "", "updated_ts": 0},
            "facts": [],
            "last_extract_ts": 0,
            "last_extract_at": 0,
            "count": 0,
        }

    def _cache_person(self, qq: str, stamp: tuple[int, int], person: dict) -> None:
        cache = self._person_cache
        cache[qq] = (stamp, person)
        while len(cache) > self._person_cache_cap:
            # LRU 淘汰最旧的条目。缓存条目永远与磁盘一致（写穿 + mtime 校验），
            # 淘汰只是退回「下次重新读盘」，不丢数据。
            cache.pop(next(iter(cache)))

    def _load_person(self, qq: str) -> dict:
        path = self._person_path(qq)
        if not path:
            return self._empty_person(qq)
        try:
            info = path.stat()
        except OSError:
            self._person_cache.pop(qq, None)
            return self._empty_person(qq)
        stamp = (info.st_mtime_ns, info.st_size)
        cached = self._person_cache.get(qq)
        if cached is not None and cached[0] == stamp:
            # 文件自上次读/写后没动过：直接用缓存，省一次读盘 + 解析 + prune。
            self._person_cache[qq] = self._person_cache.pop(qq)
            return cached[1]
        if not path.is_file():
            self._person_cache.pop(qq, None)
            return self._empty_person(qq)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                self._person_cache.pop(qq, None)
                return self._empty_person(qq)
            person = self._empty_person(qq)
            person.update(data)
            if not isinstance(person.get("profile"), dict):
                person["profile"] = {"summary": "", "updated_ts": 0}
            if not isinstance(person.get("facts"), list):
                person["facts"] = []
            person = self._prune_person(person)
        except (OSError, ValueError):
            self._person_cache.pop(qq, None)
            return self._empty_person(qq)
        self._cache_person(qq, stamp, person)
        return person

    def _prune_person(self, person: dict) -> dict:
        now = time.time()
        cutoff = (
            now - self.history_ttl_days * 86400 if self.history_ttl_days > 0 else 0.0
        )
        messages = []
        for item in person.get("messages") or []:
            if not isinstance(item, dict):
                continue
            ts = float(item.get("ts") or 0)
            body = str(item.get("text") or "").strip()
            if not body or (cutoff and ts < cutoff):
                continue
            messages.append(
                {
                    "ts": ts,
                    "group": str(item.get("group") or ""),
                    "text": body[: self.history_chars],
                }
            )
        person["messages"] = messages[-self.history_max :]

        aliases = []
        for alias in person.get("aliases") or []:
            alias = str(alias).strip()
            if alias and alias not in aliases:
                aliases.append(alias[:24])
        person["aliases"] = aliases[-20:]

        groups = person.get("groups") or {}
        if isinstance(groups, dict):
            recent = sorted(
                (
                    (str(key), value)
                    for key, value in groups.items()
                    if isinstance(value, dict)
                ),
                key=lambda pair: float(pair[1].get("last_seen") or 0),
                reverse=True,
            )[:20]
            person["groups"] = dict(recent)

        fact_ttl_days = int(getattr(self, "fact_ttl_days", 180) or 0)
        fact_max = int(getattr(self, "fact_max", 50) or 50)
        fact_cutoff = (
            now - fact_ttl_days * 86400 if fact_ttl_days > 0 else 0.0
        )
        facts = [
            item
            for item in person.get("facts") or []
            if isinstance(item, dict)
            and str(item.get("topic") or "").strip()
            and str(item.get("summary") or "").strip()
            and (not fact_cutoff or float(item.get("ts") or 0) >= fact_cutoff)
        ]
        facts.sort(key=lambda item: float(item.get("ts") or 0))
        person["facts"] = facts[-fact_max:]
        return person

    def _save_person(self, qq: str, person: dict) -> None:
        path = self._person_path(qq)
        if not path:
            return
        person = self._prune_person(person)
        tmp = path.with_name(path.name + ".tmp")
        try:
            tmp.write_text(
                json.dumps(person, ensure_ascii=False, indent=1), encoding="utf-8"
            )
            os.replace(tmp, path)
        except OSError as exc:
            logger.warning(f"[{PLUGIN_NAME}] save failed: {type(exc).__name__}")
            self._person_cache.pop(qq, None)
            return
        # 写穿后立刻记住新文件的 stat：下次读命中缓存；
        # 落盘失败则丢缓存，退回原来的「下次重新读盘」。
        try:
            info = path.stat()
        except OSError:
            self._person_cache.pop(qq, None)
            return
        self._cache_person(qq, (info.st_mtime_ns, info.st_size), person)

    # ---------------- public API for guard ----------------

    async def remember(self, event: AstrMessageEvent, group_id: str) -> None:
        if not self.enabled:
            return
        qq = str(event.get_sender_id() or "")
        path = self._person_path(qq)
        if not path:
            return
        text = (event.message_str or "").strip()
        sender = getattr(event.message_obj, "sender", None)
        card = str(getattr(sender, "card", "") or "").strip()
        nickname = str(getattr(sender, "nickname", "") or "").strip()
        display = str(event.get_sender_name() or "").strip()
        now = time.time()
        async with self._person_lock(qq):
            person = self._load_person(qq)
            person["last_seen"] = now
            if not person.get("first_seen"):
                person["first_seen"] = now
            if card:
                person["last_card"] = card
            if nickname:
                person["last_nickname"] = nickname
            aliases = list(person.get("aliases") or [])
            for value in (card, nickname, display):
                if value and value not in aliases:
                    aliases.append(value)
            person["aliases"] = aliases
            groups = person.get("groups") or {}
            old = groups.get(group_id) if isinstance(groups, dict) else None
            groups[group_id] = {
                "card": card or (old or {}).get("card", ""),
                "nickname": nickname or (old or {}).get("nickname", ""),
                "last_seen": now,
            }
            person["groups"] = groups
            reported = _extract_reported_name(text)
            if reported:
                person["preferred_name"] = reported
                if reported not in aliases:
                    aliases.append(reported)
                person["aliases"] = aliases
            if (
                text
                and not text.startswith("/")
                and len(text) >= 4
                and not text.startswith(("[图片]", "[表情]"))
            ):
                messages = list(person.get("messages") or [])
                messages.append(
                    {"ts": now, "group": group_id, "text": text[: self.history_chars]}
                )
                person["messages"] = messages
            person["count"] = int(person.get("count") or 0) + 1
            self._save_person(qq, person)

    async def forget(self, qq: str) -> None:
        path = self._person_path(qq)
        if path and path.is_file():
            try:
                path.unlink()
            except OSError:
                pass
        self._person_cache.pop(qq, None)
        self._extract_stat.pop(qq, None)
        for key in [key for key in self._last_named if key[1] == qq]:
            self._last_named.pop(key, None)

    def bump_intimacy(self, qq: str, amount: int) -> None:
        if not self.intimacy_daily_cap or amount <= 0:
            return
        path = self._person_path(qq)
        if not path:
            return
        person = self._load_person(qq)
        now = time.time()
        today = time.strftime("%Y-%m-%d", time.localtime(now))
        if str(person.get("intimacy_date") or "") != today:
            person["intimacy_date"] = today
            person["intimacy_today"] = 0
        done = int(person.get("intimacy_today") or 0)
        gain = min(amount, max(0, self.intimacy_daily_cap - done))
        if gain <= 0:
            return
        person["intimacy"] = int(person.get("intimacy") or 0) + gain
        person["intimacy_today"] = done + gain
        self._save_person(qq, person)

    def display_name(self, qq: str, group_id: str = "") -> str:
        if not qq:
            return ""
        return _person_display_name(self._load_person(qq), group_id)

    def build_hint(
        self, event: AstrMessageEvent, group_id: str, qq: str | None = None
    ) -> str:
        if not self.enabled:
            return ""
        qq = str(qq or event.get_sender_id() or "")
        if not self._person_path(qq):
            return ""
        person = self._load_person(qq)
        name = _person_display_name(person, group_id)
        text = (event.message_str or "").strip()
        recall = bool(RECALL_RE.search(text))
        now = time.time()
        parts = []
        parts.append(
            f"[本轮说话的人]\n本轮发言的是「{name or qq}」（QQ {qq}）。"
            "名字以这里为准；群名片、QQ 昵称、引用里的名字、别人的名字都不算他的。"
            f"如果本轮问到名字，只能回答「{name or qq}」。"
            "群里其他人说的名字、身份、经历不要安到他头上；"
            "引用别人的话时要说清是谁说的。"
        )
        points = int(person.get("intimacy") or 0)
        stage = _intimacy_stage(points)
        first_seen = float(person.get("first_seen") or now)
        days = max(1, int((now - first_seen) / 86400) + 1)
        parts.append(_intimacy_line(name or "群友", days, points, stage))
        if name:
            key = (group_id, qq)
            last_named = self._last_named.get(key, 0.0)
            if (
                random.random() < self.address_prob
                and now - last_named >= self.address_cooldown_sec
            ):
                self._last_named[key] = now
                parts.append(
                    f"[称呼]\n这一轮和你说话的人，你可以自然叫一次「{name}」。"
                    "只叫一次，不要每句都叫，也不要叫成别人。"
                )
        profile = str((person.get("profile") or {}).get("summary") or "").strip()
        if profile:
            parts.append(
                f"[关于他]\n（这是「{name or qq}」的画像）\n"
                + profile
                + "\n这只是背景，不是台词；不要拿画像里的词当自己的口头禅。"
            )
        limit = (
            int(getattr(self, "recall_max", 6))
            if recall
            else int(getattr(self, "fact_inject", 5))
        )
        facts = self._pick_facts(person, text, limit)
        if facts:
            lines = []
            for fact in facts:
                ts = float(fact.get("ts") or 0)
                when = time.strftime("%m-%d", time.localtime(ts)) if ts else ""
                lines.append(
                    f"- {when} {str(fact.get('topic') or '')}："
                    f"{str(fact.get('summary') or '')}"
                )
            parts.append(
                f"[他聊过]\n（以下是「{name or qq}」自己说过的事）\n"
                + "\n".join(lines)
                + "\n这些只是参考：用来理解他，不要逐条复述，不要主动提太私密"
                "的内容；也不要把他以前提过的偏好、口味或经历当成你每轮的"
                "比喻、道具或垫话——他提过，不代表这一轮还要再提。"
            )
        return "\n\n".join(parts)

    def _pick_facts(self, person: dict, query: str, limit: int) -> list[dict]:
        facts = [f for f in person.get("facts") or [] if isinstance(f, dict)]
        if not facts:
            return []
        now = time.time()
        chars = set(query or "")

        def score(fact: dict):
            topic = str(fact.get("topic") or "")
            summary = str(fact.get("summary") or "")
            tags = " ".join(str(t) for t in fact.get("tags") or [])
            rel = sum(
                1 for ch in chars if ch in topic or ch in summary or ch in tags
            )
            age_days = max(0.0, (now - float(fact.get("ts") or 0)) / 86400)
            return (rel, -age_days)

        facts.sort(key=score, reverse=True)
        return facts[:limit]

    # ---------------- LLM extraction ----------------

    def _extract_provider(self):
        try:
            if self.extract_provider_id:
                provider = self.context.get_provider_by_id(self.extract_provider_id)
                if provider is not None:
                    return provider
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] provider lookup failed: {exc}")
        try:
            return self.context.get_using_provider()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] default provider failed: {exc}")
            return None

    async def _call_llm(self, prompt: str) -> str:
        provider = self._extract_provider()
        if provider is None:
            return ""
        try:
            response = await asyncio.wait_for(
                provider.text_chat(prompt=prompt, system_prompt=EXTRACT_SYSTEM),
                timeout=self.extract_timeout_sec,
            )
        except asyncio.TimeoutError:
            logger.warning(f"[{PLUGIN_NAME}] extract timeout")
            return ""
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[{PLUGIN_NAME}] extract request failed: {type(exc).__name__}"
            )
            return ""
        return str(getattr(response, "completion_text", "") or "")

    def _merge_facts(
        self, person: dict, profile: str, new_facts: list[dict], now: float
    ) -> int:
        facts = [f for f in person.get("facts") or [] if isinstance(f, dict)]
        added = 0
        for cand in new_facts[: self.extract_max_facts_per_call]:
            match = None
            for item in facts:
                if str(item.get("topic") or "") != cand["topic"]:
                    continue
                ratio = SequenceMatcher(
                    None,
                    str(item.get("summary") or ""),
                    cand["summary"],
                ).ratio()
                if ratio >= 0.75:
                    match = item
                    break
            if match is not None:
                match["summary"] = cand["summary"]
                match["tags"] = cand["tags"]
                match["ts"] = now
                match["source_count"] = int(match.get("source_count") or 1) + 1
            else:
                facts.append(
                    {
                        "id": uuid.uuid4().hex[:12],
                        "ts": now,
                        "topic": cand["topic"],
                        "summary": cand["summary"],
                        "tags": cand["tags"],
                        "group": "",
                        "source_count": 1,
                    }
                )
                added += 1
        facts.sort(key=lambda item: float(item.get("ts") or 0))
        person["facts"] = facts[-self.fact_max :]
        if profile:
            person["profile"] = {"summary": profile, "updated_ts": now}
        return added

    async def _extract_person(self, qq: str, force: bool = False) -> bool:
        if not self.extract_enabled:
            return False
        path = self._person_path(qq)
        if not path or not path.is_file():
            return False
        person = self._load_person(qq)
        last_ts = float(person.get("last_extract_ts") or 0)
        messages = [
            item
            for item in person.get("messages") or []
            if isinstance(item, dict)
            and float(item.get("ts") or 0) > last_ts
            and str(item.get("text") or "").strip()
        ]
        if not messages:
            return False
        last_at = float(person.get("last_extract_at") or 0)
        if not force:
            # 第一次整理（last_ts == 0）视为历史回填，不受最少条数限制。
            if last_ts > 0 and len(messages) < self.extract_min_messages:
                return False
            if last_at > 0 and time.time() - last_at < self.extract_cooldown_sec:
                return False
        batch = messages[-self.extract_max_messages :]
        name = _person_display_name(person, "") or qq
        old_profile = str((person.get("profile") or {}).get("summary") or "").strip()
        known = [
            f"- {str(f.get('topic') or '')}：{str(f.get('summary') or '')}"
            for f in (person.get("facts") or [])[-10:]
            if isinstance(f, dict)
        ]
        lines = "\n".join(f"- {str(item.get('text') or '')[:200]}" for item in batch)
        prompt = (
            f"这个人叫「{name}」。\n"
            f"旧画像：{old_profile or '（无）'}\n"
            f"已知要点：\n" + ("\n".join(known) or "（无）") + "\n\n"
            f"以下是 TA 最近的发言（每行一条）：\n{lines}\n\n"
            f"请更新这个人的画像和要点，最多 {self.extract_max_facts_per_call} 条新要点。\n"
            "规则：\n"
            "- 在旧画像基础上更新：保留仍然有效的信息，合并新信息，去掉被新信息推翻的旧内容；"
            "画像控制在 80 字以内，没有变化就沿用旧画像；\n"
            "- 只写对话里明确出现的信息，不推测、不编造；\n"
            "- 不要把玩笑、群体梗、别人给的外号当成名字或身份；"
            "以用户明确说的「叫我X / 我叫X」为准；同一人多个称呼时保留最新的明确偏好，"
            "其他只当别名；\n"
            "- 忽略寒暄、语气词、重复内容；\n"
            "- 不记录密码、地址、身份证、银行卡等敏感信息；\n"
            "- facts 只输出新增或需要更新的条目，没有就空数组。"
        )
        text = await self._call_llm(prompt)
        parsed = _parse_extraction(text)
        if parsed is None:
            logger.warning(f"[{PLUGIN_NAME}] extract parse failed qq={qq}")
            return False
        now = time.time()
        added = self._merge_facts(person, parsed["profile"], parsed["facts"], now)
        newest = max(float(item.get("ts") or 0) for item in batch)
        person["last_extract_ts"] = newest
        person["last_extract_at"] = now
        remaining = [
            item
            for item in person.get("messages") or []
            if float(item.get("ts") or 0) > newest
        ]
        processed = [
            item
            for item in person.get("messages") or []
            if float(item.get("ts") or 0) <= newest
        ]
        person["messages"] = (
            processed[-self.raw_keep_after_extract :] + remaining
        )[-self.history_max :]
        self._save_person(qq, person)
        logger.info(
            f"[{PLUGIN_NAME}] extracted qq={qq} +{added} facts "
            f"total={len(person.get('facts') or [])}"
        )
        return True

    async def _extract_pending(self, force: bool = False) -> int:
        root = self._ensure_dir()
        if root is None:
            return 0
        done = 0
        for path in sorted(root.glob("*.json")):
            qq = path.stem
            if not qq.isdigit():
                continue
            try:
                if await self._extract_person(qq, force=force):
                    done += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[{PLUGIN_NAME}] extract qq={qq} failed: {type(exc).__name__}"
                )
        return done

    async def _extract_loop(self) -> None:
        try:
            await asyncio.sleep(15)
            while True:
                if self.extract_enabled:
                    try:
                        await self._extract_pending()
                    except Exception as exc:  # noqa: BLE001
                        logger.warning(
                            f"[{PLUGIN_NAME}] extract loop failed: "
                            f"{type(exc).__name__}"
                        )
                await asyncio.sleep(self.extract_interval_sec)
        except asyncio.CancelledError:
            pass

    # ---------------- web UI ----------------

    def _register_routes(self) -> None:
        routes = [
            ("/people", self.page_list, ["GET"], "List remembered people"),
            ("/person", self.page_person, ["GET"], "Read one person"),
            ("/forget", self.page_forget, ["POST"], "Forget one person"),
            ("/extract", self.page_extract, ["POST"], "Extract facts"),
            ("/fact/delete", self.page_delete_fact, ["POST"], "Delete one fact"),
            ("/config", self.page_config, ["GET"], "Memory settings"),
            ("/config", self.page_save_config, ["POST"], "Save memory settings"),
        ]
        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(
                    f"/{PLUGIN_NAME}{path}", handler, methods, desc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{PLUGIN_NAME}] register {path} failed: {exc}")

    def _summary(self, qq: str, person: dict) -> dict:
        return {
            "qq": qq,
            "name": _person_display_name(person),
            "aliases": list(person.get("aliases") or [])[-6:],
            "count": int(person.get("count") or 0),
            "messages": len(person.get("messages") or []),
            "facts": len(person.get("facts") or []),
            "intimacy": int(person.get("intimacy") or 0),
            "stage": _intimacy_stage(int(person.get("intimacy") or 0)),
            "profile": str((person.get("profile") or {}).get("summary") or ""),
            "last_seen": float(person.get("last_seen") or 0),
        }

    async def page_list(self):
        if _quart_jsonify is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        root = self._ensure_dir()
        people = []
        if root is not None:
            for path in root.glob("*.json"):
                qq = path.stem
                if not qq.isdigit():
                    continue
                people.append(self._summary(qq, self._load_person(qq)))
        people.sort(key=lambda item: item.get("last_seen") or 0, reverse=True)
        return _quart_jsonify(
            {"ok": True, "data": {"count": len(people), "people": people}}
        )

    async def page_person(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        qq = str(_quart_request.args.get("qq") or "").strip()
        if not qq:
            return _quart_jsonify({"ok": False, "message": "缺少 qq"}), 400
        person = self._load_person(qq)
        return _quart_jsonify({"ok": True, "data": person})

    async def page_forget(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        payload = await _quart_request.get_json(force=True, silent=True) or {}
        qq = str(payload.get("qq") or _quart_request.args.get("qq") or "").strip()
        if not qq:
            return _quart_jsonify({"ok": False, "message": "缺少 qq"}), 400
        await self.forget(qq)
        return _quart_jsonify({"ok": True, "data": {"qq": qq}})

    async def page_extract(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        payload = await _quart_request.get_json(force=True, silent=True) or {}
        qq = str(payload.get("qq") or "").strip()
        if qq:
            ok = await self._extract_person(qq, force=True)
            return _quart_jsonify({"ok": True, "data": {"qq": qq, "done": bool(ok)}})
        done = await self._extract_pending(force=True)
        return _quart_jsonify({"ok": True, "data": {"done": done}})

    async def page_delete_fact(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        payload = await _quart_request.get_json(force=True, silent=True) or {}
        qq = str(payload.get("qq") or "").strip()
        fact_id = str(payload.get("id") or "").strip()
        if not qq or not fact_id:
            return _quart_jsonify({"ok": False, "message": "缺少 qq 或 id"}), 400
        person = self._load_person(qq)
        facts = [
            item
            for item in person.get("facts") or []
            if str(item.get("id") or "") != fact_id
        ]
        if len(facts) == len(person.get("facts") or []):
            return _quart_jsonify({"ok": False, "message": "没有找到这条记忆"}), 404
        person["facts"] = facts
        self._save_person(qq, person)
        return _quart_jsonify({"ok": True, "data": person})

    def _snapshot_config(self) -> dict:
        return {
            "extract_enabled": self.extract_enabled,
            "extract_interval_sec": self.extract_interval_sec,
            "extract_min_messages": self.extract_min_messages,
            "extract_max_messages": self.extract_max_messages,
            "extract_provider_id": self.extract_provider_id,
            "extract_timeout_sec": self.extract_timeout_sec,
            "extract_max_facts_per_call": self.extract_max_facts_per_call,
            "fact_max": self.fact_max,
            "fact_ttl_days": self.fact_ttl_days,
            "fact_inject": self.fact_inject,
            "raw_keep_after_extract": self.raw_keep_after_extract,
        }

    async def page_config(self):
        if _quart_jsonify is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        return _quart_jsonify({"ok": True, "data": self._snapshot_config()})

    async def page_save_config(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        payload = await _quart_request.get_json(force=True, silent=True) or {}
        self.extract_enabled = bool(
            payload.get("extract_enabled", self.extract_enabled)
        )
        try:
            self.extract_interval_sec = max(
                30.0,
                float(
                    payload.get("extract_interval_sec", self.extract_interval_sec)
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            self.extract_min_messages = max(
                1,
                int(payload.get("extract_min_messages", self.extract_min_messages)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self.extract_max_messages = max(
                5,
                int(payload.get("extract_max_messages", self.extract_max_messages)),
            )
        except (TypeError, ValueError):
            pass
        self.extract_provider_id = str(
            payload.get("extract_provider_id", self.extract_provider_id) or ""
        ).strip()
        try:
            self.extract_timeout_sec = max(
                10.0,
                float(payload.get("extract_timeout_sec", self.extract_timeout_sec)),
            )
        except (TypeError, ValueError):
            pass
        try:
            self.extract_max_facts_per_call = max(
                1,
                int(
                    payload.get(
                        "extract_max_facts_per_call",
                        self.extract_max_facts_per_call,
                    )
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            self.fact_max = max(10, int(payload.get("fact_max", self.fact_max)))
        except (TypeError, ValueError):
            pass
        try:
            self.fact_ttl_days = max(
                0, int(payload.get("fact_ttl_days", self.fact_ttl_days))
            )
        except (TypeError, ValueError):
            pass
        try:
            self.fact_inject = max(
                1, int(payload.get("fact_inject", self.fact_inject))
            )
        except (TypeError, ValueError):
            pass
        try:
            self.raw_keep_after_extract = max(
                0,
                int(
                    payload.get(
                        "raw_keep_after_extract", self.raw_keep_after_extract
                    )
                ),
            )
        except (TypeError, ValueError):
            pass
        try:
            current = {}
            if self._config_path.is_file():
                current = json.loads(self._config_path.read_text(encoding="utf-8"))
            current.update(self._snapshot_config())
            tmp = self._config_path.with_name(self._config_path.name + ".tmp")
            tmp.write_text(
                json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(tmp, self._config_path)
        except OSError as exc:
            logger.warning(f"[{PLUGIN_NAME}] save config failed: {exc}")
        # 历史长度/TTL 等参数变了：缓存里的旧 prune 结果整体作废，
        # 下次读盘按新参数重剪。
        self._person_cache.clear()
        self._extract_stat.clear()
        if self.extract_enabled and self._extract_task is None:
            self._extract_task = asyncio.create_task(self._extract_loop())
        logger.info(f"[{PLUGIN_NAME}] config saved: {self._snapshot_config()}")
        return _quart_jsonify({"ok": True, "data": self._snapshot_config()})
