# おくりむかえ帳 v1（Webアプリ）

開発指示書：[../SPEC.md](../SPEC.md)

## コマンド

| コマンド | 内容 |
|---|---|
| `npm install` | 部品のインストール（最初に1回） |
| `npm run dev` | 開発用サーバー |
| `npm run lint` / `npm run typecheck` / `npm test` | 検査（各マイルストーンの完了条件） |
| `npm run build` | 本番用ビルド |

## 構成

- `src/domain/` 担当の決め方・月集計・貸し借りの純粋関数（UIとFunctionsで共用）
- `src/styles/tokens.css` 試作版の配色・フォント・ライト／ダーク
