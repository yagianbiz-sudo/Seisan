#!/usr/bin/env python3
"""JTB「九州ふっこう応援割」クーポン復活監視（Google Colab / PC 両対応）。

ページの「配布終了いたしました」は HTML には入っておらず、ページを開いた後に
KARTE（JTB が使っている外部ツール）の JavaScript が各カードに `c-close` クラスを付けて表示している。
そのため requests では検知できない。Playwright で実際の Chrome にページを開かせ、
描画後の各カードが c-close か否かを読む。
（ヘッドレス Chrome は JTB 側で 403 になるので、画面付きで起動する。Colab では xvfb の仮想画面を使う）

各県を順番に開き、前回と比べて
  - カードの配布終了 → 配布中（復活）/ 配布中 → 配布終了
  - カードの中身（枚数・割引・コード）の変更、カードの増減
  - 「更新情報」欄の変更
があったときだけ、スマホへ通知（ntfy）し、events.csv とスナップショットに記録する。

使い方:
    python jtb_watch.py --ntfy 好きなトピック名           # 監視開始
    python jtb_watch.py --ntfy 好きなトピック名 --test    # 通知テスト
    python jtb_watch.py --inspect                         # 各県のカードと状態を表示（動作確認）
    python jtb_watch.py --only 熊本 長崎 --interval 20
    python jtb_watch.py --target テスト=http://localhost:8000/fake.html   # 偽ページで試す
Colab では jtb_watch_colab.ipynb を使う。
"""
import argparse
import csv
import os
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
    "宮崎": PAGE.format("2609kyushumiyazaki"),
}

# KARTE が配布終了の印を付け終わった目印: 配布終了のカード、全部終了のときのページ側の印。
# （KARTE のコピーボタン .karte-wrapper は終了の印より先に付くので、目印には使えない）
# 印が1枚も出ないページは「全部配布中」ではなく「判定できない」として扱う
# （Colab など海外の回線では、KARTE が終了の印を付けない・遅いことがあり、全部配布中に見えてしまう）。
READY_JS = "() => document.querySelector('.c-coupon__data.c-close, .l-entry.karte-close')"
READY_TIMEOUT_MS = 15000
UNMARKED_ALERT_AFTER = 3  # 終了の印が出ない状態がこの回数続いたら、1回だけ知らせる
SETTLE_MS = 500           # 印が出始めてから、残りのカードに付き終わるまで待つ
ERROR_NOTIFY_AFTER = 5    # 連続失敗がこの回数に達したら異変として通知・記録
MAX_BACKOFF = 120         # 失敗時の待ち時間の上限(秒)
HEARTBEAT_SEC = 600       # 画面にだけ出す生存表示の間隔（記録はしない）
RESTART_EVERY = 500       # この回数ページを開いたらブラウザを開き直す（メモリ対策）


def now():
    return datetime.now(JST)


def log(msg):
    print(f"[{now():%m/%d %H:%M:%S}] {msg}", flush=True)


def _text(el):
    return " ".join(el.get_text(" ", strip=True).split()) if el else ""


def parse_page(html):
    """描画後の HTML から {"cards": [...], "updates": [...]} を作る。
    cards の各要素: section（区分見出し）, no（区分内で何枚目）, name, count, price, code, password, closed"""
    soup = BeautifulSoup(html, "html.parser")
    entry = soup.select_one(".l-entry")
    all_closed = bool(entry and "karte-close" in entry.get("class", []))
    cards = []
    sec = soup.select_one(".sec-coupon")
    if sec:
        section, no = "", 0
        # 区分見出し p.note の後ろにその区分のカードが並ぶ。文書順にたどる
        for el in sec.find_all(["p", "div"]):
            classes = el.get("class", [])
            if el.name == "p" and "note" in classes:
                section, no = _text(el), 0
            elif el.name == "div" and "c-coupon__data" in classes:
                no += 1
                labels = [_text(x) for x in el.select(".c-code .label")]
                cards.append({
                    "section": section,
                    "no": no,
                    "name": _text(el.select_one(".cnt-stay")),
                    "count": _text(el.select_one(".cnt-number")),
                    "price": _text(el.select_one(".c-price")),
                    "code": labels[0] if labels else "",
                    "password": labels[1] if len(labels) > 1 else "",
                    "closed": all_closed or "c-close" in classes,
                })
    updates = [_text(li) for li in soup.select(".c-update li")]
    # marked: 終了の印が1つでもある = KARTE が働いていて、各カードの状態を信用できる
    return {"cards": cards, "updates": updates, "marked": any(c["closed"] for c in cards)}


def card_label(c):
    return f"{c['section']} {c['no']}枚目"


def card_detail(c):
    return f"{c['name']} {c['count']} {c['price']} コード {c['code']} / パスワード {c['password']}"


def diff_pages(old, new):
    """前回と今回の parse_page 結果を比べ、[(判定, 区分, 何枚目, 内容), ...] を返す。"""
    events = []
    key = lambda c: (c["section"], c["no"])
    old_cards = {key(c): c for c in old["cards"]}
    new_cards = {key(c): c for c in new["cards"]}
    for k, c in new_cards.items():
        o = old_cards.get(k)
        if o is None:
            events.append(("カード追加", c["section"], c["no"], card_detail(c)))
            continue
        if o["closed"] and not c["closed"]:
            events.append(("復活", c["section"], c["no"], card_detail(c)))
        elif not o["closed"] and c["closed"]:
            events.append(("終了", c["section"], c["no"], card_detail(c)))
        if card_detail(o) != card_detail(c):
            events.append(("内容変更", c["section"], c["no"], f"{card_detail(o)} → {card_detail(c)}"))
    for k, o in old_cards.items():
        if k not in new_cards:
            events.append(("カード削除", o["section"], o["no"], card_detail(o)))
    added = [u for u in new["updates"] if u not in old["updates"]]
    if added:
        events.append(("更新情報", "", "", " / ".join(added)))
    return events


def open_cards(page):
    return [c for c in page["cards"] if not c["closed"]]


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
    FIELDS = ["時刻", "県", "判定", "クーポン区分", "何枚目", "クーポンの中身", "URL", "スナップショット"]

    def __init__(self, out_dir):
        self.out_dir = out_dir
        self.snap_dir = os.path.join(out_dir, "snapshots")
        os.makedirs(self.snap_dir, exist_ok=True)
        self.csv_path = os.path.join(out_dir, "events.csv")
        self.lock = threading.Lock()

    def write(self, pref, rows, url, html=None):
        """rows: [(判定, 区分, 何枚目, 中身), ...]"""
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
                for judge, section, no, detail in rows:
                    w.writerow([f"{t:%Y-%m-%d %H:%M:%S}", pref, judge, section, no, detail, url, snap])


class Browser:
    """Playwright の Chrome を1つ開き、ページを開いて描画後の HTML を返す。"""

    def __init__(self, headless=False):
        self.headless = headless
        self.pw = self.browser = self.page = None
        self.loads = 0

    def start(self):
        from playwright.sync_api import sync_playwright
        self.pw = sync_playwright().start()
        # 画面外に出して邪魔にならないようにする（Colab では xvfb の仮想画面に出る）
        self.browser = self.pw.chromium.launch(headless=self.headless, args=["--window-position=-2400,0"])
        self.page = self.browser.new_page()
        # 画像・フォント・動画は判定に要らないので読まない（軽くするため）
        self.page.route("**/*", lambda r: r.abort()
                        if r.request.resource_type in ("image", "font", "media") else r.continue_())
        self.loads = 0

    def stop(self):
        for closer in (lambda: self.browser.close(), lambda: self.pw.stop()):
            try:
                closer()
            except Exception:
                pass
        self.pw = self.browser = self.page = None

    def get(self, url):
        if self.page is None or self.loads >= RESTART_EVERY:
            self.stop()
            self.start()
        self.loads += 1
        resp = self.page.goto(url, wait_until="domcontentloaded", timeout=30000)
        if resp is None or resp.status >= 400:
            raise RuntimeError(f"HTTP {resp.status if resp else '応答なし'}")
        if self.page.url.split("?")[0] != url.split("?")[0]:
            raise RuntimeError(f"別のページに移動しました: {self.page.url}")
        try:
            self.page.wait_for_function(READY_JS, timeout=READY_TIMEOUT_MS)
            self.page.wait_for_timeout(SETTLE_MS)
        except Exception:
            pass  # 印が出なかった。判定は Watcher 側で「判定できない」として扱う
        return self.page.content()


class Watcher:
    def __init__(self, pref, url, notifier, recorder, shared=None):
        self.pref, self.url = pref, url
        self.notifier, self.recorder = notifier, recorder
        # shared["marks_seen"]: どれかの県で終了の印が読めた = この環境で KARTE が働いている
        self.shared = shared if shared is not None else {"marks_seen": False}
        self.state = None
        self.errors = 0
        self.in_error = False
        self.checks = 0
        self.unmarked = 0  # 終了の印が出ない状態が続いた回数

    def check(self, browser):
        try:
            html = browser.get(self.url)
            page = parse_page(html)
            if not page["cards"]:
                raise RuntimeError("クーポンのカードが見つかりません（ページの作りが変わった可能性）")
            if self.state is not None and page["marked"]:
                events = diff_pages(self.state, page)
                if any(e[0] == "復活" for e in events):
                    # 読み込みの途中を拾った誤検知を避けるため、もう一度開いて確かめる
                    html = browser.get(self.url)
                    page = parse_page(html)
                    events = diff_pages(self.state, page)
        except Exception as e:
            self._error(e)
            return False
        self.checks += 1
        if self.in_error:
            self.recorder.write(self.pref, [("取得復旧", "", "", "")], self.url)
            self.notifier.send(f"JTB {self.pref} 監視復旧", "再び取得できています", self.url, 3)
        self.errors, self.in_error = 0, False
        if not page["marked"]:
            self._unmarked()
            return True
        if self.unmarked:
            log(f"{self.pref}: 配布終了の表示が読めるようになりました")
        self.unmarked = 0
        self.shared["marks_seen"] = True
        if self.state is None:
            self.state = page
            opened = open_cards(page)
            log(f"{self.pref}: 監視開始（カード{len(page['cards'])}枚 / 配布中{len(opened)}枚）")
            if opened:
                rows = [("開始時に配布中", c["section"], c["no"], card_detail(c)) for c in opened]
                self.recorder.write(self.pref, rows, self.url, html)
                self._notify("配布中", rows)
            return True
        self.state = page
        if events:
            self.recorder.write(self.pref, events, self.url, html)
            judges = [e[0] for e in events]
            top = "復活" if "復活" in judges else ("終了" if "終了" in judges else "変化")
            self._notify(top, events)
        return True

    def _unmarked(self):
        """終了の印が1枚も出なかった。全カード配布中に見えるが、KARTE が働いていないだけのことが多いので、
        復活とはせず、続いたときに1回だけ知らせる。"""
        self.unmarked += 1
        if self.unmarked == 1:
            log(f"{self.pref}: 配布終了の表示が出ません（判定を保留）")
        if self.unmarked != UNMARKED_ALERT_AFTER:
            return
        if self.shared["marks_seen"]:
            title = f"【要確認】JTB {self.pref}"
            msg = (f"配布終了の表示が{self.unmarked}回続けて出ていません。"
                   "全カード配布中の可能性があります。ページで確認してください")
            priority = 4
        else:
            title = f"JTB {self.pref} 判定できません"
            msg = ("配布終了の表示が出ないため、配布中かどうか判定できません。"
                   "この環境（Colab など）では KARTE が働いていない可能性があります")
            priority = 3
        self.recorder.write(self.pref, [("判定保留", "", "", msg)], self.url)
        self.notifier.send(title, msg, self.url, priority)

    def _notify(self, top, rows):
        lines = []
        for judge, section, no, detail in rows[:10]:
            where = f"{section} {no}枚目 " if section else ""
            lines.append(f"{where}{judge} / {detail}")
        self.notifier.send(f"【{top}】JTB {self.pref}", "\n".join(lines), self.url,
                           priority=5 if top in ("復活", "配布中") else 3)

    def _error(self, e):
        self.errors += 1
        if self.errors <= 3 or self.errors % 20 == 0:
            log(f"{self.pref}: 取得失敗({self.errors}) {e}")
        if self.errors == ERROR_NOTIFY_AFTER and not self.in_error:
            self.in_error = True
            self.recorder.write(self.pref, [("取得失敗", "", "", str(e))], self.url)
            self.notifier.send(f"JTB {self.pref} 監視できていません",
                               f"{self.errors}回連続で取得失敗: {e}\nブロックされている可能性があります",
                               self.url, 4)


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="JTBクーポン復活監視")
    ap.add_argument("--ntfy", help="ntfy のトピック名（スマホアプリで同じ名前を購読）")
    ap.add_argument("--ntfy-server", default="https://ntfy.sh")
    ap.add_argument("--discord", help="Discord Webhook URL（任意）")
    ap.add_argument("--out", default="jtb_log", help="記録の保存先フォルダ")
    ap.add_argument("--interval", type=float, default=10.0, help="各県を見に行く間隔(秒)")
    ap.add_argument("--only", nargs="+", help="監視する県を絞る（例: --only 熊本 長崎）")
    ap.add_argument("--target", nargs="+", metavar="名前=URL", help="監視先を指定して置き換える（動作確認用）")
    ap.add_argument("--max-checks", type=int, default=0, help="この周回数で止める（動作確認用。0なら止めない）")
    ap.add_argument("--test", action="store_true", help="通知テストして終了")
    ap.add_argument("--inspect", action="store_true", help="各県のカードと状態を表示して終了")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    if args.target:
        targets = dict(t.split("=", 1) for t in args.target)
    else:
        targets = {k: v for k, v in TARGETS.items() if not args.only or k in args.only}
    notifier = Notifier(args.ntfy, args.ntfy_server, args.discord)

    if args.test:
        notifier.send("JTB監視テスト", "この通知が届けば設定OKです", next(iter(TARGETS.values())), 4)
        return

    browser = Browser()
    if args.inspect:
        try:
            for pref, url in targets.items():
                try:
                    page = parse_page(browser.get(url))
                except Exception as e:
                    print(f"\n===== {pref}: 取得失敗 {e}", flush=True)
                    continue
                if not page["marked"]:
                    print(f"\n===== {pref} カード{len(page['cards'])}枚 / 配布終了の表示が出ず判定できません {url}")
                    continue
                print(f"\n===== {pref} カード{len(page['cards'])}枚 / 配布中{len(open_cards(page))}枚 {url}")
                for c in page["cards"]:
                    print(f"  {'終了  ' if c['closed'] else '配布中'} {card_label(c)} {card_detail(c)}")
                for u in page["updates"]:
                    print(f"  [更新情報] {u}")
        finally:
            browser.stop()
        return

    if not args.ntfy and not args.discord:
        log("注意: 通知先が未設定です（--ntfy か --discord）。画面表示と記録のみ行います")

    recorder = Recorder(args.out)
    shared = {"marks_seen": False}
    watchers = [Watcher(p, u, notifier, recorder, shared) for p, u in targets.items()]
    log(f"{len(watchers)}県を{args.interval:g}秒おきに監視します / 記録先: {os.path.abspath(args.out)}")
    notifier.send("JTB監視を開始しました", "、".join(targets), priority=2)
    # 1周で全県を順に開く。1周が interval 秒より短ければ待つ
    gap = args.interval / max(1, len(watchers))
    last_beat = time.monotonic()
    rounds = 0
    try:
        while not args.max_checks or rounds < args.max_checks:
            for w in watchers:
                started = time.monotonic()
                ok = w.check(browser)
                if not ok:
                    browser.stop()  # 次回は開き直す
                    time.sleep(min(MAX_BACKOFF, gap * 2 ** min(w.errors, 6)))
                    continue
                time.sleep(max(0.0, gap - (time.monotonic() - started)))
            rounds += 1
            if time.monotonic() - last_beat >= HEARTBEAT_SEC:
                last_beat = time.monotonic()
                log("稼働中: " + " / ".join(
                    f"{w.pref} {'失敗中' if w.in_error else f'{w.checks}回'}" for w in watchers))
    except KeyboardInterrupt:
        pass
    finally:
        browser.stop()
        log("監視を停止しました")
        notifier.send("JTB監視が停止しました", "再開するにはもう一度実行してください", priority=3)


if __name__ == "__main__":
    main()
