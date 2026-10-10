"""Claude に「ちょる子なら今日どうするか」を推論させる部分。"""
import json

import anthropic

from . import config as C

LEARNED_MD = C.KNOWLEDGE_DIR / "learned.md"
DISTILLED_JSON = C.DATA_DIR / "distilled.json"

SYSTEM = """\
あなたは個人投資家「ちょる子」(@kabu_st0ck) の投資手法を研究しているアナリストです。
下のプレイブック（公開インタビューから再構成したルール集）と、そこから学習したメモだけを根拠にして、
「ちょる子がこのルールで今日の相場に臨んだら何をするか」を推論します。

守ること:
- ちょる子本人の実際の売買は分かりません。出すのは「ルールを今日の相場に当てはめた推定」です。本人が「今日これを買った」かのようには書かないこと。
- どの判断にも、根拠にしたルールID（E1, X1 など）を付けること。確度Cのルールに頼る判断はそう明記すること。
- 本人が公開した最新の発言（web検索で見つかったもの）がプレイブックと食い違うときは、最新の発言を優先し、食い違いを指摘すること。
- 本人も1日に数千万円の損失を出している手法です。ユーザーの資金に当てはめるときは、レバレッジを使わない場合のサイズ感と損切りラインを必ず添えること。
- 何もしないのが正解の日は「見送り」とはっきり書くこと。無理に候補を出さないこと。

出力形式（Markdown）:
## 今日の地合い判定
## ちょる子ならこうする（推定）
  - 新規の買い / 買い増し / 売り・利確 / 損切り / 見送り を、銘柄・価格帯・根拠ルールID・確度（高/中/低）つきで
## 保有ポジションへの指示
## 本人の最新の発言・動き（見つかった場合だけ。出典URLつき）
## この推定が外れるとしたら
"""


def _system_blocks():
    playbook = (C.KNOWLEDGE_DIR / "playbook.md").read_text(encoding="utf-8")
    learned = LEARNED_MD.read_text(encoding="utf-8") if LEARNED_MD.exists() else "(まだなし)"
    text = (f"{SYSTEM}\n\n<playbook>\n{playbook}\n</playbook>\n\n"
            f"<learned_notes>\n{learned}\n</learned_notes>")
    # 知識ベースは毎回同じなのでキャッシュする
    return [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]


def _call(messages, system, tools=None, effort="high"):
    client = anthropic.Anthropic()
    kwargs = dict(
        model=C.MODEL, max_tokens=32000, system=system,
        output_config={"effort": effort},
        betas=["server-side-fallback-2026-07-01"], fallbacks="default",
    )
    if tools:
        kwargs["tools"] = tools
    # web 検索がサーバー側で長引くと pause_turn で返るので、続きを取りに行く
    for _ in range(5):
        with client.beta.messages.stream(messages=messages, **kwargs) as stream:
            resp = stream.get_final_message()
        if resp.stop_reason == "refusal":
            cat = getattr(resp.stop_details, "category", None) if resp.stop_details else None
            raise RuntimeError(f"Claude が回答を断りました（category={cat}）")
        if resp.stop_reason != "pause_turn":
            break
        messages = messages + [{"role": "assistant", "content": resp.content}]
    return "".join(b.text for b in resp.content if b.type == "text")


def suggest(today, market, candidates, positions, sources, web=True):
    payload = {
        "date": today,
        "market": market,
        "rule_screen_candidates": candidates,
        "my_positions": positions,
        "recent_sources_about_choruko": [
            {k: s.get(k) for k in ("kind", "title", "url", "published", "text")}
            for s in sources
        ],
    }
    prompt = (
        f"今日は {today} です。下のデータは、プレイブックのルールで機械的にふるいにかけた結果です。\n"
        + ("まず web 検索で、ちょる子（@kabu_st0ck）が直近1〜2週間に公開した発言・記事・"
           "注目銘柄を確認してください。見つからなければ「見つからなかった」と書いてください。\n"
           if web else "")
        + "そのうえで、ちょる子なら今日どう動くかを推論してください。\n\n"
        + "<data>\n" + json.dumps(payload, ensure_ascii=False, indent=1) + "\n</data>"
    )
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}] if web else None
    return _call([{"role": "user", "content": prompt}], _system_blocks(), tools)


DISTILL_PROMPT = """\
下は、ちょる子（@kabu_st0ck）について新しく集めた記事・投稿です。
プレイブックにまだ載っていない、または食い違う情報だけを抜き出して、learned.md に追記するメモを書いてください。

形式（Markdown の箇条書き。該当がなければ「- 新しい情報なし」とだけ書く）:
- [日付] 内容（手法 / 銘柄・テーマ / 相場観 / マインド のどれか）— 確度A/B/C — 出典URL
  - 食い違う場合は、プレイブックのどのルールIDとどう違うか

本人の発言と、記者・第三者の解釈は区別すること。推測で埋めないこと。
"""


def distill(sources):
    body = json.dumps(
        [{k: s.get(k) for k in ("kind", "title", "url", "published", "text")} for s in sources],
        ensure_ascii=False, indent=1)
    return _call(
        [{"role": "user", "content": f"{DISTILL_PROMPT}\n<sources>\n{body}\n</sources>"}],
        _system_blocks(), effort="medium")
