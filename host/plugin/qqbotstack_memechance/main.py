"""Sticker marker reminder and leak sanitizer for QQBotStack.

meme_manager injects the sticker menu early in the system prompt, but the
guard appends worldbook and follow-up text after it, so the model tends to
ignore the menu. This plugin appends a short reminder at the very end and
strips leaked XML tags from outgoing text.

The optional random picker is disabled by default; the model chooses the
sticker name itself.
"""

import json
import os
import random
import re
import shutil
import time
from pathlib import Path

from astrbot.api import logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.star import Context, Star
from astrbot.core.message.components import Image, Plain
from astrbot.core.message.message_event_result import MessageChain

try:  # Quart is provided by the AstrBot dashboard.
    from quart import jsonify as _quart_jsonify, request as _quart_request
except Exception:  # noqa: BLE001
    _quart_jsonify = None
    _quart_request = None

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
REMINDER_MARK = "<!-- memechance_reminder -->"
LEAK_TAG = re.compile(r"</?[A-Za-z_][\w:.-]*(?:\s[^<>]*)?/?>")

DEFAULTS = {
    "enabled": False,
    "pack_id": "qq-fav-001",
    "probability": 0.2,
    "cooldown_sec": 60,
    "marker_reminder_enabled": True,
    "leak_sanitize_enabled": True,
    "context_keep": -1,
    "fallback_names": [],
}


def _load_config(path: Path) -> dict:
    conf = dict(DEFAULTS)
    try:
        with path.open(encoding="utf-8") as fh:
            conf.update(json.load(fh))
    except FileNotFoundError:
        logger.warning(f"[memechance] config.json not found at {path}")
    except (OSError, ValueError) as exc:
        logger.error(f"[memechance] failed to read config.json: {exc}")
    return conf


def _clamp_float(value, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(number, low), high)


class MemeChance(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        here = Path(__file__).resolve().parent
        conf = _load_config(here / "config.json")
        self.enabled = bool(conf.get("enabled", False))
        self.pack_id = str(conf.get("pack_id") or "qq-fav-001")
        self.probability = _clamp_float(conf.get("probability", 0.2), 0.2, 0.0, 1.0)
        self.cooldown = _clamp_float(conf.get("cooldown_sec", 60), 60.0, 0.0, 86400.0)
        self.marker_reminder_enabled = bool(
            conf.get("marker_reminder_enabled", True)
        )
        self.leak_sanitize_enabled = bool(conf.get("leak_sanitize_enabled", True))
        self.fallback_names = {
            str(name).strip()
            for name in (conf.get("fallback_names") or [])
            if str(name).strip()
        }
        try:
            self.context_keep = int(conf.get("context_keep", -1))
        except (TypeError, ValueError):
            self.context_keep = -1
        self.pack_dir = here.parent.parent / "plugin_data" / "meme_manager" / "packs" / self.pack_id
        self.memes_dir = self.pack_dir / "memes"
        self.files = self._scan()
        self.marker_menu = self._load_marker_menu()
        self.last_at = 0.0
        self.last_file = ""
        self._here = here
        self._register_routes()
        logger.info(
            f"[memechance] enabled={self.enabled} pack={self.pack_id} "
            f"p={self.probability} cooldown={self.cooldown}s files={len(self.files)} "
            f"reminder={self.marker_reminder_enabled} names={bool(self.marker_menu)} "
            f"fallback={len(self.fallback_names)}"
        )

    def _scan(self) -> list[str]:
        if not self.memes_dir.is_dir():
            logger.warning(f"[memechance] pack dir not found: {self.memes_dir}")
            return []
        return sorted(
            str(path)
            for path in self.memes_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in IMAGE_EXTS
        )

    def _load_marker_menu(self) -> str:
        path = self.pack_dir / "memes_data.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"[memechance] cannot read {path}: {exc}")
            return ""
        names = [str(name) for name in data if str(name).strip()]
        return "、".join(names)

    def _pick(self) -> str:
        pool = self.files
        if self.fallback_names:
            narrowed = [
                path
                for path in pool
                if Path(path).parent.name in self.fallback_names
            ]
            if narrowed:
                pool = narrowed
        if len(pool) > 1 and self.last_file:
            pool = [path for path in pool if path != self.last_file]
        path = random.choice(pool)
        self.last_file = path
        return path

    # ---------------- web UI ----------------

    def _register_routes(self) -> None:
        routes = [
            ("/config", self.page_config, ["GET"], "Meme settings"),
            ("/config", self.page_save_config, ["POST"], "Save meme settings"),
        ]
        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(
                    f"/qqbotstack_memechance{path}", handler, methods, desc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[memechance] register {path} failed: {exc}")

    def _snapshot_config(self) -> dict:
        return {
            "enabled": self.enabled,
            "pack_id": self.pack_id,
            "probability": self.probability,
            "cooldown_sec": self.cooldown,
            "marker_reminder_enabled": self.marker_reminder_enabled,
            "leak_sanitize_enabled": self.leak_sanitize_enabled,
            "context_keep": self.context_keep,
            "fallback_names": sorted(self.fallback_names),
            "pack": {
                "dir": str(self.pack_dir),
                "files": len(self.files),
                "menu_count": len([n for n in self.marker_menu.split("、") if n]),
            },
        }

    def _apply_config(self, conf: dict) -> None:
        self.enabled = bool(conf.get("enabled", False))
        pack_id = str(conf.get("pack_id") or "").strip()
        if pack_id and pack_id != self.pack_id:
            self.pack_id = pack_id
            self.pack_dir = (
                self._here.parent.parent
                / "plugin_data"
                / "meme_manager"
                / "packs"
                / self.pack_id
            )
            self.memes_dir = self.pack_dir / "memes"
            self.files = self._scan()
            self.marker_menu = self._load_marker_menu()
        self.probability = _clamp_float(conf.get("probability", 0.2), 0.2, 0.0, 1.0)
        self.cooldown = _clamp_float(conf.get("cooldown_sec", 60), 60.0, 0.0, 86400.0)
        self.marker_reminder_enabled = bool(conf.get("marker_reminder_enabled", True))
        self.leak_sanitize_enabled = bool(conf.get("leak_sanitize_enabled", True))
        try:
            self.context_keep = int(conf.get("context_keep", -1))
        except (TypeError, ValueError):
            self.context_keep = -1
        self.fallback_names = {
            str(name).strip()
            for name in (conf.get("fallback_names") or [])
            if str(name).strip()
        }

    async def page_config(self):
        if _quart_jsonify is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        return _quart_jsonify({"ok": True, "data": self._snapshot_config()})

    async def page_save_config(self):
        if _quart_jsonify is None or _quart_request is None:
            return {"ok": False, "message": "web framework unavailable"}, 500
        payload = await _quart_request.get_json(force=True, silent=True) or {}
        merged = {**self._snapshot_config(), **payload}
        self._apply_config(merged)
        conf = self._snapshot_config()
        conf.pop("pack", None)
        try:
            path = self._here / "config.json"
            tmp = path.with_name(path.name + ".tmp")
            tmp.write_text(
                json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            if path.exists():
                shutil.copy2(path, path.with_name(path.name + ".bak"))
            os.replace(tmp, path)
        except Exception as exc:  # noqa: BLE001
            logger.error(f"[memechance] save config failed: {exc}")
            return _quart_jsonify({"ok": False, "message": str(exc)}), 500
        logger.info(f"[memechance] config saved: {conf}")
        return _quart_jsonify({"ok": True, "data": self._snapshot_config()})

    @filter.on_llm_request(priority=-100)
    async def append_marker_reminder(self, event: AstrMessageEvent, req):
        if not self.marker_reminder_enabled or not self.marker_menu:
            return
        base = getattr(req, "system_prompt", "") or ""
        if REMINDER_MARK in base:
            return
        reminder = f"""


{REMINDER_MARK}
[表情标记]
配图不是每轮都要，日常约四轮一次，不要连续两轮；对方发图、情绪明显或用得上时才配。
最后单独一行写 &&名字&&，只能从下面选一个：
{self.marker_menu}
没有合适的图就不写，不要为了配图硬选。"""
        try:
            req.system_prompt = base + reminder
            logger.info(f"[memechance] reminder appended, sp_len={len(req.system_prompt)}")
        except Exception as exc:
            logger.warning(f"[memechance] reminder append failed: {exc}")
        contexts = getattr(req, "contexts", None)
        if self.context_keep >= 0 and isinstance(contexts, list):
            before = len(contexts)
            req.contexts = [] if self.context_keep == 0 else contexts[-self.context_keep:]
            logger.info(f"[memechance] contexts {before} -> {len(req.contexts)}")

    @filter.on_decorating_result(priority=90000)
    async def clean_and_roll(self, event: AstrMessageEvent):
        result = event.get_result()
        if not result or not result.chain:
            return
        if self.leak_sanitize_enabled:
            for component in result.chain:
                if isinstance(component, Plain) and component.text:
                    cleaned = LEAK_TAG.sub("", component.text)
                    if cleaned != component.text:
                        logger.info(f"[memechance] stripped leaked tag: {component.text!r}")
                        component.text = cleaned
        if not self.enabled or not self.files:
            return
        content_type = getattr(result, "result_content_type", None)
        content_type_name = str(getattr(content_type, "name", content_type) or "")
        checker = getattr(result, "is_llm_result", None)
        if content_type_name != "STREAMING_FINISH" and (
            not callable(checker) or not checker()
        ):
            return
        if event.get_extra("meme_manager_pending_images"):
            return
        for component in result.chain:
            if isinstance(component, Image):
                return
        now = time.time()
        if now - self.last_at < self.cooldown:
            return
        if random.random() >= self.probability:
            return
        path = self._pick()
        self.last_at = now
        event.set_extra("memechance_pending", path)
        logger.info(f"[memechance] hit: {Path(path).parent.name}/{Path(path).name}")

    @filter.after_message_sent()
    async def send_pending(self, event: AstrMessageEvent):
        path = event.get_extra("memechance_pending")
        if not path:
            return
        event.set_extra("memechance_pending", None)
        try:
            await self.context.send_message(
                event.unified_msg_origin,
                MessageChain([Image.fromFileSystem(path)]),
            )
            logger.info(f"[memechance] sent: {Path(path).name}")
        except Exception as exc:
            logger.error(f"[memechance] send failed: {exc}")
