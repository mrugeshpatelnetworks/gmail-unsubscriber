#!/usr/bin/env python3
"""
Gmail Promotional Email Unsubscriber
-------------------------------------
At startup you choose:
  A) App Password + IMAP  — enter email + password in terminal,
                            supports multiple accounts, no Google Console needed
  B) OAuth / Gmail API    — opens browser, uses credentials.json, single account

Uses plain input() prompts — works in every terminal (cmd, PowerShell,
Windows Terminal, VS Code, Mac/Linux).
"""

import os
import re
import base64
import imaplib
import smtplib
import pickle
import webbrowser
import getpass
import sys
from pathlib import Path
from collections import defaultdict
from email.mime.text import MIMEText
from email.header import decode_header as _mime_decode_header

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

# (search_flag, imap_folder, optional_gm_raw_filter)
SCAN_MODES = {
    "1": ("All unread emails  (recommended — catches mislabelled promos)",
          "UNSEEN", '"[Gmail]/All Mail"', None),
    "2": ("All emails — read + unread  (most thorough, slower)",
          "ALL",    '"[Gmail]/All Mail"', None),
    "3": ("Promotions folder only",
          "ALL",    '"[Gmail]/All Mail"', "category:promotions"),
    "4": ("Inbox only  (unread)",
          "UNSEEN", "INBOX",              None),
}

console = Console()


# ─────────────────────────────────────────────────────────────────────────────
# Simple terminal UI  (no prompt_toolkit / questionary)
# ─────────────────────────────────────────────────────────────────────────────

def _print_menu(title: str, options: list[str]):
    console.print(f"\n[bold]{title}[/bold]")
    for i, opt in enumerate(options, 1):
        console.print(f"  [cyan]{i}[/cyan])  {opt}")


def ask_select(title: str, options: list[str], default: int = 1) -> int:
    """Numbered menu. Returns 1-based choice index."""
    _print_menu(title, options)
    while True:
        try:
            raw = input(f"\nEnter number [1-{len(options)}] (default {default}): ").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]Cancelled.[/yellow]")
            sys.exit(0)
        if raw == "":
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return int(raw)
        console.print(f"[red]Please enter a number between 1 and {len(options)}.[/red]")


def _read_key() -> str:
    """
    Read a single keypress without waiting for Enter.
    Returns a string: 'UP','DOWN','PGUP','PGDN','SPACE','ENTER','BACKSPACE','ESC',
    a single printable character, or 'OTHER'.
    Works on Windows (msvcrt) and Unix/Mac (tty+termios).
    Falls back to plain input() if stdin is not a tty.
    """
    if not sys.stdin.isatty():
        return input()  # non-interactive fallback

    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\xe0", b"\x00"):          # extended key prefix
            ch2 = msvcrt.getch()
            return {b"H": "UP", b"P": "DOWN", b"I": "PGUP", b"Q": "PGDN"}.get(ch2, "OTHER")
        if ch == b"\r":   return "ENTER"
        if ch == b" ":    return "SPACE"
        if ch == b"\x1b": return "ESC"
        if ch == b"\x08": return "BACKSPACE"
        if ch == b"\x03": raise KeyboardInterrupt
        try:
            return ch.decode("utf-8")
        except Exception:
            return "OTHER"
    else:
        import tty, termios, select
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.buffer.read(1)
            if ch == b"\x1b":
                ready, _, _ = select.select([sys.stdin], [], [], 0.1)
                if ready:
                    seq = sys.stdin.buffer.read(2)
                    return {b"[A": "UP", b"[B": "DOWN", b"[5": "PGUP", b"[6": "PGDN"}.get(seq, "ESC")
                return "ESC"
            if ch in (b"\r", b"\n"): return "ENTER"
            if ch == b" ":           return "SPACE"
            if ch in (b"\x7f", b"\x08"): return "BACKSPACE"
            if ch == b"\x03":        raise KeyboardInterrupt
            try:
                return ch.decode("utf-8")
            except Exception:
                return "OTHER"
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)


def interactive_checkbox(title: str, options: list[str]) -> list[int]:
    """
    Full interactive checkbox.
      ↑ ↓         navigate
      Space       toggle checkbox on current item
      PgUp/PgDn   jump a page
      /           type a search filter, Enter to apply, Esc to clear
      a           select all visible
      n           deselect all visible
      Enter       confirm selection
      q           cancel
    Returns sorted list of selected 1-based indices.
    Falls back to range-input if stdin is not a tty.
    """
    if not sys.stdin.isatty():
        return _range_select_fallback(title, options)

    PAGE      = 22
    selected: set[int] = set()   # 0-based original indices
    cursor    = 0                # position in filtered list
    scroll    = 0                # top of visible window
    filt      = ""               # active search string
    status    = ""               # one-line status message

    def filtered() -> list[int]:
        if not filt:
            return list(range(len(options)))
        fl = filt.lower()
        return [i for i, o in enumerate(options) if fl in o.lower()]

    def clamp(fi: list[int]):
        nonlocal cursor, scroll
        n = len(fi)
        if n == 0:
            cursor = scroll = 0
            return
        cursor = max(0, min(cursor, n - 1))
        scroll = max(0, min(scroll, n - 1))
        if cursor < scroll:
            scroll = cursor
        elif cursor >= scroll + PAGE:
            scroll = cursor - PAGE + 1

    def render(fi: list[int]):
        # ANSI clear + move to top
        sys.stdout.write("\033[H\033[2J")
        n_sel = len(selected)
        n_vis = len(fi)
        n_tot = len(options)

        print(f"\n  \033[1m{title}\033[0m")
        print(f"  \033[32m{n_sel} selected\033[0m  ·  {n_vis}/{n_tot} shown"
              + (f"  ·  filter: \033[33m{filt}\033[0m" if filt else ""))
        if status:
            print(f"  \033[33m{status}\033[0m")
        print()
        print("  \033[2m↑↓=move  Space=check  a=all  n=none  /=search  PgUp/PgDn=page  Enter=done  q=quit\033[0m")
        print()

        visible = fi[scroll : scroll + PAGE]
        for rel, orig in enumerate(visible):
            abs_i  = scroll + rel
            is_cur = abs_i == cursor
            is_sel = orig in selected

            box   = "\033[32m[✓]\033[0m" if is_sel else "[ ]"
            arrow = "\033[36m▶\033[0m"   if is_cur else " "
            text  = options[orig]

            if is_cur:
                print(f"  {arrow} {box} \033[7m{text}\033[0m")
            elif is_sel:
                print(f"  {arrow} {box} \033[32m{text}\033[0m")
            else:
                print(f"  {arrow} {box} {text}")

        if n_vis > PAGE:
            pages  = (n_vis - 1) // PAGE + 1
            cur_pg = scroll // PAGE + 1
            end    = min(scroll + PAGE, n_vis)
            print(f"\n  \033[2mPage {cur_pg}/{pages}  ({scroll+1}–{end} of {n_vis})\033[0m")

        sys.stdout.flush()

    while True:
        fi = filtered()
        clamp(fi)
        render(fi)
        status = ""

        try:
            key = _read_key()
        except KeyboardInterrupt:
            sys.stdout.write("\033[H\033[2J")
            return []

        if key == "UP":
            if cursor > 0:
                cursor -= 1
                if cursor < scroll:
                    scroll -= 1

        elif key == "DOWN":
            if cursor < len(fi) - 1:
                cursor += 1
                if cursor >= scroll + PAGE:
                    scroll += 1

        elif key == "PGUP":
            cursor = max(0, cursor - PAGE)
            scroll = max(0, scroll - PAGE)

        elif key == "PGDN":
            n = len(fi)
            cursor = min(max(0, n - 1), cursor + PAGE)
            scroll = min(max(0, n - PAGE), scroll + PAGE)

        elif key == "SPACE":
            if fi:
                orig = fi[cursor]
                if orig in selected:
                    selected.discard(orig)
                else:
                    selected.add(orig)

        elif key == "ENTER":
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()
            return sorted(i + 1 for i in selected)

        elif key == "q":
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()
            return []

        elif key == "a":
            for i in fi:
                selected.add(i)
            status = f"Selected all {len(fi)} visible sender(s)."

        elif key == "n":
            for i in fi:
                selected.discard(i)
            status = "Deselected all visible."

        elif key == "/":
            # Open inline search prompt at bottom of screen
            sys.stdout.write("\033[H\033[2J")
            sys.stdout.flush()
            try:
                new_filt = input("  Search (Enter=apply, blank=clear): ").strip()
            except (EOFError, KeyboardInterrupt):
                new_filt = filt
            filt   = new_filt
            cursor = 0
            scroll = 0

        elif key == "ESC":
            filt   = ""
            cursor = 0
            scroll = 0

        elif key == "BACKSPACE":
            if filt:
                filt   = filt[:-1]
                cursor = 0
                scroll = 0


def _range_select_fallback(title: str, options: list[str]) -> list[int]:
    """Fallback range-input selector used when stdin is not a tty."""
    n = len(options)
    console.print(f"\n[bold]{title}[/bold]  ({n} options)\n")
    console.print("  [dim]1-10 · 1 3 5 · 1-50 75 · all · none[/dim]\n")
    while True:
        try:
            raw = input("  Select > ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw in ("none", "q", ""):
            return []
        if raw == "all":
            return list(range(1, n + 1))
        sel: set[int] = set()
        err = False
        for part in raw.replace(",", " ").split():
            if "-" in part:
                a, _, b = part.partition("-")
                if a.isdigit() and b.isdigit():
                    lo, hi = int(a), int(b)
                    if 1 <= lo <= n and 1 <= hi <= n and lo <= hi:
                        sel.update(range(lo, hi + 1))
                    else:
                        console.print(f"  [red]Out of range: {part}[/red]")
                        err = True; break
                else:
                    console.print(f"  [red]Bad range: {part}[/red]")
                    err = True; break
            elif part.isdigit():
                num = int(part)
                if 1 <= num <= n:
                    sel.add(num)
                else:
                    console.print(f"  [red]{num} out of range[/red]")
                    err = True; break
        if err:
            continue
        if not sel:
            continue
        return sorted(sel)


def ask_actions(selected_count: int) -> tuple[bool, bool]:
    """
    Simple action picker for unsubscribe / delete.
    Returns (do_unsub, do_delete).
    """
    console.print(f"\n[bold]{selected_count} sender(s) selected. What do you want to do?[/bold]")
    console.print("  [cyan]1[/cyan])  Unsubscribe only")
    console.print("  [cyan]2[/cyan])  Delete unread emails only")
    console.print("  [cyan]3[/cyan])  Both  (default)")
    console.print("  [cyan]q[/cyan])  Cancel")
    while True:
        try:
            raw = input("\n  Choice [3]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if raw in ("", "3", "both"):
            return True, True
        if raw == "1":
            return True, False
        if raw == "2":
            return False, True
        if raw == "q":
            return False, False
        console.print("  [red]Enter 1, 2, 3, or q.[/red]")


def ask_confirm(title: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"\n{title} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        console.print("\n[yellow]Cancelled.[/yellow]")
        sys.exit(0)
    if raw == "":
        return default
    return raw in ("y", "yes")


def ask_int(title: str, default: int) -> int:
    try:
        raw = input(f"\n{title} [default {default}]: ").strip()
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)
    if raw == "":
        return default
    return int(raw) if raw.isdigit() and int(raw) > 0 else default


def ask_text(title: str, validate=None) -> str:
    while True:
        try:
            raw = input(f"{title}: ").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
        if validate is None or validate(raw):
            return raw
        console.print("[red]Invalid input, try again.[/red]")


def ask_password(title: str) -> str:
    try:
        return getpass.getpass(f"{title}: ")
    except (EOFError, KeyboardInterrupt):
        sys.exit(0)


# ─────────────────────────────────────────────────────────────────────────────
# Env-var password lookup
# ─────────────────────────────────────────────────────────────────────────────

def _find_env_password(email: str) -> str | None:
    """
    Check environment variables for a saved App Password for this email.
    Supports three naming conventions:
      GMAIL_EMAIL / GMAIL_APP_PASSWORD          (single account)
      GMAIL_EMAIL_1 / GMAIL_APP_PASSWORD_1 ...  (numbered)
      GMAIL_ACCOUNTS=email:pass,email:pass       (comma-separated)
    """
    email_lower = email.strip().lower()

    # Convention 1 — single
    if os.environ.get("GMAIL_EMAIL", "").strip().lower() == email_lower:
        pwd = os.environ.get("GMAIL_APP_PASSWORD", "").strip()
        if pwd:
            return pwd

    # Convention 2 — numbered
    for i in range(1, 11):
        if os.environ.get(f"GMAIL_EMAIL_{i}", "").strip().lower() == email_lower:
            pwd = os.environ.get(f"GMAIL_APP_PASSWORD_{i}", "").strip()
            if pwd:
                return pwd

    # Convention 3 — GMAIL_ACCOUNTS=email:pass,email:pass
    for entry in os.environ.get("GMAIL_ACCOUNTS", "").split(","):
        entry = entry.strip()
        if ":" in entry:
            e, _, p = entry.partition(":")
            if e.strip().lower() == email_lower and p.strip():
                return p.strip()

    return None


def _detect_env_accounts() -> list[dict]:
    """Return list of {email, password} dicts found in environment variables."""
    accounts = []
    seen = set()

    def _add(email, pwd):
        e = email.strip().lower()
        if e and pwd.strip() and e not in seen:
            seen.add(e)
            accounts.append({"email": email.strip(), "password": pwd.strip()})

    # Single
    e = os.environ.get("GMAIL_EMAIL", "")
    p = os.environ.get("GMAIL_APP_PASSWORD", "")
    if e and p:
        _add(e, p)

    # Numbered
    for i in range(1, 11):
        e = os.environ.get(f"GMAIL_EMAIL_{i}", "")
        p = os.environ.get(f"GMAIL_APP_PASSWORD_{i}", "")
        if e and p:
            _add(e, p)

    # Comma-separated
    for entry in os.environ.get("GMAIL_ACCOUNTS", "").split(","):
        entry = entry.strip()
        if ":" in entry:
            e, _, p = entry.partition(":")
            if e and p:
                _add(e, p)

    return accounts


# ─────────────────────────────────────────────────────────────────────────────
# Email parsing helpers
# ─────────────────────────────────────────────────────────────────────────────

def _decode_mime(s: str) -> str:
    """Decode MIME encoded-word strings like =?UTF-8?Q?Groupon_Flash?= into plain text."""
    try:
        parts = _mime_decode_header(s)
        out = []
        for chunk, charset in parts:
            if isinstance(chunk, bytes):
                out.append(chunk.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(chunk)
        return "".join(out).strip()
    except Exception:
        return s


def _parse_from_str(value: str) -> tuple[str, str]:
    # Decode any MIME-encoded name first
    value = _decode_mime(value)
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


# ─────────────────────────────────────────────────────────────────────────────
# IMAP
# ─────────────────────────────────────────────────────────────────────────────

def _imap_connect(email: str, password: str) -> imaplib.IMAP4_SSL:
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(email, password)
    return mail


def _imap_fetch_senders(mail: imaplib.IMAP4_SSL,
                         max_results: int,
                         mode_key: str,
                         account_email: str) -> dict:
    """Fetch unique senders — only reads From + List-Unsubscribe headers."""
    _, search_flag, folder, gm_raw = SCAN_MODES[mode_key]

    typ, _ = mail.select(folder, readonly=True)
    if typ != "OK":
        raise RuntimeError(f"Cannot open folder {folder}")

    if gm_raw:
        typ, data = mail.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW", gm_raw)
    else:
        typ, data = mail.uid("SEARCH", None, search_flag)

    if typ != "OK" or not data or not data[0]:
        return {}

    all_uids = data[0].split()
    uids_to_fetch = all_uids[-max_results:][::-1]   # newest first

    senders: dict = defaultdict(lambda: {
        "name": "", "email": "", "count": 0,
        "unsubscribe": None, "account": account_email,
    })

    BATCH = 50
    with Progress(
        SpinnerColumn(),
        TextColumn(f"  [cyan]{account_email}[/cyan] scanning…"),
        BarColumn(), MofNCompleteColumn(),
        console=console, transient=True,
    ) as progress:
        task = progress.add_task("", total=len(uids_to_fetch))

        for i in range(0, len(uids_to_fetch), BATCH):
            batch   = uids_to_fetch[i : i + BATCH]
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

            for item in msg_data:
                if not isinstance(item, tuple) or len(item) < 2:
                    continue
                raw = item[1]
                if isinstance(raw, bytes):
                    raw = raw.decode("utf-8", errors="replace")

                from_val = unsub_val = ""
                for line in raw.splitlines():
                    ll = line.lower()
                    if ll.startswith("from:"):
                        from_val = line[5:].strip()
                    elif ll.startswith("list-unsubscribe:"):
                        unsub_val = line[17:].strip()
                    elif line.startswith((" ", "\t")) and unsub_val:
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
                         sender_emails: list[str],
                         account_email: str) -> int:
    mail.select('"[Gmail]/All Mail"', readonly=False)
    total = 0
    for sender_email in sender_emails:
        try:
            typ, data = mail.uid(
                "SEARCH", "CHARSET", "UTF-8",
                "UNSEEN", "FROM", f'"{sender_email}"',
            )
            if typ != "OK" or not data or not data[0]:
                continue
            uids = data[0].split()
            for i in range(0, len(uids), 100):
                batch   = uids[i : i + 100]
                uid_str = ",".join(u.decode() for u in batch)
                mail.uid("COPY",  uid_str, '"[Gmail]/Trash"')
                mail.uid("STORE", uid_str, "+FLAGS", "(\\Deleted)")
                total  += len(batch)
            mail.expunge()
        except Exception as e:
            console.print(f"    [red]Error trashing mail from {sender_email}: {e}[/red]")
    return total


def _imap_send_unsub(email: str, password: str, mailto_url: str) -> bool:
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
# OAuth
# ─────────────────────────────────────────────────────────────────────────────

def _oauth_get_service():
    if not OAUTH_AVAILABLE:
        console.print("[red]OAuth libraries not installed.[/red]\n"
                      "Run: pip install google-auth google-auth-oauthlib google-api-python-client")
        raise SystemExit(1)
    if not CREDS_FILE.exists():
        console.print(Panel(
            "[bold red]credentials.json not found![/bold red]\n\n"
            "One-time setup:\n"
            "1. https://console.cloud.google.com/ → create/select a project\n"
            "2. APIs & Services → Enable APIs → Gmail API → Enable\n"
            "3. Credentials → + Create Credentials → OAuth client ID\n"
            "   (configure consent screen first if prompted → External)\n"
            "4. Application type: [bold]Desktop app[/bold] → Create → Download JSON\n"
            "5. Rename to [bold]credentials.json[/bold] → place next to this script\n"
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
    _, search_flag, folder, gm_raw = SCAN_MODES[mode_key]
    query     = "is:unread" if search_flag == "UNSEEN" else ""
    label_ids = None
    if folder == "INBOX":
        label_ids = ["INBOX"]
    if gm_raw == "category:promotions":
        label_ids, query = ["CATEGORY_PROMOTIONS"], ""

    senders  = defaultdict(lambda: {"name":"","email":"","count":0,"unsubscribe":None,"account":"OAuth"})
    page_tok = None
    fetched  = 0

    with Progress(SpinnerColumn(),
                  TextColumn("  [cyan]OAuth account[/cyan] scanning…"),
                  BarColumn(), MofNCompleteColumn(),
                  console=console, transient=True) as progress:
        task = progress.add_task("", total=max_results)
        while fetched < max_results:
            batch  = min(100, max_results - fetched)
            kwargs = dict(userId="me", maxResults=batch)
            if query:      kwargs["q"]         = query
            if label_ids:  kwargs["labelIds"]  = label_ids
            if page_tok:   kwargs["pageToken"] = page_tok
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


def _oauth_delete_unread(service, sender_emails: list[str]) -> int:
    total = 0
    for ea in sender_emails:
        page_tok, ids = None, []
        while True:
            kwargs = dict(userId="me", q=f"from:{ea} is:unread", maxResults=500)
            if page_tok: kwargs["pageToken"] = page_tok
            res = service.users().messages().list(**kwargs).execute()
            ids.extend(m["id"] for m in res.get("messages", []))
            page_tok = res.get("nextPageToken")
            if not page_tok: break
        for i in range(0, len(ids), 1000):
            service.users().messages().batchModify(
                userId="me",
                body={"ids": ids[i:i+1000], "addLabelIds": ["TRASH"],
                      "removeLabelIds": ["INBOX","UNREAD","CATEGORY_PROMOTIONS"]},
            ).execute()
            total += len(ids[i:i+1000])
    return total


# ─────────────────────────────────────────────────────────────────────────────
# Display
# ─────────────────────────────────────────────────────────────────────────────

def show_table(senders: dict):
    table = Table(
        title=f"[bold]Unique Senders[/bold]  ({len(senders)} total)",
        header_style="bold cyan", show_lines=False,
    )
    table.add_column("#",            style="dim",    width=4,  justify="right")
    table.add_column("Display Name", style="white",  min_width=22, max_width=30)
    table.add_column("Email",        style="cyan",   min_width=26, max_width=40)
    table.add_column("Count",        style="yellow", width=6,  justify="right")
    table.add_column("Accounts",     style="magenta",width=8,  justify="right")
    table.add_column("Unsub",        style="green",  width=6,  justify="center")

    for i, s in enumerate(
        sorted(senders.values(), key=lambda x: x["count"], reverse=True), 1
    ):
        accts = s.get("accounts", [])
        table.add_row(
            str(i),
            (s["name"] or "—")[:30],
            s["email"][:40],
            str(s["count"]),
            str(len(accts)),
            "[green]yes[/green]" if s["unsubscribe"] else "[red dim]no[/red dim]",
        )
    console.print(table)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    console.print(Panel(
        "[bold cyan]Gmail Promotional Email Unsubscriber[/bold cyan]\n"
        "[dim]Scan · Select · Unsubscribe · Delete[/dim]",
        border_style="cyan",
    ))

    # ── Step 1: Auth method ───────────────────────────────────────────────
    method_idx = ask_select(
        "How do you want to sign in to Gmail?",
        [
            "App Password + IMAP  (enter email & password here — supports multiple accounts)",
            "Google OAuth          (opens browser, uses credentials.json — single account)",
        ],
        default=1,
    )
    method = "imap" if method_idx == 1 else "oauth"

    # ── Step 2: Collect credentials ───────────────────────────────────────
    accounts   = []   # [{"email": ..., "password": ...}]
    service    = None

    if method == "imap":
        # ── Check env vars first ──────────────────────────────────────────
        env_accounts = _detect_env_accounts()
        if env_accounts:
            console.print(
                f"\n[green]✓ Found {len(env_accounts)} account(s) in environment variables:[/green]"
            )
            for a in env_accounts:
                console.print(f"    • {a['email']}")
            use_env = ask_select(
                "Use saved credentials?",
                [
                    "Yes — use environment variable credentials",
                    "No  — enter credentials manually",
                ],
                default=1,
            )
            if use_env == 1:
                accounts = env_accounts
                # Validate each env-var account
                validated = []
                for acct in accounts:
                    console.print(f"  [cyan]Testing {acct['email']}…[/cyan] ", end="")
                    try:
                        test = _imap_connect(acct["email"], acct["password"])
                        test.logout()
                        console.print("[green]✓[/green]")
                        validated.append(acct)
                    except Exception as e:
                        console.print(f"[red]✗ {e}[/red]")
                accounts = validated
                if not accounts:
                    console.print("[red]No env-var accounts connected — falling back to manual entry.[/red]")
                    env_accounts = []   # fall through to manual

        if not accounts:
            # ── Manual entry ──────────────────────────────────────────────
            num_accounts = ask_select(
                "How many Gmail accounts do you want to scan?",
                ["1", "2", "3", "4", "5"],
                default=1,
            )

            for i in range(num_accounts):
                console.print(f"\n[bold]── Account {i+1} of {num_accounts} ──[/bold]")
                email = ask_text(
                    "Gmail address",
                    validate=lambda v: "@" in v and "." in v,
                )

                # Check if env var has a password for this email
                env_pwd = _find_env_password(email)
                if env_pwd:
                    console.print(f"  [green]✓ App Password found in environment variables[/green]")
                    password = env_pwd
                else:
                    console.print(
                        "  [dim]Tip: App Password = 16-char code from "
                        "myaccount.google.com/apppasswords[/dim]"
                    )
                    password = ask_password("  Password or App Password")

                console.print("  [cyan]Testing connection…[/cyan] ", end="")
                try:
                    test = _imap_connect(email, password)
                    test.logout()
                    console.print("[green]✓ Connected[/green]")
                    accounts.append({"email": email, "password": password})
                except imaplib.IMAP4.error as e:
                    console.print("[red]✗ Failed[/red]")
                    console.print(Panel(
                        f"[red]Could not sign in to {email}[/red]\n\n"
                        "Common fixes:\n"
                        "• Wrong App Password → regenerate at myaccount.google.com/apppasswords\n"
                        "• IMAP not enabled → Gmail Settings → "
                        "Forwarding and POP/IMAP → Enable IMAP\n"
                        "• 2-Step Verification off → required for App Passwords\n\n"
                        f"[dim]{e}[/dim]",
                        border_style="red",
                    ))
                    if ask_confirm("  Retry with a different password?"):
                        password = ask_password("  Password or App Password")
                        try:
                            test = _imap_connect(email, password)
                            test.logout()
                            console.print("  [green]✓ Connected[/green]")
                            accounts.append({"email": email, "password": password})
                        except Exception as e2:
                            console.print(f"  [red]✗ Still failed ({e2}) — skipping.[/red]")
                    else:
                        console.print(f"  [yellow]Skipping {email}[/yellow]")

        if not accounts:
            console.print("[red]No accounts connected — exiting.[/red]")
            return

    else:
        console.print("\n[cyan]Connecting via OAuth (browser will open)…[/cyan]")
        service = _oauth_get_service()
        console.print("[green]✓ Connected[/green]")

    # ── Step 3: Scan options ──────────────────────────────────────────────
    mode_idx = ask_select(
        "Which emails should be scanned?",
        [label for label, *_ in SCAN_MODES.values()],
        default=1,
    )
    mode_key = list(SCAN_MODES.keys())[mode_idx - 1]

    per_label = "per account " if len(accounts) > 1 else ""
    max_results = ask_int(f"How many emails to scan {per_label}(0 = unlimited)?", default=1000)
    if max_results == 0:
        max_results = 999_999

    # ── Step 4: Scan ──────────────────────────────────────────────────────
    all_senders: dict = {}
    imap_conns:  dict = {}   # email -> (mail_obj, password)

    if method == "imap":
        for acct in accounts:
            console.print(f"\n[bold]Scanning[/bold] [cyan]{acct['email']}[/cyan]…")
            try:
                mail = _imap_connect(acct["email"], acct["password"])
                imap_conns[acct["email"]] = (mail, acct["password"])
                senders = _imap_fetch_senders(mail, max_results, mode_key, acct["email"])
                console.print(f"  [green]✓ {len(senders)} unique sender(s)[/green]")
                for ea, data in senders.items():
                    all_senders[f"{ea}||{acct['email']}"] = data
            except Exception as e:
                console.print(f"  [red]Scan failed: {e}[/red]")
    else:
        senders = _oauth_fetch_senders(service, max_results, mode_key)
        console.print(f"  [green]✓ {len(senders)} unique sender(s)[/green]")
        for ea, data in senders.items():
            all_senders[f"{ea}||OAuth"] = data

    if not all_senders:
        console.print("[yellow]No senders found.[/yellow]")
        return

    # ── Flatten: one entry per sender email, track ALL accounts it was seen in ──
    # Same sender found in 3 accounts → shows once, actions applied to all 3.
    flat: dict = {}
    for key, data in all_senders.items():
        ea, acct = key.split("||", 1)
        if ea not in flat:
            flat[ea] = dict(data)
            flat[ea]["accounts"] = [acct]          # list of gmail accounts
        else:
            flat[ea]["count"] += data["count"]
            if acct not in flat[ea]["accounts"]:
                flat[ea]["accounts"].append(acct)
            # Keep the best unsubscribe link we've seen
            if not flat[ea]["unsubscribe"] and data.get("unsubscribe"):
                flat[ea]["unsubscribe"] = data["unsubscribe"]

    console.print(
        f"\n[green]Found {len(flat)} unique sender(s)"
        + (f" across {len(accounts)} accounts" if len(accounts) > 1 else "")
        + ".[/green]\n"
    )
    show_table(flat)

    # ── Step 5: Choose senders (interactive checkbox) ─────────────────────
    sorted_s  = sorted(flat.values(), key=lambda x: x["count"], reverse=True)
    can_unsub = [s for s in sorted_s if s["unsubscribe"]]
    no_link   = [s for s in sorted_s if not s["unsubscribe"]]

    if no_link:
        console.print(f"[yellow]{len(no_link)} sender(s) have no unsubscribe link (excluded).[/yellow]")
    if not can_unsub:
        console.print("[red]No senders with an unsubscribe link found.[/red]")
        return

    # Build label for each checkbox row
    def _row_label(s: dict) -> str:
        accts = s.get("accounts", [])
        acct_label = (f"{len(accts)} accts" if len(accts) > 1
                      else accts[0][:22] if accts else "")
        name  = (s["name"] or s["email"])[:28]
        email = s["email"][:36]
        return f"{name:<28}  {email:<36}  {s['count']:>4} emails  {acct_label}"

    checkbox_opts = [_row_label(s) for s in can_unsub]

    selected_indices = interactive_checkbox(
        f"Select senders to UNSUBSCRIBE / DELETE from  ({len(can_unsub)} available):",
        checkbox_opts,
    )
    if not selected_indices:
        console.print("\n[yellow]Nothing selected — bye![/yellow]")
        return

    selected_senders = [can_unsub[i - 1] for i in selected_indices]
    selected_emails  = [s["email"] for s in selected_senders]

    # ── Step 6: Choose actions ────────────────────────────────────────────
    do_unsub, do_delete = ask_actions(len(selected_emails))
    if not do_unsub and not do_delete:
        console.print("[yellow]Cancelled.[/yellow]")
        return

    if not ask_confirm(f"Proceed with {len(selected_emails)} sender(s)?"):
        console.print("[yellow]Cancelled.[/yellow]")
        return

    # ── Step 7: Unsubscribe ───────────────────────────────────────────────
    if do_unsub:
        console.print(f"\n[bold cyan]Unsubscribing from {len(selected_emails)} sender(s)…[/bold cyan]\n")
        ok_mail, ok_web, failed = [], [], []

        for s in selected_senders:
            ea    = s["email"]
            unsub = s["unsubscribe"]
            accts = s.get("accounts", [])
            console.print(f"  [white]{s['name'] or ea} <{ea}>[/white]"
                          + (f"  [dim]({', '.join(accts)})[/dim]" if len(accts) > 1 else ""))

            sent = False
            if unsub and unsub.get("mailto"):
                # Try each account — succeed on first
                for acct in accts:
                    if method == "imap" and acct in imap_conns:
                        _, pwd = imap_conns[acct]
                        if _imap_send_unsub(acct, pwd, unsub["mailto"]):
                            sent = True
                            break
                    elif method == "oauth" and service:
                        try:
                            m2   = re.match(r"mailto:([^?]+)(?:\?(.*))?", unsub["mailto"], re.I)
                            to_a = m2.group(1).strip()
                            prms = {}
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
                            break
                        except Exception as e:
                            console.print(f"    [red]Error: {e}[/red]")

            if sent:
                console.print("    [green]✓ Unsubscribe email sent[/green]")
                ok_mail.append(ea)
            elif unsub and unsub.get("http"):
                webbrowser.open(unsub["http"])
                console.print("    [yellow]↗ Unsubscribe page opened in browser[/yellow]")
                ok_web.append(ea)
            else:
                console.print("    [red]✗ No usable unsubscribe method[/red]")
                failed.append(ea)

        console.print(
            f"\n[bold]Unsubscribe results:[/bold]\n"
            f"  [green]Auto sent      : {len(ok_mail)}[/green]\n"
            f"  [yellow]Browser opened : {len(ok_web)}[/yellow]\n"
            f"  [red]Failed         : {len(failed)}[/red]"
        )

    # ── Step 8: Delete (from ALL accounts the sender was seen in) ────────
    if do_delete:
        console.print(f"\n[bold cyan]Deleting unread emails from {len(selected_emails)} sender(s)…[/bold cyan]")
        total_deleted = 0

        if method == "imap":
            # Build per-account work list: each account deletes senders it received from
            by_account: dict = defaultdict(list)
            for s in selected_senders:
                for acct in s.get("accounts", []):
                    by_account[acct].append(s["email"])

            for acct_email, email_list in by_account.items():
                if acct_email not in imap_conns:
                    continue
                mail, _ = imap_conns[acct_email]
                console.print(f"\n  [magenta]{acct_email}[/magenta]  ({len(email_list)} sender(s))…")
                with Progress(SpinnerColumn(), TextColumn("  Moving to Trash…"),
                              console=console, transient=True) as p:
                    p.add_task("", total=None)
                    n = _imap_delete_unread(mail, email_list, acct_email)
                console.print(f"  [green]✓ {n} email(s) moved to Trash[/green]")
                total_deleted += n
        else:
            with Progress(SpinnerColumn(), TextColumn("  Moving to Trash…"),
                          console=console, transient=True) as p:
                p.add_task("", total=None)
                total_deleted = _oauth_delete_unread(service, selected_emails)
            console.print(f"  [green]✓ {total_deleted} email(s) moved to Trash[/green]")

        console.print("[dim]  Trash auto-empties after 30 days.[/dim]")

    # ── Cleanup ───────────────────────────────────────────────────────────
    for mail, _ in imap_conns.values():
        try:
            mail.logout()
        except Exception:
            pass

    console.print("\n[bold green]All done![/bold green]")
    input("\nPress Enter to close…")


if __name__ == "__main__":
    main()
