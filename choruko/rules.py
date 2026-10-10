"""プレイブックのルールを機械判定する部分。AI に渡す前の「下ごしらえ」。

AI はここの判定結果を出発点にして推論する。数値の閾値は config.py にまとめてある。
"""
import csv
from dataclasses import dataclass, field

from . import config as C


# ---------- 地合い（E1〜E4） ----------

REGIMES = {
    "panic": "パニック（E1/E3: 悲観の極み。逆張り買いの本命局面。ただし初動は分割で入る＝X3）",
    "fear": "恐怖（打診買いを始める局面。本命は分割の2回目以降）",
    "neutral": "中立（指数より個別の押し目だけを拾う。基本は待つ）",
    "greed": "強欲（新規の逆張りは見送り。攻めの財布は利確を検討）",
}


def classify_regime(fg=None, nvi=None, vix=None):
    """恐怖指数から地合いを判定。どれも取れなければ None。"""
    if fg is None and nvi is None and vix is None:
        return None
    if (fg is not None and fg < C.FG_EXTREME_FEAR) or (nvi is not None and nvi >= C.NVI_PANIC):
        return "panic"
    if ((fg is not None and fg < C.FG_FEAR) or (nvi is not None and nvi >= C.NVI_FEAR)
            or (vix is not None and vix >= C.VIX_FEAR)):
        return "fear"
    if fg is not None and fg >= C.FG_GREED and (nvi is None or nvi <= C.NVI_CALM):
        return "greed"
    return "neutral"


# ---------- ユニバース（U1） ----------

@dataclass
class Stock:
    code: str
    name: str
    sector: str
    leader: bool
    themes: list


def load_universe(path=None):
    with open(path or C.UNIVERSE_CSV, encoding="utf-8") as f:
        return [Stock(r["code"], r["name"], r["sector"], r["leader"] == "1",
                      [t for t in r["themes"].split(";") if t])
                for r in csv.DictReader(f)]


# ---------- 個別株の買い候補（E5 + 選定フロー） ----------

@dataclass
class Candidate:
    stock: Stock
    snap: object
    signals: list = field(default_factory=list)
    score: float = 0.0

    def plan(self):
        last = self.snap.last
        target = None
        ma25_dev = self.snap.ma25_dev
        if ma25_dev is not None and ma25_dev < 0:
            target = last / (1 + ma25_dev / 100)  # 25日線まで戻る想定（X4）
        return {
            "entry": round(last, 1),
            "stop": round(last * (1 + C.STOP_LOSS_PCT / 100), 1),  # X1
            "target_ma25": round(target, 1) if target else None,
        }

    def to_dict(self):
        return {"code": self.stock.code, "name": self.stock.name,
                "sector": self.stock.sector, "leader": self.stock.leader,
                "themes": self.stock.themes, "score": round(self.score, 1),
                "signals": self.signals, "metrics": self.snap.to_dict(),
                "plan": self.plan()}


def evaluate(stock, snap, themes=None):
    themes = C.CURRENT_THEMES if themes is None else themes
    c = Candidate(stock, snap)
    dd, dev, r = snap.drawdown_20d, snap.ma25_dev, snap.rsi14
    if dd is not None and dd <= C.DRAWDOWN_FROM_20D_HIGH:
        c.signals.append(f"20日高値から{dd:.1f}%（E5）")
        c.score += 2
    if dev is not None and dev <= C.MA25_DEVIATION:
        c.signals.append(f"25日線乖離{dev:.1f}%（E5）")
        c.score += 2
    if r is not None and r <= C.RSI_OVERSOLD:
        c.signals.append(f"RSI14={r:.0f}（E5）")
        c.score += 1.5
    oversold = bool(c.signals)
    if stock.leader:
        c.signals.append("業界1位（選定フロー4）")
        c.score += 1
    hit = [t for t in stock.themes if t in themes]
    if hit:
        c.signals.append(f"今年のテーマ: {'/'.join(hit)}")
        c.score += 1
    if not oversold:
        c.score = 0  # 安くなっていなければ逆張り候補ではない
    return c


def rank(candidates, top=10):
    return sorted((c for c in candidates if c.score > 0),
                  key=lambda c: c.score, reverse=True)[:top]


# ---------- 保有ポジションの売り判定（X1, X4） ----------

def check_position(pos, snap, regime):
    """pos: {'code','entry','shares','wallet'('attack'|'defense')}。"""
    pnl = (snap.last / pos["entry"] - 1) * 100
    actions = []
    if pnl <= C.STOP_LOSS_PCT:
        actions.append(f"損切り: 買値から{pnl:.1f}%（X1: −10%で機械的に切る）")
    if pos.get("wallet", "attack") == "attack" and pnl > 0:
        dev = snap.ma25_dev
        if dev is not None and dev >= 0:
            actions.append("利確検討: 25日線まで戻した（X4）")
        if regime == "greed":
            actions.append("利確検討: 地合いが強欲に転じた（X4）")
    return {"code": pos["code"], "entry": pos["entry"], "last": round(snap.last, 1),
            "pnl%": round(pnl, 2), "wallet": pos.get("wallet", "attack"),
            "actions": actions or ["保有継続"]}
