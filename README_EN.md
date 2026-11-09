<p align="center">
  <img src="https://raw.githubusercontent.com/iamafreeride/Nikki4-webcheckin/main/assets/icon.png" alt="Shining Nikki" width="112" height="112">
</p>

<h1 align="center">Nikki4-webcheckin</h1>

<p align="center">
  Daily automatic <b>check-in</b> + <b>reward redemption</b> on the Shining Nikki (閃耀暖暖) TW website
</p>

<p align="center">
  <a href="https://hub.docker.com/r/iamafreeride/nikki4-webcheckin"><img alt="Docker Hub" src="https://img.shields.io/docker/pulls/iamafreeride/nikki4-webcheckin?style=for-the-badge"></a>
  <a href="https://github.com/iamafreeride/Nikki4-webcheckin/actions"><img alt="Build" src="https://img.shields.io/github/actions/workflow/status/iamafreeride/Nikki4-webcheckin/docker.yml?style=for-the-badge&label=build"></a>
  <a href="LICENSE"><img alt="License" src="https://img.shields.io/github/license/iamafreeride/Nikki4-webcheckin?style=for-the-badge"></a>
</p>

**English** | [繁體中文](README.zh-TW.md)

Opens <https://nikki4.com.tw/checkin/sign?activity_id=0> with real mobile emulation (iPhone 390×844 viewport, DPR 3, touch, iPhone UA), logs in, closes the welcome popup, clicks check-in, then redeems gifts on <https://nikki4.com.tw/checkin/gift?activity_id=0> in priority order. It runs once and exits with a clear exit code. Structure follows [simao-silva/noip-renewer](https://github.com/simao-silva/noip-renewer) (MIT).

## Flow

1. Open the check-in page in mobile emulation.
2. Log in with **email** and **password** (if the account has several characters, the first is selected by default).
3. Close the welcome popup and click **check-in** (an already-checked-in button counts as done for today).
4. Read this month's **points** and **signed days** from the page's own activity API.
5. If signed days ≥ `MIN_SIGNED_DAYS` (default 30) and points suffice, redeem gifts by priority.

Points and signed days **reset at 23:59 on the last day of each month**, so don't wait until the last minute.

## Redemption plan

Default priority (earlier items first; skipped if points are short or the monthly limit is reached):

| # | Gift | Points | Monthly limit |
|---|---|---|---|
| 1 | Pink Diamonds (粉鑽) | 25 | 2 |
| 2 | Phantom Ticket Stamina Pack (幻券體力禮包) | 120 | 1 |
| 3 | Memory Key Pack (記憶鑰匙禮包) | 80 | 1 |
| 4 | Memory Track (記憶之軌) | 25 | 2 |
| 5 | Mystery Ticket (謎之券) | 25 | 2 |
| 6 | Impression Fragment · Rare (印象碎片·稀有) | 10 | 3 |
| 7 | Stamina (體力) | 10 | 3 |
| 8 | Gold (金幣) | 10 | 3 |
| 9 | 30-day streak reward (30天連簽獎勵) | 0 | 1 (needs 30 consecutive days) |

Limits and points are checked against the **live numbers returned by the game API**, so nothing is redeemed twice.

Custom priority via `REDEEM_PLAN` (JSON, earlier first):

```bash
-e REDEEM_PLAN='[{"name":"粉鑽","cost":25,"limit":2},{"name":"幻券體力禮包","cost":120,"limit":1}]'
```

## Quick start

### Docker

```bash
docker pull iamafreeride/nikki4-webcheckin:latest

docker run --rm \
  -e NIKKI_EMAIL=you@example.com \
  -e NIKKI_PASSWORD='your-password' \
  iamafreeride/nikki4-webcheckin:latest
```

Build it yourself (only if you changed the code):

```bash
git clone https://github.com/iamafreeride/Nikki4-webcheckin.git
cd Nikki4-webcheckin
docker build -t nikki4-webcheckin .
```

Or with compose (credentials in `.env`):

```bash
cp .env.example .env    # set NIKKI_EMAIL / NIKKI_PASSWORD
docker compose up --build
```

### Windows (no Docker)

1. Install Python 3.9+ (tick *Add python.exe to PATH*).
2. Double-click **`run.bat`**. The first run creates `.venv` and installs selenium; credentials are prompted if not set (password input is hidden). Edge with iPhone emulation is the default.

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
.\.venv\Scripts\python checkin.py --email you@example.com --password 'your-password'
```

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `NIKKI_EMAIL` (or `EMAIL`) | required | Login email |
| `NIKKI_PASSWORD` (or `PASSWORD`) | required | Login password |
| `REDEEM` | `true` | `false` = check in only, no redemption |
| `DRY_RUN` | `false` | Print the redemption plan without clicking |
| `MIN_SIGNED_DAYS` | `30` | Skip redemption if signed days are below this |
| `REDEEM_PLAN` | see table | Custom priority (JSON) |
| `BROWSER` | `chrome` | `chrome` / `edge` / `firefox` |
| `HEADLESS` | `true` | `false` opens a visible window |
| `DEBUG` | `false` | Save screenshot + DOM to `artifacts/` on failure |
| `LOGIN_TIMEOUT` | `90` | Seconds to wait for login |
| `MOBILE_EMULATION` | iPhone 390×844 | Custom deviceMetrics / UA (JSON) |
| `SITE` / `SIGN_URL` / `GIFT_URL` | official site | Override, e.g. for a test site |

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Check-in done (or already done today) and redemption finished normally |
| `1` | Failure: login rejected, element not found, redemption failed |
| `2` | Config error: credentials missing |

## Scheduling (once a day)

Linux / NAS:

```cron
10 9 * * * cd /opt/Nikki4-webcheckin && /usr/bin/docker compose run --rm checkin >> checkin.log 2>&1
```

Windows Task Scheduler: run `C:\path\to\run.bat` (remove the trailing `pause` for background runs). Re-running on the same day is safe: it reports already checked in and skips items at their limit.

## Troubleshooting

- **Login fails**: run once with `-e DEBUG=true -v "$PWD/artifacts:/app/artifacts"` and check the screenshot. Common causes: special characters in the password eaten by the shell (use single quotes), the account requires SMS/email verification, or the site changed.
- **"Signed days insufficient", nothing redeemed**: intentional (`MIN_SIGNED_DAYS=30`). Lower it, e.g. `-e MIN_SIGNED_DAYS=0`, to redeem earlier.
- **Redeem button not found**: the gift page button is `.btn-exchange[ga-data^='ck-gift-']`; `btn-exchange-dis` means it can't be redeemed right now (not enough points or limit reached) and is skipped.
- **Reward not in game**: per official rules, rewards go to the **in-game mailbox**, possibly with a delay. The character bound at first login decides the recipient and can't be changed.

## Project layout

```
checkin.py          login → check in → read points → redeem
run.bat             Windows one-click runner
Dockerfile          Debian + Chromium + chromedriver (mobile emulation)
docker-compose.yml
requirements.txt
.env.example
.github/workflows/docker.yml
```

## Disclaimer

- For **your own account**, once a day.
- This is browser automation, not an official API. It may break when the site changes and may conflict with event terms. Use at your own risk.
- Not affiliated with Paper Games / Infold.

## License

MIT, see [LICENSE](LICENSE).
