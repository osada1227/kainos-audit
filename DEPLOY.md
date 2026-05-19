# デプロイ手順（m-osada 用）

カイノス様の操作は「URLを開いてログイン → 使う」だけ。
m-osada 様側で1回だけ以下の作業を行えば、URL を共有するだけで利用開始できます。

---

## 全体のゴール

カイノス様にお渡しするもの（メールやチャットで送る）:
- 🌐 URL: `https://<アプリ名>.streamlit.app`
- 👤 ユーザー名: `kainos`
- 🔐 パスワード: `(setup_initial.py が発行する文字列)`

カイノス様にやってもらうこと: **URLを開いてログインするだけ**

---

## m-osada 様の作業（初回 30分、以降は不要）

### 1. ローカルで初期セットアップ（5分）

```bash
cd /path/to/カイノス様
python3 setup_initial.py
```

出力される情報を**この場で控える**:
- `cookie_key` の文字列 → Streamlit Cloud Secrets に貼る
- `admin` のパスワード → m-osada 様用、自分で保管
- `kainos` のパスワード → カイノス様に連絡する用

> ⚠ パスワードは setup_initial.py の出力以外には残りません（auth_config.yamlにはハッシュのみ）。失くしたら `manage_users.py rotate kainos` で再発行可能。

### 2. Anthropic API キーを取得（10分）

1. https://console.anthropic.com にアクセス → ログイン or 新規登録
2. 左メニューの「Plans & Billing」で最低 $5 をチャージ（Sonnet 4.6 なら 200回程度の審査分）
3. 「API Keys」→「Create Key」→ 名前を `kainos-audit-prod` 等にして発行
4. `sk-ant-...` で始まる文字列を控える（**1度しか表示されない**）

### 3. GitHub に push（5分）

```bash
git init
git add app.py audit_subcontract.py chat_subcontract.py manage_users.py setup_initial.py \
        system_prompt/ extracted/ sources/ \
        auth_config.yaml requirements.txt \
        .flake8 .gitignore \
        .streamlit/secrets.toml.example \
        DEPLOY.md README.md 2>/dev/null
git commit -m "initial deploy"
git remote add origin git@github.com:<your-account>/kainos-audit.git
git push -u origin main
```

> 公開リポジトリで OK（パスワードはbcryptハッシュのみ、APIキーはコミットしない）

### 4. Streamlit Cloud にデプロイ（10分）

1. https://share.streamlit.io にログイン（GitHub アカウント連携）
2. 「**New app**」をクリック
3. リポジトリ・ブランチ・`app.py` を選択
4. **Advanced settings → Secrets** に以下を貼り付け:

   ```toml
   [auth]
   cookie_key = "ここに setup_initial.py 出力の cookie_key"

   [anthropic]
   api_key = "sk-ant-... ここに発行したキー"
   ```

5. 「Deploy!」をクリック → 数分待つと URL 発行

### 5. カイノス様に連絡（5分）

メール／チャットで以下を送付:

```
件名: 再下請負通知書 審査アシスタント ご利用案内

下記URLでログインしてご利用いただけます。

  URL    : https://<アプリ名>.streamlit.app
  ユーザー: kainos
  パスワード: (setup_initial.py 出力の kainos パスワード)

使い方:
  1. URL を開く
  2. ログイン
  3. 「📑 構造化審査」タブで通知書 (PDF/画像) をアップロード
  4. 「🔍 構造化審査を実行」をクリック
  5. 結果を確認 / Word でダウンロード可能

操作で不明な点があればお問い合わせください。
```

---

## ユーザー追加・削除（必要に応じて）

### 新規ユーザーを追加

```bash
python3 manage_users.py add yamamoto "山本" yamamoto@kainos.co.jp
# パスワードを対話入力
git add auth_config.yaml
git commit -m "add user: yamamoto"
git push
```
→ Streamlit Cloud が自動再デプロイ、即座にログイン可能。

### ユーザー削除

```bash
python3 manage_users.py remove yamamoto
git add auth_config.yaml && git commit -m "remove yamamoto" && git push
```

### パスワード忘れ対応

```bash
python3 manage_users.py rotate kainos
# 新パスワード生成 → カイノス様に再送
git add auth_config.yaml && git commit -m "rotate password" && git push
```

### 一覧確認

```bash
python3 manage_users.py list
```

---

## ローカル動作確認（任意）

デプロイ前に手元でテストしたい場合:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# secrets.toml を編集して cookie_key と api_key を埋める
streamlit run app.py
# → http://localhost:8501 でブラウザ起動
```

---

## コストの目安（Sonnet 4.6 / 現状コーパス 427K）

| シナリオ | コスト |
|---|---:|
| 初回審査（cache_create） | 約 250円 |
| 2件目以降（5分以内 cache_hit） | 約 27円 |
| バッチ10件連続 | 約 270円 |

月100件想定で 2,500〜3,000円程度。

請求は Anthropic アカウント → race-tech 側でまとめて管理（カイノス様は意識しない）。

---

## トラブルシューティング

| 症状 | 対処 |
|---|---|
| 「APIキー未設定」表示が出る | Streamlit Cloud Secrets の `[anthropic] api_key` が空。再設定して app を Reboot |
| ログインできない | パスワード再発行 → push |
| アプリが重い / 落ちる | Streamlit Cloud 無料枠 1GB を超過。「Reboot app」で復旧 |
| URLが変わってしまった | アプリ名を変えなければ固定。変更時はカイノス様に再連絡 |
| カイノス様から修正依頼 | リポジトリで修正 → push → 自動再デプロイ |

---

## 既知の制約

- Streamlit Community Cloud 無料枠は数十分アイドルでスリープ → 再アクセス時の初回はやや遅い
- `sessions/` 保存履歴はコンテナ再起動で消える（恒久保存が必要なら別途検討）
- 通知書アップロードはメモリ上のみ（ディスク非永続）→ プライバシー安全
