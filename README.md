# Gmail Unsubscriber

A privacy-first command-line tool that scans your Gmail for promotional and newsletter emails, shows you a checklist of every unique sender, and lets you **unsubscribe and delete** in one go — including emails Gmail mislabelled and never put in the Promotions folder.

```
┌─────────────────────────────────────────────┐
│       Gmail Promotional Email Unsubscriber  │
│           Scan · Select · Unsubscribe       │
└─────────────────────────────────────────────┘

Which emails should be scanned for senders?
❯ All unread emails  (catches promos Gmail missed)
  All emails — read + unread  (most thorough)
  Promotions folder only
  Inbox only (unread)

  #   Display Name             Email                          Count   Unsub Link
  1   Shopify                  no-reply@shopify.com             47      yes
  2   LinkedIn                 messages-noreply@linkedin.com    31      yes
  3   Newsletter Co            hello@newsletter.co              18      yes
  ...

Select senders to UNSUBSCRIBE from:
  [ ] Shopify <no-reply@shopify.com>  (47 emails)
  [ ] LinkedIn <messages-noreply@linkedin.com>  (31 emails)
  ✓   Newsletter Co <hello@newsletter.co>  (18 emails)
```

---

## Features

- **Scans all unread email** — not just the Promotions folder, so nothing is missed
- **Privacy-preserving** — only reads email headers (From, List-Unsubscribe), never the body
- **Automatic unsubscribe** — sends unsubscribe emails via `List-Unsubscribe` header automatically
- **Browser fallback** — opens HTTP unsubscribe links in your browser when mailto: isn't available
- **Bulk delete** — moves all unread emails from selected senders to Trash in one batch operation
- **Four scan modes** — all unread, all mail, promotions only, or inbox only
- **Works on Windows, Mac, and Linux**

---

## Requirements

- Python 3.9 or higher
- A Google account (Gmail)
- 3 minutes for one-time Google API setup

---

## Step 1 — Download the code

**Option A — Clone with Git**
```bash
git clone https://github.com/YOUR_USERNAME/gmail-unsubscriber.git
cd gmail-unsubscriber
```

**Option B — Download ZIP**
1. Click the green **Code** button at the top of this page
2. Click **Download ZIP**
3. Unzip the folder and open a terminal inside it

---

## Step 2 — Set up Gmail API access (one time only)

This tool uses Google's official Gmail API. You need to create your own API credentials — this keeps your data completely private (no third-party servers involved).

> **This takes about 3 minutes the first time. You never need to do it again.**

### 2a. Create a Google Cloud project

1. Go to [https://console.cloud.google.com/](https://console.cloud.google.com/)
2. Click the project dropdown at the top → **New Project**
3. Give it any name (e.g. `gmail-unsubscriber`) → **Create**
4. Make sure the new project is selected in the dropdown

### 2b. Enable the Gmail API

1. In the left menu go to **APIs & Services → Library**
2. Search for **Gmail API**
3. Click it → click **Enable**

### 2c. Create OAuth credentials

1. Go to **APIs & Services → Credentials**
2. Click **+ Create Credentials → OAuth client ID**
3. If prompted to configure the consent screen first:
   - Click **Configure Consent Screen**
   - Choose **External** → **Create**
   - Fill in **App name** (any name), **User support email** (your Gmail), **Developer contact email** (your Gmail)
   - Click **Save and Continue** through all steps (you can leave everything else blank)
   - Click **Back to Dashboard**
   - Go back to **Credentials → + Create Credentials → OAuth client ID**
4. For **Application type** choose **Desktop app**
5. Give it any name → **Create**
6. Click **Download JSON** on the confirmation dialog
7. Rename the downloaded file to exactly **`credentials.json`**
8. Move it into the `gmail-unsubscriber` folder (same folder as `gmail_unsubscriber.py`)

### 2d. Add yourself as a test user

Because this app is in "Testing" mode, only explicitly added users can sign in.

1. Go to **APIs & Services → OAuth consent screen**
2. Scroll down to **Test users** → click **+ Add Users**
3. Enter your Gmail address → **Save**

> **Note:** You only need to add yourself. This is a local tool — no one else signs in.

---

## Step 3 — Install and run

### Windows

Double-click **`setup.bat`** — it installs dependencies and launches the tool automatically.

Or in a terminal:
```cmd
pip install -r requirements.txt
python gmail_unsubscriber.py
```

### Mac / Linux

```bash
chmod +x setup.sh
./setup.sh
```

Or manually:
```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python gmail_unsubscriber.py
```

### First run

A browser window will open asking you to sign into your Google account. Grant the requested permissions and return to the terminal. The tool will start scanning immediately.

Your login is saved to `token.pickle` so you won't need to sign in again.

---

## Step 4 — Using the tool

### Choose what to scan

```
Which emails should be scanned for senders?
❯ All unread emails  (catches promos Gmail missed) ← recommended
  All emails — read + unread  (most thorough)
  Promotions folder only
  Inbox only (unread)
```

**Recommended:** "All unread emails" catches promotional emails that Gmail incorrectly sorted into your inbox instead of Promotions.

### Choose how many to scan

```
How many emails to scan? [1000]
```

Enter a number or press Enter to use the default (1000). Higher numbers take longer but find more senders.

### Review the sender table

The tool displays every unique sender with:
- Their display name and email address
- How many emails they've sent you
- Whether they include an unsubscribe link

### Select senders to unsubscribe from

```
Select senders to UNSUBSCRIBE from:
  (Space = toggle, A = select all/none, Enter = confirm)

  [ ] Shopify <no-reply@shopify.com>  (47 emails)
  [ ] LinkedIn <messages-noreply@linkedin.com>  (31 emails)
  [ ] Newsletter Co <hello@newsletter.co>  (18 emails)
```

- Press **Space** to select/deselect a sender
- Press **A** to select all or deselect all
- Press **Enter** when done

### Choose what to do

```
What do you want to do?
  ✓ Unsubscribe  (send unsubscribe request / open browser)
  ✓ Delete unread emails from these senders
```

Both are selected by default. Uncheck either one if you only want to do one action.

---

## Troubleshooting

### "Error 403: access_denied"

You haven't added yourself as a test user. Follow **Step 2d** above.

### "credentials.json not found"

The credentials file is missing or in the wrong location. Make sure `credentials.json` is in the same folder as `gmail_unsubscriber.py`. Follow **Step 2c** above.

### The tool asks me to sign in every time

Delete `token.pickle` and sign in again. The token may have expired or been revoked.

```bash
# Mac / Linux
rm token.pickle

# Windows
del token.pickle
```

### Unsubscribe opened a browser but nothing happened

Some senders require you to click a button on their unsubscribe page. The tool opens the page — complete the step manually in the browser tab.

### I want to re-authenticate (switch accounts)

Delete the saved token and restart:
```bash
rm token.pickle   # or: del token.pickle on Windows
python gmail_unsubscriber.py
```

---

## Privacy & Security

- **Your emails never leave your computer.** The tool calls Gmail API directly from your machine.
- **No email body is read.** Only the `From` and `List-Unsubscribe` headers are fetched.
- **`credentials.json` and `token.pickle` are in `.gitignore`** and will never be committed if you fork this repo.
- **Deleted emails go to Trash**, not permanent deletion. You have 30 days to recover them.

---

## Permissions explained

The tool requests three Gmail scopes:

| Scope | Why it's needed |
|---|---|
| `gmail.readonly` | Read email headers to find senders |
| `gmail.send` | Send unsubscribe emails via `mailto:` links |
| `gmail.modify` | Move emails to Trash (batchModify) |

---

## Project structure

```
gmail-unsubscriber/
├── gmail_unsubscriber.py   # main script
├── requirements.txt        # Python dependencies
├── setup.bat               # Windows one-click launcher
├── setup.sh                # Mac/Linux one-click launcher
├── .gitignore              # excludes credentials and token
├── LICENSE                 # MIT
└── README.md               # this file

# These are created at runtime and gitignored:
├── credentials.json        # your Google API credentials (keep private)
└── token.pickle            # your saved login token (keep private)
```

---

## Contributing

Pull requests welcome! Some ideas for improvements:

- [ ] Export sender list to CSV
- [ ] Filter senders by domain
- [ ] Dry-run mode (show what would be deleted without doing it)
- [ ] Unsubscribe success/failure log file
- [ ] Support for multiple Gmail accounts

---

## License

MIT — see [LICENSE](LICENSE).
