# Gmail Unsubscriber

A privacy-first **desktop GUI app** that scans your Gmail for promotional and newsletter emails, shows every unique sender in a searchable table, and lets you **unsubscribe and delete unread emails** in one click — including emails Gmail mislabelled and never put in the Promotions folder.

Supports **multiple Gmail accounts** simultaneously, auto-detects saved credentials from environment variables, and never sends your data to any third-party server.

---

## Features

| Feature | Details |
|---|---|
| **Desktop GUI** | Native PySide6 window — no terminal needed after setup |
| **Two sign-in methods** | Google OAuth (browser) or App Password + IMAP |
| **Multiple Gmail accounts** | Scan all accounts at once, deduplicated sender list |
| **Env-var auto-detect** | Reads saved Gmail credentials from environment variables automatically |
| **Four scan modes** | All unread, all mail, Promotions only, or Inbox only |
| **Real-time filter** | Search 400+ senders instantly by name or email |
| **Privacy-preserving** | Only reads `From` and `List-Unsubscribe` headers — email body is never touched |
| **Auto unsubscribe** | Sends unsubscribe emails via `List-Unsubscribe` header automatically |
| **Browser fallback** | Opens HTTP unsubscribe links in your browser when mailto isn't available |
| **Bulk delete** | Moves all unread emails from selected senders to Trash in one operation |
| **Works on Windows, Mac, Linux** | Pure Python + PySide6 |

---

## Screenshots

```
┌─ Gmail Unsubscriber ─────────────────────────────────────────────────────┐
│  Sign-in method                                                           │
│  ○ Sign in with Google  (OAuth — recommended)                             │
│  ● App Password + IMAP  (supports multiple accounts)                      │
│                                                                           │
│  ✓  Found 2 accounts in environment variables — passwords pre-filled.     │
│  ┌─ detected from env ──────────────────────────────────────────────────┐ │
│  │  you@gmail.com         [••••••••••••••••••••] 👁   ✓ Connected      │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────────────────────┐ │
│  │  other@gmail.com       [••••••••••••••••••••] 👁   ✓ Connected      │ │
│  └───────────────────────────────────────────────────────────────────────┘ │
│  + Add another account                                                    │
│                          [ Continue → ]                                   │
└───────────────────────────────────────────────────────────────────────────┘

┌─ Senders (312) ───────────────────────────────────────── 298 have unsub link ┐
│  🔍 Filter by name or email…                  [ Select All ] [ Clear ]       │
│  ┌────┬───────────────────────────┬──────────────────────────┬───────┬─────┐ │
│  │ ☑  │ Sender                    │ Email                    │ Count │ ✓   │ │
│  ├────┼───────────────────────────┼──────────────────────────┼───────┼─────┤ │
│  │ ☑  │ Shopify                   │ no-reply@shopify.com     │  47   │  ✓  │ │
│  │ ☑  │ LinkedIn                  │ messages@linkedin.com    │  31   │  ✓  │ │
│  │ ☐  │ Newsletter Co             │ hello@newsletter.co      │  18   │  ✓  │ │
│  └────┴───────────────────────────┴──────────────────────────┴───────┴─────┘ │
│  2 selected           [ Unsubscribe ] [ Delete Unread ] [ Both ✓ ]           │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Requirements

- Python 3.9 or higher
- A Gmail account
- For **OAuth sign-in**: a one-time Google Cloud setup (~3 minutes)
- For **App Password sign-in**: 2-Step Verification enabled on your Google account

---

## Step 1 — Download

**Clone with Git**
```bash
git clone https://github.com/mrugeshpatelnetworks/gmail-unsubscriber.git
cd gmail-unsubscriber
```

**Or download ZIP**
1. Click the green **Code** button → **Download ZIP**
2. Unzip and open a terminal inside the folder

---

## Step 2 — Install dependencies

### Windows
Double-click **`setup.bat`** — installs everything and launches the app automatically.

Or manually:
```cmd
pip install -r requirements.txt
python gmail_unsubscriber.py
```

### Mac / Linux
```bash
pip3 install -r requirements.txt
python3 gmail_unsubscriber.py
```

Or with a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python gmail_unsubscriber.py
```

---

## Step 3 — Choose a sign-in method

The app supports two ways to connect your Gmail. Pick whichever is easier for you.

---

### Method A — App Password + IMAP *(easier, supports multiple accounts)*

This method does not require any Google Cloud setup. It uses Gmail's IMAP protocol with an App Password — a special password just for this app.

#### 3A-1. Enable 2-Step Verification
If not already on: [myaccount.google.com/security](https://myaccount.google.com/security) → **2-Step Verification → Turn On**

#### 3A-2. Generate an App Password
1. Go to [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
2. Sign in if asked
3. Under **Select app** choose **Mail**; under **Select device** choose **Windows Computer** (or Mac/Linux)
4. Click **Generate** — copy the 16-character password shown
5. You won't see it again, but you can always generate a new one

#### 3A-3. Save credentials as environment variables *(optional but recommended)*

Saving your credentials as environment variables means the app auto-fills them every time — no typing.

**Windows (permanent):**
```cmd
setx GMAIL_EMAIL "you@gmail.com"
setx GMAIL_APP_PASSWORD "xxxx xxxx xxxx xxxx"
```
Close and reopen your terminal after running these. For a second account:
```cmd
setx GMAIL_EMAIL_2 "other@gmail.com"
setx GMAIL_APP_PASSWORD_2 "yyyy yyyy yyyy yyyy"
```

**Mac / Linux (add to `~/.zshrc` or `~/.bashrc`):**
```bash
export GMAIL_EMAIL="you@gmail.com"
export GMAIL_APP_PASSWORD="xxxx xxxx xxxx xxxx"

# Second account:
export GMAIL_EMAIL_2="other@gmail.com"
export GMAIL_APP_PASSWORD_2="yyyy yyyy yyyy yyyy"
```
Then run `source ~/.zshrc` (or restart your terminal).

**Supported variable names:**

| Purpose | Variable names accepted |
|---|---|
| Email | `GMAIL_EMAIL`, `GMAIL_USER`, `GOOGLE_EMAIL` |
| Password | `GMAIL_APP_PASSWORD`, `GMAIL_APP_PASS`, `GMAIL_PASSWORD`, `GMAIL_PASS` |
| Second account | `GMAIL_EMAIL_2`, `GMAIL_APP_PASSWORD_2` (up to `_9`) |

If credentials are found, the app shows a green banner and pre-fills all account rows automatically.

#### 3A-4. Launch the app
Run `python gmail_unsubscriber.py` (or double-click `setup.bat` on Windows).

In the app:
1. Select **App Password + IMAP**
2. If env vars were found — rows are pre-filled. Click **Connect →**
3. If not found — enter your Gmail address and App Password manually
4. Click **+ Add another account** to connect additional accounts
5. Click **Continue →** once all accounts show ✓ Connected

---

### Method B — Google OAuth *(single account, requires Google Cloud setup)*

Use this if you prefer not to use App Passwords, or if your organisation requires OAuth.

> This takes about 3 minutes the first time. You never need to do it again.

#### 3B-1. Create a Google Cloud project
1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Click the project dropdown → **New Project** → name it anything → **Create**

#### 3B-2. Enable the Gmail API
1. **APIs & Services → Library** → search **Gmail API** → **Enable**

#### 3B-3. Create OAuth credentials
1. **APIs & Services → Credentials → + Create Credentials → OAuth client ID**
2. If asked to configure the consent screen:
   - Choose **External** → **Create**
   - Fill in App name, your Gmail as support and developer email
   - Click through all steps → **Save and Continue**
3. Back in Credentials: Application type → **Desktop app** → **Create**
4. Click **Download JSON** → rename the file to **`credentials.json`**
5. Place `credentials.json` in the same folder as `gmail_unsubscriber.py`

#### 3B-4. Add yourself as a test user
1. **APIs & Services → OAuth consent screen → Test users → + Add Users**
2. Enter your Gmail address → **Save**

> Without this step, sign-in will fail with "Error 403: access_denied"

#### 3B-5. Launch the app
Run `python gmail_unsubscriber.py`. Select **Sign in with Google (OAuth)** → **Connect →**. A browser window opens — sign in and grant access. Your token is saved to `token.pickle` so you won't need to sign in again.

---

## Step 4 — Configure the scan

After connecting, you'll see the **Configure Scan** screen:

| Option | Recommended? |
|---|---|
| All unread emails | ✅ Recommended — catches promos Gmail mislabelled |
| All emails (read + unread) | Use if you want the most thorough scan (slower) |
| Promotions folder only | Use if you only want the obvious newsletters |
| Inbox unread only | Use for a quick inbox-only pass |

Drag the slider to set how many emails to scan per account (100 – 10,000). Default is 1,000.

Click **Start Scan →**

---

## Step 5 — Review senders and take action

The **Senders** screen shows every unique sender found:

- **Click any row** or press **Space** to check / uncheck a sender
- **Type in the filter box** to instantly search by name or email
- **Select All** / **Clear** buttons for bulk selection
- The **✓** column shows whether a sender has an unsubscribe link

When ready, pick an action:

| Button | What it does |
|---|---|
| **Unsubscribe** | Sends unsubscribe email automatically, or opens browser link |
| **Delete Unread** | Moves all unread emails from that sender to Trash |
| **Both ✓** | Does both at the same time |

Confirm the dialog and the **Processing** screen shows live progress per sender.

---

## Troubleshooting

### "Error 403: access_denied" (OAuth)
You haven't added yourself as a test user — follow **Step 3B-4**.

### "Login failed" (IMAP)
- Make sure **2-Step Verification is ON** on your Google account (required for App Passwords)
- Regenerate your App Password at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
- Make sure **IMAP is enabled** in Gmail: Settings → See all settings → Forwarding and POP/IMAP → Enable IMAP

### "credentials.json not found" (OAuth)
Place `credentials.json` in the same folder as `gmail_unsubscriber.py`.

### Env vars not being detected
- On Windows, restart your terminal after running `setx`
- Confirm the variable exists: `echo %GMAIL_EMAIL%` (Windows) or `echo $GMAIL_EMAIL` (Mac/Linux)
- The email must contain `@gmail.com` or `@googlemail.com`

### The app asks me to sign in every time (OAuth)
Delete `token.pickle` and re-authenticate:
```bash
rm token.pickle        # Mac / Linux
del token.pickle       # Windows
```

### An unsubscribe link opened in my browser but nothing happened
Some senders require you to click a confirm button on their page. Complete the step manually in the browser tab.

---

## Privacy & Security

- **Your emails never leave your computer.** The app talks directly to Gmail — no third-party servers.
- **No email body is read.** Only `From` and `List-Unsubscribe` headers are fetched.
- **`credentials.json` and `token.pickle` are in `.gitignore`** and will never be committed.
- **Deleted emails go to Trash**, not permanent deletion. You have 30 days to recover them in Gmail.
- App Passwords can be revoked any time at [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords).

---

## Gmail API permission scopes (OAuth only)

| Scope | Why it's needed |
|---|---|
| `gmail.readonly` | Read email headers to find senders |
| `gmail.send` | Send unsubscribe emails via `mailto:` links |
| `gmail.modify` | Move emails to Trash |

---

## Project structure

```
gmail-unsubscriber/
├── gmail_unsubscriber.py   # main app (PySide6 GUI)
├── requirements.txt        # Python dependencies
├── setup.bat               # Windows one-click launcher
├── .gitignore              # excludes credentials and token
└── README.md               # this file

# Created at runtime — gitignored, keep private:
├── credentials.json        # Google OAuth credentials (OAuth method only)
└── token.pickle            # saved OAuth login token (OAuth method only)
```

---

## License

MIT — see [LICENSE](LICENSE).
