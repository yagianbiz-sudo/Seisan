"""調整用パラメータ。確度C（推定）の数値はここに集め、検証しながら書き換える。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
KNOWLEDGE_DIR = ROOT / "knowledge"
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
UNIVERSE_CSV = DATA_DIR / "universe.csv"
SOURCES_JSONL = DATA_DIR / "sources.jsonl"   # 集めた記事・投稿の蓄積
POSITIONS_JSON = DATA_DIR / "positions.json"  # 自分の保有（売りシグナル判定に使う）

MODEL = "claude-opus-5-5"

# 今年のテーマ（ナレッジ5-3・7章）。年が変わったら / 発言が出たら更新する。
CURRENT_THEMES = ["AI・半導体", "建設", "メガバンク", "内需"]

# --- 恐怖指数（ナレッジ5-4） ---
FG_EXTREME_FEAR = 20     # Fear & Greed がこれ未満で「極度の恐怖」= 買い場（ナレッジ5-4, 確度A）
FG_FEAR = 35
FG_GREED = 65            # これ以上は過熱。新規の逆張り買いは控える（確度C）
NVI_PANIC = 40           # 日経VI（確度C：一般的な目安）
NVI_FEAR = 28
NVI_CALM = 22
VIX_FEAR = 30

# --- 個別株の「安いとき」（確度C） ---
DRAWDOWN_FROM_20D_HIGH = -8.0   # %
MA25_DEVIATION = -5.0           # %
RSI_OVERSOLD = 35.0

# --- エグジット ---
STOP_LOSS_PCT = -10.0           # ナレッジ5-5（確度A）
