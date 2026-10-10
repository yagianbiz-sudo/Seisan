# ちょる子式トレード推論ツール

個人投資家ちょる子（[@kabu_st0ck](https://x.com/kabu_st0ck)）が公開インタビューや著書で語った手法をルール化して蓄積し、
「このルールで今日の相場に臨んだら、ちょる子は何をするか」を AI（Claude）に推論させるツールです。

> ⚠️ 出てくるのは**ルールを当てはめた推定**です。本人の実際の売買ではありませんし、投資助言でもありません。
> 本人も1日に数千万円の損失を出しています。レバレッジと集中投資で大きく増やした手法なので、そのままの再現性は低いです。

## 仕組み

```
 [1] 蓄積                [2] ルール判定（AIなし）          [3] AI推論
 knowledge/playbook.md ─┐  恐怖指数(F&G・日経VI・VIX) → 地合い ┐
 knowledge/learned.md  ─┤  時価総額1兆円超の大型株 → 逆張り候補 ├→ Claude（+本人の最新発言をweb検索）
 data/sources.jsonl    ─┘  自分の保有 → 損切り(−10%)/利確      ┘   → reports/YYYY-MM-DD.md
   ↑ collect（ニュース自動収集） / note（X投稿を手入力） / distill（AIが新しい学びを抽出）
```

- `knowledge/playbook.md` … 手法の本体。ルールごとに ID（E1, X1…）、出典、確度（A=本人発言、B=二次情報、C=推定）を付けています
- `config.py` … 確度Cの閾値（どこまで下げたら「安い」とみなすか、など）と、今年のテーマ
- `data/universe.csv` … 監視する大型株と、業界1位かどうか・テーマのタグ（時価総額は年1回くらい見直す）

## セットアップ

```bash
pip install -r choruko/requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...      # Windows は set / $env:
```

## 毎日の使い方（リポジトリ直下で実行）

```bash
python -m choruko collect          # 関連ニュースを集める
python -m choruko suggest          # 今日のレポート（AI + 本人の最新発言をweb検索）
```

| コマンド | 内容 |
|---|---|
| `collect` | Google ニュースから「ちょる子」関連の記事を集めて `data/sources.jsonl` に蓄積 |
| `note "本文" --url URL --kind x` | X の投稿やセミナーのメモを手で記録（X は自動取得しない） |
| `distill` | 未学習の蓄積から新しい手法・発言を抽出し `knowledge/learned.md` に追記（AI）。確かなものは手で playbook に昇格させる |
| `screen` | AIを使わず、ルールだけで地合いと逆張り候補を表示 |
| `suggest [--no-web] [--no-ai]` | 「ちょる子ならこうする」レポートを `reports/` に保存 |
| `pos add 8035 38000 100 [--wallet defense]` / `pos list` / `pos rm 8035` | 自分の保有を登録すると、損切り・利確の判定が付く |

日経VIは日経のページから取得を試み、取れなければ警告を出します。そのときは `--nvi 31.5` のように手で入力してください。
Fear & Greed も `--fg` で上書きできます。

## 「勝てるか」を確かめる

1. まず数週間は `suggest` のレポートを保存するだけにして、提案が当たったかを記録する（ペーパートレード）
2. 本人が売買を公開したら `note` で記録し、`distill` で推論とのズレを learned.md に残す
3. ズレが続くルールは `config.py` の閾値か playbook を直す

## テスト

```bash
python -m unittest discover -s choruko/tests -t .
```
