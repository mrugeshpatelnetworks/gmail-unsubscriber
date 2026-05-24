#!/usr/bin/env python3
"""
Gmail Promotional Email Unsubscriber
-------------------------------------
Scans your Gmail (all unread, promotions, or inbox) for newsletter/promo senders,
shows a checklist of unique senders, unsubscribes from selected ones, and optionally
deletes all their unread emails.

GitHub: https://github.com/YOUR_USERNAME/gmail-unsubscriber
"""

import re
import base64
import pickle
import webbrowser
from pathlib import Path
from collections import defaultdict
from email.mime.text import MIMEText

from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import questionary
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, MofNCompleteColumn
from rich.panel import Panel

# ── OAuth Scopes ──────────────────────────────────────────────────────────────
# gmail.readonly  – list & read message headers
# gmail.send      – send unsubscribe emails via mailto: links
# gmail.modify    – move emails to Trash (batchModify)
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

TOKEN_FILE = Path(__file__).parent / "token.pickle"
CREDS_FILE = Path(__file__).parent / "credentials.json"

# Scan modes: (display label, Gmail search query, Gmail label IDs or None)
SCAN_MODES = {
    "all_unread":  ("All unread emails  (catches promos Gmail missed)", "is:unread", None),
    "all_mail":    ("All emails — read + unread  (most thorough)",      "",          None),
    "promos_only": ("Promotions folder only",                           "",          ["CATEGORY_PROMOTIONS"]),
    "inbox":       ("Inbox only  (unread)",                             "is:unread", ["INBOX"]),
}

console = Console()


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_service():
    """Authenticate with Gmail API. Opens browser on first run."""
    if not CREDS_FILE.exists():
        console.print(Panel(
            "[bold red]credentials.json not found![/bold red]\n\n"
            "One-time setup (3 minutes):\n"
            "1. Go to [link=https://console.cloud.google.com/]https://console.cloud.google.com/[/link]\n"
            "2. Create or select a project\n"
            "3. [bold]APIs & Services → Enable APIs[/bold] → search [bold]Gmail API[/bold] → Enable\n"
            "4. [bold]APIs & Services → Credentials → + Create Credentials → OAuth client ID[/bold]\n"
            "5. Application type: [bold]Desktop app[/bold] → Create → Download JSON\n"
            "6. Rename the downloaded file to [bold]credentials.json[/bold] and place it here:\n"
            f"   [cyan]{CREDS_FILE}[/cyan]\n\n"
            "7. Back in Google Cloud Console go to\n"
            "   [bold]APIs & Services → OAuth consent screen → Test users → + Add Users[/bold]\n"
            "   and add your Gmail address.",
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
                creds = None   # force re-auth if refresh fails

        if not creds or not creds.valid:
            flow = InstalledAppFlow.from_client_secrets_file(str(CREDS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as f:
            pickle.dump(creds, f)

    return build("gmail", "v1", credentials=creds)


# ── Email parsing helpers ─────────────────────────────────────────────────────

def parse_from(headers: list) -> tuple:
    """Return (display_name, email_address) from message headers."""
    for h in headers:
        if h["name"].lower() == "from":
            v = h["value"]
            m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', v)
            if m:
                return m.group(1).strip(), m.group(2).strip().lower()
            return v.strip(), v.strip().lower()
    return "Unknown", "unknown"


def parse_unsubscribe(headers: list):
    """
    Parse the List-Unsubscribe header.
    Returns {'mailto': ..., 'http': ...} or None.
    """
    for h in headers:
        if h["name"].lower() == "list-unsubscribe":
            raw = h["value"]
            mailto = re.findall(r"<(mailto:[^>]+)>", raw, re.I)
            http   = re.findall(r"<(https?://[^>]+)>", raw, re.I)
            return {
                "mailto": mailto[0] if mailto else None,
                "http":   http[0]   if http   else None,
            }
    return None


# ── Scanning ──────────────────────────────────────────────────────────────────

def fetch_senders(service, max_results: int, query: str, label_ids: list) -> dict:
    """
    Page through Gmail and collect unique sender metadata.
    Only downloads message headers (fast, privacy-preserving — no email body is read).
    """
    senders = defaultdict(lambda: {
        "name": "", "email": "", "count": 0, "unsubscribe": None
    })

    page_token = None
    fetched = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Scanning emails…", total=max_results)

        while fetched < max_results:
            batch = min(100, max_results - fetched)
            kwargs: dict = dict(userId="me", maxResults=batch)
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
                        userId="me",
                        id=msg["id"],
                        format="metadata",
                        metadataHeaders=["From", "List-Unsubscribe"],
                    ).execute()
                    hdrs         = detail.get("payload", {}).get("headers", [])
                    name, email  = parse_from(hdrs)
                    unsub        = parse_unsubscribe(hdrs)

                    s = senders[email]
                    s["name"]  = s["name"] or name
                    s["email"] = email
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


# ── Display ───────────────────────────────────────────────────────────────────

def show_table(senders: dict):
    """Print a Rich table of all unique senders."""
    table = Table(
        title=f"[bold]Unique Senders[/bold]  ({len(senders)} total)",
        header_style="bold cyan",
        show_lines=False,
    )
    table.add_column("#",            style="dim",    width=4,  justify="right")
    table.add_column("Display Name", style="white",  min_width=25, max_width=35)
    table.add_column("Email",        style="cyan",   min_width=28, max_width=42)
    table.add_column("Count",        style="yellow", width=7,  justify="right")
    table.add_column("Unsub Link",   style="green",  width=10, justify="center")

    for i, s in enumerate(
        sorted(senders.values(), key=lambda x: x["count"], reverse=True), 1
    ):
        has = s["unsubscribe"] is not None
        table.add_row(
            str(i),
            (s["name"] or "—")[:35],
            s["email"][:42],
            str(s["count"]),
            "[green]yes[/green]" if has else "[red dim]no[/red dim]",
        )
    console.print(table)


# ── Sender selection ──────────────────────────────────────────────────────────

def choose_senders(senders: dict) -> list:
    """
    Interactive checkbox — all unchecked by default.
    Only senders with a List-Unsubscribe header appear here.
    """
    sorted_s  = sorted(senders.values(), key=lambda x: x["count"], reverse=True)
    can_unsub = [s for s in sorted_s if s["unsubscribe"]]
    no_link   = [s for s in sorted_s if not s["unsubscribe"]]

    if no_link:
        console.print(
            f"[yellow]{len(no_link)} sender(s) have no unsubscribe link and are excluded.[/yellow]"
        )
    if not can_unsub:
        console.print("[red]No senders with an unsubscribe link found.[/red]")
        return []

    choices = [
        questionary.Choice(
            title=(
                f"{(s['name'] or s['email'])[:32]:32}  "
                f"<{s['email'][:38]}>"
                f"  ({s['count']} emails)"
            ),
            value=s["email"],
            checked=False,    # all unchecked — user picks what to remove
        )
        for s in can_unsub
    ]

    console.print(
        "\n[bold]Space[/bold] = toggle  |  "
        "[bold]A[/bold] = select all / none  |  "
        "[bold]Enter[/bold] = confirm\n"
    )
    selected = questionary.checkbox(
        "Select senders to UNSUBSCRIBE from:",
        choices=choices,
    ).ask()
    return selected or []


# ── Unsubscribe ───────────────────────────────────────────────────────────────

def _send_unsub_mail(service, mailto_url: str) -> bool:
    """Send a mailto: unsubscribe request via Gmail API."""
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
        mime         = MIMEText(body)
        mime["to"]   = to_addr
        mime["subject"] = subject
        raw = base64.urlsafe_b64encode(mime.as_bytes()).decode()
        service.users().messages().send(userId="me", body={"raw": raw}).execute()
        return True
    except Exception as e:
        console.print(f"    [red]Send error: {e}[/red]")
        return False


def process_unsubscriptions(service, selected_emails: list, senders: dict):
    """Unsubscribe from each selected sender using mailto: or HTTP link."""
    console.print(
        f"\n[bold cyan]Unsubscribing from {len(selected_emails)} sender(s)…[/bold cyan]\n"
    )
    ok_mail, ok_web, failed = [], [], []

    for email in selected_emails:
        s     = senders.get(email)
        label = f"{s['name'] or email} <{email}>"
        unsub = s["unsubscribe"]
        console.print(f"  [white]{label}[/white]")

        # Prefer mailto: (fully automatic), fall back to HTTP (opens browser)
        if unsub and unsub.get("mailto"):
            if _send_unsub_mail(service, unsub["mailto"]):
                console.print("    [green]✓ Unsubscribe email sent[/green]")
                ok_mail.append(email)
                continue

        if unsub and unsub.get("http"):
            webbrowser.open(unsub["http"])
            console.print("    [yellow]↗ Unsubscribe page opened in browser[/yellow]")
            ok_web.append(email)
        else:
            console.print("    [red]✗ No usable unsubscribe method[/red]")
            failed.append(email)

    console.print(
        f"\n[bold]Unsubscribe results:[/bold]\n"
        f"  [green]Auto (email sent) : {len(ok_mail)}[/green]\n"
        f"  [yellow]Browser opened    : {len(ok_web)}[/yellow]\n"
        f"  [red]Failed            : {len(failed)}[/red]"
    )
    if ok_web:
        console.print(
            "[dim]For browser-opened pages, complete the unsubscribe step manually.[/dim]"
        )


# ── Delete unread ─────────────────────────────────────────────────────────────

def delete_unread_emails(service, selected_emails: list):
    """
    Find all unread emails from selected senders and move them to Trash.
    Uses batchModify (up to 1000 per call) — fast even for large inboxes.
    Emails auto-purge from Trash after 30 days, or empty Trash manually.
    """
    console.print(
        f"\n[bold cyan]Searching for unread emails from "
        f"{len(selected_emails)} sender(s)…[/bold cyan]\n"
    )

    all_ids: list = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Collecting message IDs…", total=len(selected_emails))

        for email in selected_emails:
            page_token = None
            while True:
                kwargs = dict(userId="me", q=f"from:{email} is:unread", maxResults=500)
                if page_token:
                    kwargs["pageToken"] = page_token
                res        = service.users().messages().list(**kwargs).execute()
                msgs       = res.get("messages", [])
                all_ids.extend(m["id"] for m in msgs)
                page_token = res.get("nextPageToken")
                if not page_token:
                    break
            progress.update(task, advance=1)

    if not all_ids:
        console.print("[yellow]No unread emails found from these senders.[/yellow]")
        return

    console.print(f"[yellow]Found {len(all_ids)} unread email(s) to move to Trash.[/yellow]")
    if not questionary.confirm(
        f"Move all {len(all_ids)} unread email(s) to Trash?"
    ).ask():
        console.print("[yellow]Skipped deletion.[/yellow]")
        return

    CHUNK = 1000   # Gmail API limit per batchModify call
    trashed = 0

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        console=console,
        transient=True,
    ) as progress:
        task = progress.add_task("Moving to Trash…", total=len(all_ids))
        for i in range(0, len(all_ids), CHUNK):
            chunk = all_ids[i : i + CHUNK]
            service.users().messages().batchModify(
                userId="me",
                body={
                    "ids":            chunk,
                    "addLabelIds":    ["TRASH"],
                    "removeLabelIds": ["INBOX", "UNREAD", "CATEGORY_PROMOTIONS"],
                },
            ).execute()
            trashed += len(chunk)
            progress.update(task, advance=len(chunk))

    console.print(f"[green]✓ {trashed} email(s) moved to Trash.[/green]")
    console.print(
        "[dim]Emails auto-delete from Trash after 30 days, "
        "or empty Trash manually inside Gmail.[/dim]"
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold cyan]Gmail Promotional Email Unsubscriber[/bold cyan]\n"
        "[dim]Scan · Select · Unsubscribe · Delete[/dim]",
        border_style="cyan",
    ))

    # Step 1 — authenticate
    console.print("[cyan]Connecting to Gmail…[/cyan]")
    service = get_service()
    console.print("[green]✓ Connected[/green]\n")

    # Step 2 — choose scan scope
    mode_key = questionary.select(
        "Which emails should be scanned for senders?",
        choices=[
            questionary.Choice(
                "All unread emails  (catches promos Gmail missed) ← recommended",
                value="all_unread",
            ),
            questionary.Choice(
                "All emails — read + unread  (most thorough)",
                value="all_mail",
            ),
            questionary.Choice("Promotions folder only",   value="promos_only"),
            questionary.Choice("Inbox only  (unread)",     value="inbox"),
        ],
        default="all_unread",
    ).ask()

    _, query, label_ids = SCAN_MODES[mode_key]

    # Step 3 — how many to scan
    raw = questionary.text(
        "How many emails to scan?",
        default="1000",
        validate=lambda v: v.isdigit() and int(v) > 0 or "Enter a positive number",
    ).ask()
    max_results = int(raw or 1000)

    # Step 4 — scan
    senders = fetch_senders(service, max_results, query, label_ids)
    if not senders:
        console.print("[yellow]No emails found with the selected filter.[/yellow]")
        return

    console.print(f"\n[green]Found {len(senders)} unique sender(s).[/green]\n")
    show_table(senders)

    # Step 5 — choose senders
    selected = choose_senders(senders)
    if not selected:
        console.print("\n[yellow]Nothing selected — bye![/yellow]")
        return

    # Step 6 — choose actions
    console.print(f"\n[bold]Selected {len(selected)} sender(s).[/bold]")
    actions = questionary.checkbox(
        "What do you want to do?",
        choices=[
            questionary.Choice(
                "Unsubscribe  (send unsubscribe request / open browser)",
                value="unsub",
                checked=True,
            ),
            questionary.Choice(
                "Delete unread emails from these senders",
                value="delete",
                checked=True,
            ),
        ],
    ).ask() or []

    if not actions:
        console.print("[yellow]No actions selected — bye![/yellow]")
        return

    if not questionary.confirm("Proceed?").ask():
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # Step 7 — execute
    if "unsub" in actions:
        process_unsubscriptions(service, selected, senders)

    if "delete" in actions:
        delete_unread_emails(service, selected)

    console.print("\n[bold green]All done! 🎉[/bold green]")


if __name__ == "__main__":
    main()
