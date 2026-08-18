# フリカレ監視BOT / Freecal Reader

フリカレ（freecalend.com）の**公開カレンダー**を取得し、Discord通知やChatGPT/Codexでの予定整理に利用するプロジェクトです。

## 取得方式

通常は、フリカレ自身の公開ページが利用している `/open/data` へHTTPでアクセスします。

```text
FreecalClient (auto)
├─ 1. HTTP直接取得       ← 通常はこちら
└─ 2. Selenium/Chrome    ← HTTP失敗時のフォールバック
```

`mem230522` の2026年8月を使った実環境検証では、HTTP・Seleniumの両方が30件を取得し、空白だけの表示差を除いて予定内容が一致しました。

### 主な特徴

- Chromeを起動しない軽量なHTTP取得を標準経路に採用
- HTTP取得に失敗した場合は従来のSelenium方式へ自動切替
- `230522` / `mem230522` / 公開URLを同じ入力として扱える
- `_dateYYYYMM` の月指定URLに対応
- 月指定・期間指定・複数月の取得に対応
- 同じ日に複数予定がある場合も別イベントとして解析
- 日付・時刻・予定名をJSONで返却
- ChatGPT/Codex Skill用 `skills/freecal/SKILL.md` を同梱

## JSONで予定を取得

通常は `auto` のままで構いません。

```bash
python freecal_cli.py 230522 --month 2026-08 --pretty
```

公開URLをそのまま渡すこともできます。

```bash
python freecal_cli.py https://freecalend.com/open/mem230522 --month 2026-08 --pretty
```

期間指定では、開始日は含み、終了日は含みません。

```bash
python freecal_cli.py 230522 \
  --start 2026-08-17 \
  --end 2026-09-02 \
  --pretty
```

取得方式を明示する場合:

```bash
# HTTPのみ
python freecal_cli.py 230522 --month 2026-08 --backend http --pretty

# Seleniumのみ
python freecal_cli.py 230522 --month 2026-08 --backend selenium --pretty
```

出力には、実際に使われた取得方式が `backend` として含まれます。

```json
{
  "user_id": "230522",
  "source_url": "https://freecalend.com/open/mem230522_date202608",
  "event_count": 1,
  "events": [
    {
      "date": "2026-08-17",
      "title": "予定名",
      "time": "21:00",
      "user_id": "230522",
      "all_day": false
    }
  ],
  "backend": "http"
}
```

## テスト

```bash
pip install -r requirements-dev.txt
python -m pytest -q
```

HTTPとSeleniumの実データ比較は、GitHub Actionsの `freecal-live-validation` を手動実行して確認できます。

## ファイル構成

```text
freecal_bot/
├── bot.py                       # 既存Discord BOT
├── freecal_core.py              # 共通モデル・解析 + Selenium取得
├── freecal_http.py              # 軽量HTTP取得
├── freecal_client.py            # auto/http/selenium の切替
├── freecal_cli.py               # JSON CLI
├── config.py                    # Discord設定
├── requirements.txt             # 実行依存ライブラリ
├── requirements-dev.txt         # テスト依存ライブラリ
├── tests/
│   ├── test_freecal_core.py
│   └── test_freecal_http.py
├── skills/
│   └── freecal/
│       └── SKILL.md             # ChatGPT/Codex Skill
└── scripts/                     # 検証・診断ツール
```

## ChatGPT / Codex Skill

`skills/freecal/SKILL.md` は、公開フリカレに対して次の処理を行うワークフローを定義しています。

- 月間予定を表にする
- 指定期間の予定を抽出する
- 同じ日の複数予定を分けて表示する
- 公開予定がない日を確認する
- 複数人の公開予定を比較する

予定が公開されていない日は、本人が必ず空いている日とは扱いません。

## Discord BOT

Discord BOTは既存機能を維持しています。

### 必要な環境

- Python 3.11以上
- Discord BOTトークン
- Google Chrome（既存BOTまたはSeleniumフォールバックを使用する場合）

### インストール

```bash
git clone [repository_url]
cd freecal_bot
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### BOT起動

```bash
python bot.py
```

主なコマンド:

| コマンド | 説明 |
|---|---|
| `!check` | 監視ユーザー一覧 |
| `!check [名前]` | 今日の予定を確認 |
| `!calendar [名前]` | 今後の全予定を表示 |
| `!status` | 監視状況（管理者のみ） |
| `!adduser` | ユーザー追加（管理者のみ） |
| `!removeuser` | ユーザー削除（管理者のみ） |
| `!setchannel` | 通知チャンネル設定（管理者のみ） |

## トラブルシューティング

CLIの通常取得で問題が出た場合は、まずバックエンドを分けて確認します。

```bash
python freecal_cli.py 230522 --month 2026-08 --backend http --pretty
python freecal_cli.py 230522 --month 2026-08 --backend selenium --pretty
```

- HTTPだけ失敗する場合: フリカレの内部データ取得仕様が変更された可能性があります。
- Seleniumだけ失敗する場合: Chrome/Selenium環境を確認してください。
- 両方失敗する場合: 公開URL、公開範囲、フリカレ側の障害を確認してください。

## セキュリティ

- 公開カレンダーのみを対象にします。
- 非公開情報や認証が必要なカレンダーを迂回して取得しません。
- Discord BOTトークンをGitへコミットしないでください。

---

Version 8.x
