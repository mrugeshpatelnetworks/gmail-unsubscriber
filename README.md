# Gmail Unsubscriber

A privacy-first command-line tool that scans **multiple Gmail accounts**, finds every unique sender across all of them, and lets you **unsubscribe and bulk-delete** unread emails — all from one checklist.

```
┌──────────────────────────────────────────────────────────┐
│   Gmail Unsubscriber  ·  Multi-Account Edition           │
│   Scan · Select · Unsubscribe · Delete                   │
└──────────────────────────────────────────────────────────┘

✓ 2 accounts detected.

Which accounts should be scanned?
  ✓  you@gmail.com        [IMAP]
  ✓  other@gmail.com      [IMAP]

Scanning you@gmail.com…       ████████████  1000/1000
Scanning other@gmail.com…     ████████████  1000/1000

Total: 184 unique sender(s) across 2 account(s).

  #   Account              Display Name         Email                   Count  Unsub
  1   you@gmail.com        Shopify              no-reply@shopify.com      47    yes
  2   other@gmail.com      LinkedIn             messages@linkedin.com     31    yes
  3   you@gmail.com        Newsletter Co        hello@newsletter.co       18    yes
  ...

Select senders to UNSUBSCRIBE from:
  [ ] Shopify  (47 emails)
  ✓   LinkedIn  (31 emails)
  ✓   Newsletter Co  (18 emails)
```

---

## Features

| Feature | Details |
|---|---|
| **Multi-account** | Scan 2, 5, or 10 Gmail accounts in one run |
| **Env var auth** | Reads App Passwords from environment variables — no Google Console setup per account |
| **OAuth fallback** | Still supports `credentials.json` if you already set that up |
| **All unread** | Scans your full inbox, not just the Promotions folder |
| **Privacy-first** | Only reads `From` and `List-Unsubscribe` headers — email body is never touched |
| **Auto-unsubscribe** | Sends unsubscribe emails via `List-Unsubscribe: <mailto:…>` automatically |
| **Browser fallback** | Opens HTTP unsubscribe links in your browser |
| **Bulk delete** | Moves all unread emails from selected senders to Trash |
| **Cross-platform** | Windows, Mac, Linux |

---

## Requirements

- Python 3.9 or higher
- Gmail with **2-Step Verification** enabled (needed for App Passwords)

---

## Setup

### Method A — App Password + Environment Variables *(recommended, easiest for multiple accounts)*

No Google Cloud Console setup needed. Works with any number of Gmail accounts.

#### Step 1 — Generate an App Password for each Gmail account

For **each** Gmail account you want to scan:

1. Go to [myaccount.google.com/security](https://myaccount.google.com/security)
2. Make sure **2-Step Verification** is turned ON (required)
3. In the search bar type **"App passwords"** and open it
   *(or go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords))*
4. Click **Create** → give it a name (e.g. "Gmail Unsubscriber") → **Create**
5. Copy the **16-character password** shown (with or without spaces)

#### Step 2 — Enable IMAP in Gmail

For **each** Gmail account:

1. Open Gmail → click the gear icon → **See all settings**
2. Go to the **Forwarding and POP/IMAP** tab
3. Under **IMAP access** → select **Enable IMAP**
4. Click **Save Changes**

#### Step 3 — Set environment variables

**Windows** (Command Prompt, permanent):
```cmd
setx GMAIL_EMAIL_1 "you@gmail.com"
setx GMAIL_APP_PASSWORD_1 "abcd efgh ijkl mnop"
setx GMAIL_EMAIL_2 "other@gmail.com"
setx GMAIL_APP_PASSWORD_2 "qrst uvwx yz12 3456"
```
> After `setx`, close and reopen your terminal for the variables to take effect.

**Windows** (PowerShell, permanent):
```powershell
[System.Environment]::SetEnvironmentVariable("GMAIL_EMAIL_1", "you@gmail.com", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL_APP_PASSWORD_1", "abcd efgh ijkl mnop", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL_EMAIL_2", "other@gmail.com", "User")
[System.Environment]::SetEnvironmentVariable("GMAIL_APP_PASSWORD_2", "qrst uvwx yz12 3456", "User")
```

**Mac / Linux** (add to `~/.zshrc` or `~/.bashrc`):
```bash
export GMAIL_EMAIL_1="you@gmail.com"
export GMAIL_APP_PASSWORD_1="abcd efgh ijkl mnop"
export GMAIL_EMAIL_2="other@gmail.com"
export GMAIL_APP_PASSWORD_2="qrst uvwx yz12 3456"
```
Then run `source ~/.zshrc` (or open a new terminal).

#### Naming conventions supported

All three formats work — use whichever fits your setup:

```bash
# Format 1 — numbered (recommended for multiple accounts)
GMAIL_EMAIL_1=you@gmail.com
GMAIL_APP_PASSWORD_1=xxxx xxxx xxxx xxxx
GMAIL_EMAIL_2=other@gmail.com
GMAIL_APP_PASSWORD_2=yyyy yyyy yyyy yyyy

# Format 2 — single (one account only)
GMAIL_EMAIL=you@gmail.com
GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

# Format 3 — comma-separated string
GMAIL_ACCOUNTS=you@gmail.com:xxxx xxxx xxxx xxxx,other@gmail.com:yyyy yyyy yyyy yyyy
```

---

### Method B — OAuth / Gmail API *(alternative, one-time Google Console setup)*

Use this only if you can't use App Passwords (e.g. a Google Workspace account with restrictions).

#### Step 1 — Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create or select a project
3. **APIs & Services → Enable APIs** → search **Gmail API** → Enable

#### Step 2 — Create OAuth credentials

1. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
2. If prompted, configure the consent screen first:
   - External → fill in App name + your email → Save and Continue through all steps
3. Application type: **Desktop app** → Create
4. **Download JSON** → rename to `credentials.json` → place in the project folder

#### Step 3 — Add yourself as a test user

1. **APIs & Services → OAuth consent screen → Test users → + Add Users**
2. Add your Gmail address

> For multiple OAuth accounts, save each credentials file as `credentials_account1.json`, `credentials_account2.json`, etc.

---

## Installation & running

### Windows
```cmd
pip install -r requirements.txt
python gmail_unsubscriber.py
```
Or double-click **`setup.bat`**.

### Mac / Linux
```bash
chmod +x setup.sh && ./setup.sh
```
Or manually:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python gmail_unsubscriber.py
```

---

## How to use

### 1. Account selection
If multiple accounts are detected, a checkbox lets you choose which ones to include in this scan.

### 2. Scan scope
```
Which emails should be scanned?
❯ All unread emails  (recommended — catches mislabelled promos)
  All emails — read + unread  (most thorough)
  Promotions folder only
  Inbox only (unread)
```

### 3. How many to scan
Enter a number per account (default: 1000). The tool fetches only headers — no message bodies.

### 4. Review the sender table
All unique senders across all accounts, sorted by email count. The **Account** column shows which Gmail account each sender wrote to.

### 5. Select senders to unsubscribe from
- **Space** — toggle a sender
- **A** — select all / deselect all
- **Enter** — confirm

### 6. Choose actions
```
What do you want to do?
  ✓ Unsubscribe (send request / open browser)
  ✓ Delete their unread emails
```

---

## Troubleshooting

### "IMAP error: [AUTHENTICATIONFAILED]"
- Wrong App Password — regenerate one at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- IMAP not enabled — Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP
- 2-Step Verification not on — required for App Passwords

### "No Gmail accounts found"
Environment variables aren't set or the terminal wasn't restarted after `setx`. Check with:
```powershell
# PowerShell
echo $env:GMAIL_EMAIL_1

# Command Prompt
echo %GMAIL_EMAIL_1%

# Mac/Linux
echo $GMAIL_EMAIL_1
```

### "Error 403: access_denied" (OAuth only)
Add your Gmail address as a test user:  
Google Cloud Console → APIs & Services → OAuth consent screen → Test users → + Add Users

### Unsubscribe opened a browser but nothing happened
Complete the unsubscribe step manually in the browser tab — some senders require a button click.

### I want to re-authenticate (OAuth only)
```bash
# Delete the saved token for that account
del token_you_at_gmail_com.pickle   # Windows
rm token_you_at_gmail_com.pickle    # Mac/Linux
```

---

## Privacy & security

- **Your emails never leave your machine.** IMAP connects directly from your computer to Gmail.
- **No message bodies are read.** Only `From` and `List-Unsubscribe` headers are fetched.
- **App Passwords are stored in your OS environment** — not in any file this tool writes.
- **`credentials.json` and `token*.pickle` are in `.gitignore`** and will never be committed.
- **Deleted emails go to Trash** (not permanent deletion) — recoverable for 30 days.

---

## OAuth permissions (if using Method B)

| Scope | Purpose |
|---|---|
| `gmail.readonly` | Read message headers |
| `gmail.send` | Send unsubscribe emails |
| `gmail.modify` | Move emails to Trash |

---

## Project structure

```
gmail-unsubscriber/
├── gmail_unsubscriber.py   ← main script
├── requirements.txt        ← Python dependencies
├── setup.bat               ← Windows one-click launcher
├── setup.sh                ← Mac/Linux one-click launcher
├── .gitignore
├── LICENSE
└── README.md

# Created at runtime (gitignored — never committed):
├── token_*.pickle          ← saved OAuth tokens
└── credentials*.json       ← your Google API credentials
```

---

## Contributing

Pull requests welcome. Ideas:

- [ ] Export sender list to CSV
- [ ] Dry-run mode (preview without acting)
- [ ] Per-account summary report
- [ ] Scheduled/automatic runs

---

## License

MIT — see [LICENSE](LICENSE).
