"""ちょる子の出演動画を集めて、字幕（文字起こし）をテキストで保存する。

お手元のPCで実行する（要: pip install yt-dlp）。
    python -m choruko yt discover        # 出演動画を探して data/videos.json に一覧化
    python -m choruko yt fetch --limit 100   # 字幕を knowledge/transcripts/ に保存
    python -m choruko yt bundle          # 字幕をまとめて、チャット・プロジェクトに入れやすい大きさに分割
"""
import html
import json
import re
import tempfile
import time
from pathlib import Path

from . import config as C

VIDEOS_JSON = C.DATA_DIR / "videos.json"
TRANSCRIPTS_DIR = C.KNOWLEDGE_DIR / "transcripts"
BUNDLE_DIR = C.KNOWLEDGE_DIR / "transcripts_bundle"

NAME_RE = re.compile(r"ちょる子|チョルコ|ちょるこ|choruko", re.I)

# YouTube 検索（ytsearchN:）。タイトルにちょる子が無い出演回も拾うため幅広めにする。
SEARCH_QUERIES = [
    "ちょる子", "ちょる子 株", "ちょる子 投資", "ちょる子 株ライブ 田端",
    "日曜夜も株ライブ ちょる子", "ちょる子 テスタ", "ちょる子 松井証券",
    "ちょる子 ReHacQ", "ちょる子 MONEY&MATE", "ちょる子 ブルーモ証券 投資教室",
    "ちょる子 PIVOT", "ちょる子 億り人 ママ投資家", "ちょる子 日経平均",
    "ちょる子 暴落", "ちょる子 半導体", "ちょる子 高配当", "ちょる子 NISA",
    "ちょる子 米国株", "ちょる子 WBS", "ちょる子 テスタの魔法株学校",
]

# 出演の多いチャンネル。動画・ライブ一覧から、タイトルにちょる子を含むものを拾う。
CHANNEL_TABS = [
    "https://www.youtube.com/@tabbata/streams",      # 田端大学 投資学部（日曜夜の株ライブ）
    "https://www.youtube.com/@tabbata/videos",
    "https://www.youtube.com/@bloomo-academy/videos",  # ブルーモ証券「ちょる子の投資教室」
    "https://www.youtube.com/@MatsuiSecurities/videos",  # 松井証券
    "https://www.youtube.com/@ReHacQ/videos",
    "https://www.youtube.com/@pivot00/videos",
]


# ---------- 字幕テキスト化（純粋関数。テスト対象） ----------

_TS = re.compile(r"^\d{2}:\d{2}(:\d{2})?\.\d{3} --> ")
_TAG = re.compile(r"<[^>]+>")


def vtt_to_text(vtt):
    """WebVTT から本文だけを取り出す。自動字幕の「前の行の繰り返し」も取り除く。"""
    out = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if (not line or line == "WEBVTT" or _TS.match(line) or line.isdigit()
                or line.startswith(("Kind:", "Language:", "NOTE", "STYLE"))):
            continue
        line = html.unescape(_TAG.sub("", line)).strip()
        if not line or line in out[-3:]:
            continue
        out.append(line)
    return "\n".join(out)


# ---------- 一覧づくり ----------

def _ydl(**extra):
    import yt_dlp  # 字幕取得を使うときだけ必要
    params = {"quiet": True, "no_warnings": True, "ignoreerrors": True}
    params.update(extra)
    return yt_dlp.YoutubeDL(params)


def load_videos():
    if VIDEOS_JSON.exists():
        return json.loads(VIDEOS_JSON.read_text(encoding="utf-8"))
    return {}


def save_videos(videos):
    VIDEOS_JSON.parent.mkdir(parents=True, exist_ok=True)
    VIDEOS_JSON.write_text(json.dumps(videos, ensure_ascii=False, indent=1), encoding="utf-8")


def _add(videos, entry, source, verified):
    vid = entry.get("id")
    if not vid or len(vid) != 11:  # チャンネルや再生リストは除く
        return False
    if vid in videos:
        if verified and not videos[vid]["verified"]:
            videos[vid]["verified"] = True
        return False
    videos[vid] = {
        "id": vid, "title": entry.get("title") or "", "channel": entry.get("channel") or entry.get("uploader") or "",
        "url": f"https://www.youtube.com/watch?v={vid}", "source": source,
        "verified": verified, "status": "new",
    }
    return True


def discover(per_query=100, log=print, browser=None):
    videos = load_videos()
    extra = {"extract_flat": "in_playlist"}
    if browser:
        extra["cookiesfrombrowser"] = (browser,)
    with _ydl(**extra) as ydl:
        for q in SEARCH_QUERIES:
            info = ydl.extract_info(f"ytsearch{per_query}:{q}", download=False) or {}
            n = sum(_add(videos, e, f"search:{q}", bool(NAME_RE.search(e.get("title") or "")))
                    for e in info.get("entries") or [] if e)
            log(f"  検索「{q}」: 新規 {n}")
        for url in CHANNEL_TABS:
            info = ydl.extract_info(url, download=False) or {}
            hits = [e for e in info.get("entries") or [] if e and NAME_RE.search(e.get("title") or "")]
            n = sum(_add(videos, e, f"channel:{url}", True) for e in hits)
            log(f"  {url}: タイトルにちょる子 {len(hits)}本（新規 {n}）")
    save_videos(videos)
    return videos


def add_url(url):
    m = re.search(r"(?:v=|youtu\.be/|shorts/|live/)([\w-]{11})", url)
    if not m:
        raise ValueError(f"動画IDが読み取れません: {url}")
    videos = load_videos()
    added = _add(videos, {"id": m.group(1)}, "manual", True)
    save_videos(videos)
    return added


# ---------- 字幕取得 ----------

def _pick_vtt(files, vid):
    """手動字幕 > 自動字幕。どちらも ja 系を優先する。"""
    cands = sorted(f for f in files if f.name.startswith(vid) and f.suffix == ".vtt")
    for f in cands:
        if ".ja." in f.name or f.name.endswith(".ja.vtt"):
            return f
    return cands[0] if cands else None


def transcript_path(meta):
    date = meta.get("upload_date") or "00000000"
    return TRANSCRIPTS_DIR / f"{date[:4]}-{date[4:6]}-{date[6:]}_{meta['id']}.md"


def fetch(limit=100, log=print, sleep=3.0, browser=None):
    """未取得の動画から最大 limit 本の字幕を保存する。"""
    videos = load_videos()
    todo = [v for v in videos.values() if v["status"] == "new"]
    # タイトルで確認できたものを先に、それ以外（説明欄で確認）を後に
    todo.sort(key=lambda v: not v["verified"])
    TRANSCRIPTS_DIR.mkdir(parents=True, exist_ok=True)
    done = 0
    for v in todo:
        if done >= limit:
            break
        with tempfile.TemporaryDirectory() as tmp:
            params = dict(skip_download=True, writesubtitles=True, writeautomaticsub=True,
                          subtitleslangs=["ja.*", "ja"], subtitlesformat="vtt",
                          outtmpl=str(Path(tmp) / "%(id)s.%(ext)s"))
            if browser:
                params["cookiesfrombrowser"] = (browser,)
            with _ydl(**params) as ydl:
                info = ydl.extract_info(v["url"], download=True)
            if not info:
                v["status"] = "error"
                log(f"  × 取得失敗（非公開・会員限定など）: {v['title'][:40]}")
                continue
            v.update(title=info.get("title") or v["title"], channel=info.get("channel") or v["channel"],
                     upload_date=info.get("upload_date"), duration=info.get("duration"))
            desc = info.get("description") or ""
            if not v["verified"] and not NAME_RE.search(v["title"] + desc):
                v["status"] = "not_choruko"
                continue
            v["verified"] = True
            vtt = _pick_vtt(list(Path(tmp).iterdir()), v["id"])
            if not vtt:
                v["status"] = "no_subs"
                log(f"  △ 字幕なし: {v['title'][:40]}")
                continue
            text = vtt_to_text(vtt.read_text(encoding="utf-8", errors="replace"))
            manual = any(k.startswith("ja") for k in (info.get("subtitles") or {}))
            kind = "投稿者" if manual else "自動生成（誤字あり）"
        path = transcript_path(v)
        header = (f"# {v['title']}\n\n- チャンネル: {v['channel']}\n- 公開日: {path.stem[:10]}\n"
                  f"- URL: {v['url']}\n- 字幕: {kind}\n\n"
                  "## 文字起こし\n\n")
        path.write_text(header + text + "\n", encoding="utf-8")
        v["status"] = "ok"
        v["transcript"] = path.name
        done += 1
        log(f"  ○ {done}/{limit} {path.stem[:10]} {v['title'][:50]}")
        save_videos(videos)  # 途中で止めても続きから再開できるように
        time.sleep(sleep)
    save_videos(videos)
    return done


def bundle(max_chars=400_000):
    """字幕を古い順につなげ、max_chars ごとに分割して保存する。作ったファイルの一覧を返す。"""
    files = sorted(TRANSCRIPTS_DIR.glob("*.md"))
    BUNDLE_DIR.mkdir(parents=True, exist_ok=True)
    for old in BUNDLE_DIR.glob("*.md"):
        old.unlink()
    out, buf, n = [], [], 0
    for f in files:
        t = f.read_text(encoding="utf-8")
        if buf and n + len(t) > max_chars:
            out.append(buf)
            buf, n = [], 0
        buf.append(t)
        n += len(t)
    if buf:
        out.append(buf)
    paths = []
    for i, parts in enumerate(out, 1):
        p = BUNDLE_DIR / f"choruko_youtube_{i:02d}.md"
        p.write_text(f"# ちょる子 出演動画 文字起こし集 {i}/{len(out)}\n\n" + "\n\n---\n\n".join(parts),
                     encoding="utf-8")
        paths.append(p)
    return paths


def summary():
    videos = load_videos()
    counts = {}
    for v in videos.values():
        counts[v["status"]] = counts.get(v["status"], 0) + 1
    return len(videos), counts
