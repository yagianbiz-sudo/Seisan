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

# 今年のテーマ（ナレッジ5-2・7章）。年が変わったら / 発言が出たら更新する。
CURRENT_THEMES = ["AI・半導体", "建設", "メガバンク", "内需"]

# --- 恐怖指数（ナレッジ5-3。動画での本人の基準） ---
FG_EXTREME_FEAR = 20     # Fear & Greed がこれ未満＝買いサイン
FG_FEAR = 25             # 25未満を Extreme Fear と説明している
FG_SELL = 80             # 80超で売る（25-12）
NVI_CRASH = 50           # F&G 20未満とそろえば暴落＝買い（26-05〜09）
NVI_EXTREME = 60         # 単独でも買い（26-03〜04、26-09）
NVI_FEAR = 30            # 30〜32超で大型優良株（25-11〜26-01）
VIX_FEAR = 30            # 本人は使っていない。補助（確度C）

# --- 個別株の「安いとき」（確度C） ---
DRAWDOWN_FROM_20D_HIGH = -8.0   # %
MA25_DEVIATION = -5.0           # %
RSI_OVERSOLD = 35.0

# --- エグジット ---
STOP_LOSS_PCT = -10.0           # ナレッジ5-5（確度A）
