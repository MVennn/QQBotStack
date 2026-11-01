"""QQBotStack media tools plugin.

Owns the LLM tools that touch external content:
  - parse_share_link  (B站/抖音/快手/小红书 via astrbot_plugin_parser)
  - recommend_food    (via astrbot_plugin_what_to_eat)
  - fetch_api         (via astrbot_plugin_apis, allowlisted)

Also owns the runtime takeovers that stop parser / apis / what_to_eat from
answering first and swallowing the default LLM. Guard keeps the wake-up
regexes and sets event extras; this plugin only handles tools + takeover.

WebUI page: views/settings/index.html
"""

from __future__ import annotations

import asyncio
import html as _html
import json
import os
import re
import shutil
import time
import xml.etree.ElementTree as ET
from urllib.parse import quote
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import Image, Json, Plain
from astrbot.api.star import Context, Star, StarTools, register
from astrbot.core.message.message_event_result import MessageChain
from astrbot.core.star.star import star_map
from astrbot.core.star.star_handler import star_handlers_registry

try:  # Quart is provided by the AstrBot dashboard.
    from quart import jsonify as _quart_jsonify, request as _quart_request
except Exception:  # noqa: BLE001
    _quart_jsonify = None
    _quart_request = None

PLUGIN_NAME = "qqbotstack_tools"
HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "config.json"

SHARE_URL_RE = re.compile(
    r"https?://(?:[A-Za-z0-9-]+\.)*(?:"
    r"bilibili\.com|b23\.tv|bili2233\.cn|"
    r"douyin\.com|iesdouyin\.com|"
    r"kuaishou\.com|chenzhongtech\.com|"
    r"xiaohongshu\.com|xhslink\.com|xhslink\.cn"
    r")[^\s<>\"'）)】]*",
    re.IGNORECASE,
)

PARSER_TOOL_ONLY_WHITELIST = ["__qqbotstack_tool_only__"]

DEFAULT_API_ALLOWLIST = [
    "看看治愈", "讲个笑话", "来句诗", "讲讲古诗", "挑战古诗词",
    "来句情话", "毒鸡汤", "来碗鸡汤", "今日运势", "看看动漫",
    "来个头像", "电脑壁纸", "高清壁纸", "bing图",
]

DEFAULTS = {
    "api_allowlist": list(DEFAULT_API_ALLOWLIST),
    "takeover_parser": True,
    "takeover_apis": True,
    "takeover_food": True,
    "share_fallback_enabled": True,
    "share_meta_timeout": 10.0,
}


def _find_plugin_meta(name: str):
    for metadata in star_map.values():
        if metadata.name == name:
            return metadata
    return None


def _find_plugin(name: str):
    meta = _find_plugin_meta(name)
    if meta is not None and meta.star_cls is not None:
        return meta.star_cls
    return None


def _load_config() -> dict:
    conf = dict(DEFAULTS)
    try:
        with CONFIG_PATH.open(encoding="utf-8") as fh:
            conf.update(json.load(fh))
    except FileNotFoundError:
        logger.warning(f"[{PLUGIN_NAME}] config.json not found, using defaults")
    except (OSError, ValueError) as exc:
        logger.error(f"[{PLUGIN_NAME}] failed to read config.json: {exc}")
    return conf


def _save_config(conf: dict) -> None:
    payload = json.dumps(conf, ensure_ascii=False, indent=2)
    tmp = CONFIG_PATH.with_name(CONFIG_PATH.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    if CONFIG_PATH.exists():
        try:
            shutil.copy2(CONFIG_PATH, CONFIG_PATH.with_name(CONFIG_PATH.name + ".bak"))
        except OSError as exc:
            logger.warning(f"[{PLUGIN_NAME}] backup failed: {exc}")
    os.replace(tmp, CONFIG_PATH)


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
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except Exception:  # noqa: BLE001
            return _extract_url_from_text(data)
    if not isinstance(data, dict):
        return None
    meta = data.get("meta") if isinstance(data.get("meta"), dict) else {}
    priority_paths = (
        ("miniapp", "legacyUrl"), ("miniapp", "pcJumpUrl"), ("miniapp", "jumpUrl"),
        ("miniapp", "sourceUrl"), ("miniapp", "url"),
        ("detail_1", "qqdocurl"), ("detail_1", "jumpUrl"), ("detail_1", "url"),
        ("detail_1", "sourceUrl"), ("detail_1", "shareUrl"), ("detail_1", "targetUrl"),
        ("news", "jumpUrl"), ("news", "url"), ("news", "sourceUrl"), ("news", "shareUrl"),
        ("music", "musicUrl"), ("music", "jumpUrl"), ("music", "url"),
    )
    for first, second in priority_paths:
        node = meta.get(first)
        if not isinstance(node, dict):
            continue
        value = node.get(second)
        if not isinstance(value, str):
            continue
        cleaned = value.replace("\\/", "/")
        url = _extract_url_from_text(cleaned)
        if url:
            return url
    for value in _iter_strings(data):
        url = _extract_url_from_text(value.replace("\\/", "/"))
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


@register(
    PLUGIN_NAME,
    "M.Venn",
    "媒体与小功能：分享解析、吃什么、API 小工具，以及 parser/apis/what_to_eat 的运行时接管",
    "1.0.0",
)
class ToolsPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        conf = _load_config()
        self.api_allowlist = tuple(
            str(x).strip() for x in (conf.get("api_allowlist") or []) if str(x).strip()
        )
        self.takeover_parser = bool(conf.get("takeover_parser", True))
        self.takeover_apis = bool(conf.get("takeover_apis", True))
        self.takeover_food = bool(conf.get("takeover_food", True))
        self.share_fallback_enabled = bool(conf.get("share_fallback_enabled", True))
        self.share_meta_timeout = float(conf.get("share_meta_timeout") or 10)
        self._search_cache: dict[str, tuple[float, str]] = {}
        self._register_routes()
        logger.info(
            f"[{PLUGIN_NAME}] loaded allowlist={len(self.api_allowlist)} "
            f"takeover={self.takeover_parser}/{self.takeover_apis}/{self.takeover_food} "
            f"fallback={self.share_fallback_enabled}"
        )

    @filter.on_astrbot_loaded()
    async def on_astrbot_loaded(self):
        self.ensure_takeover()
        self._check_api_allowlist()

    def _check_api_allowlist(self) -> None:
        if not self.api_allowlist:
            return
        plugin = _find_plugin("astrbot_plugin_apis")
        if plugin is None:
            return
        try:
            missing = [
                name
                for name in self.api_allowlist
                if plugin.core.api_mgr.get_entry(name) is None
            ]
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] allowlist check failed: {exc}")
            return
        if missing:
            logger.warning(f"[{PLUGIN_NAME}] api_allowlist missing: {missing}")

    # ---------------- runtime takeovers ----------------

    def ensure_takeover(self) -> None:
        if self.takeover_parser:
            self._takeover_parser()
        if self.takeover_apis:
            self._disable_handlers("astrbot_plugin_apis", ("on_message",))
        if self.takeover_food:
            self._disable_handlers(
                "astrbot_plugin_what_to_eat", ("on_what_to_eat",)
            )

    def _takeover_parser(self) -> None:
        plugin = _find_plugin("astrbot_plugin_parser")
        if plugin is None:
            return
        cfg = getattr(plugin, "cfg", None)
        if cfg is None:
            return
        try:
            current = list(getattr(cfg, "whitelist", []) or [])
            if current != PARSER_TOOL_ONLY_WHITELIST:
                cfg.whitelist = list(PARSER_TOOL_ONLY_WHITELIST)
                logger.info(
                    f"[{PLUGIN_NAME}] parser auto-parse disabled; "
                    "share links go through parse_share_link"
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] parser takeover failed: {exc}")

    def _disable_handlers(
        self, plugin_name: str, handler_names: tuple[str, ...]
    ) -> None:
        meta = _find_plugin_meta(plugin_name)
        if meta is None or not meta.module_path:
            return
        try:
            for handler in star_handlers_registry.get_handlers_by_module_name(
                meta.module_path
            ):
                if handler.handler_name in handler_names and handler.enabled:
                    handler.enabled = False
                    logger.info(
                        f"[{PLUGIN_NAME}] disabled {plugin_name}."
                        f"{handler.handler_name}"
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] takeover {plugin_name} failed: {exc}")

    # ---------------- web UI ----------------

    def _register_routes(self) -> None:
        routes = [
            ("/config", self.page_config, ["GET"], "Tools settings"),
            ("/config", self.page_save_config, ["POST"], "Save tools settings"),
        ]
        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(
                    f"/{PLUGIN_NAME}{path}", handler, methods, desc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{PLUGIN_NAME}] register {path} failed: {exc}")

    def _snapshot(self) -> dict:
        return {
            "api_allowlist": list(self.api_allowlist),
            "takeover_parser": self.takeover_parser,
            "takeover_apis": self.takeover_apis,
            "takeover_food": self.takeover_food,
            "share_fallback_enabled": self.share_fallback_enabled,
            "share_meta_timeout": self.share_meta_timeout,
        }

    async def page_config(self):
        if _quart_jsonify is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        return _quart_jsonify({"ok": True, "data": self._snapshot()})

    async def page_save_config(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        payload = await _quart_request.get_json(force=True, silent=True) or {}
        merged = {**self._snapshot(), **payload}
        raw = merged.get("api_allowlist") or []
        if isinstance(raw, str):
            raw = raw.replace("，", ",").replace("、", ",").split(",")
        allowlist = []
        for item in raw if isinstance(raw, list) else []:
            name = str(item).strip()
            if name and name not in allowlist:
                allowlist.append(name)
        self.api_allowlist = tuple(allowlist)
        self.takeover_parser = bool(merged.get("takeover_parser", True))
        self.takeover_apis = bool(merged.get("takeover_apis", True))
        self.takeover_food = bool(merged.get("takeover_food", True))
        self.share_fallback_enabled = bool(
            merged.get("share_fallback_enabled", True)
        )
        try:
            self.share_meta_timeout = max(3.0, float(merged.get("share_meta_timeout", 10)))
        except (TypeError, ValueError):
            self.share_meta_timeout = 10.0
        _save_config(self._snapshot())
        self.ensure_takeover()
        logger.info(f"[{PLUGIN_NAME}] config saved: {self._snapshot()}")
        return _quart_jsonify({"ok": True, "data": self._snapshot()})

    # ---------------- LLM tools ----------------

    @filter.llm_tool(name="parse_share_link")
    async def parse_share_link(self, event: AstrMessageEvent, url: str = "") -> str:
        """解析并发送用户分享的 B站/抖音/快手/小红书 链接或 QQ 卡片。

        发送媒体或卡片后，返回作品标题、作者和简介，供你用一两句话自然接住。
        发送后不要复述标题、不要列点、不要解释工具调用。

        Args:
            url(string): 要解析的分享链接；留空时从当前消息的文本或卡片中提取
        """
        target = (url or "").strip()
        if not target:
            target = event.get_extra("qqbotstack_share_url") or _extract_share_url(event)
        if not target:
            return "没有找到可解析的分享链接"
        if not SHARE_URL_RE.search(target):
            return "这个链接不在支持范围内"

        parser_plugin = _find_plugin("astrbot_plugin_parser")
        if parser_plugin is None:
            return await self._fallback_share(event, target, "解析器插件未安装")

        self._takeover_parser()
        keyword, match = self._match_parser(parser_plugin, target)
        if match is None:
            return await self._fallback_share(event, target, "暂不支持这个链接")

        parser = getattr(parser_plugin, "parser_map", {}).get(keyword)
        if parser is None:
            return await self._fallback_share(event, target, "该平台解析器未启用")

        try:
            result = await parser.parse(keyword, match)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[{PLUGIN_NAME}] parse failed ({type(exc).__name__}): {exc}"
            )
            return await self._fallback_share(event, target, "解析失败")

        try:
            await parser_plugin.sender.send_parse_result(event, result)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                f"[{PLUGIN_NAME}] send parse result failed "
                f"({type(exc).__name__}): {exc}"
            )
            return await self._fallback_share(
                event, target, "媒体发送失败", force_send=True
            )

        return self._format_parse_result(result, target)

    @staticmethod
    def _match_parser(parser_plugin, target: str):
        patterns = getattr(parser_plugin, "key_pattern_list", []) or []
        for keyword, pattern in patterns:
            if keyword and keyword not in target:
                continue
            try:
                match = pattern.search(target)
            except Exception:  # noqa: BLE001
                continue
            if match:
                return keyword, match
        return "", None

    @staticmethod
    def _format_parse_result(result, target: str) -> str:
        platform = getattr(
            getattr(result, "platform", None), "display_name", "未知平台"
        )
        title = (getattr(result, "title", "") or "").strip()
        author_obj = getattr(result, "author", None)
        author = (getattr(author_obj, "name", "") or "").strip() if author_obj else ""
        text = (getattr(result, "text", "") or "").strip()
        link = getattr(result, "url", None) or target
        parts = [f"平台：{platform}"]
        if title:
            parts.append(f"标题：{title[:80]}")
        if author:
            parts.append(f"作者：{author[:40]}")
        if text:
            parts.append(f"简介：{text[:160]}")
        parts.append(f"链接：{link}")
        return "；".join(parts)

    async def _fallback_share(
        self, event: AstrMessageEvent, target: str, reason: str, force_send: bool = False
    ) -> str:
        if not self.share_fallback_enabled:
            return f"{reason}；链接：{target}"
        meta = None
        try:
            meta = await asyncio.wait_for(
                self._ytdlp_meta(target), timeout=self.share_meta_timeout
            )
        except Exception as exc:  # noqa: BLE001
            logger.info(
                f"[{PLUGIN_NAME}] yt-dlp fallback failed "
                f"({type(exc).__name__}): {exc}"
            )
        if not meta:
            try:
                meta = await asyncio.wait_for(
                    self._og_meta(target), timeout=self.share_meta_timeout
                )
            except Exception as exc:  # noqa: BLE001
                logger.info(
                    f"[{PLUGIN_NAME}] OG fallback failed ({type(exc).__name__}): {exc}"
                )
        if not meta:
            return f"{reason}；链接：{target}"

        if force_send or not event.get_extra("qqbotstack_share_fallback_sent"):
            chain = []
            thumbnail = meta.get("thumbnail") or ""
            if thumbnail.startswith(("http://", "https://")):
                try:
                    chain.append(Image.fromURL(thumbnail))
                except Exception:  # noqa: BLE001
                    pass
            title = (meta.get("title") or "").strip()
            author = (meta.get("author") or "").strip()
            line = " - ".join(part for part in (title, author) if part)
            chain.append(Plain(f"{line}\n{target}".strip()))
            try:
                await event.send(event.chain_result(chain))
                event.set_extra("qqbotstack_share_fallback_sent", True)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    f"[{PLUGIN_NAME}] fallback send failed "
                    f"({type(exc).__name__}): {exc}"
                )

        parts = []
        if meta.get("title"):
            parts.append(f"标题：{meta['title'][:80]}")
        if meta.get("author"):
            parts.append(f"作者：{meta['author'][:40]}")
        if meta.get("description"):
            parts.append(f"简介：{meta['description'][:160]}")
        parts.append(f"链接：{target}")
        return "；".join(parts)

    @staticmethod
    async def _ytdlp_meta(url: str) -> dict | None:
        import yt_dlp

        options = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }

        def run():
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=False)
            if not isinstance(info, dict):
                return None
            return {
                "title": info.get("title") or "",
                "author": info.get("uploader") or info.get("channel") or "",
                "description": info.get("description") or "",
                "thumbnail": info.get("thumbnail") or "",
            }

        return await asyncio.to_thread(run)

    @staticmethod
    async def _og_meta(url: str) -> dict | None:
        import aiohttp

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            )
        }
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url, headers=headers, allow_redirects=True
            ) as response:
                if response.status >= 400:
                    return None
                html = await response.text(errors="ignore")

        def find(prop: str) -> str:
            pattern = (
                r'<meta[^>]+(?:property|name)=["\']'
                + re.escape(prop)
                + r'["\'][^>]+content=["\']([^"\']*)'
            )
            match = re.search(pattern, html, re.IGNORECASE)
            if not match:
                pattern = (
                    r'<meta[^>]+content=["\']([^"\']*)["\'][^>]+'
                    r'(?:property|name)=["\']'
                    + re.escape(prop)
                    + r'["\']'
                )
                match = re.search(pattern, html, re.IGNORECASE)
            return match.group(1) if match else ""

        title = find("og:title")
        description = find("og:description")
        thumbnail = find("og:image")
        if not (title or description or thumbnail):
            return None
        return {
            "title": title,
            "author": "",
            "description": description,
            "thumbnail": thumbnail,
        }

    # ---------------- keyless web search ----------------

    NEWS_RE = re.compile(r"(新闻|最新|最近|news|recent|latest)", re.I)
    FACT_RE = re.compile(
        r"(是谁|叫什么|什么人|介绍|歌手|演员|球员|球队|公司|电影|游戏|"
        r"是什么|哪年|出生|singer|actor|actress|player|footballer|"
        r"politician|company|film|movie|game|who is|what is|biography)",
        re.I,
    )

    @staticmethod
    def _clean_html(text: str) -> str:
        text = re.sub(r"<[^>]+>", "", text or "")
        return _html.unescape(text).strip()

    @classmethod
    def _parse_bing(cls, html_text: str, limit: int) -> list[dict]:
        results = []
        blocks = re.findall(r'<li class="b_algo".*?</li>', html_text or "", re.S | re.I)
        for block in blocks:
            match = re.search(
                r'<h2[^>]*>\s*<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
                block,
                re.S | re.I,
            )
            if not match:
                continue
            url = _html.unescape(match.group(1))
            title = cls._clean_html(match.group(2))[:120]
            snippet = ""
            sm = re.search(r"<p[^>]*>(.*?)</p>", block, re.S | re.I)
            if sm:
                snippet = cls._clean_html(sm.group(1))[:240]
            if title and url.startswith("http"):
                results.append({"title": title, "url": url, "snippet": snippet})
            if len(results) >= limit:
                break
        return results

    @staticmethod
    async def _fetch_search(url: str, params: dict) -> str:
        import aiohttp

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/126.0 Safari/537.36"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
        }
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                url, params=params, headers=headers, allow_redirects=True
            ) as response:
                if response.status != 200:
                    return ""
                return await response.text(errors="ignore")

    async def _bing_search(self, query: str, limit: int) -> list[dict]:
        try:
            text = await self._fetch_search(
                "https://www.bing.com/search",
                {"q": query, "count": str(limit), "setlang": "zh-CN"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] bing search failed: {type(exc).__name__}")
            return []
        return self._parse_bing(text, limit)

    async def _google_news(self, query: str, limit: int) -> list[dict]:
        try:
            text = await self._fetch_search(
                "https://news.google.com/rss/search",
                {"q": query, "hl": "zh-CN", "gl": "CN", "ceid": "CN:zh-Hans"},
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] google news failed: {type(exc).__name__}")
            return []
        if not text:
            return []
        try:
            root = ET.fromstring(text)
        except ET.ParseError:
            return []
        results = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            pub = (item.findtext("pubDate") or "").strip()
            source = (item.findtext("source") or "").strip()
            if not title or not link:
                continue
            results.append(
                {
                    "title": title[:120],
                    "url": link,
                    "snippet": (pub + " " + source).strip()[:240],
                }
            )
            if len(results) >= limit:
                break
        return results

    async def _wikipedia(self, query: str, limit: int) -> list[dict]:
        lang = "zh" if re.search(r"[\u4e00-\u9fa5]", query) else "en"
        base = f"https://{lang}.wikipedia.org/w/api.php"
        try:
            text = await self._fetch_search(
                base,
                {
                    "action": "query",
                    "list": "search",
                    "srsearch": query,
                    "format": "json",
                    "utf8": "1",
                    "srlimit": str(limit),
                },
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] wikipedia search failed: {type(exc).__name__}")
            return []
        if not text:
            return []
        try:
            data = json.loads(text)
        except ValueError:
            return []
        titles = [
            item.get("title")
            for item in (data.get("query") or {}).get("search") or []
            if item.get("title")
        ]
        results = []
        for title in titles[:limit]:
            snippet = ""
            try:
                extract_text = await self._fetch_search(
                    base,
                    {
                        "action": "query",
                        "prop": "extracts",
                        "exintro": "1",
                        "explaintext": "1",
                        "titles": title,
                        "format": "json",
                        "utf8": "1",
                        "redirects": "1",
                    },
                )
                if extract_text:
                    pages = (json.loads(extract_text).get("query") or {}).get(
                        "pages"
                    ) or {}
                    for page in pages.values():
                        snippet = str(page.get("extract") or "").strip()
                        break
            except Exception:  # noqa: BLE001
                snippet = ""
            results.append(
                {
                    "title": str(title)[:120],
                    "url": f"https://{lang}.wikipedia.org/wiki/{quote(str(title).replace(' ', '_'))}",
                    "snippet": snippet[:300],
                }
            )
        return results

    async def _search(self, query: str, limit: int) -> list[dict]:
        if self.NEWS_RE.search(query):
            results = await self._google_news(query, limit)
            if results:
                return results
        if self.FACT_RE.search(query):
            results = await self._wikipedia(query, limit)
            if results:
                return results
        results = await self._bing_search(query, limit)
        if results:
            return results
        results = await self._wikipedia(query, limit)
        if results:
            return results
        return await self._google_news(query, limit)

    @filter.llm_tool(name="web_search")
    async def web_search(
        self, event: AstrMessageEvent, query: str, count: int = 3
    ) -> str:
        """搜索网页，返回标题、链接和摘要。用于查证具体名字、事实、作品、新闻。

        本轮只查一次，不要换语言重复搜索；角色扮演设定以世界书为准。
        查到结果后用一两句话自然接住，不要逐条复述，不要贴一串链接。

        Args:
            query(string): 搜索关键词
            count(number): 返回条数，1-5，默认 3
        """
        query = (query or "").strip()
        if not query:
            return "缺少搜索关键词"
        previous = event.get_extra("qqbotstack_web_search_query")
        if previous:
            return (
                f"本轮已经查过「{previous}」了；直接用之前的结果回答，"
                "不要重复搜索。"
            )
        event.set_extra("qqbotstack_web_search_query", query)
        cached = self._search_cache.get(query)
        now = time.time()
        if cached and now - cached[0] < 600:
            return cached[1]
        try:
            limit = max(1, min(5, int(count or 3)))
        except (TypeError, ValueError):
            limit = 3
        results = await self._search(query, limit)
        if not results:
            return "没有搜到结果；直接说不知道，不要编。"
        lines = []
        for index, item in enumerate(results, 1):
            lines.append(
                f"{index}. {item['title']}\n   {item['url']}\n   {item['snippet']}"
            )
        formatted = (
            "搜索结果：\n"
            + "\n".join(lines)
            + "\n\n用一两句话自然接住；不要逐条复述，不要贴链接列表。"
        )
        self._search_cache[query] = (now, formatted)
        if len(self._search_cache) > 100:
            oldest = sorted(self._search_cache.items(), key=lambda kv: kv[1][0])[:20]
            for key, _ in oldest:
                self._search_cache.pop(key, None)
        return formatted

    @filter.llm_tool(name="recommend_food")
    async def recommend_food(self, event: AstrMessageEvent) -> str:
        """推荐今天吃什么。随机选一个食物，有配图就发出来，并把食物名返回给你。

        拿到结果后用一两句自己的话说出这个推荐，不要复读工具返回的原句，
        不要列多个选项让他挑，不要解释工具调用。
        """
        plugin = _find_plugin("astrbot_plugin_what_to_eat")
        if plugin is None:
            return "推荐插件未加载，只能凭空说了"
        try:
            food = plugin.food_manager.get_random_food()
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] food pick failed: {exc}")
            return "这会儿没想出来，让用户自己定"
        if not food:
            return "没想出来吃什么，让用户自己定"
        chain = []
        try:
            image_path = plugin.image_manager.get_random_image(food)
            if image_path:
                chain.append(Image.fromFileSystem(str(image_path)))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] food image failed: {exc}")
        if chain:
            try:
                await event.send(MessageChain(chain))
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{PLUGIN_NAME}] food image send failed: {exc}")
                return f"推荐：{food}（配图发送失败）"
        return f"已推荐{food}。用一两句自己的话把这个推荐说出来。"

    @filter.llm_tool(name="fetch_api")
    async def fetch_api(
        self, event: AstrMessageEvent, api_name: str, extra: str = ""
    ) -> str:
        """调用一个小功能接口（笑话、诗句、壁纸、运势等）。

        文本类结果会直接返回给你，由你原样带给用户再补一句自己的话；
        图片/视频/音频类结果会直接发送到群里。只能使用本轮提示列出的白名单功能名。

        Args:
            api_name(string): 功能名，必须来自本轮提示列出的白名单
            extra(string): 可选的补充参数，多个用空格分隔（如生成二维码的文字）
        """
        name = (api_name or "").strip()
        if name not in self.api_allowlist:
            return "这个功能不在可用列表里；只能用提示里列出的名字"
        plugin = _find_plugin("astrbot_plugin_apis")
        if plugin is None:
            return "API 插件未加载"
        try:
            entry = plugin.core.api_mgr.get_entry(name)
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] fetch_api lookup failed: {exc}")
            return "这个功能暂时没取到内容"
        if entry is None:
            return "没找到这个功能"
        try:
            entry.updated_params = await plugin._build_params(
                event, entry, [a for a in (extra or "").split() if a]
            )
            data = await plugin.core.data_service.fetch(
                entry, use_local=bool(getattr(plugin.cfg, "use_local", True))
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] fetch_api {name} failed: {exc}")
            return "这个功能暂时没取到内容"
        if data is None:
            return "这个功能暂时没取到内容"

        save_data = bool(getattr(plugin.cfg, "save_data", True))
        if data.data_type.is_text:
            text = (data.final_text or "").strip()
            if not save_data:
                data.unlink()
            if not text:
                return "这个功能暂时没取到内容"
            return (
                f"「{name}」的内容：{text[:400]}\n"
                "把上面的内容原样发给用户，再补一句你自己的话；"
                "不要改动原句，不要解释工具调用。"
            )

        try:
            comp = await plugin.data_to_comp(data)
            await event.send(MessageChain([comp]))
        except Exception as exc:  # noqa: BLE001
            logger.warning(f"[{PLUGIN_NAME}] fetch_api send {name} failed: {exc}")
            if not save_data:
                data.unlink()
            return "内容拿到了，但发送失败"
        if not save_data:
            data.unlink()
        return f"已发送「{name}」的{data.data_type}内容，用一两句话自然接住。"
