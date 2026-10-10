"""ちょる子式トレード推論ツール。

使い方（リポジトリ直下で）:
    python -m choruko collect                 # ちょる子関連の記事を集めて蓄積
    python -m choruko note "Xの投稿本文" --url https://x.com/kabu_st0ck/status/... --kind x
    python -m choruko distill                 # 集めた情報から新しい学びを learned.md に追記（AI）
    python -m choruko screen                  # ルールだけで地合いと逆張り候補を判定（AIなし）
    python -m choruko suggest                 # 今日の「ちょる子ならこうする」レポート（AI）
    python -m choruko pos add 8035 38000 100 --wallet attack
    python -m choruko pos list / pos rm 8035

日経VIが自動で取れないときは --nvi 31.5 のように手で渡す。
"""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import date

from . import collector, config as C, market, rules


def log(msg):
    print(msg, file=sys.stderr, flush=True)


def _try(label, fn):
    try:
        return fn()
    except Exception as e:  # 1つ取れなくても全体は止めない
        log(f"  ! {label} の取得に失敗: {e}")
        return None


def gather_market(nvi=None, fg=None):
    log("相場データを取得中…")
    fg_data = {"score": fg, "rating": "manual"} if fg is not None else _try("Fear & Greed", market.fetch_fear_greed)
    if nvi is None:
        nvi = _try("日経VI（--nvi で手入力可）", market.fetch_nikkei_vi)
    vix = _try("VIX", lambda: market.fetch_daily("^VIX"))
    n225 = _try("日経平均", lambda: market.fetch_daily("^N225"))

    universe = rules.load_universe()
    with ThreadPoolExecutor(max_workers=8) as ex:
        snaps = list(ex.map(lambda s: (s, _try(s.code, lambda: market.fetch_daily(s.code))), universe))

    fg_score = fg_data["score"] if fg_data else None
    vix_last = vix.last if vix else None
    regime = rules.classify_regime(fg_score, nvi, vix_last)
    summary = {
        "fear_greed": fg_data,
        "nikkei_vi": nvi,
        "vix": round(vix_last, 2) if vix_last else None,
        "nikkei225": n225.to_dict() if n225 else None,
        "regime": regime,
        "regime_note": rules.REGIMES.get(regime, "恐怖指数が取れず判定できない"),
        "current_themes": C.CURRENT_THEMES,
    }
    cands = [rules.evaluate(s, snap) for s, snap in snaps if snap]
    return summary, cands, {s.code: snap for s, snap in snaps if snap}, regime


def load_positions():
    if not C.POSITIONS_JSON.exists():
        return []
    return json.loads(C.POSITIONS_JSON.read_text(encoding="utf-8"))


def save_positions(ps):
    C.POSITIONS_JSON.write_text(json.dumps(ps, ensure_ascii=False, indent=1), encoding="utf-8")


def check_positions(snaps, regime):
    out = []
    for p in load_positions():
        snap = snaps.get(p["code"]) or _try(p["code"], lambda: market.fetch_daily(p["code"]))
        if snap:
            out.append(rules.check_position(p, snap, regime))
    return out


def print_screen(summary, top, pos_checks):
    print("## 地合い")
    print(json.dumps(summary, ensure_ascii=False, indent=1))
    print("\n## ルール上の逆張り候補（スコア順）")
    if not top:
        print("該当なし（安くなっている大型株がない＝待つ日）")
    for c in top:
        d = c.to_dict()
        print(f"- {d['code']} {d['name']}  score={d['score']}  終値{d['plan']['entry']} "
              f"損切り{d['plan']['stop']} 目標(25日線){d['plan']['target_ma25']}")
        print(f"    {' / '.join(d['signals'])}")
    if pos_checks:
        print("\n## 保有ポジション")
        for p in pos_checks:
            print(f"- {p['code']} 買値{p['entry']} → {p['last']} ({p['pnl%']}%) : {' / '.join(p['actions'])}")


def cmd_collect(a):
    added, total = collector.collect_news()
    print(f"{total}件見つかり、新規{added}件を {C.SOURCES_JSONL} に追加")


def cmd_note(a):
    n = collector.add_note(a.text, url=a.url, kind=a.kind, date=a.date)
    print("追加しました" if n else "同じものが既にあります")


def cmd_distill(a):
    from . import advisor
    done = set(json.loads(advisor.DISTILLED_JSON.read_text())) if advisor.DISTILLED_JSON.exists() else set()
    todo = [s for s in collector.load_sources() if s["id"] not in done]
    if not todo:
        print("新しく学ぶ情報はありません（先に collect / note を）")
        return
    log(f"{len(todo)}件を読み込ませています…")
    notes = advisor.distill(todo)
    with open(advisor.LEARNED_MD, "a", encoding="utf-8") as f:
        f.write(f"\n### {date.today()} 追記（{len(todo)}件から）\n{notes.strip()}\n")
    advisor.DISTILLED_JSON.write_text(json.dumps(sorted(done | {s['id'] for s in todo})))
    print(notes)
    print(f"\n→ {advisor.LEARNED_MD} に追記しました。内容を確認して、確かなものは playbook.md に昇格させてください。")


def cmd_screen(a):
    summary, cands, snaps, regime = gather_market(a.nvi, a.fg)
    print_screen(summary, rules.rank(cands, a.top), check_positions(snaps, regime))


def cmd_suggest(a):
    summary, cands, snaps, regime = gather_market(a.nvi, a.fg)
    top = rules.rank(cands, a.top)
    pos_checks = check_positions(snaps, regime)
    if a.no_ai:
        print_screen(summary, top, pos_checks)
        return
    from . import advisor
    log("Claude が推論中…（web検索ありだと数分かかることがあります）")
    today = date.today().isoformat()
    report = advisor.suggest(today, summary, [c.to_dict() for c in top], pos_checks,
                             collector.recent(a.sources), web=not a.no_web)
    C.REPORTS_DIR.mkdir(exist_ok=True)
    path = C.REPORTS_DIR / f"{today}.md"
    header = (f"# ちょる子式 推論レポート {today}\n\n"
              "> 公開情報から再構成したルールを今日の相場に当てはめた**推定**です。"
              "本人の実際の売買ではなく、投資助言でもありません。最終判断はご自身で。\n\n")
    path.write_text(header + report, encoding="utf-8")
    print(header + report)
    log(f"\n保存: {path}")


def cmd_pos(a):
    ps = load_positions()
    if a.action == "add":
        ps = [p for p in ps if p["code"] != a.code] + [{
            "code": a.code, "entry": a.entry, "shares": a.shares,
            "wallet": a.wallet, "date": date.today().isoformat()}]
        save_positions(ps)
    elif a.action == "rm":
        save_positions([p for p in ps if p["code"] != a.code])
    for p in load_positions():
        print(f"{p['code']}  買値{p['entry']}  {p['shares']}株  {p['wallet']}  ({p['date']})")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m choruko", description="ちょる子式トレード推論")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("collect", help="関連記事を集める").set_defaults(fn=cmd_collect)

    p = sub.add_parser("note", help="X投稿やメモを手で記録")
    p.add_argument("text")
    p.add_argument("--url", default="")
    p.add_argument("--kind", default="note", choices=["x", "note", "seminar", "book", "news"])
    p.add_argument("--date", help="発言日 (YYYY-MM-DD)")
    p.set_defaults(fn=cmd_note)

    sub.add_parser("distill", help="集めた情報から学びを抽出（AI）").set_defaults(fn=cmd_distill)

    for name, fn in (("screen", cmd_screen), ("suggest", cmd_suggest)):
        p = sub.add_parser(name)
        p.add_argument("--nvi", type=float, help="日経VIを手入力")
        p.add_argument("--fg", type=float, help="Fear&Greedを手入力")
        p.add_argument("--top", type=int, default=10)
        if name == "suggest":
            p.add_argument("--no-web", action="store_true", help="本人の最新発言をweb検索しない")
            p.add_argument("--no-ai", action="store_true", help="AIを呼ばずルール判定だけ")
            p.add_argument("--sources", type=int, default=30, help="AIに渡す蓄積情報の件数")
        p.set_defaults(fn=fn)

    p = sub.add_parser("pos", help="自分の保有ポジション")
    p.add_argument("action", choices=["add", "rm", "list"])
    p.add_argument("code", nargs="?")
    p.add_argument("entry", nargs="?", type=float)
    p.add_argument("shares", nargs="?", type=int)
    p.add_argument("--wallet", default="attack", choices=["attack", "defense"])
    p.set_defaults(fn=cmd_pos)

    a = ap.parse_args(argv)
    if a.cmd == "pos" and a.action == "add" and None in (a.code, a.entry, a.shares):
        ap.error("pos add CODE ENTRY SHARES")
    if a.cmd == "pos" and a.action == "rm" and not a.code:
        ap.error("pos rm CODE")
    a.fn(a)


if __name__ == "__main__":
    main()
