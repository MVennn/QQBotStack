#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把一份 Markdown 设定集切成世界书条目，供 qqbotstack_guard 按关键词注入。

用法：
    python tools/build-worldbook.py --src <设定集.md> --out <worldbook.json>
    python tools/build-worldbook.py --src <设定集.md> --out <worldbook.json> --book-name 绿海

切分规则（与具体作品无关，纯结构驱动）：
- 按二级标题 `##` 切条目；`#` 一级标题当作「卷」前缀拼进条目名；
- 条目的 keys = 小节标题 + 正文里所有 `**加粗**` 术语（去重、去通用词、最多 8 个）；
- 第一条是常驻条目（每轮注入），内容取「卷一下的第一节 + 卷二下的第一节」，截断到 500 字；
- 每条正文截断到 700 字，在句号 / 感叹号 / 问号 / 换行处断开。

为什么不把设定直接塞进人格提示词：整本设定动辄几万字，每轮都注入既贵又会让
模型分不清「人格」和「设定」。世界书只在提到相关词时才注入，才是对的用法。
产物含作品内容，**不入库**（见 .gitignore），只提交本脚本。
"""
from __future__ import annotations

import argparse
import json
import os
import re

# 这些词太泛，出现在几乎每个小节里，当 key 会命中一片
GENERIC_KEYS = {
    "绿海", "世界", "设定", "规则", "说明", "总览", "序", "附录",
    "身份", "年龄", "级别", "外形", "经历", "动机", "关系", "能力", "写法",
    "序章", "终章", "幕间", "基线", "中段", "后段", "个人回",
}
# 只接受「像一个词」的加粗内容：中文/字母/数字/中点，2–10 字，不含标点与空格
KEY_SHAPE = re.compile(r"[\u4e00-\u9fffA-Za-z0-9·\-]{2,10}")
# 这些小节是「关于这本书的说明」，不是世界设定
SKIP_TITLES = {"编纂说明", "目录", "后记"}

# 人物语气相关的小节排在同节其他内容前面 —— 聊天里最常命中的是「这个人怎么说话」，
# 不是他的外形或履历。排序后，同一人物被提及时，前三槽优先给语气与性格。
TONE_HINTS = ("语言", "说话", "口吻", "语气", "话最多", "性格", "脾气", "行事准则")

# 条目优先级：命中数相同时，人物 > 剧情 > 世界观 > 附录。
# 否则「梵铭」在别的章节里被加粗一次，就会把真正的人物条目挤掉。
PRIORITY_CHARACTER = 80
PRIORITY_STORY = 70
PRIORITY_WORLD = 50
PRIORITY_APPENDIX = 10
PRIORITY_IDENTITY = 95
PRIORITY_TONE = 85

# 人物条目的关键词只收本人与本人的别名；正文里顺带提到的其他人物不再当 key，
# 否则「蒂米」会被玟德的语言条目抢走（那条里提了一句蒂米）。
CHARACTER_NAMES = {
    "梵铭", "铭", "玟德", "犹达斯", "蒂米", "拉斐尔", "乌列",
    "拉贵尔", "悠塔", "拉梵", "神父", "小伯", "赤鬼", "阿悠", "阿铭",
}
SUBJECT_ALIASES = {
    "梵铭": {"拉贵尔", "神父", "小伯", "阿铭"},
    "犹达斯": {"悠塔", "阿悠"},
    "玟德": {"赤鬼"},
    "拉斐尔": {"拉梵"},
}


def split_sections(text: str) -> list:
    """返回 [(卷名, 小节标题, 正文)]。"""
    sections = []
    cur_vol = ""
    start_vol = ""
    name = None
    buf = []

    def flush():
        nonlocal name, buf
        if name is not None:
            sections.append((start_vol, name, "\n".join(buf).strip()))
        name = None
        buf = []

    for line in text.splitlines():
        if line.startswith("# ") and not line.startswith("## "):
            flush()
            cur_vol = line[2:].strip()
            continue
        if line.startswith("## "):
            flush()
            start_vol = cur_vol
            name = line[3:].strip()
            continue
        if name is not None:
            buf.append(line)
    flush()
    return sections


def clean_heading(heading: str) -> str:
    return re.sub(r"^[\d.\s]+", "", heading).strip()


def truncate(text: str, limit: int) -> str:
    text = text.strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for mark in ("。", "！", "？", "\n"):
        pos = cut.rfind(mark)
        if pos > limit * 0.6:
            return cut[: pos + 1]
    return cut


def bold_terms(body: str) -> list:
    return re.findall(r"\*\*(.+?)\*\*", body)


def split_subsections(body: str) -> tuple:
    """把一节按 `###` 拆成 (前言, [(子标题, 子正文)])。没有子标题时返回 (body, [])。"""
    pre = []
    subs = []
    cur = None
    buf = []
    for line in body.splitlines():
        if line.startswith("### ") and not line.startswith("#### "):
            if cur is None:
                pre = buf
            else:
                subs.append((cur, "\n".join(buf).strip()))
            cur = line[4:].strip()
            buf = []
        else:
            buf.append(line)
    if cur is None:
        return body.strip(), []
    subs.append((cur, "\n".join(buf).strip()))
    return "\n".join(pre).strip(), subs


def title_keys(title: str) -> list:
    """标题本身 + 去掉括号后按分隔符拆出的词。避免「一 · 灰烬与余火」这种整串 key 永远命不中。"""
    stripped = re.sub(r"[【（(][^】）)]*[】）)]", "", title).strip()
    keys = [title, stripped]
    for part in re.split(r"[·、：:]", stripped):
        part = part.strip()
        if len(part) < 2 or part in GENERIC_KEYS:
            continue
        # 「十一」「二十一」这类序号没有检索价值，还会误命中
        if re.fullmatch(r"[零一二三四五六七八九十百千]+", part):
            continue
        keys.append(part)
    return list(dict.fromkeys(k for k in keys if k))


def entry_priority(vol: str, title: str) -> int:
    if "身份辨析" in title:
        return PRIORITY_IDENTITY
    if "口吻速查" in title:
        return PRIORITY_TONE
    if "人物" in vol or title in {
        "梵铭", "铭", "玟德", "犹达斯", "蒂米", "拉斐尔", "乌列",
        "赫尔墨斯", "乌列尔", "卡戎",
    }:
        return PRIORITY_CHARACTER
    if "剧情" in vol or "大纲" in vol or "粗纲" in title or "分章" in title:
        return PRIORITY_STORY
    if vol.startswith("附"):
        return PRIORITY_APPENDIX
    return PRIORITY_WORLD


def term_allowed(term: str, subject: str, sub: str) -> bool:
    """人物条目的 key 只留本人与别名；关系类小节例外，那里本来就要多人名。"""
    if subject not in CHARACTER_NAMES or sub in ("关系", "关系矩阵"):
        return True
    if term in CHARACTER_NAMES and term != subject:
        return term in SUBJECT_ALIASES.get(subject, set())
    return True


def build(src: str, book_name: str, make_constant: bool = True) -> dict:
    text = open(src, encoding="utf-8").read()
    sections = split_sections(text)

    entries = []
    # 常驻条目：取前两卷各自的第一节，给模型一个不跑偏的世界骨架。
    # 跳过「编纂说明」这类关于书的说明。
    if make_constant:
        seeds = []
        seen_vol = set()
        for vol, head, body in sections:
            title = clean_heading(head)
            if not vol or not body or title in SKIP_TITLES:
                continue
            if vol not in seen_vol:
                seen_vol.add(vol)
                seeds.append(body)
            if len(seeds) >= 2:
                break
        if seeds:
            entries.append({
                "name": "世界观总览",
                "constant": True,
                "priority": 100,
                "content": truncate("\n".join(seeds), 500),
            })

    for vol, head, body in sections:
        if not body:
            continue
        title = clean_heading(head)
        if not title or title in SKIP_TITLES:
            continue
        priority = entry_priority(vol, title)
        base_keys = title_keys(title)
        pre, subs = split_subsections(body)

        # 短节不拆；长节按 ### 拆开，否则人物最重要的「语言 / 性格」会被 700 字截断吃掉。
        if subs and len(body) > 700:
            items = []
            if pre:
                items.append(("总览", pre))
            items.extend(subs)
            # 语气 / 性格 > 总览 > 其余；同档保持原顺序
            def rank(item):
                name = item[0]
                if any(hint in name for hint in TONE_HINTS):
                    return 0
                if name == "总览":
                    return 1
                return 2

            items.sort(key=rank)
            for sub, sub_body in items:
                if not sub_body:
                    continue
                keys = list(base_keys)
                if sub != "总览" and sub not in GENERIC_KEYS:
                    keys.extend(title_keys(sub))
                for term in bold_terms(sub_body):
                    term = term.strip()
                    if term in GENERIC_KEYS:
                        continue
                    if not term_allowed(term, title, sub):
                        continue
                    if KEY_SHAPE.fullmatch(term):
                        keys.append(term)
                keys = list(dict.fromkeys(keys))[:12]
                entries.append({
                    "name": " · ".join(p for p in (vol, title, sub) if p),
                    "keys": keys,
                    "priority": priority,
                    "content": truncate(sub_body, 700),
                })
            continue

        keys = list(base_keys)
        for term in bold_terms(body):
            term = term.strip()
            if term in GENERIC_KEYS:
                continue
            if not term_allowed(term, title, ""):
                continue
            if KEY_SHAPE.fullmatch(term):
                keys.append(term)
        keys = list(dict.fromkeys(keys))[:12]
        entries.append({
            "name": (vol + " · " + title) if vol else title,
            "keys": keys,
            "priority": priority,
            "content": truncate(body, 700),
        })

    return {"name": book_name, "entries": entries}


VIEW_TEMPLATE = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>世界书 · __BOOK__</title>
<style>
  :root { color-scheme: light dark; }
  * { box-sizing: border-box; }
  body { margin: 0; padding: 20px; font: 14px/1.6 -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif; }
  h1 { font-size: 18px; margin: 0 0 4px; }
  .meta { opacity: .65; font-size: 12px; margin-bottom: 16px; }
  .bar { display: flex; gap: 10px; align-items: center; margin-bottom: 16px; flex-wrap: wrap; }
  input { flex: 1 1 260px; padding: 8px 12px; border: 1px solid rgba(128,128,128,.45); border-radius: 8px; background: transparent; color: inherit; font: inherit; }
  .count { font-size: 12px; opacity: .7; white-space: nowrap; }
  .entry { border: 1px solid rgba(128,128,128,.28); border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; }
  .entry.constant { border-color: rgba(255,159,69,.6); }
  .head { display: flex; gap: 8px; align-items: baseline; flex-wrap: wrap; }
  .name { font-weight: 600; }
  .tag { font-size: 11px; padding: 1px 7px; border-radius: 999px; background: rgba(255,159,69,.18); color: #d9822b; }
  .keys { margin: 6px 0 8px; display: flex; gap: 6px; flex-wrap: wrap; }
  .key { font-size: 11px; padding: 1px 8px; border-radius: 999px; background: rgba(128,128,128,.16); }
  .body { white-space: pre-wrap; word-break: break-word; max-height: 260px; overflow: auto; padding-right: 6px; }
  .empty { opacity: .6; text-align: center; padding: 40px 0; }
</style>
</head>
<body>
  <h1>世界书 · __BOOK__</h1>
  <div class="meta">__TOTAL__ 条 · 正文合计 __CHARS__ 字 · 常驻 __CONST__ 条</div>
  <div class="bar">
    <input id="q" type="search" placeholder="搜条目名、关键词或正文…">
    <span class="count" id="count"></span>
  </div>
  <div id="list"></div>
<script>
const DATA = __DATA__;
const list = document.getElementById('list');
const q = document.getElementById('q');
const counter = document.getElementById('count');

function esc(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function render(keyword) {
  const kw = (keyword || '').trim().toLowerCase();
  const hits = DATA.entries.filter(function (e) {
    if (!kw) return true;
    const hay = [e.name, (e.keys || []).join(' '), e.content].join(' ').toLowerCase();
    return hay.indexOf(kw) >= 0;
  });
  counter.textContent = hits.length + ' / ' + DATA.entries.length;
  if (!hits.length) {
    list.innerHTML = '<div class="empty">没有匹配的条目</div>';
    return;
  }
  list.innerHTML = hits.map(function (e) {
    const keys = (e.keys || []).map(function (k) {
      return '<span class="key">' + esc(k) + '</span>';
    }).join('');
    return '<div class="entry' + (e.constant ? ' constant' : '') + '">' +
      '<div class="head"><span class="name">' + esc(e.name) + '</span>' +
      (e.constant ? '<span class="tag">常驻</span>' : '') +
      '<span class="count">' + String(e.content || '').length + ' 字</span></div>' +
      (keys ? '<div class="keys">' + keys + '</div>' : '') +
      '<div class="body">' + esc(e.content) + '</div></div>';
  }).join('');
}

q.addEventListener('input', function () { render(q.value); });
render('');
</script>
</body>
</html>
"""


def render_view(data: dict) -> str:
    entries = data.get("entries", [])
    return (
        VIEW_TEMPLATE
        .replace("__BOOK__", data.get("name", "世界书"))
        .replace("__TOTAL__", str(len(entries)))
        .replace("__CHARS__", str(sum(len(e.get("content", "")) for e in entries)))
        .replace("__CONST__", str(sum(1 for e in entries if e.get("constant"))))
        .replace("__DATA__", json.dumps(data, ensure_ascii=False))
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Markdown 设定集 → 世界书 JSON")
    parser.add_argument(
        "--src", required=True, nargs="+",
        help="设定集 Markdown 路径，可给多份（第一份负责常驻总览，其余只贡献关键词条目）",
    )
    parser.add_argument("--out", required=True, help="输出 JSON 路径")
    parser.add_argument("--book-name", default="", help="世界书名称，默认取文件名")
    parser.add_argument(
        "--aliases",
        default="",
        help="别名补进关键词，形如 拉贵尔=梵铭,神父=梵铭（别名=条目里已有的词）",
    )
    parser.add_argument(
        "--view",
        default="",
        help="同时生成 WebUI 浏览页，值为插件目录（会写 <dir>/views/worldbook/index.html）",
    )
    args = parser.parse_args()

    for src in args.src:
        if not os.path.isfile(src):
            print(f"✗ 找不到设定集：{src}")
            return 2

    book_name = args.book_name or os.path.splitext(os.path.basename(args.src[0]))[0]
    data = {"name": book_name, "entries": []}
    for index, src in enumerate(args.src):
        data["entries"].extend(build(src, book_name, make_constant=(index == 0))["entries"])

    for pair in filter(None, (p.strip() for p in args.aliases.split(","))):
        alias, _, target = pair.partition("=")
        alias, target = alias.strip(), target.strip()
        if not alias or not target:
            continue
        for entry in data["entries"]:
            keys = entry.get("keys") or []
            if target in keys and alias not in keys:
                entry["keys"] = (keys + [alias])[:12]

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)

    total = sum(len(e["content"]) for e in data["entries"])
    constant = sum(1 for e in data["entries"] if e.get("constant"))
    print(f"✓ {len(data['entries'])} 条（常驻 {constant} 条），正文合计 {total} 字 → {args.out}")

    if args.view:
        view_dir = os.path.join(args.view, "views", "worldbook")
        os.makedirs(view_dir, exist_ok=True)
        view_path = os.path.join(view_dir, "index.html")
        with open(view_path, "w", encoding="utf-8") as fh:
            fh.write(render_view(data))
        print(f"✓ WebUI 浏览页 → {view_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
