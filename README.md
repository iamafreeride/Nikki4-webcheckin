<p align="center">
  <img src="https://raw.githubusercontent.com/iamafreeride/Nikki4-webcheckin/main/assets/icon.png" alt="閃耀暖暖" width="112" height="112">
</p>

<h1 align="center">Nikki4-webcheckin</h1>

<p align="center">
  《閃耀暖暖》官網「簽到有禮」每日自動<b>簽到</b>＋<b>兌換獎勵</b>
</p>

<p align="center">
  <a href="https://hub.docker.com/r/iamafreeride/nikki4-webcheckin"><img alt="Docker Hub" src="https://img.shields.io/docker/pulls/iamafreeride/nikki4-webcheckin?style=for-the-badge"></a>
  <a href="https://github.com/iamafreeride/Nikki4-webcheckin/actions"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/iamafreeride/Nikki4-webcheckin/docker.yml?style=for-the-badge&label=build"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/iamafreeride/Nikki4-webcheckin?style=for-the-badge"></a>
</p>

[English](README_EN.md) | **繁體中文**

以真正的手機模擬（iPhone 390×844、DPR 3、觸控、iPhone UA）開啟 <https://nikki4.com.tw/checkin/sign?activity_id=0>，登入、關閉歡迎彈窗、按「簽到」，再到 <https://nikki4.com.tw/checkin/gift?activity_id=0> 依優先順序兌換獎勵。跑完就結束並回傳明確退出碼。結構沿用 [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer)（MIT）。

## 流程

1. 手機模擬開啟簽到頁。
2. 以**信箱**與**密碼**登入（帳號有多個角色時預設選第一個）。
3. 關閉「歡迎，XXX」彈窗並點「簽到」（按鈕已是「已簽到」視為今日完成）。
4. 直接呼叫頁面自己使用的活動 API，讀取本月**積分**與**簽到天數**。
5. 簽到天數 ≥ `MIN_SIGNED_DAYS`（預設 30）且積分足夠時，依優先順序兌換。

積分與簽到天數會在**每月最後一天 23:59 清零**，別拖到最後一刻。

## 兌換規則

預設優先順序（先換前面；積分不足或已達每月上限就跳過）：

| # | 禮物 | 積分 | 每月上限 |
|---|---|---|---|
| 1 | 粉鑽 | 25 | 2 |
| 2 | 幻券體力禮包 | 120 | 1 |
| 3 | 記憶鑰匙禮包 | 80 | 1 |
| 4 | 記憶之軌 | 25 | 2 |
| 5 | 謎之券 | 25 | 2 |
| 6 | 印象碎片·稀有 | 10 | 3 |
| 7 | 體力 | 10 | 3 |
| 8 | 金幣 | 10 | 3 |
| 9 | 30天連簽獎勵 | 0 | 1（需連續 30 天） |

每月上限與積分以**遊戲 API 回傳的即時數字**判斷，不會重複兌換。

用 `REDEEM_PLAN` 自訂優先順序（JSON，前面的先換）：

```bash
-e REDEEM_PLAN='[{"name":"粉鑽","cost":25,"limit":2},{"name":"幻券體力禮包","cost":120,"limit":1}]'
```

## 快速開始

### Docker

```bash
docker pull iamafreeride/nikki4-webcheckin:latest

docker run --rm \
  -e NIKKI_EMAIL=you@example.com \
  -e NIKKI_PASSWORD='your-password' \
  iamafreeride/nikki4-webcheckin:latest
```

自己 build（改過程式才需要）：

```bash
git clone https://github.com/iamafreeride/Nikki4-webcheckin.git
cd Nikki4-webcheckin
docker build -t nikki4-webcheckin .
```

或用 compose（帳密寫在 `.env`）：

```bash
cp .env.example .env    # 填入 NIKKI_EMAIL / NIKKI_PASSWORD
docker compose up --build
```

### Windows 本機（不用 Docker）

1. 安裝 Python 3.9+（勾選 *Add python.exe to PATH*）。
2. 雙擊 **`run.bat`**：第一次會建立 `.venv` 並安裝 selenium；沒設定帳密時會詢問（密碼輸入不顯示）。預設使用 Edge + iPhone 模擬。

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python checkin.py --email you@example.com --password 'your-password'
```

## 環境變數

| 變數 | 預設 | 說明 |
|---|---|---|
| `NIKKI_EMAIL`（或 `EMAIL`） | 必填 | 登入信箱 |
| `NIKKI_PASSWORD`（或 `PASSWORD`） | 必填 | 登入密碼 |
| `REDEEM` | `true` | `false` = 只簽到、不兌換 |
| `DRY_RUN` | `false` | 只印出兌換計畫，不真的點 |
| `MIN_SIGNED_DAYS` | `30` | 本月簽到天數未達此值就不兌換 |
| `REDEEM_PLAN` | 見上表 | 自訂優先順序（JSON） |
| `BROWSER` | `chrome` | `chrome` / `edge` / `firefox` |
| `HEADLESS` | `true` | `false` 會開視窗 |
| `DEBUG` | `false` | 失敗時把截圖與 DOM 存到 `artifacts/` |
| `LOGIN_TIMEOUT` | `90` | 等登入完成的秒數 |
| `MOBILE_EMULATION` | iPhone 390×844 | 自訂 deviceMetrics / UA（JSON） |
| `SITE` / `SIGN_URL` / `GIFT_URL` | 官網 | 可換成測試站 |

## 退出碼

| 代碼 | 意義 |
|---|---|
| `0` | 簽到完成（或今日已簽），且兌換流程正常結束 |
| `1` | 失敗：登入被拒、找不到元素、兌換失敗 |
| `2` | 設定錯誤：缺少帳密 |

## 排程（每天一次）

Linux / NAS：

```cron
10 9 * * * cd /opt/Nikki4-webcheckin && /usr/bin/docker compose run --rm checkin >> checkin.log 2>&1
```

Windows 工作排程器：程式填 `C:\path\to\run.bat`（要背景執行就拿掉 `run.bat` 最後的 `pause`）。同一天重跑是安全的：會顯示「已簽到」並跳過已達上限的項目。

## 疑難排解

- **登入失敗**：加上 `-e DEBUG=true -v "$PWD/artifacts:/app/artifacts"` 跑一次，查看截圖。常見原因：密碼含特殊字元被 shell 吃掉（請用單引號）、帳號需要簡訊／信箱驗證、官網改版。
- **「簽到天數不足」而沒兌換**：這是刻意設計（`MIN_SIGNED_DAYS=30`）。想提早兌換就調小，例如 `-e MIN_SIGNED_DAYS=0`。
- **找不到兌換按鈕**：禮物頁按鈕為 `.btn-exchange[ga-data^='ck-gift-']`；若是 `btn-exchange-dis` 代表目前不可兌換（積分不足或已達上限），程式會跳過。
- **獎勵沒進遊戲**：依官方規則，獎勵發到**遊戲內信箱**，可能延遲；首次登入綁定的角色決定收件信箱，無法更改。

## 專案結構

```
checkin.py          登入 → 簽到 → 讀積分 → 兌換
run.bat             Windows 一鍵執行
Dockerfile          Debian + Chromium + chromedriver（支援手機模擬）
docker-compose.yml
requirements.txt
.env.example
.github/workflows/docker.yml
```

## 免責聲明

- 僅供**你自己的帳號**每天一次使用。
- 這是瀏覽器自動化，不是官方 API；官網改版可能失效，也可能與活動條款有出入，風險自負。
- 本專案與 Paper Games／品玩邦無任何關係。

## 授權

MIT，見 [LICENSE](LICENSE)。
