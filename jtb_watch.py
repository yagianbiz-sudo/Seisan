#!/usr/bin/env python3
"""JTB「九州ふっこう応援割」クーポンページ変化監視（Google Colab / PC 両対応）。

各県のクーポンページを1秒おきに取得し、内容が変わったときだけ
  - スマホへプッシュ通知（ntfy。音はスマホ側だけ、PCは無音）
  - 記録（events.csv に差分、snapshots/ に変化後のHTML）
を行う。変化がなければ何も記録しない。

判定は「特定の文言を探す」のではなく「ページの文字・ボタンが変わったか」で行う。
起動直後に数回取得して、毎回変わる部分（時刻・トークン等）を自動で無視対象にする。
数字だけの変化（時刻・閲覧数など）も無視する。

使い方:
    python jtb_watch.py --ntfy 好きなトピック名           # 監視開始
    python jtb_watch.py --ntfy 好きなトピック名 --test    # 通知テスト
    python jtb_watch.py --inspect                         # 取得できた文字・ボタンを表示（動作確認）
    python jtb_watch.py --only 熊本 長崎 --interval 2
Colab では jtb_watch_colab.ipynb を使う。
"""
import argparse
import csv
import difflib
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

JST = timezone(timedelta(hours=9))
PAGE = "https://www.jtb.co.jp/myjtb/campaign/coupon/detail/{}/page.asp"

TARGETS = {
    "熊本": PAGE.format("2609kyushukumamoto"),
    "福岡": PAGE.format("2609kyushufukuoka"),
    "佐賀": PAGE.format("2609kyushusaga"),
    "長崎": PAGE.format("2609kyushunagasaki"),
    "鹿児島": PAGE.format("2609kyushukagoshima"),
}

# 差分の追加行/削除行にこれらが含まれたら、通知タイトルに「復活?」「終了?」を付ける（目安）。
# ページ文言が分かったら調整する。判定に関係なく、変化があれば必ず通知・記録はする。
REVIVE_WORDS = ["取得する", "獲得する", "クーポンを取得", "予約する", "配布中"]
END_WORDS = ["終了", "上限", "予定枚数", "在庫", "受付停止", "なくなり"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
}

WARMUP_FETCHES = 4        # 起動時に取得して揺れる行を学習する回数
ERROR_NOTIFY_AFTER = 10   # 連続失敗がこの回数に達したら異変として通知・記録
MAX_BACKOFF = 60          # 失敗時の待ち時間の上限(秒)
HEARTBEAT_SEC = 300       # 画面にだけ出す生存表示の間隔（記録はしない）


def now():
    return datetime.now(JST)


def log(msg):
    print(f"[{now():%m/%d %H:%M:%S}] {msg}", flush=True)


def extract_lines(html):
    """ページを「見える文字の行」と「ボタン・リンクの状態の行」に分解する。"""
    soup = BeautifulSoup(html, "html.parser")
    for t in soup(["script", "style", "noscript", "template", "svg"]):
        t.decompose()
    lines = []
    for el in soup.find_all(["a", "button", "input"]):
        if el.name == "input" and el.get("type", "").lower() == "hidden":
            continue
        label = " ".join(el.get_text(" ", strip=True).split()) or el.get("value", "") or el.get("alt", "")
        flags = []
        if el.has_attr("disabled"):
            flags.append("disabled")
        cls = " ".join(el.get("class", []))
        if any(k in cls for k in ("disable", "inactive", "end", "off", "soldout")):
            flags.append(f"class={cls}")
        if not label and not flags:
            continue
        href = (el.get("href") or "").split("?")[0]
        lines.append(f"[{el.name}] {label} {href} {' '.join(flags)}".rstrip())
    for raw in soup.get_text("\n").splitlines():
        s = " ".join(raw.split())
        if s:
            lines.append(s)
    seen, out = set(), []
    for s in lines:
        if s not in seen:
            seen.add(s)
            out.append(s)
    return out


def page_title(html):
    """クーポン名として記録する見出し（h1 → title の順）。"""
    soup = BeautifulSoup(html, "html.parser")
    for el in (soup.find("h1"), soup.title):
        if el and el.get_text(strip=True):
            return " ".join(el.get_text(" ", strip=True).split())
    return ""


def normalize(line):
    """比較用。トークン等の長いランダム文字列と数字を伏せる（時刻・アクセス数などで誤検知しないため）。"""
    line = re.sub(r"[A-Za-z0-9_\-]{20,}", "*", line)
    return re.sub(r"[0-9０-９]+", "#", line)


def hint(added, removed):
    """差分から「復活?」「終了?」の目安を付ける。押せないボタン(disabled)は終了側に数える。"""
    def has(words, s):
        return any(w in s for w in words)
    revive = sum(has(REVIVE_WORDS, s) and "disabled" not in s for s in added)
    revive += sum(has(END_WORDS, s) for s in removed)
    end = sum(has(REVIVE_WORDS, s) for s in removed)
    end += sum(has(END_WORDS, s) or (has(REVIVE_WORDS, s) and "disabled" in s) for s in added)
    if revive > end:
        return "復活?"
    if end > revive:
        return "終了?"
    return "変化"


class Notifier:
    def __init__(self, ntfy_topic=None, ntfy_server="https://ntfy.sh", discord_webhook=None):
        self.ntfy_topic = ntfy_topic
        self.ntfy_server = ntfy_server.rstrip("/")
        self.discord = discord_webhook

    def send(self, title, message, url=None, priority=4):
        log(f"通知: {title} / {message.splitlines()[0] if message else ''}")
        if self.ntfy_topic:
            body = {"topic": self.ntfy_topic, "title": title, "message": message[:3500],
                    "priority": priority, "tags": ["ticket"]}
            if url:
                body["click"] = url
                body["actions"] = [{"action": "view", "label": "ページを開く", "url": url}]
            self._post(self.ntfy_server, json=body)
        if self.discord:
            self._post(self.discord, json={"content": f"**{title}**\n{message[:1800]}\n{url or ''}"})

    def _post(self, url, **kw):
        try:
            requests.post(url, timeout=10, **kw).raise_for_status()
        except Exception as e:  # 通知失敗でも監視は止めない
            log(f"通知失敗: {e}")


class Recorder:
    FIELDS = ["時刻", "県", "クーポン名", "種別", "判定", "追加された行", "消えた行", "URL", "スナップショット"]

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.snap_dir = os.path.join(out_dir, "snapshots")
        os.makedirs(self.snap_dir, exist_ok=True)
        self.csv_path = os.path.join(out_dir, "events.csv")
        self.lock = threading.Lock()

    def write(self, pref, kind, judge, url, added=(), removed=(), html=None, title=""):
        t = now()
        snap = ""
        if html is not None:
            snap = os.path.join(self.snap_dir, f"{t:%Y%m%d_%H%M%S}_{pref}.html")
            with open(snap, "w", encoding="utf-8") as f:
                f.write(html)
        with self.lock:
            new = not os.path.exists(self.csv_path)
            # utf-8-sig: Excel で開いても文字化けしない
            with open(self.csv_path, "a", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                if new:
                    w.writerow(self.FIELDS)
                w.writerow([f"{t:%Y-%m-%d %H:%M:%S}", pref, title, kind, judge,
                            "\n".join(added), "\n".join(removed), url, snap])


class Watcher:
    def __init__(self, pref, url, interval, notifier, recorder):
        self.pref, self.url, self.interval = pref, url, interval
        self.notifier, self.recorder = notifier, recorder
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        self.ignore = set()
        self.lines = None
        self.html = None
        self.raw = {}  # 比較用の行 → 表示用の元の行
        self.prev_raw = {}
        self.errors = 0
        self.in_error = False
        self.checks = 0

    def fetch(self):
        r = self.session.get(self.url, timeout=10)
        if r.status_code >= 400:
            raise RuntimeError(f"HTTP {r.status_code}")
        r.encoding = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else r.apparent_encoding
        raw = extract_lines(r.text)
        # ログイン画面などへ飛ばされたら、それも「変化」として拾う
        if r.url.split("?")[0] != self.url:
            raw.insert(0, f"[redirect] {r.url.split('?')[0]}")
        lines, self.raw = [], {}
        for s in raw:
            n = normalize(s)
            if n not in self.raw:
                self.raw[n] = s
                lines.append(n)
        return r.text, lines

    def warmup(self):
        """数回取得して、毎回変わる行（時刻やトークン）を無視対象として覚える。"""
        samples = []
        for _ in range(WARMUP_FETCHES):
            html, lines = self.fetch()
            samples.append(set(lines))
            time.sleep(self.interval)
        common = set.intersection(*samples)
        self.ignore = set.union(*samples) - common
        self.html, self.lines = html, [s for s in lines if s not in self.ignore]
        self.prev_raw = self.raw
        log(f"{self.pref}: 監視開始（{len(self.lines)}行を監視 / 揺れる{len(self.ignore)}行は無視）")

    def check(self):
        html, lines = self.fetch()
        lines = [s for s in lines if s not in self.ignore]
        if lines == self.lines:
            self.prev_raw = self.raw
            return
        added, removed = [], []
        for op in difflib.ndiff(self.lines, lines):
            if op.startswith("+ "):
                added.append(self.raw[op[2:]])
            elif op.startswith("- "):
                removed.append(self.prev_raw.get(op[2:], op[2:]))
        if not added and not removed:  # 並び順だけの変化は無視
            self.lines, self.prev_raw = lines, self.raw
            return
        judge = hint(added, removed)
        title = page_title(html)
        self.recorder.write(self.pref, "ページ変化", judge, self.url, added, removed, html, title)
        msg = (title + "\n" if title else "") + "\n".join([f"＋ {s}" for s in added[:8]] + [f"－ {s}" for s in removed[:8]])
        self.notifier.send(f"【{judge}】JTB {self.pref}", msg, self.url,
                           priority=5 if judge == "復活?" else 4)
        self.html, self.lines, self.prev_raw = html, lines, self.raw

    def run(self, stop):
        backoff = self.interval
        while not stop.is_set():
            if self.lines is None:
                try:
                    self.warmup()
                except Exception as e:
                    self._error(e)
                    stop.wait(min(MAX_BACKOFF, backoff))
                    backoff *= 2
                    continue
            started = time.monotonic()
            try:
                self.check()
                self.checks += 1
                if self.in_error:
                    self.recorder.write(self.pref, "取得復旧", "", self.url)
                    self.notifier.send(f"JTB {self.pref} 監視復旧", "再び取得できています", self.url, 3)
                self.errors, self.in_error, backoff = 0, False, self.interval
            except Exception as e:
                self._error(e)
                backoff = min(MAX_BACKOFF, backoff * 2)
                stop.wait(backoff)
                continue
            stop.wait(max(0.0, self.interval - (time.monotonic() - started)))

    def _error(self, e):
        self.errors += 1
        if self.errors <= 3 or self.errors % 20 == 0:
            log(f"{self.pref}: 取得失敗({self.errors}) {e}")
        if self.errors == ERROR_NOTIFY_AFTER and not self.in_error:
            self.in_error = True
            self.recorder.write(self.pref, "取得失敗", str(e), self.url)
            self.notifier.send(f"JTB {self.pref} 監視できていません",
                               f"{self.errors}回連続で取得失敗: {e}\nブロックされている可能性があります",
                               self.url, 4)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="JTBクーポンページ変化監視")
    ap.add_argument("--ntfy", help="ntfy のトピック名（スマホアプリで同じ名前を購読）")
    ap.add_argument("--ntfy-server", default="https://ntfy.sh")
    ap.add_argument("--discord", help="Discord Webhook URL（任意）")
    ap.add_argument("--out", default="jtb_log", help="記録の保存先フォルダ")
    ap.add_argument("--interval", type=float, default=1.0, help="各ページの取得間隔(秒)")
    ap.add_argument("--only", nargs="+", help="監視する県を絞る（例: --only 熊本 長崎）")
    ap.add_argument("--test", action="store_true", help="通知テストして終了")
    ap.add_argument("--inspect", action="store_true", help="取得結果を表示して終了")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    targets = {k: v for k, v in TARGETS.items() if not args.only or k in args.only}
    notifier = Notifier(args.ntfy, args.ntfy_server, args.discord)

    if args.test:
        notifier.send("JTB監視テスト", "この通知が届けば設定OKです", next(iter(TARGETS.values())), 4)
        return

    if args.inspect:
        for pref, url in targets.items():
            w = Watcher(pref, url, args.interval, notifier, None)
            try:
                w.fetch()
                lines = list(w.raw.values())
            except Exception as e:
                print(f"\n===== {pref}: 取得失敗 {e}")
                continue
            print(f"\n===== {pref} ({len(lines)}行) {url}")
            for s in lines:
                print("  " + s)
        return

    if not args.ntfy and not args.discord:
        log("注意: 通知先が未設定です（--ntfy か --discord）。画面表示と記録のみ行います")

    recorder = Recorder(args.out)
    stop = threading.Event()
    watchers = [Watcher(p, u, args.interval, notifier, recorder) for p, u in targets.items()]
    threads = []
    for i, w in enumerate(watchers):
        th = threading.Thread(target=w.run, args=(stop,), daemon=True)
        th.start()
        threads.append(th)
        time.sleep(args.interval / max(1, len(watchers)))  # 同時アクセスを避けてずらす
    log(f"{len(watchers)}ページを{args.interval:g}秒おきに監視中 / 記録先: {os.path.abspath(args.out)}")
    notifier.send("JTB監視を開始しました", "、".join(targets), priority=2)

    try:
        while True:
            time.sleep(HEARTBEAT_SEC)
            log("稼働中: " + " / ".join(
                f"{w.pref} {'失敗中' if w.in_error else ('準備中' if w.lines is None else f'{w.checks}回')}"
                for w in watchers))
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        log("監視を停止しました")
        notifier.send("JTB監視が停止しました", "再開するにはセルを実行し直してください", priority=3)


if __name__ == "__main__":
    main()
