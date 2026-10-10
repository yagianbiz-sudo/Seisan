"""ナレッジのルールを機械判定する部分。AI に考えさせる前の「下ごしらえ」。

AI はここの判定結果を出発点にして推論する。数値の閾値は config.py にまとめてある。
"""
import csv
from dataclasses import dataclass, field

from . import config as C


# ---------- 地合い（5-4） ----------

REGIMES = {
    "panic": "暴落（5-3: F&G 20未満と日経VI 50超がそろった、または日経VI 60超。大型優良株をまとめて買う日。ただし初動で買い増しすぎない＝ケース7）",
    "fear": "恐怖（片方だけ恐怖。資金の一部で少しずつ。本命はそろってから）",
    "neutral": "平常（暴落待ち。テーマ株は資金が入っているものだけ。基本は待つ）",
    "greed": "過熱（5-5: F&G 80超は売り。新規は買わず、現物を落として先物で残る）",
}


def classify_regime(fg=None, nvi=None, vix=None):
    """恐怖指数から地合いを判定（ナレッジ5-3）。どれも取れなければ None。"""
    if fg is None and nvi is None and vix is None:
        return None
    fg_fear = fg is not None and fg < C.FG_EXTREME_FEAR
    if (fg_fear and nvi is not None and nvi >= C.NVI_CRASH) or (nvi is not None and nvi >= C.NVI_EXTREME):
        return "panic"
    if ((fg is not None and fg < C.FG_FEAR) or (nvi is not None and nvi >= C.NVI_FEAR)
            or (vix is not None and vix >= C.VIX_FEAR)):
        return "fear"
    if fg is not None and fg > C.FG_SELL:
        return "greed"
    return "neutral"


# ---------- ユニバース（5-2） ----------

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


# ---------- 個別株の買い候補（5-2〜5-4） ----------

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
            target = last / (1 + ma25_dev / 100)  # 25日線まで戻る想定（5-5）
        return {
            "entry": round(last, 1),
            "stop": round(last * (1 + C.STOP_LOSS_PCT / 100), 1),  # 5-5
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
        c.signals.append(f"20日高値から{dd:.1f}%（5-4・STEP4）")
        c.score += 2
    if dev is not None and dev <= C.MA25_DEVIATION:
        c.signals.append(f"25日線乖離{dev:.1f}%（5-4・STEP4）")
        c.score += 2
    if r is not None and r <= C.RSI_OVERSOLD:
        c.signals.append(f"RSI14={r:.0f}（5-4・STEP4）")
        c.score += 1.5
    oversold = bool(c.signals)
    if stock.leader:
        c.signals.append("業界1位（5-3）")
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


# ---------- 保有ポジションの売り判定（5-5） ----------

def check_position(pos, snap, regime):
    """pos: {'code','entry','shares','wallet'('attack'|'defense')}。"""
    pnl = (snap.last / pos["entry"] - 1) * 100
    actions = []
    if pnl <= C.STOP_LOSS_PCT:
        actions.append(f"損切り: 買値から{pnl:.1f}%（5-5: −10%で機械的に切る）")
    if pos.get("wallet", "attack") == "attack" and pnl > 0:
        dev = snap.ma25_dev
        if dev is not None and dev >= 0:
            actions.append("利確検討: 25日線まで戻した（5-5）")
        if regime == "greed":
            actions.append("利確検討: 地合いが強欲に転じた（5-5）")
    return {"code": pos["code"], "entry": pos["entry"], "last": round(snap.last, 1),
            "pnl%": round(pnl, 2), "wallet": pos.get("wallet", "attack"),
            "actions": actions or ["保有継続"]}
