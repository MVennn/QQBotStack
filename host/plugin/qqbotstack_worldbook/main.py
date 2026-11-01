"""QQBotStack worldbook plugin.

Owns worldbook.json, the matching/scoring algorithm and the injection block.
Guard calls `build_block()` through star_map; if this plugin is missing or
fails, guard falls back to its own copy of worldbook.json.

WebUI page: views/editor/index.html, backed by the /qqbotstack_worldbook/*
web APIs registered below.
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any

from astrbot.api import logger
from astrbot.api.star import Context, Star, register

try:  # Quart is provided by the AstrBot dashboard; tests may import without it.
    from quart import jsonify, request
except Exception:  # noqa: BLE001
    jsonify = None
    request = None

PLUGIN_NAME = "qqbotstack_worldbook"
HERE = Path(__file__).resolve().parent
WORLDBOOK_PATH = HERE / "worldbook.json"

LORE_MAX_ENTRIES = 2
LORE_MAX_CHARS = 1400
LORE_HEADER = (
    "\n\n[以下是你所知道的设定，用于保持世界观一致；"
    "不要原文复述，也不要解释它从哪来]\n"
)


def _load_data(path: Path) -> dict:
    try:
        with path.open(encoding="utf-8") as fh:
            data = json.load(fh)
    except FileNotFoundError:
        logger.warning(f"[{PLUGIN_NAME}] worldbook.json not found at {path}")
        return {"name": "", "entries": []}
    except (OSError, ValueError) as exc:
        logger.error(f"[{PLUGIN_NAME}] failed to read worldbook.json: {exc}")
        return {"name": "", "entries": []}
    if isinstance(data, list):
        return {"name": "", "entries": data}
    if not isinstance(data, dict):
        return {"name": "", "entries": []}
    entries = data.get("entries")
    if not isinstance(entries, list):
        entries = []
    return {"name": str(data.get("name") or ""), "entries": entries}


def _clean_entry(raw: dict, *, require_name: bool = True) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("条目必须是对象")
    name = str(raw.get("name") or "").strip()
    if require_name and not name:
        raise ValueError("条目名称不能为空")
    content = str(raw.get("content") or "").strip()
    if not content:
        raise ValueError(f"条目「{name or '未命名'}」的正文不能为空")
    keys_raw = raw.get("keys") or []
    if isinstance(keys_raw, str):
        keys_raw = [item for item in keys_raw.replace("，", ",").replace("、", ",").split(",")]
    if not isinstance(keys_raw, list):
        keys_raw = []
    keys: list[str] = []
    for item in keys_raw:
        key = str(item).strip()
        if key and key not in keys:
            keys.append(key)
    constant = bool(raw.get("constant", False))
    if not keys and not constant:
        raise ValueError(f"条目「{name}」至少要有一个关键词，或者设为常驻")
    try:
        priority = int(raw.get("priority", 50))
    except (TypeError, ValueError):
        raise ValueError(f"条目「{name}」的优先级必须是数字")
    priority = max(0, min(100, priority))
    return {
        "name": name,
        "keys": keys,
        "priority": priority,
        "content": content,
        "constant": constant,
    }


def _write_data(path: Path, data: dict) -> None:
    """Atomic write with a .bak copy of the previous file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    if path.exists():
        try:
            shutil.copy2(path, path.with_name(path.name + ".bak"))
        except OSError as exc:
            logger.warning(f"[{PLUGIN_NAME}] backup failed: {exc}")
    os.replace(tmp, path)


@register(
    PLUGIN_NAME,
    "M.Venn",
    "世界书：关键词匹配、常驻条目、优先级注入，带 WebUI 编辑器",
    "1.0.0",
)
class WorldbookPlugin(Star):
    def __init__(self, context: Context):
        super().__init__(context)
        self._lock = threading.Lock()
        self._path = WORLDBOOK_PATH
        self._data = _load_data(self._path)
        self.title = str(self._data.get("name") or "")
        self.entries: list[dict] = [
            entry for entry in self._data.get("entries") or [] if isinstance(entry, dict)
        ]
        self._register_routes()
        logger.info(
            f"[{PLUGIN_NAME}] loaded {len(self.entries)} entries "
            f"from {self._path.name}"
        )

    # ---------------- matching / injection ----------------

    def _pick(
        self, text: str, max_entries: int = LORE_MAX_ENTRIES, max_chars: int = LORE_MAX_CHARS
    ) -> list[dict]:
        text = (text or "").strip()
        if not self.entries or not text:
            return []
        picked: list[dict] = []
        used = 0
        for entry in self.entries:
            if not entry.get("constant"):
                continue
            body = str(entry.get("content") or "")
            if used + len(body) > max_chars:
                continue
            picked.append(entry)
            used += len(body)

        scored: list[tuple[int, dict]] = []
        for entry in self.entries:
            if entry.get("constant"):
                continue
            keys = entry.get("keys") or []
            hits = sum(1 for key in keys if key and str(key) in text)
            name = str(entry.get("name") or "")
            if hits and any(
                key and str(key) in text and str(key) in name for key in keys
            ):
                # 问谁就优先给谁的人物页，别让通用条目占满槽位。
                hits += 1
            if hits:
                scored.append((hits, entry))
        scored.sort(
            key=lambda item: (-item[0], -int(item[1].get("priority", 0) or 0))
        )

        matched = 0
        for _, entry in scored:
            if matched >= max_entries:
                break
            body = str(entry.get("content") or "")
            if used + len(body) > max_chars:
                continue
            picked.append(entry)
            used += len(body)
            matched += 1
        return picked

    def build_block(
        self,
        text: str,
        max_entries: int = LORE_MAX_ENTRIES,
        max_chars: int = LORE_MAX_CHARS,
    ) -> str:
        """Return the lore block to append to the system prompt ('' if none)."""
        picked = self._pick(text, max_entries, max_chars)
        if not picked:
            return ""
        body = "\n\n".join(
            "· "
            + str(entry.get("name") or "")
            + "："
            + str(entry.get("content") or "")
            for entry in picked
        )
        return LORE_HEADER + body

    def reload(self) -> int:
        data = _load_data(self._path)
        with self._lock:
            self._data = data
            self.title = str(data.get("name") or "")
            self.entries = [
                entry for entry in data.get("entries") or [] if isinstance(entry, dict)
            ]
        return len(self.entries)

    # ---------------- web APIs ----------------

    def _register_routes(self) -> None:
        routes = [
            ("/entries", self.page_entries, ["GET"], "List worldbook entries"),
            ("/entry", self.page_upsert_entry, ["POST"], "Create or update entry"),
            ("/entry", self.page_delete_entry, ["DELETE"], "Delete entry"),
            ("/entry/delete", self.page_delete_entry_post, ["POST"], "Delete entry (bridge)"),
            ("/match", self.page_match, ["POST"], "Preview matched entries"),
            ("/import", self.page_import, ["POST"], "Replace all entries"),
            ("/reload", self.page_reload, ["POST"], "Reload worldbook.json"),
        ]
        for path, handler, methods, desc in routes:
            try:
                self.context.register_web_api(
                    f"/{PLUGIN_NAME}{path}", handler, methods, desc
                )
            except Exception as exc:  # noqa: BLE001
                logger.warning(f"[{PLUGIN_NAME}] register {path} failed: {exc}")

    @staticmethod
    def _json(payload: dict[str, Any], status: int = 200):
        if jsonify is None:
            raise RuntimeError("Web framework is unavailable")
        return jsonify(payload), status

    def _snapshot(self) -> dict:
        return {
            "title": self.title,
            "count": len(self.entries),
            "entries": list(self.entries),
            "path": str(self._path),
        }

    async def page_entries(self):
        return self._json({"ok": True, "data": self._snapshot()})

    async def page_upsert_entry(self):
        if request is None:
            raise RuntimeError("Web framework is unavailable")
        payload = await request.get_json(force=True, silent=True) or {}
        entry = _clean_entry(payload)
        original = str(payload.get("original_name") or "").strip()
        with self._lock:
            entries = list(self.entries)
            index = None
            for i, item in enumerate(entries):
                if original and str(item.get("name") or "") == original:
                    index = i
                    break
            if index is None:
                for i, item in enumerate(entries):
                    if str(item.get("name") or "") == entry["name"]:
                        index = i
                        break
            if index is None:
                entries.append(entry)
            else:
                if original and original != entry["name"]:
                    for item in entries:
                        if str(item.get("name") or "") == entry["name"]:
                            raise ValueError(f"已存在同名条目「{entry['name']}」")
                entries[index] = entry
            data = {"name": self.title, "entries": entries}
            _write_data(self._path, data)
        self.reload()
        return self._json({"ok": True, "data": self._snapshot()})

    def _delete_by_name(self, name: str):
        name = str(name or "").strip()
        if not name:
            raise ValueError("缺少条目名称")
        with self._lock:
            entries = [
                item
                for item in self.entries
                if str(item.get("name") or "") != name
            ]
            if len(entries) == len(self.entries):
                raise ValueError(f"没有找到条目「{name}」")
            data = {"name": self.title, "entries": entries}
            _write_data(self._path, data)
        self.reload()
        return self._json({"ok": True, "data": self._snapshot()})

    async def page_delete_entry(self):
        if request is None:
            raise RuntimeError("Web framework is unavailable")
        return self._delete_by_name(request.args.get("name") or "")

    async def page_delete_entry_post(self):
        """Bridge 只有 apiGet/apiPost，页面删除走 POST /entry/delete。"""
        if request is None:
            raise RuntimeError("Web framework is unavailable")
        payload = await request.get_json(force=True, silent=True) or {}
        return self._delete_by_name(payload.get("name") or "")

    async def page_match(self):
        if request is None:
            raise RuntimeError("Web framework is unavailable")
        payload = await request.get_json(force=True, silent=True) or {}
        text = str(payload.get("text") or "")
        try:
            max_entries = max(1, min(6, int(payload.get("max_entries", LORE_MAX_ENTRIES))))
        except (TypeError, ValueError):
            max_entries = LORE_MAX_ENTRIES
        try:
            max_chars = max(200, min(6000, int(payload.get("max_chars", LORE_MAX_CHARS))))
        except (TypeError, ValueError):
            max_chars = LORE_MAX_CHARS
        picked = self._pick(text, max_entries, max_chars)
        return self._json(
            {
                "ok": True,
                "data": {
                    "text": text,
                    "picked": picked,
                    "block": self.build_block(text, max_entries, max_chars),
                },
            }
        )

    async def page_import(self):
        if request is None:
            raise RuntimeError("Web framework is unavailable")
        payload = await request.get_json(force=True, silent=True) or {}
        raw_entries = payload.get("entries")
        if not isinstance(raw_entries, list):
            raise ValueError("entries 必须是数组")
        cleaned = [_clean_entry(item) for item in raw_entries]
        names = [item["name"] for item in cleaned]
        if len(names) != len(set(names)):
            raise ValueError("导入数据里有重复的条目名称")
        title = str(payload.get("title") or self.title)
        with self._lock:
            _write_data(self._path, {"name": title, "entries": cleaned})
        self.reload()
        return self._json({"ok": True, "data": self._snapshot()})

    async def page_reload(self):
        count = self.reload()
        return self._json({"ok": True, "data": {"count": count}})
