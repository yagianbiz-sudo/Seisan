# ちょる子ナレッジ & トレード推論ツール

個人投資家ちょる子（[@kabu_st0ck](https://x.com/kabu_st0ck)）の手法・考え方・発言・売買事例を集めたナレッジベースと、
それを使って「ちょる子ならどうするか」を AI に考えさせるための道具一式です。

> ⚠️ AI が出すのは、公開情報から考え方を推定したものです。本人の実際の売買ではありませんし、投資助言でもありません。
> 本人も1日に数千万円の損失を出しています。集中投資と信用レバレッジで大きく増やした手法で、再現性は高くありません。

## 中身

| ファイル | 役割 |
|---|---|
| `knowledge/choruko_principles.md` | **原理**。具体ルールを「なぜそうするのか」まで抽象化したもの。需給を読む7つのレンズ、酒田五法などチャートの需給的な読み方、意思決定の型、局面別の行動表、反例 |
| `knowledge/choruko_kb.md` | **ナレッジ本体**。年表、哲学、ルール（資金管理・銘柄選び・恐怖指数・チャート・利確・損切り・先物・季節性）、ケース16件、注目銘柄、判断フロー、直近の構え。YouTube 202本の字幕と記事約40本から作成 |
| `knowledge/choruko_videolog.md` | **出演動画ログ**。193本分の日付別の相場観、売買の記録、銘柄への見方、引用つきの考え方 |
| `knowledge/watchlist.md` | **日々の監視銘柄群**。本人が名前を出した銘柄を6つの層（計器・本命・日経3・AI基盤・サブテーマ・守り・指数）に分けた監視リストと毎日の見方。一覧は `data/universe.csv` |
| `knowledge/persona_prompt.md` | **AI への指示文**と、毎日の相談テンプレ |
| `knowledge/learned.md` | （任意）新しく集めた情報の追記先 |

## API なしでチャットで使う（おすすめ）

1. claude.ai でプロジェクトを作り、`persona_prompt.md` の「指示文」をプロジェクトの指示に貼る
2. `choruko_principles.md`・`choruko_kb.md`・`choruko_videolog.md` をプロジェクトのナレッジにアップロードする
3. そのプロジェクトでチャットを始め、相談テンプレに今日の数字を埋めて送る

今日の数字は、次のコマンドでテンプレに入れた状態で出せます（Python だけで動き、API キーは不要です）。

```bash
python -m choruko prompt          # Fear&Greed・日経VI・日経平均・ルールで拾った逆張り候補・保有の損切り判定を文面にする
python -m choruko prompt --nvi 31.5   # 日経VIが自動で取れないときは手入力
python -m choruko pos add 8035 38000 100   # 保有を登録すると損切り・利確の判定も入る
```

出力は `reports/prompt-YYYY-MM-DD.md` にも保存されます。それをチャットに貼ってください。

## 出演動画の字幕を100本集める

お手元のPCで実行します（`pip install yt-dlp`）。字幕は YouTube の自動生成なので誤字はありますが、話の中身は十分に読めます。

```bash
python -m choruko yt discover             # 出演動画を探す（検索20パターン＋田端大学・松井証券・ブルーモ証券・ReHacQ・PIVOT のチャンネル）
python -m choruko yt fetch --limit 100    # 字幕を knowledge/transcripts/ に保存（途中で止めても続きから再開）
python -m choruko yt bundle               # 約40万字ずつにまとめて knowledge/transcripts_bundle/ に出力
python -m choruko yt add https://www.youtube.com/watch?v=...   # 見つからなかった動画を手で追加
```

- 一覧は `data/videos.json` です。確認済みの44本（田端大学の日曜ライブ、テスタの魔法株学校、ちょる子の投資教室、ReHacQ など）が最初から入っています。
- 「ボットではないことを確認」と出て止まるときは、`--browser chrome`（または edge / firefox）を付けてください。ブラウザのログイン情報を使って取得します。
- 取り終わったら、`git add choruko/knowledge/transcripts choruko/data/videos.json && git commit -m "Add transcripts" && git push` を実行してください。push 後に Claude Code へ「字幕をナレッジに統合して」と頼めば、ナレッジに統合されます。
- `transcripts_bundle/` のファイルは、そのまま claude.ai のプロジェクトのナレッジに追加することもできます。

## ナレッジを育てる

- YouTube の動画ページで「文字起こしを表示」から全文をコピーし、チャットに貼って「ちょる子ナレッジに統合して」と頼む
- X の投稿や新しい記事も同じやり方で追加できます
- `choruko_kb.md` の末尾に、優先して埋めたい未確認点の一覧があります
- ツールで記録する場合: `python -m choruko collect`（ニュースを自動収集）、`python -m choruko note "本文" --url URL --kind x`

## API を使う場合（任意）

`ANTHROPIC_API_KEY` を設定すると、次のコマンドが使えます（従量課金）。

- `python -m choruko suggest`: レポートを自動生成
- `python -m choruko distill`: 集めた情報から学びを抽出

## テスト

```bash
python -m unittest discover -s choruko/tests -t .
```
