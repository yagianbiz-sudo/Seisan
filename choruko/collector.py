"""ちょる子に関する公開情報を集めて data/sources.jsonl に貯める。

- 自動: Google ニュース RSS で「ちょる子」関連の記事を拾う（見出しと要約）
- 手動: X の投稿やセミナーのメモを `note` コマンドで貼り付ける
  （X は API が有料で、スクレイピングは規約違反になるので自動取得しない）
"""
import hashlib
import json
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from . import config as C
from .market import http_get

QUERIES = ["ちょる子 投資", "ちょる子 株", "ちょる子 銘柄"]


class _Text(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, d):
        self.parts.append(d)


def strip_html(s):
    p = _Text()
    p.feed(s or "")
    return " ".join(" ".join(p.parts).split())


def _id(url, text=""):
    return hashlib.sha1((url or text).encode()).hexdigest()[:16]


def load_sources(path=None):
    path = path or C.SOURCES_JSONL
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_sources(items, path=None):
    """id が既にあるものは飛ばして追記。追加した件数を返す。"""
    path = path or C.SOURCES_JSONL
    seen = {s["id"] for s in load_sources(path)}
    new = [i for i in items if i["id"] not in seen]
    if new:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for i in new:
                f.write(json.dumps(i, ensure_ascii=False) + "\n")
    return len(new)


def parse_rss(xml_text, query=""):
    items = []
    for it in ET.fromstring(xml_text).iter("item"):
        title = (it.findtext("title") or "").strip()
        link = (it.findtext("link") or "").strip()
        desc = strip_html(it.findtext("description") or "")
        try:
            published = parsedate_to_datetime(it.findtext("pubDate")).isoformat()
        except (TypeError, ValueError):
            published = None
        # 同名の別人・無関係記事を落とす
        if "ちょる子" not in title + desc:
            continue
        items.append({
            "id": _id(link), "kind": "news", "title": title, "url": link,
            "published": published, "text": desc, "query": query,
            "collected": datetime.now(timezone.utc).isoformat(),
        })
    return items


def collect_news(queries=QUERIES):
    items = []
    for q in queries:
        url = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
               + "&hl=ja&gl=JP&ceid=JP:ja")
        items += parse_rss(http_get(url), q)
    return append_sources(items), len(items)


def add_note(text, url="", kind="note", date=None):
    item = {
        "id": _id(url, text), "kind": kind, "title": text[:40], "url": url,
        "published": date or datetime.now(timezone.utc).isoformat(),
        "text": text, "collected": datetime.now(timezone.utc).isoformat(),
    }
    return append_sources([item])


def recent(n=30, kinds=None):
    """新しい順に n 件。"""
    src = [s for s in load_sources() if not kinds or s["kind"] in kinds]
    src.sort(key=lambda s: s.get("published") or s.get("collected") or "", reverse=True)
    return src[:n]
