#!/usr/bin/env python3
"""
Gmail Promotional Email Unsubscriber — Multi-Account Edition
-------------------------------------------------------------
Supports multiple Gmail accounts via:
  • App Password + IMAP  (reads from env vars — no Google Console setup per account)
  • OAuth / Gmail API    (existing credentials.json flow — one-time setup)

Env var format (set these on your machine):
  Single account:
    GMAIL_EMAIL=you@gmail.com
    GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx

  Multiple accounts (numbered):
    GMAIL_EMAIL_1=you@gmail.com
    GMAIL_APP_PASSWORD_1=xxxx xxxx xxxx xxxx
    GMAIL_EMAIL_2=other@gmail.com
    GMAIL_APP_PASSWORD_2=yyyy yyyy yyyy yyyy

  Comma-separated (alternative):
    GMAIL_ACCOUNTS=you@gmail.com:xxxx xxxx xxxx xxxx,other@gmail.com:yyyy yyyy yyyy yyyy

How to generate an App Password:
  1. Go to myaccount.google.com/security
  2. Enable 2-Step Verification (required)
  3. Search for "App passwords" → Generate one → choose "Mail" + "Windows/Mac/Linux"
  4. Copy the 16-character password → set as env var
"""

import os
import re
import base64
import imaplib
import smtplib
import pickle
import webbrowser
from email.mime.text import MIMEText
from email.header import decode_header as _decode_header
from pathlib import Path
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

import questionary
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn
from rich.panel import Panel

# ── Optional OAuth (Gmail API) imports ───────────────────────────────────────
try:
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build as _build_service
    OAUTH_AVAILABLE = True
except ImportError:
    OAUTH_AVAILABLE = False

OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

SCAN_MODES = {
    "all_unread":  ("All unread emails  (catches promos Gmail missed)", "UNSEEN",  "[Gmail]/All Mail"),
    "all_mail":    ("All emails — read + unread  (most thorough)",      "ALL",     "[Gmail]/All Mail"),
    "promos_only": ("Promotions folder only",                           "ALL",     "[Gmail]/All Mail", "category:promotions"),
    "inbox":       ("Inbox only  (unread)",                             "UNSEEN",  "INBOX"),
}

console = Console()


# ── Account config ────────────────────────────────────────────────────────────

@dataclass
class Account:
    email: str
    app_password: Optional[str] = None   # IMAP / SMTP auth
    oauth_creds_file: Optional[Path] = None  # OAuth credentials.json
    label: str = ""                      # display label
    token_file: Optional[Path] = None

    def __post_init__(self):
        if not self.label:
            self.label = self.email
        if self.oauth_creds_file and not self.token_file:
            safe = re.sub(r"[^\w]", "_", self.email)
            self.token_file = self.oauth_creds_file.parent / f"token_{safe}.pickle"

    @property
    def uses_imap(self) -> bool:
        return bool(self.app_password)

    @property
    def uses_oauth(self) -> bool:
        return bool(self.oauth_creds_file)


def detect_accounts_from_env() -> list[Account]:
    """
    Auto-detect Gmail accounts from environment variables.
    Supports three naming conventions (see module docstring).
    """
    accounts: list[Account] = []

    # Convention 1 — GMAIL_ACCOUNTS=email:pass,email:pass
    raw = os.environ.get("GMAIL_ACCOUNTS", "").strip()
    if raw:
        for entry in raw.split(","):
            entry = entry.strip()
            if ":" in entry:
                email, _, pwd = entry.partition(":")
                accounts.append(Account(email=email.strip(), app_password=pwd.strip()))
        if accounts:
            return accounts

    # Convention 2 — numbered: GMAIL_EMAIL_1 / GMAIL_APP_PASSWORD_1 …
    for i in range(1, 11):
        email = os.environ.get(f"GMAIL_EMAIL_{i}", "").strip()
        pwd   = os.environ.get(f"GMAIL_APP_PASSWORD_{i}", "").strip()
        if email and pwd:
            accounts.append(Account(email=email, app_password=pwd))

    if accounts:
        return accounts

    # Convention 3 — single: GMAIL_EMAIL / GMAIL_APP_PASSWORD
    email = os.environ.get("GMAIL_EMAIL", "").strip()
    pwd   = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
    if email and pwd:
        accounts.append(Account(email=email, app_password=pwd))
        return accounts

    return accounts


def detect_oauth_accounts() -> list[Account]:
    """Find credentials.json files in the script directory for OAuth accounts."""
    if not OAUTH_AVAILABLE:
        return []
    here = Path(__file__).parent
    creds_files = list(here.glob("credentials*.json"))
    accounts = []
    for cf in creds_files:
        # Try to read the client_email / account hint from the file
        try:
            import json
            data = json.loads(cf.read_text())
            hint = data.get("installed", {}).get("client_id", cf.stem)
        except Exception:
            hint = cf.stem
        accounts.append(Account(
            email=hint,
            oauth_creds_file=cf,
            label=f"OAuth ({cf.name})",
        ))
    return accounts


# ── IMAP client ───────────────────────────────────────────────────────────────

class IMAPClient:
    def __init__(self, account: Account):
        self.account = account
        self._imap: Optional[imaplib.IMAP4_SSL] = None

    def connect(self):
        self._imap = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
        self._imap.login(self.account.email, self.account.app_password)
        return self

    def disconnect(self):
        if self._imap:
            try:
                self._imap.logout()
            except Exception:
                pass
            self._imap = None

    def __enter__(self):
        return self.connect()

    def __exit__(self, *_):
        self.disconnect()

    # ── Helpers ──

    @staticmethod
    def _decode_str(raw) -> str:
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", errors="replace")
        return raw or ""

    @staticmethod
    def _parse_from(raw_header: str) -> tuple[str, str]:
        m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', raw_header.strip())
        if m:
            return m.group(1).strip(), m.group(2).strip().lower()
        return raw_header.strip(), raw_header.strip().lower()

    @staticmethod
    def _parse_unsubscribe(raw_header: str) -> Optional[dict]:
        if not raw_header:
            return None
        mailto = re.findall(r"<(mailto:[^>]+)>", raw_header, re.I)
        http   = re.findall(r"<(https?://[^>]+)>", raw_header, re.I)
        if not mailto and not http:
            return None
        return {
            "mailto": mailto[0] if mailto else None,
            "http":   http[0]   if http   else None,
        }

    # ── Fetch senders ──

    def fetch_senders(self, max_results: int, mode_key: str) -> dict:
        mode = SCAN_MODES[mode_key]
        imap_search = mode[1]
        folder      = mode[2]
        # Gmail-specific extra search (e.g. category:promotions)
        gm_raw      = mode[3] if len(mode) > 3 else None

        self._imap.select(f'"{folder}"', readonly=True)

        if gm_raw:
            _, data = self._imap.uid("SEARCH", "CHARSET", "UTF-8",
                                     "X-GM-RAW", f'"{gm_raw}"')
        else:
            _, data = self._imap.uid("SEARCH", None, imap_search)

        all_uids = data[0].split() if data and data[0] else []
        # Newest first, capped at max_results
        uids_to_fetch = all_uids[-max_results:][::-1]

        senders: dict = defaultdict(lambda: {
            "name": "", "email": "", "count": 0, "unsubscribe": None,
            "account": self.account.email,
        })

        with Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]{self.account.email}[/cyan] scanning…"),
            BarColumn(),
            MofNCompleteColumn(),
            console=console,
            transient=True,
        ) as progress:
            task = progress.add_task("", total=len(uids_to_fetch))

            BATCH = 50
            for i in range(0, len(uids_to_fetch), BATCH):
                batch = uids_to_fetch[i : i + BATCH]
                uid_str = b",".join(batch)
                try:
                    _, msg_data = self._imap.uid(
                        "FETCH", uid_str,
                        "(BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)])",
                    )
                except Exception:
                    progress.update(task, advance=len(batch))
                    continue

                for item in msg_data:
                    if not isinstance(item, tuple):
                        continue
                    raw_headers = self._decode_str(item[1])

                    from_val  = ""
                    unsub_val = ""
                    for line in raw_headers.splitlines():
                        ll = line.lower()
                        if ll.startswith("from:"):
                            from_val = line[5:].strip()
                        elif ll.startswith("list-unsubscribe:"):
                            unsub_val = line[17:].strip()
                        elif line.startswith((" ", "\t")) and unsub_val:
                            unsub_val += " " + line.strip()

                    if not from_val:
                        continue

                    name, email = self._parse_from(from_val)
                    unsub       = self._parse_unsubscribe(unsub_val)

                    s = senders[email]
                    s["name"]  = s["name"] or name
                    s["email"] = email
                    s["count"] += 1
                    if unsub and not s["unsubscribe"]:
                        s["unsubscribe"] = unsub

                progress.update(task, advance=len(batch))

        return dict(senders)

    # ── Delete unread ──

    def delete_unread_from(self, sender_emails: list[str]) -> int:
        """Move all unread emails from sender_emails to Trash. Returns count moved."""
        self._imap.select('"[Gmail]/All Mail"')
        total_moved = 0

        for sender_email in sender_emails:
            try:
                _, data = self._imap.uid(
                    "SEARCH", "CHARSET", "UTF-8",
                    "UNSEEN", "FROM", f'"{sender_email}"',
                )
                uids = data[0].split() if data and data[0] else []
                if not uids:
                    continue

                # Process in batches of 100
                for i in range(0, len(uids), 100):
                    batch = uids[i : i + 100]
                    uid_str = b",".join(batch)
                    # Copy to Trash
                    self._imap.uid("COPY", uid_str, '"[Gmail]/Trash"')
                    # Mark deleted in All Mail
                    self._imap.uid("STORE", uid_str, "+FLAGS", "(\\Deleted)")
                    total_moved += len(batch)

                self._imap.expunge()
            except Exception as e:
                console.print(f"    [red]IMAP error for {sender_email}: {e}[/red]")

        return total_moved

    # ── Send unsubscribe email ──

    def send_unsubscribe_email(self, mailto_url: str) -> bool:
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
            msg["From"]    = self.account.email
            msg["To"]      = to_addr
            msg["Subject"] = subject
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
                smtp.ehlo()
                smtp.starttls()
                smtp.login(self.account.email, self.account.app_password)
                smtp.sendmail(self.account.email, to_addr, msg.as_string())
            return True
        except Exception as e:
            console.print(f"    [red]SMTP error: {e}[/red]")
            return False


# ── OAuth client (unchanged from v1) ─────────────────────────────────────────

def get_oauth_service(account: Account):
    if not OAUTH_AVAILABLE or not account.oauth_creds_file:
        return None

    creds = None
    if account.token_file and account.token_file.exists():
        with open(account.token_file, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                creds = None
        if not creds or not creds.valid:
            flow  = InstalledAppFlow.from_client_secrets_file(
                str(account.oauth_creds_file), OAUTH_SCOPES
            )
            creds = flow.run_local_server(port=0)
        if account.token_file:
            with open(account.token_file, "wb") as f:
                pickle.dump(creds, f)

    return _build_service("gmail", "v1", credentials=creds)


def oauth_fetch_senders(service, max_results: int, mode_key: str,
                        account_email: str) -> dict:
    mode = SCAN_MODES[mode_key]
    query     = "is:unread" if mode[1] == "UNSEEN" else ""
    label_ids = None
    if mode[2] == "INBOX":
        label_ids = ["INBOX"]
    elif mode_key == "promos_only":
        label_ids = ["CATEGORY_PROMOTIONS"]
    if len(mode) > 3 and mode_key == "promos_only":
        label_ids = ["CATEGORY_PROMOTIONS"]

    senders = defaultdict(lambda: {
        "name": "", "email": "", "count": 0, "unsubscribe": None,
        "account": account_email,
    })
    page_token = None
    fetched    = 0

    with Progress(
        SpinnerColumn(),
        TextColumn(f"[cyan]{account_email}[/cyan] scanning…"),
        BarColumn(), MofNCompleteColumn(),
        console=console, transient=True,
    ) as progress:
        task = progress.add_task("", total=max_results)

        while fetched < max_results:
            batch  = min(100, max_results - fetched)
            kwargs = dict(userId="me", maxResults=batch)
            if query:
                kwargs["q"] = query
            if label_ids:
                kwargs["labelIds"] = label_ids
            if page_token:
                kwargs["pageToken"] = page_token

            res  = service.users().messages().list(**kwargs).execute()
            msgs = res.get("messages", [])
            if not msgs:
                break

            for msg in msgs:
                try:
                    detail = service.users().messages().get(
                        userId="me", id=msg["id"], format="metadata",
                        metadataHeaders=["From", "List-Unsubscribe"],
                    ).execute()
                    hdrs        = detail.get("payload", {}).get("headers", [])
                    from_val    = next((h["value"] for h in hdrs if h["name"].lower() == "from"), "")
                    unsub_val   = next((h["value"] for h in hdrs if h["name"].lower() == "list-unsubscribe"), "")
                    m2          = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', from_val.strip())
                    name        = m2.group(1).strip() if m2 else from_val.strip()
                    email_addr  = m2.group(2).strip().lower() if m2 else from_val.strip().lower()
                    mailto      = re.findall(r"<(mailto:[^>]+)>", unsub_val, re.I)
                    http        = re.findall(r"<(https?://[^>]+)>", unsub_val, re.I)
                    unsub       = {"mailto": mailto[0] if mailto else None,
                                   "http":   http[0]   if http   else None} if (mailto or http) else None

                    s = senders[email_addr]
                    s["name"]  = s["name"] or name
                    s["email"] = email_addr
                    s["count"] += 1
                    if unsub and not s["unsubscribe"]:
                        s["unsubscribe"] = unsub
                except Exception:
                    pass

                fetched += 1
                progress.update(task, advance=1)
                if fetched >= max_results:
                    break

            page_token = res.get("nextPageToken")
            if not page_token:
                break

    return dict(senders)


def oauth_delete_unread(service, sender_emails: list[str]) -> int:
    total = 0
    for email_addr in sender_emails:
        page_token = None
        ids = []
        while True:
            kwargs = dict(userId="me", q=f"from:{email_addr} is:unread", maxResults=500)
            if page_token:
                kwargs["pageToken"] = page_token
            res = service.users().messages().list(**kwargs).execute()
            ids.extend(m["id"] for m in res.get("messages", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
        for i in range(0, len(ids), 1000):
            chunk = ids[i : i + 1000]
            service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "addLabelIds": ["TRASH"],
                      "removeLabelIds": ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"]},
            ).execute()
            total += len(chunk)
    return total


# ── Display ───────────────────────────────────────────────────────────────────

def show_table(senders: dict, show_account_col: bool = False):
    title = f"[bold]Unique Senders[/bold]  ({len(senders)} total)"
    table = Table(title=title, header_style="bold cyan", show_lines=False)
    table.add_column("#",            style="dim",    width=4,  justify="right")
    if show_account_col:
        table.add_column("Account",  style="magenta", max_width=22)
    table.add_column("Display Name", style="white",  min_width=22, max_width=32)
    table.add_column("Email",        style="cyan",   min_width=26, max_width=40)
    table.add_column("Count",        style="yellow", width=6,  justify="right")
    table.add_column("Unsub Link",   style="green",  width=10, justify="center")

    for i, s in enumerate(
        sorted(senders.values(), key=lambda x: x["count"], reverse=True), 1
    ):
        has = s["unsubscribe"] is not None
        row = [str(i)]
        if show_account_col:
            row.append(s.get("account", "")[:22])
        row += [
            (s["name"] or "—")[:32],
            s["email"][:40],
            str(s["count"]),
            "[green]yes[/green]" if has else "[red dim]no[/red dim]",
        ]
        table.add_row(*row)
    console.print(table)


# ── Checklist selection ───────────────────────────────────────────────────────

def choose_senders(senders: dict, show_account: bool = False) -> list[str]:
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
                (f"[{s['account'][:18]}] " if show_account else "")
                + f"{(s['name'] or s['email'])[:30]:30}  "
                + f"<{s['email'][:36]}>"
                + f"  ({s['count']})"
            ),
            value=s["email"],
            checked=False,
        )
        for s in can_unsub
    ]

    console.print("\n[bold]Space[/bold]=toggle  [bold]A[/bold]=all/none  [bold]Enter[/bold]=confirm\n")
    return questionary.checkbox("Select senders to UNSUBSCRIBE from:", choices=choices).ask() or []


# ── Unsubscribe dispatcher ────────────────────────────────────────────────────

def do_unsubscribe(selected_emails: list[str], senders: dict,
                   imap_clients: dict, oauth_services: dict):
    """
    Route each sender's unsubscribe to the right account client.
    imap_clients  : {account_email -> IMAPClient}
    oauth_services: {account_email -> service}
    """
    console.print(f"\n[bold cyan]Unsubscribing from {len(selected_emails)} sender(s)…[/bold cyan]\n")
    ok_mail, ok_web, failed = [], [], []

    for email_addr in selected_emails:
        s         = senders[email_addr]
        acct      = s.get("account", "")
        unsub     = s["unsubscribe"]
        label     = f"{s['name'] or email_addr} <{email_addr}>"
        console.print(f"  [white]{label}[/white]  [dim]({acct})[/dim]")

        sent = False
        if unsub and unsub.get("mailto"):
            if acct in imap_clients:
                sent = imap_clients[acct].send_unsubscribe_email(unsub["mailto"])
            elif acct in oauth_services:
                # OAuth send
                try:
                    m     = re.match(r"mailto:([^?]+)(?:\?(.*))?", unsub["mailto"], re.I)
                    to_a  = m.group(1).strip()
                    prms  = {}
                    if m.group(2):
                        for kv in m.group(2).split("&"):
                            if "=" in kv:
                                k, v = kv.split("=", 1)
                                prms[k.lower()] = v.replace("+", " ")
                    mime           = MIMEText(prms.get("body", "Please unsubscribe me."))
                    mime["to"]     = to_a
                    mime["subject"]= prms.get("subject", "Unsubscribe")
                    raw  = base64.urlsafe_b64encode(mime.as_bytes()).decode()
                    oauth_services[acct].users().messages().send(
                        userId="me", body={"raw": raw}
                    ).execute()
                    sent = True
                except Exception as e:
                    console.print(f"    [red]OAuth send error: {e}[/red]")

        if sent:
            console.print("    [green]✓ Unsubscribe email sent[/green]")
            ok_mail.append(email_addr)
        elif unsub and unsub.get("http"):
            webbrowser.open(unsub["http"])
            console.print("    [yellow]↗ Unsubscribe page opened in browser[/yellow]")
            ok_web.append(email_addr)
        else:
            console.print("    [red]✗ No usable unsubscribe method[/red]")
            failed.append(email_addr)

    console.print(
        f"\n[bold]Unsubscribe results:[/bold]\n"
        f"  [green]Auto sent      : {len(ok_mail)}[/green]\n"
        f"  [yellow]Browser opened : {len(ok_web)}[/yellow]\n"
        f"  [red]Failed         : {len(failed)}[/red]"
    )


def do_delete(selected_emails: list[str], senders: dict,
              imap_clients: dict, oauth_services: dict):
    """Delete unread emails, routing to the correct account."""
    console.print(
        f"\n[bold cyan]Deleting unread emails from {len(selected_emails)} sender(s)…[/bold cyan]\n"
    )

    # Group selected senders by account
    by_account: dict[str, list[str]] = defaultdict(list)
    for email_addr in selected_emails:
        acct = senders[email_addr].get("account", "")
        by_account[acct].append(email_addr)

    total = 0
    for acct, email_list in by_account.items():
        console.print(f"  [magenta]{acct}[/magenta] — {len(email_list)} sender(s)…")
        if acct in imap_clients:
            with Progress(SpinnerColumn(), TextColumn("Moving to Trash…"),
                          console=console, transient=True) as p:
                p.add_task("", total=None)
                n = imap_clients[acct].delete_unread_from(email_list)
            console.print(f"    [green]✓ {n} email(s) moved to Trash[/green]")
            total += n
        elif acct in oauth_services:
            with Progress(SpinnerColumn(), TextColumn("Moving to Trash…"),
                          console=console, transient=True) as p:
                p.add_task("", total=None)
                n = oauth_delete_unread(oauth_services[acct], email_list)
            console.print(f"    [green]✓ {n} email(s) moved to Trash[/green]")
            total += n
        else:
            console.print(f"    [red]No client available for {acct}[/red]")

    console.print(f"\n[green]✓ Total: {total} email(s) moved to Trash[/green]")
    console.print("[dim]Emails auto-purge from Trash after 30 days.[/dim]")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold cyan]Gmail Promotional Email Unsubscriber[/bold cyan]\n"
        "[dim]Multi-Account · Scan · Select · Unsubscribe · Delete[/dim]",
        border_style="cyan",
    ))

    # ── Step 1: Discover accounts ──────────────────────────────────────────
    env_accounts   = detect_accounts_from_env()
    oauth_accounts = detect_oauth_accounts()
    all_accounts   = env_accounts + [
        a for a in oauth_accounts
        if a.email not in {e.email for e in env_accounts}
    ]

    if not all_accounts:
        console.print(Panel(
            "[yellow]No Gmail accounts found![/yellow]\n\n"
            "Set environment variables before running:\n\n"
            "[bold]Single account:[/bold]\n"
            "  GMAIL_EMAIL=you@gmail.com\n"
            "  GMAIL_APP_PASSWORD=xxxx xxxx xxxx xxxx\n\n"
            "[bold]Multiple accounts:[/bold]\n"
            "  GMAIL_EMAIL_1=you@gmail.com\n"
            "  GMAIL_APP_PASSWORD_1=xxxx xxxx xxxx xxxx\n"
            "  GMAIL_EMAIL_2=other@gmail.com\n"
            "  GMAIL_APP_PASSWORD_2=yyyy yyyy yyyy yyyy\n\n"
            "[bold]How to get an App Password:[/bold]\n"
            "  1. myaccount.google.com/security\n"
            "  2. Enable 2-Step Verification\n"
            "  3. Search 'App passwords' → Mail → Generate\n"
            "  4. Copy the 16-char code → save as env var\n\n"
            "[bold]OR[/bold] place credentials.json in this folder for OAuth.",
            title="Setup Required", border_style="red",
        ))
        raise SystemExit(1)

    if len(all_accounts) == 1:
        selected_accounts = all_accounts
        console.print(f"[green]✓ 1 account detected:[/green] {all_accounts[0].email}\n")
    else:
        console.print(f"[green]✓ {len(all_accounts)} account(s) detected.[/green]\n")
        choices = [
            questionary.Choice(
                title=f"{a.email}  [{'IMAP' if a.uses_imap else 'OAuth'}]",
                value=a,
                checked=True,
            )
            for a in all_accounts
        ]
        selected_accounts = questionary.checkbox(
            "Which accounts should be scanned?",
            choices=choices,
        ).ask() or []
        if not selected_accounts:
            console.print("[yellow]No accounts selected — bye![/yellow]")
            return

    # ── Step 2: Scan options ──────────────────────────────────────────────
    mode_key = questionary.select(
        "Which emails should be scanned?",
        choices=[
            questionary.Choice("All unread emails  (recommended — catches mislabelled promos)",
                               value="all_unread"),
            questionary.Choice("All emails — read + unread  (most thorough)",
                               value="all_mail"),
            questionary.Choice("Promotions folder only",        value="promos_only"),
            questionary.Choice("Inbox only  (unread)",          value="inbox"),
        ],
        default="all_unread",
    ).ask()

    raw = questionary.text(
        "How many emails to scan per account?",
        default="1000",
        validate=lambda v: v.isdigit() and int(v) > 0 or "Enter a positive number",
    ).ask()
    max_results = int(raw or 1000)

    # ── Step 3: Scan all selected accounts ────────────────────────────────
    all_senders: dict = {}
    imap_clients:  dict[str, IMAPClient]  = {}
    oauth_services: dict[str, object]     = {}

    for acct in selected_accounts:
        console.print(f"\n[bold]Scanning[/bold] [cyan]{acct.email}[/cyan]…")
        try:
            if acct.uses_imap:
                client = IMAPClient(acct)
                client.connect()
                imap_clients[acct.email] = client
                senders = client.fetch_senders(max_results, mode_key)
            elif acct.uses_oauth:
                service = get_oauth_service(acct)
                if not service:
                    console.print(f"  [red]OAuth failed for {acct.email}[/red]")
                    continue
                oauth_services[acct.email] = service
                senders = oauth_fetch_senders(service, max_results, mode_key, acct.email)
            else:
                console.print(f"  [red]No auth method available for {acct.email}[/red]")
                continue

            console.print(f"  [green]✓ {len(senders)} unique sender(s)[/green]")

            # Merge: if same sender appears in multiple accounts, keep both entries
            # disambiguated by account prefix
            for email_addr, data in senders.items():
                key = f"{email_addr}||{acct.email}"
                all_senders[key] = data

        except imaplib.IMAP4.error as e:
            console.print(f"  [red]IMAP error for {acct.email}: {e}[/red]")
            console.print(
                "  [dim]Check your App Password. Make sure 2-Step Verification is ON\n"
                "  and IMAP is enabled: Gmail → Settings → See all settings → "
                "Forwarding and POP/IMAP → Enable IMAP[/dim]"
            )
        except Exception as e:
            console.print(f"  [red]Error scanning {acct.email}: {e}[/red]")

    if not all_senders:
        console.print("[yellow]No senders found across all accounts.[/yellow]")
        return

    # ── Step 4: Display & select ──────────────────────────────────────────
    multi = len(selected_accounts) > 1
    # Flatten: use email as key for display, keep last-seen account
    flat_senders: dict = {}
    for key, data in all_senders.items():
        email_addr = key.split("||")[0]
        if email_addr not in flat_senders:
            flat_senders[email_addr] = data
        else:
            flat_senders[email_addr]["count"] += data["count"]

    console.print(f"\n[green]Total: {len(flat_senders)} unique sender(s) across "
                  f"{len(selected_accounts)} account(s).[/green]\n")
    show_table(flat_senders, show_account_col=multi)

    selected = choose_senders(flat_senders, show_account=multi)
    if not selected:
        console.print("\n[yellow]Nothing selected — bye![/yellow]")
        return

    # Restore full per-account data for routing
    for email_addr in selected:
        if email_addr not in all_senders:
            # Find the right key
            for key, data in all_senders.items():
                if key.startswith(email_addr + "||"):
                    flat_senders[email_addr] = data
                    break

    # ── Step 5: Actions ───────────────────────────────────────────────────
    console.print(f"\n[bold]{len(selected)} sender(s) selected.[/bold]")
    actions = questionary.checkbox(
        "What do you want to do?",
        choices=[
            questionary.Choice("Unsubscribe (send request / open browser)",
                               value="unsub", checked=True),
            questionary.Choice("Delete their unread emails",
                               value="delete", checked=True),
        ],
    ).ask() or []

    if not actions or not questionary.confirm("Proceed?").ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    if "unsub" in actions:
        do_unsubscribe(selected, flat_senders, imap_clients, oauth_services)

    if "delete" in actions:
        do_delete(selected, flat_senders, imap_clients, oauth_services)

    # ── Cleanup ───────────────────────────────────────────────────────────
    for client in imap_clients.values():
        client.disconnect()

    console.print("\n[bold green]All done! 🎉[/bold green]")


if __name__ == "__main__":
    main()
