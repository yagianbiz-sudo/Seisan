"""相場データの取得と指標計算。標準ライブラリのみ。

取得元（どれも非公式・無料の公開エンドポイントなので、仕様が変わったら直す）:
  - 株価: Yahoo Finance chart API
  - Fear & Greed: CNN dataviz
  - 日経VI: 日経平均プロファイルのページ（取れなければ --nvi で手入力）
"""
import json
import re
import urllib.request
from dataclasses import dataclass, field

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def http_get(url, timeout=20, accept="*/*"):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": accept, "Accept-Language": "ja,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode(r.headers.get_content_charset() or "utf-8", "replace")


# ---------- 指標計算（純粋関数。テスト対象） ----------

def sma(values, n):
    if len(values) < n:
        return None
    return sum(values[-n:]) / n


def rsi(values, n=14):
    """Wilder の RSI。"""
    if len(values) < n + 1:
        return None
    gains, losses = [], []
    for a, b in zip(values[:-1], values[1:]):
        d = b - a
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[:n]) / n
    avg_l = sum(losses[:n]) / n
    for g, l in zip(gains[n:], losses[n:]):
        avg_g = (avg_g * (n - 1) + g) / n
        avg_l = (avg_l * (n - 1) + l) / n
    if avg_l == 0:
        return 100.0
    return 100.0 - 100.0 / (1.0 + avg_g / avg_l)


def pct(a, b):
    return (a / b - 1.0) * 100.0 if b else None


@dataclass
class StockSnapshot:
    code: str
    closes: list
    volumes: list = field(default_factory=list)

    @property
    def last(self):
        return self.closes[-1]

    @property
    def change_1d(self):
        return pct(self.closes[-1], self.closes[-2]) if len(self.closes) >= 2 else None

    @property
    def drawdown_20d(self):
        """20日高値からの下落率(%)。"""
        if len(self.closes) < 20:
            return None
        return pct(self.last, max(self.closes[-20:]))

    @property
    def ma25_dev(self):
        m = sma(self.closes, 25)
        return pct(self.last, m) if m else None

    @property
    def ma75_dev(self):
        m = sma(self.closes, 75)
        return pct(self.last, m) if m else None

    @property
    def rsi14(self):
        return rsi(self.closes, 14)

    @property
    def volume_ratio(self):
        """直近出来高 / 20日平均。"""
        if len(self.volumes) < 21:
            return None
        avg = sum(self.volumes[-21:-1]) / 20
        return self.volumes[-1] / avg if avg else None

    def to_dict(self):
        r = lambda x: None if x is None else round(x, 2)
        return {
            "code": self.code, "last": r(self.last), "chg1d%": r(self.change_1d),
            "dd20d%": r(self.drawdown_20d), "ma25dev%": r(self.ma25_dev),
            "ma75dev%": r(self.ma75_dev), "rsi14": r(self.rsi14),
            "vol_ratio": r(self.volume_ratio),
        }


# ---------- 取得 ----------

def yahoo_symbol(code):
    return code if (code.startswith("^") or "." in code) else f"{code}.T"


def fetch_daily(code, range_="6mo"):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{yahoo_symbol(code)}"
           f"?range={range_}&interval=1d")
    res = json.loads(http_get(url, accept="application/json"))["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = [(c, v or 0) for c, v in zip(q["close"], q["volume"]) if c is not None]
    if len(rows) < 2:
        raise ValueError(f"{code}: 価格データが足りない")
    return StockSnapshot(code, [c for c, _ in rows], [v for _, v in rows])


def fetch_fear_greed():
    """CNN Fear & Greed Index。戻り値 {'score': float, 'rating': str}。"""
    data = json.loads(http_get(
        "https://production.dataviz.cnn.io/index/fearandgreed/graphdata",
        accept="application/json"))
    fg = data["fear_and_greed"]
    return {"score": round(float(fg["score"]), 1), "rating": fg.get("rating")}


def fetch_nikkei_vi():
    html = http_get("https://indexes.nikkei.co.jp/nkave/index/profile?idx=nk225vi")
    for pat in (r'id="price"[^>]*>\s*([\d,]+\.\d+)',
                r'現在値[^0-9]{0,200}?([\d,]+\.\d+)'):
        m = re.search(pat, html, re.S)
        if m:
            return float(m.group(1).replace(",", ""))
    raise ValueError("日経VIをページから読み取れなかった")
