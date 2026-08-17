# フリカレ監視BOT

フリーカレンダー（フリカレ）の公開スケジュールを取得し、Discord通知やChatGPTでの予定整理に利用するプロジェクトです。

## 新しい取得コア

従来のDiscord BOT内に直接組み込まれていた取得処理を、再利用可能な `freecal_core.py` として分離しています。

主な改善点:

- Discord表示処理とWeb取得処理を分離
- 固定3秒待機ではなく、ページ読込とDOM安定を確認して待機
- ChromeDriverはSelenium Managerに任せ、新コアでは `webdriver-manager` を不要化
- `230522` / `mem230522` / 公開URLを同じ入力として扱える
- `_dateYYYYMM` の月指定URLへ直接アクセス
- 日付・時刻・予定名を構造化データとして返す
- 月指定、開始日・終了日指定に対応
- 重複予定を除去
- JSON CLIを用意
- ChatGPT Skill用の `skills/freecal/SKILL.md` を追加

### JSONで予定を取得

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
  --end 2026-09-01 \
  --pretty
```

出力例:

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
  ]
}
```

### テスト

```bash
pip install -r requirements-dev.txt
pytest -q
```

## Discord BOT

### 必要な環境

- Python 3.11以上
- Google Chrome（最新版）
- Discord BOTトークン

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

### 設定

`config.py` を編集します。

```python
DISCORD_BOT_TOKEN = "あなたのBOTトークン"
```

環境変数を使用する場合は `.env` を利用してください。

### BOTの起動

```bash
python bot.py
```

### Discord上での初期設定

```text
!setchannel #通知チャンネル
!adduser 123456 ユーザー名
```

## コマンド一覧

| コマンド | 説明 |
|---|---|
| `!check` | 監視ユーザー一覧 |
| `!check [名前]` | 今日の予定を確認 |
| `!calendar [名前]` | 今後の全予定を表示 |
| `!status` | 監視状況（管理者のみ） |
| `!adduser` | ユーザー追加（管理者のみ） |
| `!removeuser` | ユーザー削除（管理者のみ） |
| `!setchannel` | 通知チャンネル設定（管理者のみ） |

## ファイル構成

```text
freecal_bot/
├── bot.py                       # 既存Discord BOT
├── freecal_core.py              # 再利用可能な取得・解析コア
├── freecal_cli.py               # JSON CLI
├── config.py                    # Discord設定
├── requirements.txt             # 実行依存ライブラリ
├── requirements-dev.txt         # テスト依存ライブラリ
├── tests/
│   └── test_freecal_core.py     # 解析・期間指定テスト
├── skills/
│   └── freecal/
│       └── SKILL.md             # ChatGPT Skill
├── users.json                   # ユーザー情報（自動生成）
├── previous_data.json           # 前回データ（自動生成）
└── screenshots/                 # 既存BOTのデバッグ画像
```

## ChatGPT Skill

`skills/freecal/SKILL.md` は、公開フリカレを取得して次の処理を行うためのワークフローを定義しています。

- 月間予定を表にする
- 指定期間の予定を抽出する
- 公開予定がない日を確認する
- 複数人の公開予定を比較する

予定が公開されていない日を、本人が必ず空いている日とは扱いません。

## トラブルシューティング

### BOTまたはCLIが起動しない

- `python --version` を確認
- Google Chromeが利用できることを確認
- `pip install -r requirements.txt` を再実行

### スケジュールが取得できない

- 公開フリカレURLをブラウザで直接開けるか確認
- ユーザーIDが正しいか確認
- フリカレ側のDOM構造が変更されていないか確認
- 既存Discord BOTでは `screenshots/` のデバッグ画像も確認

## セキュリティ

- Discord BOTトークンをGitへコミットしない
- 非公開カレンダーや認証が必要な情報の取得には使用しない
- Skillでは公開URLまたは公開ユーザーIDのみを対象にする

## 詳細ドキュメント

- [利用ガイド](user_guide.md)
- [管理者ガイド](admin_guide.md)
- [開発ナレッジ](dev_knowledge.md)

---

Version 8.0 development branch
