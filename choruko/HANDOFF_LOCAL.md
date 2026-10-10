# 引き継ぎ書：ローカルの Claude Code へ

> この文書は、クラウド上の Claude Code セッションから、ユーザーの PC で動く Claude Code への引き継ぎです。
> あなた（ローカル）に頼みたいのは、**ローカルでしかできない作業だけ**です。
> ナレッジの執筆・統合はクラウド側でやるので、ここではやらないでください。

## 1. 背景（30秒で）

- ユーザーは、個人投資家「ちょる子」（X: @kabu_st0ck）の手法を AI に覚えさせ、チャット上で「ちょる子ならどうするか」を考えさせたい。
- API は費用がかかるので使わない。claude.ai のプロジェクトに、ナレッジ（`choruko/knowledge/choruko_kb.md`）と指示文（`persona_prompt.md`）を入れて使う。
- ナレッジは、これまで Web 検索で拾った記事・動画の**見出しや要約**から作っている。クラウド環境は YouTube にも主要ニュースサイトにも接続できないため、中身は読めていない。
- **ちょる子は YouTube に大量に出演している**（毎週日曜21時の田端大学「株ライブ」、松井証券、ブルーモ証券、ReHacQ など）。その字幕を100本以上集めることが、今いちばん価値のある作業。

## 2. リポジトリ

- GitHub: `yagianbiz-sudo/seisan`、作業ブランチ: **`claude/focused-gates-it47u5`**
- まだ clone していなければ:
  ```
  git clone https://github.com/yagianbiz-sudo/seisan.git
  cd seisan
  git checkout claude/focused-gates-it47u5
  ```
- コードは `choruko/` の中にある。概要は `choruko/README.md` を参照。コマンドはすべてリポジトリ直下で `python -m choruko ...` の形で実行する。
- テスト: `python -m unittest discover -s choruko/tests -t .`（ネットに出ない。13件）

## 3. やってほしいこと（優先順）

### タスクA【最優先】YouTube 字幕を100本以上集める

クラウドでは一度も実際の YouTube で動かせていないので、**動作確認と修正もこのタスクに含まれる**。

1. `pip install yt-dlp`
2. `python -m choruko yt discover`
   - 検索20パターンと `choruko/youtube.py` の `CHANNEL_TABS`（田端大学・ブルーモ・松井証券・ReHacQ・PIVOT）から、出演動画を `choruko/data/videos.json` に追加する。最初から44本が入っている。
   - **確認:** `CHANNEL_TABS` のチャンネルハンドルは推測を含む（`@bloomo-academy`、`@MatsuiSecurities`、`@ReHacQ`、`@pivot00`）。0本しか拾えないチャンネルがあれば、正しいハンドルを調べて直す。
   - **確認:** 田端大学の日曜ライブは毎週あるので、数十本は見つかるはず。少なければ `/streams` タブが取れているかを調べる。
3. `python -m choruko yt fetch --limit 150`
   - 字幕を `choruko/knowledge/transcripts/YYYY-MM-DD_<動画ID>.md` に保存する。途中で止まっても、再実行すれば続きから再開する。
   - 「Sign in to confirm you're not a bot」や 429 エラーが出たら、`--browser chrome`（ユーザーが普段使っているブラウザ）を付ける。それでも止まるなら、`youtube.py` の `sleep` を延ばす。
   - `status=no_subs`（字幕なし）や `not_choruko`（本人不在）は正常な除外なので、気にしなくてよい。
4. `python -m choruko yt bundle`
   - `choruko/knowledge/transcripts_bundle/` に、約40万字ずつのファイルを作る。
5. **完了の条件**
   - `status=ok` が100本以上ある（`python -m choruko yt status` で確認できる）。
   - 田端大学の日曜ライブが、できるだけ全回分そろっている。

### タスクB 相場データ取得の実地確認

クラウドからはデータ取得先に接続できず、**実データでは一度も動かしていない**。

1. `python -m choruko screen` を実行し、次がすべて取れるかを確認する。
   - Fear & Greed（CNN）
   - 日経VI（日経のページを HTML から解析）
   - VIX
   - 日経平均
   - `choruko/data/universe.csv` の約50銘柄（Yahoo Finance）
2. 取れないものは `choruko/market.py` を直す。特に日経VI の解析は推測で書いた正規表現なので、失敗する可能性が高い。どうしても取れなければ別の取得元を探す。だめなら、`--nvi` での手入力に頼る旨を README に書く。
3. 銘柄コード `285A`（キオクシア）など、Yahoo で取れない銘柄がないかも確認する。
4. `python -m choruko prompt` が、数字の入った相談文を出力することを確認する。
5. 直したら、テストを足すか既存テストが通ることを確認する。

### タスクC（任意・ユーザーが望めば）記事本文の取得

クラウドからは楽天証券トウシル、ログミー、JBpress、テレ東、CREAL、note などに接続できなかった。

- `choruko_kb.md` の第10章にある記事 URL のうち**無料で読めるもの**の本文を取得して、`choruko/knowledge/articles/` にテキストで保存する。
- **やらないこと:** 有料記事やログインが必要なものは取らない。

## 4. やらないでほしいこと

- **ナレッジ（`choruko_kb.md`、`persona_prompt.md`）を書き換えない。** 字幕の読み込みと統合はクラウド側でやる。
- **`python -m choruko suggest` / `distill` は実行しない。** Anthropic API を使うので課金が発生する。
- 字幕を要約・加工しない。生のまま渡してほしい。
- `main` ブランチには push しない。

## 5. 成果物の渡し方

**まず、リポジトリが公開か非公開かを確認する**（GitHub のリポジトリページ、または `gh repo view yagianbiz-sudo/seisan --json visibility`）。

- **非公開なら:** 字幕もコードの修正も、作業ブランチに commit して push する。
  ```
  git add choruko/knowledge/transcripts choruko/knowledge/transcripts_bundle choruko/data/videos.json choruko/*.py
  git commit -m "Add YouTube transcripts and fix data fetchers"
  git push origin claude/focused-gates-it47u5
  ```
- **公開なら:** 字幕は他人の動画の書き起こしなので、**公開リポジトリには上げない**。
  - `transcripts_bundle/` のファイルをユーザーの Google ドライブ（例:「ちょる子字幕」フォルダ）に置いてもらう。
  - コードの修正だけを push する。字幕のフォルダは `.gitignore` に足す。

## 6. 終わったらユーザーに伝えること

次の内容を短くまとめて、ユーザーに伝えてください。ユーザーがそれをクラウド側のセッションに貼れば、引き継ぎが完了します。

- 字幕を取れた本数。チャンネル別の内訳と、最も古い日付・最も新しい日付
- 取れなかった動画の本数と、主な理由
- `market.py` などを直した内容と、取れなかったデータ
- 成果物の置き場所（push したブランチ、または Google ドライブのフォルダ名）
