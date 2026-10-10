# ちょる子ナレッジ & トレード推論ツール

個人投資家ちょる子（[@kabu_st0ck](https://x.com/kabu_st0ck)）の手法・考え方・発言・売買事例を集めたナレッジベースと、
それを使って「ちょる子ならどうするか」を AI に考えさせるための道具一式です。

> ⚠️ AI が出すのは、公開情報から考え方を推定したものです。本人の実際の売買ではありませんし、投資助言でもありません。
> 本人も1日に数千万円の損失を出しています。集中投資と信用レバレッジで大きく増やした手法で、再現性は高くありません。

## 中身

| ファイル | 役割 |
|---|---|
| `knowledge/choruko_kb.md` | **ナレッジ本体**。年表、哲学、ルール、ケーススタディ11件、注目銘柄の履歴、判断フロー、情報源（記事・インタビュー37件＋YouTube16本） |
| `knowledge/persona_prompt.md` | **AI への指示文**と、毎日の相談テンプレ |
| `knowledge/learned.md` | （任意）新しく集めた情報の追記先 |

## API なしでチャットで使う（おすすめ）

1. claude.ai でプロジェクトを作り、`persona_prompt.md` の「指示文」をプロジェクトの指示に貼る
2. `choruko_kb.md` をプロジェクトのナレッジにアップロードする
3. そのプロジェクトでチャットを始め、相談テンプレに今日の数字を埋めて送る

今日の数字は、次のコマンドでテンプレに入れた状態で出せます（Python だけで動き、API キーは不要です）。

```bash
python -m choruko prompt          # Fear&Greed・日経VI・日経平均・ルールで拾った逆張り候補・保有の損切り判定を文面にする
python -m choruko prompt --nvi 31.5   # 日経VIが自動で取れないときは手入力
python -m choruko pos add 8035 38000 100   # 保有を登録すると損切り・利確の判定も入る
```

出力は `reports/prompt-YYYY-MM-DD.md` にも保存されます。それをチャットに貼ってください。

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
