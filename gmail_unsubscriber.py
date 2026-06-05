#!/usr/bin/env python3
"""
Gmail Promotional Email Unsubscriber
-------------------------------------
At startup you choose:
  A) OAuth via credentials.json  — single account, Google Console setup once
  B) App Password + IMAP         — enter email + password in terminal,
                                   supports as many accounts as you like

GitHub: https://github.com/YOUR_USERNAME/gmail-unsubscriber
"""

import re
import base64
import imaplib
import smtplib
import pickle
import webbrowser
from pathlib import Path
from collections import defaultdict
from email.mime.text import MIMEText

import questionary
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn
from rich.panel import Panel

# ── Optional: OAuth / Gmail API ───────────────────────────────────────────────
try:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as _build
    OAUTH_AVAILABLE = True
except ImportError:
    OAUTH_AVAILABLE = False

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
TOKEN_FILE = Path(__file__).parent / "token.pickle"
CREDS_FILE = Path(__file__).parent / "credentials.json"

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

SCAN_MODES = {
    "all_unread":  ("All unread emails  (catches promos Gmail missed)",
                    "UNSEEN",  '"[Gmail]/All Mail"', None),
    "all_mail":    ("All emails — read + unread  (most thorough)",
                    "ALL",     '"[Gmail]/All Mail"', None),
    "promos_only": ("Promotions folder only",
                    "ALL",     '"[Gmail]/All Mail"', "category:promotions"),
    "inbox":       ("Inbox only  (unread)",
                    "UNSEEN",  "INBOX",              None),
}

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# IMAP helpers
# ─────────────────────────────────────────────────────────────────────────────

def _imap_connect(email: str, password: str) -> imaplib.IMAP4_SSL:
    """Open an authenticated IMAP connection. Raises on failure."""
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(email, password)
    return mail


def _parse_from_str(value: str) -> tuple:
    m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', value.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    v = value.strip()
    return v, v.lower()


def _parse_unsub_str(value: str) -> dict | None:
    if not value:
        return None
    mailto = re.findall(r"<(mailto:[^>]+)>", value, re.I)
    http   = re.findall(r"<(https?://[^>]+)>", value, re.I)
    if not mailto and not http:
        return None
    return {
        "mailto": mailto[0] if mailto else None,
        "http":   http[0]   if http   else None,
    }


def _imap_fetch_senders(mail: imaplib.IMAP4_SSL,
                         max_results: int,
                         mode_key: str,
                         account_email: str) -> dict:
    """
    Fetch unique senders from one IMAP connection.
    Only reads From + List-Unsubscribe headers — body is never downloaded.
    """
    _, search_term, folder, gm_raw = SCAN_MODES[mode_key]

    # Select folder (read-only for safety during scan)
    typ, _ = mail.select(folder, readonly=True)
    if typ != "OK":
        raise RuntimeError(f"Cannot open folder {folder} for {account_email}")

    # Search for message UIDs
    if gm_raw:
        # Gmail-specific IMAP extension for category search
        typ, data = mail.uid("SEARCH", "CHARSET", "UTF-8",
                             "X-GM-RAW", gm_raw)
    else:
        typ, data = mail.uid("SEARCH", None, search_term)

    if typ != "OK" or not data or not data[0]:
        return {}

    all_uids = data[0].split()          # list of bytes, e.g. [b'1', b'2', ...]
    # Work newest-first, cap at max_results
    uids_to_fetch = all_uids[-max_results:][::-1]

    senders: dict = defaultdict(lambda: {
        "name": "", "email": "", "count": 0,
        "unsubscribe": None, "account": account_email,
    })

    BATCH = 50   # fetch 50 headers per IMAP round-trip

    with Progress(
        SpinnerColumn(),
        TextColumn(f"  [cyan]{account_email}[/cyan] scanning…"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("", total=len(uids_to_fetch))

        for i in range(0, len(uids_to_fetch), BATCH):
            batch = uids_to_fetch[i : i + BATCH]
            # UIDs as a comma-separated ASCII string
            uid_str = ",".join(u.decode() for u in batch)

            try:
                typ, msg_data = mail.uid(
                    "FETCH", uid_str,
                    "(BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)])",
                )
            except Exception:
                progress.update(task, advance=len(batch))
                continue

            if typ != "OK" or not msg_data:
                progress.update(task, advance=len(batch))
                continue

            # IMAP FETCH response alternates: (metadata, header_bytes), b')', ...
            for item in msg_data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw = item[1]
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")

                # Parse raw header block
                from_val  = ""
                unsub_val = ""
                for line in raw.splitlines():
                    ll = line.lower()
                    if ll.startswith("from:"):
                        from_val = line[5:].strip()
                    elif ll.startswith("list-unsubscribe:"):
                        unsub_val = line[17:].strip()
                    elif line.startswith((" ", "\t")):
                        # Header continuation
                        if unsub_val:
                            unsub_val += " " + line.strip()

                if not from_val:
                    continue

                name, email_addr = _parse_from_str(from_val)
                unsub            = _parse_unsub_str(unsub_val)

                s = senders[email_addr]
                s["name"]  = s["name"] or name
                s["email"] = email_addr
                s["count"] += 1
                if unsub and not s["unsubscribe"]:
                    s["unsubscribe"] = unsub

            progress.update(task, advance=len(batch))

    return dict(senders)


def _imap_delete_unread(mail: imaplib.IMAP4_SSL,
                         sender_emails: list,
                         account_email: str) -> int:
    """Move all unread emails from sender_emails to Trash. Returns count moved."""
    # Need write access for delete
    mail.select('"[Gmail]/All Mail"', readonly=False)
    total = 0

    for sender_email in sender_emails:
        try:
            # Search unread from this sender
            typ, data = mail.uid(
                "SEARCH", "CHARSET", "UTF-8",
                "UNSEEN", "FROM", f'"{sender_email}"',
            )
            if typ != "OK" or not data or not data[0]:
                continue

            uids = data[0].split()
            if not uids:
                continue

            # Process in batches of 100
            for i in range(0, len(uids), 100):
                batch   = uids[i : i + 100]
                uid_str = ",".join(u.decode() for u in batch)

                # Copy to Trash folder
                mail.uid("COPY", uid_str, '"[Gmail]/Trash"')
                # Mark deleted in All Mail so expunge removes it there too
                mail.uid("STORE", uid_str, "+FLAGS", "(\\Deleted)")
                total += len(batch)

            mail.expunge()

        except Exception as e:
            console.print(f"    [red]Error trashing mail from {sender_email}: {e}[/red]")

    return total


def _imap_send_unsub(email: str, password: str, mailto_url: str) -> bool:
    """Send an unsubscribe email via SMTP using the app password."""
    m = re.match(r"mailto:([^?]+)(?:\?(.*))?", mailto_url, re.I)
    if not m:
        return False
    to_addr = m.group(1).strip()
    params: dict = {}
    if m.group(2):
        for kv in m.group(2).split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                params[k.lower()] = v.replace("+", " ")
    subject = params.get("subject", "Unsubscribe")
    body    = params.get("body",    "Please unsubscribe me from this mailing list.")
    try:
        msg            = MIMEText(body)
        msg["From"]    = email
        msg["To"]      = to_addr
        msg["Subject"] = subject
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(email, password)
            smtp.sendmail(email, to_addr, msg.as_string())
        return True
    except Exception as e:
        console.print(f"    [red]SMTP error: {e}[/red]")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# OAuth helpers  (unchanged from v1)
# ─────────────────────────────────────────────────────────────────────────────

def _oauth_get_service():
    if not OAUTH_AVAILABLE:
        console.print("[red]OAuth libraries not installed. Run: pip install google-auth google-auth-oauthlib google-api-python-client[/red]")
        raise SystemExit(1)
    if not CREDS_FILE.exists():
        console.print(Panel(
            "[bold red]credentials.json not found![/bold red]\n\n"
            "One-time setup (3 minutes):\n"
            "1. https://console.cloud.google.com/ → create/select a project\n"
            "2. APIs & Services → Enable APIs → Gmail API → Enable\n"
            "3. Credentials → + Create Credentials → OAuth client ID\n"
            "   (configure consent screen if prompted → External)\n"
            "4. Application type: [bold]Desktop app[/bold] → Create → Download JSON\n"
            "5. Rename to [bold]credentials.json[/bold] and place next to this script\n"
            "6. OAuth consent screen → Test users → + Add Users → your Gmail",
            title="Setup Required", border_style="red",
        ))
        raise SystemExit(1)

    creds = None
    if TOKEN_FILE.exists():
        with open(TOKEN_FILE, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            flow  = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), OAUTH_SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return _build("gmail", "v1", credentials=creds)


def _oauth_fetch_senders(service, max_results: int, mode_key: str) -> dict:
    _, search_term, folder, gm_raw = SCAN_MODES[mode_key]
    query     = "is:unread" if search_term == "UNSEEN" else ""
    label_ids = None
    if folder == "INBOX":
        label_ids = ["INBOX"]
    if gm_raw == "category:promotions":
        label_ids = ["CATEGORY_PROMOTIONS"]
        query     = ""

    senders   = defaultdict(lambda: {"name":"","email":"","count":0,"unsubscribe":None,"account":"OAuth"})
    page_tok  = None
    fetched   = 0

    with Progress(SpinnerColumn(),
                  TextColumn("  [cyan]OAuth account[/cyan] scanning…"),
                  BarColumn(), MofNCompleteColumn(),
                  console=console, transient=True) as progress:
        task = progress.add_task("", total=max_results)
        while fetched < max_results:
            batch  = min(100, max_results - fetched)
            kwargs = dict(userId="me", maxResults=batch)
            if query:
                kwargs["q"] = query
            if label_ids:
                kwargs["labelIds"] = label_ids
            if page_tok:
                kwargs["pageToken"] = page_tok
            res  = service.users().messages().list(**kwargs).execute()
            msgs = res.get("messages", [])
            if not msgs:
                break
            for msg in msgs:
                try:
                    d     = service.users().messages().get(
                        userId="me", id=msg["id"], format="metadata",
                        metadataHeaders=["From", "List-Unsubscribe"],
                    ).execute()
                    hdrs  = d.get("payload", {}).get("headers", [])
                    fv    = next((h["value"] for h in hdrs if h["name"].lower() == "from"), "")
                    uv    = next((h["value"] for h in hdrs if h["name"].lower() == "list-unsubscribe"), "")
                    name, ea = _parse_from_str(fv)
                    unsub    = _parse_unsub_str(uv)
                    s = senders[ea]
                    s["name"]  = s["name"] or name
                    s["email"] = ea
                    s["count"] += 1
                    if unsub and not s["unsubscribe"]:
                        s["unsubscribe"] = unsub
                except Exception:
                    pass
                fetched += 1
                progress.update(task, advance=1)
                if fetched >= max_results:
                    break
            page_tok = res.get("nextPageToken")
            if not page_tok:
                break
    return dict(senders)


def _oauth_delete_unread(service, sender_emails: list) -> int:
    total = 0
    for ea in sender_emails:
        page_tok = None
        ids = []
        while True:
            kwargs = dict(userId="me", q=f"from:{ea} is:unread", maxResults=500)
            if page_tok:
                kwargs["pageToken"] = page_tok
            res = service.users().messages().list(**kwargs).execute()
            ids.extend(m["id"] for m in res.get("messages", []))
            page_tok = res.get("nextPageToken")
            if not page_tok:
                break
        for i in range(0, len(ids), 1000):
            chunk = ids[i : i + 1000]
            service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk,
                      "addLabelIds": ["TRASH"],
                      "removeLabelIds": ["INBOX","UNREAD","CATEGORY_PROMOTIONS"]},
            ).execute()
            total += len(chunk)
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────

def show_table(senders: dict, multi_account: bool = False):
    table = Table(
        title=f"[bold]Unique Senders[/bold]  ({len(senders)} total)",
        header_style="bold cyan", show_lines=False,
    )
    table.add_column("#",            style="dim",     width=4,  justify="right")
    if multi_account:
        table.add_column("Account",  style="magenta", max_width=24)
    table.add_column("Display Name", style="white",   min_width=22, max_width=32)
    table.add_column("Email",        style="cyan",    min_width=26, max_width=40)
    table.add_column("Count",        style="yellow",  width=6,  justify="right")
    table.add_column("Unsub Link",   style="green",   width=10, justify="center")

    for i, s in enumerate(
        sorted(senders.values(), key=lambda x: x["count"], reverse=True), 1
    ):
        row = [str(i)]
        if multi_account:
            row.append(s.get("account","")[:24])
        row += [
            (s["name"] or "—")[:32],
            s["email"][:40],
            str(s["count"]),
            "[green]yes[/green]" if s["unsubscribe"] else "[red dim]no[/red dim]",
        ]
        table.add_row(*row)
    console.print(table)


def choose_senders(senders: dict, multi_account: bool = False) -> list:
    sorted_s  = sorted(senders.values(), key=lambda x: x["count"], reverse=True)
    can_unsub = [s for s in sorted_s if s["unsubscribe"]]
    no_link   = [s for s in sorted_s if not s["unsubscribe"]]

    if no_link:
        console.print(f"[yellow]{len(no_link)} sender(s) have no unsubscribe link (excluded).[/yellow]")
    if not can_unsub:
        console.print("[red]No senders with an unsubscribe link found.[/red]")
        return []

    choices = [
        questionary.Choice(
            title=(
                (f"[{s['account'][:20]}]  " if multi_account else "")
                + f"{(s['name'] or s['email'])[:30]:30}  "
                + f"<{s['email'][:36]}>"
                + f"  ({s['count']} emails)"
            ),
            value=s["email"],
            checked=False,
        )
        for s in can_unsub
    ]

    console.print("\n[bold]Space[/bold]=toggle  [bold]A[/bold]=all/none  [bold]Enter[/bold]=confirm\n")
    return questionary.checkbox("Select senders to UNSUBSCRIBE from:", choices=choices).ask() or []


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold cyan]Gmail Promotional Email Unsubscriber[/bold cyan]\n"
        "[dim]Scan · Select · Unsubscribe · Delete[/dim]",
        border_style="cyan",
    ))

    # ── Step 1: Choose auth method ────────────────────────────────────────
    method = questionary.select(
        "How do you want to sign in to Gmail?",
        choices=[
            questionary.Choice(
                "App Password  (enter email + password here — supports multiple accounts)",
                value="imap",
            ),
            questionary.Choice(
                "Google OAuth  (opens browser, uses credentials.json — single account)",
                value="oauth",
            ),
        ],
    ).ask()

    if method is None:
        return

    # ── Step 2: Collect account credentials ──────────────────────────────
    accounts = []   # list of {"email": ..., "password": ...}  (IMAP only)
    service  = None  # OAuth only

    if method == "imap":
        num_str = questionary.select(
            "How many Gmail accounts do you want to scan?",
            choices=["1", "2", "3", "4", "5"],
        ).ask()
        if num_str is None:
            return
        num_accounts = int(num_str)

        for i in range(1, num_accounts + 1):
            console.print(f"\n[bold]Account {i} of {num_accounts}[/bold]")

            email = questionary.text(
                "Gmail address:",
                validate=lambda v: "@" in v or "Enter a valid email",
            ).ask()
            if email is None:
                return
            email = email.strip()

            console.print(
                "[dim]App Password = 16-char code from "
                "myaccount.google.com/apppasswords\n"
                "Regular password works only if 2FA is OFF (not recommended)[/dim]"
            )
            password = questionary.password("Password or App Password:").ask()
            if password is None:
                return

            # Test the connection before continuing
            console.print(f"  [cyan]Testing connection…[/cyan]", end=" ")
            try:
                test = _imap_connect(email, password.strip())
                test.logout()
                console.print("[green]✓[/green]")
                accounts.append({"email": email, "password": password.strip()})
            except imaplib.IMAP4.error as e:
                console.print(f"[red]✗ Failed[/red]")
                console.print(Panel(
                    f"[red]Could not sign in to {email}[/red]\n\n"
                    "Common causes:\n"
                    "• Wrong App Password — regenerate at myaccount.google.com/apppasswords\n"
                    "• IMAP not enabled — Gmail → Settings → Forwarding and POP/IMAP → Enable IMAP\n"
                    "• 2-Step Verification is OFF — required for App Passwords\n\n"
                    f"[dim]Error: {e}[/dim]",
                    border_style="red",
                ))
                retry = questionary.confirm("Try a different password for this account?").ask()
                if retry:
                    password = questionary.password("Password or App Password:").ask()
                    if password is None:
                        return
                    try:
                        test = _imap_connect(email, password.strip())
                        test.logout()
                        console.print(f"  [green]✓ Connected[/green]")
                        accounts.append({"email": email, "password": password.strip()})
                    except Exception as e2:
                        console.print(f"  [red]✗ Still failed: {e2} — skipping this account.[/red]")
                else:
                    console.print(f"  [yellow]Skipping {email}[/yellow]")

        if not accounts:
            console.print("[red]No accounts connected — exiting.[/red]")
            return

    else:
        # OAuth
        console.print("\n[cyan]Connecting via OAuth…[/cyan]")
        service = _oauth_get_service()
        console.print("[green]✓ Connected[/green]")

    # ── Step 3: Scan options ──────────────────────────────────────────────
    mode_key = questionary.select(
        "\nWhich emails should be scanned?",
        choices=[
            questionary.Choice(
                "All unread emails  (recommended — catches mislabelled promos)",
                value="all_unread",
            ),
            questionary.Choice(
                "All emails — read + unread  (most thorough, slower)",
                value="all_mail",
            ),
            questionary.Choice("Promotions folder only",  value="promos_only"),
            questionary.Choice("Inbox only  (unread)",    value="inbox"),
        ],
        default="all_unread",
    ).ask()
    if mode_key is None:
        return

    raw = questionary.text(
        f"How many emails to scan{'per account' if len(accounts) > 1 else ''}?",
        default="1000",
        validate=lambda v: v.isdigit() and int(v) > 0 or "Enter a positive number",
    ).ask()
    if raw is None:
        return
    max_results = int(raw)

    # ── Step 4: Scan ──────────────────────────────────────────────────────
    all_senders: dict = {}    # keyed by "email||account" to allow same sender in 2 accounts
    imap_conns:  dict = {}    # account_email -> (imap_conn, password) for actions later

    if method == "imap":
        for acct in accounts:
            console.print(f"\n[bold]Scanning[/bold] [cyan]{acct['email']}[/cyan]…")
            try:
                mail = _imap_connect(acct["email"], acct["password"])
                imap_conns[acct["email"]] = (mail, acct["password"])
                senders = _imap_fetch_senders(mail, max_results, mode_key, acct["email"])
                console.print(f"  [green]✓ {len(senders)} unique sender(s) found[/green]")
                for email_addr, data in senders.items():
                    key = f"{email_addr}||{acct['email']}"
                    all_senders[key] = data
            except Exception as e:
                console.print(f"  [red]Scan failed: {e}[/red]")
    else:
        senders = _oauth_fetch_senders(service, max_results, mode_key)
        console.print(f"  [green]✓ {len(senders)} unique sender(s) found[/green]")
        for email_addr, data in senders.items():
            all_senders[f"{email_addr}||OAuth"] = data

    if not all_senders:
        console.print("[yellow]No senders found.[/yellow]")
        return

    # Flatten for display: merge counts if same sender appears in 2+ accounts
    flat: dict = {}
    for key, data in all_senders.items():
        sender_email = key.split("||")[0]
        if sender_email not in flat:
            flat[sender_email] = dict(data)
        else:
            flat[sender_email]["count"] += data["count"]

    multi = len(accounts) > 1
    console.print(f"\n[green]Found {len(flat)} unique sender(s)"
                  + (f" across {len(accounts)} accounts" if multi else "")
                  + ".[/green]\n")
    show_table(flat, multi_account=multi)

    # ── Step 5: Select senders ────────────────────────────────────────────
    selected = choose_senders(flat, multi_account=multi)
    if not selected:
        console.print("\n[yellow]Nothing selected — bye![/yellow]")
        return

    # ── Step 6: Actions ───────────────────────────────────────────────────
    console.print(f"\n[bold]{len(selected)} sender(s) selected.[/bold]")
    actions = questionary.checkbox(
        "What do you want to do?",
        choices=[
            questionary.Choice("Unsubscribe  (send request / open browser)",
                               value="unsub",   checked=True),
            questionary.Choice("Delete their unread emails",
                               value="delete",  checked=True),
        ],
    ).ask() or []

    if not actions:
        console.print("[yellow]No actions chosen — bye![/yellow]")
        return
    if not questionary.confirm("Proceed?").ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # ── Step 7: Execute ───────────────────────────────────────────────────
    if "unsub" in actions:
        console.print(f"\n[bold cyan]Unsubscribing from {len(selected)} sender(s)…[/bold cyan]\n")
        ok_mail, ok_web, failed = [], [], []

        for sender_email in selected:
            data  = flat[sender_email]
            unsub = data["unsubscribe"]
            acct  = data.get("account", "")
            console.print(f"  [white]{data['name'] or sender_email} <{sender_email}>[/white]"
                          + (f"  [dim]({acct})[/dim]" if multi else ""))

            sent = False
            if unsub and unsub.get("mailto"):
                if method == "imap" and acct in imap_conns:
                    _, pwd = imap_conns[acct]
                    sent = _imap_send_unsub(acct, pwd, unsub["mailto"])
                elif method == "oauth" and service:
                    try:
                        m2    = re.match(r"mailto:([^?]+)(?:\?(.*))?", unsub["mailto"], re.I)
                        to_a  = m2.group(1).strip()
                        prms  = {}
                        if m2.group(2):
                            for kv in m2.group(2).split("&"):
                                if "=" in kv:
                                    k, v = kv.split("=", 1)
                                    prms[k.lower()] = v.replace("+", " ")
                        mime = MIMEText(prms.get("body", "Please unsubscribe me."))
                        mime["to"]      = to_a
                        mime["subject"] = prms.get("subject", "Unsubscribe")
                        raw_b64 = base64.urlsafe_b64encode(mime.as_bytes()).decode()
                        service.users().messages().send(
                            userId="me", body={"raw": raw_b64}
                        ).execute()
                        sent = True
                    except Exception as e:
                        console.print(f"    [red]OAuth send error: {e}[/red]")

            if sent:
                console.print("    [green]✓ Unsubscribe email sent[/green]")
                ok_mail.append(sender_email)
            elif unsub and unsub.get("http"):
                webbrowser.open(unsub["http"])
                console.print("    [yellow]↗ Unsubscribe page opened in browser[/yellow]")
                ok_web.append(sender_email)
            else:
                console.print("    [red]✗ No usable unsubscribe method[/red]")
                failed.append(sender_email)

        console.print(
            f"\n[bold]Unsubscribe results:[/bold]\n"
            f"  [green]Auto sent      : {len(ok_mail)}[/green]\n"
            f"  [yellow]Browser opened : {len(ok_web)}[/yellow]\n"
            f"  [red]Failed         : {len(failed)}[/red]"
        )

    if "delete" in actions:
        console.print(f"\n[bold cyan]Deleting unread emails from {len(selected)} sender(s)…[/bold cyan]")

        if method == "imap":
            # Group selected senders by account
            by_account: dict = defaultdict(list)
            for sender_email in selected:
                acct = flat[sender_email].get("account", "")
                by_account[acct].append(sender_email)

            total_deleted = 0
            for acct_email, sender_list in by_account.items():
                if acct_email not in imap_conns:
                    continue
                mail, _ = imap_conns[acct_email]
                console.print(f"\n  [magenta]{acct_email}[/magenta]  ({len(sender_list)} sender(s))")
                with Progress(SpinnerColumn(), TextColumn("  Moving to Trash…"),
                              console=console, transient=True) as p:
                    p.add_task("", total=None)
                    n = _imap_delete_unread(mail, sender_list, acct_email)
                console.print(f"  [green]✓ {n} email(s) moved to Trash[/green]")
                total_deleted += n
        else:
            with Progress(SpinnerColumn(), TextColumn("  Moving to Trash…"),
                          console=console, transient=True) as p:
                p.add_task("", total=None)
                total_deleted = _oauth_delete_unread(service, selected)
            console.print(f"  [green]✓ {total_deleted} email(s) moved to Trash[/green]")

        console.print("[dim]  Trash auto-empties after 30 days, or empty it manually in Gmail.[/dim]")

    # ── Cleanup ───────────────────────────────────────────────────────────
    for mail, _ in imap_conns.values():
        try:
            mail.logout()
        except Exception:
            pass

    console.print("\n[bold green]All done! 🎉[/bold green]")


if __name__ == "__main__":
    main()
