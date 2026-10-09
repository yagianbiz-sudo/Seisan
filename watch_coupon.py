#!/usr/bin/env python3
"""じゃらん「九州ふっこう応援割」クーポン復活監視。

復活時に表示される文言がページに現れたら、PCにデスクトップ通知を出す。
標準ライブラリのみ。Windows / macOS / Linux 対応。

使い方:
    python watch_coupon.py              # 10秒おきに監視
    python watch_coupon.py --once       # 1回だけ判定結果を表示（動作確認用）
    python watch_coupon.py --test       # 通知のテスト
    python watch_coupon.py --interval 15
"""
import argparse
import subprocess
import sys
import time
import urllib.request
import webbrowser
from datetime import datetime

URL = "https://www.jalan.net/kyushu-shien/"

# クーポン復活時のウィンドウに出る文言。どれか1つでも含まれれば「復活」と判定。
KEYWORDS = [
    "九州ふっこう応援割クーポンで予約時最大50%OFF",
    "獲得不要で利用可能",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "ja,en;q=0.8",
}

# 連続して取得失敗したらエラー通知（ブロックされて気付かない事故を防ぐ）
ERROR_NOTIFY_AFTER = 6


def log(msg):
    print(f"[{datetime.now():%H:%M:%S}] {msg}", flush=True)


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


def find_keywords(html):
    # 全角/半角%の揺れを吸収
    text = html.replace("％", "%")
    return [k for k in KEYWORDS if k in text]


def notify(title, message):
    try:
        if sys.platform == "win32":
            ps = (
                "Add-Type -AssemblyName System.Windows.Forms;"
                "$n=New-Object System.Windows.Forms.NotifyIcon;"
                "$n.Icon=[System.Drawing.SystemIcons]::Information;"
                "$n.Visible=$true;"
                f"$n.ShowBalloonTip(10000,'{title}','{message}',"
                "[System.Windows.Forms.ToolTipIcon]::Info);"
                "Start-Sleep -Seconds 11;$n.Dispose()"
            )
            subprocess.Popen(["powershell", "-NoProfile", "-Command", ps])
            # トーストは見逃しやすいので、確実に気付けるようダイアログも出す
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command",
                 "Add-Type -AssemblyName PresentationFramework;"
                 f"[System.Windows.MessageBox]::Show('{message}','{title}')"]
            )
        elif sys.platform == "darwin":
            subprocess.Popen(
                ["osascript", "-e",
                 f'display notification "{message}" with title "{title}" sound name "Glass"']
            )
        else:
            subprocess.Popen(["notify-send", "-u", "critical", title, message])
    except Exception as e:  # 通知失敗でも監視は止めない
        log(f"通知失敗: {e}")
    print("\a", end="", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--interval", type=float, default=10.0, help="監視間隔(秒)")
    ap.add_argument("--once", action="store_true", help="1回判定して終了")
    ap.add_argument("--test", action="store_true", help="通知テストして終了")
    ap.add_argument("--url", default=URL)
    args = ap.parse_args()

    if args.test:
        notify("クーポン監視テスト", "通知が表示されれば成功です")
        return

    if args.once:
        hits = find_keywords(fetch(args.url))
        print("検知:", hits if hits else "なし（クーポン未復活）")
        return

    log(f"監視開始: {args.url} / {args.interval:g}秒おき / Ctrl+Cで停止")
    prev = None  # 前回「文言あり」だったか
    errors = 0
    while True:
        try:
            hits = find_keywords(fetch(args.url))
            errors = 0
            present = bool(hits)
            if prev is None:
                log("現在: " + ("文言あり（既に表示中の可能性。誤検知なら KEYWORDS を調整）"
                              if present else "文言なし（待機中）"))
                if present:
                    notify("クーポン監視", "開始時点で既に文言が検出されました")
            elif present and not prev:
                log(f"★復活を検知: {hits}")
                notify("九州ふっこう応援割 復活！", "クーポンが復活した可能性があります")
                webbrowser.open(args.url)
            elif prev and not present:
                log("文言が消えました（再び待機）")
            prev = present
        except Exception as e:
            errors += 1
            log(f"取得失敗({errors}): {e}")
            if errors == ERROR_NOTIFY_AFTER:
                notify("クーポン監視エラー", f"{errors}回連続で取得失敗。監視できていません")
        time.sleep(args.interval)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
