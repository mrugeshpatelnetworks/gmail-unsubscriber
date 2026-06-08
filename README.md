# Email Unsubscriber

A privacy-first **desktop GUI app** that scans your Gmail and Yahoo Mail for promotional and newsletter emails, shows every unique sender in a searchable table, and **silently unsubscribes and deletes them in one click** — completely in the background, no browser windows.

Supports **Gmail and Yahoo Mail simultaneously**, handles multi-step confirmation pages and confirmation emails automatically, and never sends your data to any third-party server.

> **Origin story:** I looked at my wife's inbox one day — 2,847 unread emails from every store, newsletter, and promo she'd ever signed up for over 5 years. Built this over a weekend. Deleted 500,000+ emails across her accounts and a few family accounts. Inbox looked brand new. Sharing it in case it helps someone else.

---

## Features

| Feature | Details |
|---|---|
| **Desktop GUI** | Native PySide6 window — no terminal needed after setup |
| **Gmail + Yahoo Mail** | Both providers work side-by-side in the same session |
| **Multiple accounts** | Connect as many accounts as you want simultaneously |
| **Silent unsubscribe** | HTTP requests in the background — no browser popup, no clicking |
| **RFC 8058 one-click POST** | Uses the fastest unsubscribe method when the sender supports it |
| **Auto-confirm pages** | If the unsubscribe URL leads to a "click here to confirm" page, it clicks it automatically |
| **Auto-confirm emails** | If a "confirm your unsubscription" email arrives, it finds the link and clicks it automatically |
| **Browser fallback** | Only opens a browser tab if silent HTTP completely fails |
| **Body link extraction** | Finds unsubscribe links in the email body when the header has none |
| **Actionable-only list** | Only shows senders that actually have an unsubscribe path — no clutter |
| **Four scan modes** | All unread, all mail, Promotions only, Inbox only |
| **Real-time filter** | Search hundreds of senders instantly by name or email |
| **Bulk delete** | Removes ALL emails from selected senders (read + unread) in one operation |
| **Env-var auto-detect** | Reads saved credentials from environment variables — no typing on launch |
| **Works everywhere** | Windows, macOS, Linux — pure Python + PySide6 |

---

## How unsubscribing works

Most apps just open a browser tab and leave you to click around. This app goes further:

```
1. Silent HTTP request to the unsubscribe URL
   ├─ RFC 8058 one-click POST  (if sender supports it — fastest, most reliable)
   └─ Plain GET request        (standard fallback)

2. If the response page has a "confirm" button or link → auto-clicks it silently

3. After all senders are processed, waits 8 seconds then scans your Inbox
   for any "confirm your unsubscription" emails → auto-clicks those too

4. Only if HTTP completely fails → opens your browser as a last resort
```

You watch the progress log fill up with ✓ marks. No clicking around on websites.

---

## Screenshots

```
┌─ Email Unsubscriber ──────────────────────────────────────────────────────┐
│  Sign-in method                                                             │
│  ○ Sign in with Google  (OAuth — recommended)                               │
│  ● App Password + IMAP  (Gmail + Yahoo, multiple accounts)                  │
│                                                                             │
│  ✓  Found 3 accounts in environment variables — passwords pre-filled.       │
│  ┌─ detected from env ────────────────────────────────────────────────────┐ │
│  │  you@gmail.com         [••••••••••••••••] 👁   ✓ Connected            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  other@gmail.com       [••••••••••••••••] 👁   ✓ Connected            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │  you@yahoo.com         [••••••••••••••••] 👁   ✓ Connected            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
│  + Add another account                                                      │
│                              [ Continue → ]                                 │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ Senders (298) ─────────────────────── all have unsubscribe links ──────────┐
│  🔍 Filter by name or email…                    [ Select All ] [ Clear ]     │
│  ┌────┬───────────────────────────┬───────────────────────────┬───────┐      │
│  │ ☑  │ Sender                    │ Email                     │ Count │      │
│  ├────┼───────────────────────────┼───────────────────────────┼───────┤      │
│  │ ☑  │ Shopify                   │ no-reply@shopify.com      │  147  │      │
│  │ ☑  │ LinkedIn                  │ messages@linkedin.com     │   83  │      │
│  │ ☐  │ Groupon                   │ deals@groupon.com         │   61  │      │
│  └────┴───────────────────────────┴───────────────────────────┴───────┘      │
│  2 selected              [ Unsubscribe ]   [ Unsubscribe + Delete ]          │
└─────────────────────────────────────────────────────────────────────────────┘

┌─ Processing (2 senders) ────────────────────────────────────────────────────┐
│  ████████████████████████████████████████  100%                             │
│                                                                             │
│  ✉  deals@groupon.com      — Confirm email clicked (GET 200)               │
│  ✓  messages@linkedin.com  — Unsubscribed silently (POST 200 → confirm GET 200) │
│  ✓  no-reply@shopify.com   — Unsubscribed silently (GET 200)               │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.9 or higher
- A Gmail and/or Yahoo Mail account
- For **Gmail App Password**: 2-Step Verification enabled on your Google account
- For **Yahoo App Password**: Any Yahoo account (see Step 3)
- For **Google OAuth**: A one-time Google Cloud setup (~3 minutes)

---

## Step 1 — Download

**Clone with Git**
```bash
git clone https://github.com/mrugeshpatelnetworks/gmail-unsubscriber.git
cd gmail-unsubscriber
```

**Or download ZIP**
1. Click the green **Code** button → **Download ZIP**
2. Unzip to any folder (not your home root — pick somewhere like `Documents/`)

---

## Step 2 — Install and launch

The setup scripts install Python and all dependencies automatically if anything is missing. No manual steps.

### Windows
Double-click **`setup.bat`**

### Mac — double-click (no Terminal needed)
Double-click **`setup.command`** in Finder

> First time only: right-click → **Open** → **Open** (macOS security prompt)

### Mac / Linux — Terminal
```bash
bash setup.sh
```

All three scripts:
1. Detect Python — install automatically if missing (winget / Homebrew / apt / dnf)
2. Create a `.venv/` virtual environment
3. Install PySide6 and dependencies
4. Detect any saved credentials and display which accounts were found
5. Launch the app

---

## Step 3 — Connect your accounts

The app supports three connection methods. **App Password + IMAP is recommended** — it's the only one that supports Yahoo Mail and multiple accounts.

---

### Method A — App Password + IMAP *(recommended — Gmail + Yahoo, multiple accounts)*

No Google Cloud setup required. Works with any number of Gmail and Yahoo accounts simultaneously.

#### Gmail setup

**1. Enable 2-Step Verification** (if not already on)
[myaccount.google.com/security](https://myaccount.google.com/security) → **2-Step Verification → Turn On**

**2. Generate a Gmail App Password**
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Select app: **Mail** — Select device: **Windows Computer** (or Mac)
3. Click **Generate** — copy the 16-character password
4. You won't see it again, but you can always generate a new one

**3. Enable IMAP in Gmail**
Gmail Settings → **See all settings** → **Forwarding and POP/IMAP** → **Enable IMAP** → Save

---

#### Yahoo setup

**1. Generate a Yahoo App Password**
1. Go to [login.yahoo.com/account/security](https://login.yahoo.com/account/security)
2. Scroll to **App passwords** → **Generate app password**
3. Choose **Other app** — name it anything (e.g. "Email Unsubscriber")
4. Copy the generated password

**2. Enable IMAP in Yahoo Mail**
Yahoo Mail → **Settings** (⚙️) → **More Settings** → **Mailboxes** → enable IMAP access

---

#### Save credentials as environment variables *(optional — enables auto-fill)*

Saving credentials as environment variables means the app pre-fills them every time you launch — no typing.

**Windows (permanent — run once in Command Prompt):**
```cmd
:: Gmail
setx GMAIL_EMAIL "you@gmail.com"
setx GMAIL_APP_PASSWORD "xxxx xxxx xxxx xxxx"

:: Yahoo
setx YAHOO_EMAIL "you@yahoo.com"
setx YAHOO_APP_PASSWORD "xxxx xxxx xxxx xxxx"

:: Second Gmail account
setx GMAIL_EMAIL_2 "other@gmail.com"
setx GMAIL_APP_PASSWORD_2 "yyyy yyyy yyyy yyyy"
```
Close and reopen your terminal after running `setx` commands.

**Mac / Linux (add to `~/.zshrc` or `~/.bashrc`):**
```bash
# Gmail
export GMAIL_EMAIL="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"

# Yahoo
export YAHOO_EMAIL="you@yahoo.com"
export YAHOO_APP_PASSWORD="xxxx xxxx xxxx xxxx"

# Second Gmail account
export GMAIL_EMAIL_2="other@gmail.com"
export GMAIL_APP_PASSWORD_2="yyyy yyyy yyyy yyyy"
```
Then run `source ~/.zshrc` (or restart your terminal).

**All supported variable names:**

| Provider | Email variable | Password variable |
|---|---|---|
| Gmail | `GMAIL_EMAIL`, `GMAIL_USER`, `GOOGLE_EMAIL` | `GMAIL_APP_PASSWORD`, `GMAIL_APP_PASS`, `GMAIL_PASSWORD` |
| Yahoo | `YAHOO_EMAIL`, `YAHOO_USER` | `YAHOO_APP_PASSWORD`, `YAHOO_APP_PASS`, `YAHOO_PASSWORD` |
| Multiple accounts | Add `_2` through `_9` suffix to any variable | Same suffix on the matching password variable |

---

#### In the app

1. Select **App Password + IMAP**
2. If env vars were found — rows are already filled in with a green "detected from env" badge. Click **Connect →**
3. Otherwise — type your email and App Password. Click **+ Add another account** for more accounts
4. Wait for each row to show **✓ Connected**
5. Click **Continue →**

---

### Method B — Google OAuth *(Gmail only, single account)*

Use this if you prefer not to use App Passwords or if your organisation requires OAuth. Takes ~3 minutes to set up once.

**1. Create a Google Cloud project**
[console.cloud.google.com](https://console.cloud.google.com/) → project dropdown → **New Project** → Create

**2. Enable the Gmail API**
**APIs & Services → Library** → search **Gmail API** → **Enable**

**3. Create OAuth credentials**
1. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
2. Configure consent screen if prompted: choose **External**, fill in app name and your email, click through
3. Application type → **Desktop app** → **Create**
4. Click **Download JSON** → rename to **`credentials.json`**
5. Place `credentials.json` in the same folder as `gmail_unsubscriber.py`

**4. Add yourself as a test user**
**APIs & Services → OAuth consent screen → Test users → + Add Users** → enter your Gmail

> Without this step you'll get "Error 403: access_denied"

**5. In the app**
Select **Sign in with Google (OAuth)** → **Connect →**. A browser opens — sign in and grant access. Your token is saved to `token.pickle` so you won't need to sign in again.

---

## Step 4 — Configure the scan

| Mode | Best for |
|---|---|
| **All unread** | ✅ Recommended — finds everything Gmail mislabelled |
| **All mail (read + unread)** | Most thorough; slower on large inboxes |
| **Promotions folder only** | Quick pass for obvious newsletters |
| **Inbox unread only** | Fast inbox cleanup |

Use the slider to set how many emails to scan per account (100 – 10,000). Default 1,000.

> **Note:** The results list only shows senders that have an unsubscribe link. Transactional emails (receipts, 2FA codes, bank statements) are automatically excluded — they won't have unsubscribe links so they never appear.

---

## Step 5 — Review and act

The **Senders** screen shows every unique sender with an unsubscribe path:

- **Click a row** or press **Space** to check / uncheck
- **Type in the filter box** to search by name or email instantly
- **Select All / Clear** for bulk selection

Choose an action:

| Button | What it does |
|---|---|
| **Unsubscribe** | Silently unsubscribes in the background. Auto-confirms confirmation pages and confirmation emails. Browser opens only as a last resort. |
| **Unsubscribe + Delete** | Unsubscribes (as above) AND moves every email from that sender to Trash — read and unread |

The **Processing** screen shows a live log:

| Icon | Meaning |
|---|---|
| ✓ | Silently unsubscribed |
| ✉ | Confirmation email found and clicked |
| ↗ | HTTP failed — opened in browser as fallback |
| ✗ | No unsubscribe link found |

---

## Step 6 — Results

The results screen shows:
- ✓ **green** — silently unsubscribed in background
- ↗ **amber** — browser was opened as fallback (only if HTTP failed)
- ✗ **red** — no unsubscribe link found (expand to see which senders)
- 🗑 **blue** — total emails moved to Trash

Deleted emails sit in Trash for **30 days** before permanent removal. If you regret anything, go to Gmail / Yahoo Mail → Trash and restore it.

---

## Troubleshooting

### "Login failed" — Gmail
- Make sure **2-Step Verification is ON** (required for App Passwords)
- Regenerate your App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- Confirm **IMAP is enabled**: Gmail Settings → Forwarding and POP/IMAP → Enable IMAP
- App Passwords use the format `xxxx xxxx xxxx xxxx` — spaces are OK

### "Login failed" — Yahoo
- Go to [login.yahoo.com/account/security](https://login.yahoo.com/account/security) → **Generate app password**
- Make sure IMAP is enabled: Yahoo Mail Settings → More Settings → Mailboxes
- If your Yahoo account has 2-Step Verification OFF, try enabling it first

### "Error 403: access_denied" — Google OAuth
You haven't added yourself as a test user — follow **Step 3B, item 4**.

### "credentials.json not found" — Google OAuth
Place `credentials.json` in the same folder as `gmail_unsubscriber.py`.

### Env vars not detected
- **Windows:** Close your terminal completely and reopen it after `setx`
- Confirm: `echo %GMAIL_EMAIL%` (Windows) or `echo $GMAIL_EMAIL` (Mac/Linux)
- The email must be a supported domain (`@gmail.com`, `@yahoo.com`, etc.)

### Token expired — app asks me to sign in again (OAuth)
```bash
rm token.pickle        # Mac / Linux
del token.pickle       # Windows
```
Then relaunch — a new browser sign-in will run once.

### Some senders don't appear in the list
Only senders with a detectable unsubscribe path are shown. If a sender has no `List-Unsubscribe` header AND no unsubscribe link anywhere in their email body, they are excluded. This is intentional — the app only shows senders it can actually act on.

### Unsubscribe said ✓ but I'm still getting emails
- Some senders take 5–10 business days to process unsubscribe requests
- Check the ✉ log — if a confirmation email was expected but not caught, open the email manually and click the link
- A small number of senders ignore unsubscribe requests entirely (they're usually spam — use a spam filter)

---

## Privacy & Security

- **Your emails never leave your computer.** The app connects directly to Gmail / Yahoo Mail — no third-party servers involved.
- **Only headers are normally read.** Only `From`, `List-Unsubscribe`, and `List-Unsubscribe-Post` headers are fetched during the scan. Email bodies are only accessed when a header link is missing and the app looks for one in the body.
- **`credentials.json` and `token.pickle` are in `.gitignore`** and will never be committed to git.
- **Deleted emails go to Trash** — not permanent deletion. You have 30 days to recover anything in Gmail or Yahoo Mail Trash.
- **App Passwords can be revoked** at any time without changing your main password.
  - Gmail: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
  - Yahoo: [login.yahoo.com/account/security](https://login.yahoo.com/account/security)

---

## Gmail API permission scopes (OAuth sign-in only)

| Scope | Why it's needed |
|---|---|
| `gmail.readonly` | Read email headers to build the sender list |
| `gmail.send` | Reserved for future mailto unsubscribe support |
| `gmail.modify` | Move emails to Trash |

---

## Project structure

```
gmail-unsubscriber/
├── gmail_unsubscriber.py        # main app — all GUI and logic
├── requirements.txt             # Python dependencies
├── setup.bat                    # Windows  — double-click to install + launch
├── setup.command                # Mac      — double-click in Finder
├── setup.sh                     # Linux    — run in terminal
├── .github/
│   ├── ISSUE_TEMPLATE/
│   │   ├── bug_report.md
│   │   └── feature_request.md
│   └── PULL_REQUEST_TEMPLATE.md
├── CODE_OF_CONDUCT.md
├── CONTRIBUTING.md
├── SECURITY.md
├── .gitignore
└── README.md

# Created at runtime (gitignored — keep private):
├── credentials.json             # Google OAuth credentials (OAuth only)
├── token.pickle                 # saved OAuth token (OAuth only)
└── .venv/                       # Python virtual environment (setup script)
```

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Bug reports and feature requests welcome — use the issue templates.

## Security

To report a vulnerability privately, see [SECURITY.md](SECURITY.md).

## License

MIT — see [LICENSE](LICENSE).
