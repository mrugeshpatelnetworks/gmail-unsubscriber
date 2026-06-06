#!/usr/bin/env python3
"""
Gmail Unsubscriber — PySide6 Desktop App
Council design: QTableView + QAbstractTableModel + QSortFilterProxyModel
Thread-safe scanning via QThread + Signal/Slot | QStackedWidget navigation
"""

# ── Standard library ──────────────────────────────────────────────────────────
import os, sys, re, imaplib, email as _email_lib, webbrowser, pickle, base64
from pathlib import Path
from dataclasses import dataclass, field
from email.header import decode_header as _mime_decode
from collections import defaultdict
from typing import Optional

# ── PySide6 ───────────────────────────────────────────────────────────────────
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QLineEdit, QRadioButton, QButtonGroup,
    QProgressBar, QTableView, QHeaderView, QAbstractItemView,
    QListWidget, QListWidgetItem, QFrame, QStackedWidget,
    QMessageBox, QSlider, QGroupBox, QSizePolicy, QScrollArea,
    QCheckBox, QAbstractScrollArea, QToolButton
)
from PySide6.QtCore import (
    Qt, QThread, Signal, QAbstractTableModel, QModelIndex,
    QSortFilterProxyModel, QRegularExpression, QTimer, QSize,
    QObject, QEvent
)
from PySide6.QtGui import QFont, QColor, QIcon, QPixmap, QPalette

# ── Optional OAuth ────────────────────────────────────────────────────────────
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build as _build_gmail
    OAUTH_AVAILABLE = True
except ImportError:
    OAUTH_AVAILABLE = False

# ── Constants ─────────────────────────────────────────────────────────────────
APP_NAME     = "Gmail Unsubscriber"
APP_VERSION  = "2.0"
IMAP_HOST    = "imap.gmail.com"
IMAP_PORT    = 993
CREDS_FILE   = Path(__file__).parent / "credentials.json"
TOKEN_FILE   = Path(__file__).parent / "token.pickle"
OAUTH_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]
SCAN_MODES = {
    "all_unread": ("UNSEEN", '"[Gmail]/All Mail"', None),
    "all_mail":   ("ALL",    '"[Gmail]/All Mail"', None),
    "promos":     ("ALL",    '"[Gmail]/All Mail"', "category:promotions"),
    "inbox":      ("UNSEEN", "INBOX",              None),
}


# ═══════════════════════════════════════════════════════════════════════════════
# Data
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Sender:
    email:       str
    name:        str            = ""
    count:       int            = 0
    unsubscribe: Optional[dict] = None   # {'mailto': ..., 'http': ...}
    accounts:    list           = field(default_factory=list)


@dataclass
class AppState:
    auth_method:   str    = ""       # "imap" | "oauth"
    imap_conns:    dict   = field(default_factory=dict)   # {email: (conn, password)}
    oauth_service: object = None
    scan_scope:    str    = "all_unread"
    max_emails:    int    = 1000
    senders:       list   = field(default_factory=list)   # Sender objects
    do_unsub:      bool   = True
    do_delete:     bool   = True
    unsub_ok:      list   = field(default_factory=list)
    unsub_web:     list   = field(default_factory=list)
    unsub_fail:    list   = field(default_factory=list)
    deleted_count: int    = 0


# ═══════════════════════════════════════════════════════════════════════════════
# Email helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _decode_mime(s: str) -> str:
    try:
        parts = _mime_decode(s)
        out = []
        for chunk, charset in parts:
            if isinstance(chunk, bytes):
                out.append(chunk.decode(charset or "utf-8", errors="replace"))
            else:
                out.append(str(chunk))
        return "".join(out).strip()
    except Exception:
        return s


def _parse_from(value: str) -> tuple:
    value = _decode_mime(value)
    m = re.match(r'^"?([^"<]*)"?\s*<([^>]+)>', value.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip().lower()
    v = value.strip()
    return v, v.lower()


def _parse_unsub(value: str) -> Optional[dict]:
    if not value:
        return None
    mailto = re.findall(r"<(mailto:[^>]+)>", value, re.I)
    http   = re.findall(r"<(https?://[^>]+)>", value, re.I)
    if not mailto and not http:
        return None
    return {"mailto": mailto[0] if mailto else None,
            "http":   http[0]   if http   else None}


def _extract_body_unsub_url(body: str) -> Optional[str]:
    """
    Scan an email body (HTML or plain text) for an unsubscribe URL.
    Returns the first URL whose href or link-text matches unsubscribe keywords.
    """
    # Decode common HTML entities so regex sees clean URLs
    body = body.replace("&amp;", "&").replace("&#38;", "&") \
               .replace("&lt;", "<").replace("&gt;", ">")

    KEYWORDS = re.compile(
        r'unsub|opt.?out|manage.{0,20}pref|remove.{0,20}list|email.{0,20}pref',
        re.I)

    # HTML <a href="...">link text</a>
    for m in re.finditer(
            r'<a[^>]+href=["\']([^"\'>\s]{8,})["\'][^>]*>(.*?)</a>',
            body, re.I | re.S):
        url  = m.group(1).strip()
        text = re.sub(r'<[^>]+>', '', m.group(2)).strip()
        if url.startswith("http") and KEYWORDS.search(url + " " + text):
            return url

    # Plain-text URLs (e.g. in text/plain part or unlinked HTML)
    for url in re.findall(r'https?://[^\s<>"\']{8,}', body):
        if KEYWORDS.search(url):
            return url

    return None


def _find_body_unsub_link(mail, sender_email: str) -> Optional[str]:
    """
    Fetch the most recent email from sender_email via IMAP, parse its body,
    and return the first unsubscribe URL found — or None.
    """
    try:
        mail.select('"[Gmail]/All Mail"', readonly=True)
        typ, data = mail.uid("SEARCH", "CHARSET", "UTF-8",
                             "FROM", f'"{sender_email}"')
        if typ != "OK" or not data or not data[0]:
            return None
        uids = data[0].split()
        if not uids:
            return None

        # Use the most recent email from this sender
        uid = uids[-1].decode()
        typ, msg_data = mail.uid("FETCH", uid, "(RFC822)")
        if typ != "OK" or not msg_data:
            return None

        raw = next((i[1] for i in msg_data if isinstance(i, tuple) and len(i) >= 2), None)
        if not raw:
            return None

        # Parse with Python's email library for proper MIME handling
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="replace")
        msg = _email_lib.message_from_bytes(raw)

        html_body, text_body = "", ""
        if msg.is_multipart():
            for part in msg.walk():
                ct = part.get_content_type()
                try:
                    payload = part.get_payload(decode=True)
                    if not payload:
                        continue
                    decoded = payload.decode(
                        part.get_content_charset() or "utf-8", errors="replace")
                    if ct == "text/html"  and not html_body:
                        html_body = decoded
                    elif ct == "text/plain" and not text_body:
                        text_body = decoded
                except Exception:
                    continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    decoded = payload.decode(
                        msg.get_content_charset() or "utf-8", errors="replace")
                    if msg.get_content_type() == "text/html":
                        html_body = decoded
                    else:
                        text_body = decoded
            except Exception:
                pass

        # HTML usually has proper href links; try it first
        return (_extract_body_unsub_url(html_body) or
                _extract_body_unsub_url(text_body))
    except Exception:
        return None


def _detect_gmail_env_accounts() -> list:
    """
    Scan os.environ for Gmail credential pairs.
    Recognises:
      • GMAIL_EMAIL  /  GMAIL_PASSWORD  (+ _APP_PASSWORD, _APP_PASS, _PASS variants)
      • GMAIL_EMAIL_1 / GMAIL_PASSWORD_1 … (indexed, up to _9)
      • GOOGLE_EMAIL / GOOGLE_PASSWORD variants
    Returns [(email, password), ...] deduplicated by email (case-insensitive).
    """
    env   = os.environ
    found, seen = [], set()

    def _push(e: str, p: str):
        e = e.strip()
        if (e and p and e.lower() not in seen and
                ("@gmail.com" in e.lower() or "@googlemail.com" in e.lower())):
            seen.add(e.lower())
            found.append((e, p.strip()))

    E_KEYS = ["GMAIL_EMAIL", "GMAIL_USER", "GOOGLE_EMAIL"]
    P_KEYS = ["GMAIL_APP_PASSWORD", "GMAIL_APP_PASS", "GMAIL_PASSWORD",
              "GMAIL_PASS",         "GOOGLE_APP_PASSWORD", "GOOGLE_PASSWORD"]

    # singular keys
    for ek in E_KEYS:
        if ek in env:
            for pk in P_KEYS:
                if pk in env:
                    _push(env[ek], env[pk])
                    break

    # indexed keys  GMAIL_EMAIL_1 / GMAIL_PASSWORD_1, …
    for i in range(1, 10):
        email = next(
            (env[k] for k in [f"GMAIL_EMAIL_{i}", f"GMAIL_USER_{i}",
                               f"GOOGLE_EMAIL_{i}"] if k in env), "")
        if not email:
            break
        pwd = next(
            (env[k] for k in [f"GMAIL_APP_PASSWORD_{i}", f"GMAIL_APP_PASS_{i}",
                               f"GMAIL_PASSWORD_{i}",    f"GMAIL_PASS_{i}"] if k in env), "")
        _push(email, pwd)

    return found


# ═══════════════════════════════════════════════════════════════════════════════
# Workers  (QThread)
# ═══════════════════════════════════════════════════════════════════════════════

class IMAPAuthWorker(QThread):
    success = Signal(str, object)   # (email, conn)
    error   = Signal(str)

    def __init__(self, email: str, password: str):
        super().__init__()
        self._email, self._password = email, password

    def run(self):
        try:
            conn = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
            conn.login(self._email, self._password)
            self.success.emit(self._email, conn)
        except imaplib.IMAP4.error as e:
            self.error.emit(
                f"Login failed: {e}\n\n"
                "Common fixes:\n"
                "• Gmail Settings → Forwarding and POP/IMAP → Enable IMAP\n"
                "• 2-Step Verification must be ON for App Passwords\n"
                "• Generate App Password at myaccount.google.com/apppasswords"
            )
        except Exception as e:
            self.error.emit(str(e))


class OAuthWorker(QThread):
    success = Signal(object)
    error   = Signal(str)

    def run(self):
        try:
            if not OAUTH_AVAILABLE:
                self.error.emit("OAuth libraries not installed.\nRun: pip install google-auth google-auth-oauthlib google-api-python-client")
                return
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
            svc = _build_gmail("gmail", "v1", credentials=creds)
            self.success.emit(svc)
        except Exception as e:
            self.error.emit(str(e))


class ScanWorker(QThread):
    progress = Signal(int, int, str)   # (current, total, last_sender_name)
    finished = Signal(list)            # list[Sender]
    error    = Signal(str)

    def __init__(self, mail, account_email: str, max_results: int, mode_key: str):
        super().__init__()
        self._mail, self._acct = mail, account_email
        self._max, self._mode  = max_results, mode_key
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            search_flag, folder, gm_raw = SCAN_MODES[self._mode]
            typ, _ = self._mail.select(folder, readonly=True)
            if typ != "OK":
                self.error.emit(f"Cannot open folder {folder}")
                return

            if gm_raw:
                typ, data = self._mail.uid("SEARCH", "CHARSET", "UTF-8", "X-GM-RAW", gm_raw)
            else:
                typ, data = self._mail.uid("SEARCH", None, search_flag)

            if typ != "OK" or not data or not data[0]:
                self.finished.emit([])
                return

            all_uids = data[0].split()
            uids     = all_uids[-self._max:][::-1]
            total    = len(uids)
            senders: dict = {}

            for i in range(0, total, 50):
                if self._stop:
                    break
                batch   = uids[i:i+50]
                uid_str = ",".join(u.decode() for u in batch)
                try:
                    typ, msg_data = self._mail.uid(
                        "FETCH", uid_str,
                        "(BODY.PEEK[HEADER.FIELDS (FROM LIST-UNSUBSCRIBE)])"
                    )
                except Exception:
                    self.progress.emit(min(i + 50, total), total, "")
                    continue

                if typ != "OK" or not msg_data:
                    continue

                last = ""
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
                    name, ea = _parse_from(from_val)
                    unsub    = _parse_unsub(unsub_val)
                    if ea not in senders:
                        senders[ea] = Sender(email=ea, name=name, count=1,
                                              unsubscribe=unsub, accounts=[self._acct])
                    else:
                        senders[ea].count += 1
                        if unsub and not senders[ea].unsubscribe:
                            senders[ea].unsubscribe = unsub
                    last = name or ea

                self.progress.emit(min(i + 50, total), total, last)

            result = sorted(senders.values(), key=lambda s: s.count, reverse=True)
            self.finished.emit(result)
        except Exception as e:
            self.error.emit(str(e))


class ActionWorker(QThread):
    """Runs unsubscribe + delete actions on selected senders."""
    item_done = Signal(str, str, str)   # (email, status, message)  status: ok|web|fail
    progress  = Signal(int, int)        # (done, total)
    finished  = Signal(int)             # total_deleted

    def __init__(self, senders: list, imap_conns: dict, do_unsub: bool, do_delete: bool):
        super().__init__()
        self._senders    = senders
        self._imap_conns = imap_conns
        self._do_unsub   = do_unsub
        self._do_delete  = do_delete

    def run(self):
        total         = len(self._senders)
        total_deleted = 0

        for idx, sender in enumerate(self._senders):
            # ── Unsubscribe ──────────────────────────────────────────
            if self._do_unsub:
                unsub = sender.unsubscribe
                url   = None

                # 1. HTTP link from List-Unsubscribe header (instant, no fetch needed)
                if unsub and unsub.get("http"):
                    url = unsub["http"]

                # 2. No header link — fetch one real email body and extract the link
                if not url:
                    for acct in sender.accounts:
                        if acct in self._imap_conns:
                            conn, _ = self._imap_conns[acct]
                            url = _find_body_unsub_link(conn, sender.email)
                            if url:
                                break

                if url:
                    webbrowser.open(url)
                    self.item_done.emit(sender.email, "ok", "Unsubscribe link opened in browser")
                else:
                    self.item_done.emit(sender.email, "fail", "No unsubscribe link found")

            # ── Delete unread ────────────────────────────────────────
            if self._do_delete:
                by_acct: dict = defaultdict(list)
                for acct in sender.accounts:
                    by_acct[acct].append(sender.email)

                for acct, emails in by_acct.items():
                    if acct not in self._imap_conns:
                        continue
                    mail, _ = self._imap_conns[acct]
                    try:
                        mail.select('"[Gmail]/All Mail"', readonly=False)
                        for ea in emails:
                            typ, data = mail.uid("SEARCH", "CHARSET", "UTF-8",
                                                  "UNSEEN", "FROM", f'"{ea}"')
                            if typ != "OK" or not data or not data[0]:
                                continue
                            uids = data[0].split()
                            for i in range(0, len(uids), 100):
                                batch   = uids[i:i+100]
                                uid_str = ",".join(u.decode() for u in batch)
                                mail.uid("COPY",  uid_str, '"[Gmail]/Trash"')
                                mail.uid("STORE", uid_str, "+FLAGS", "(\\Deleted)")
                                total_deleted += len(batch)
                            mail.expunge()
                    except Exception:
                        pass

            self.progress.emit(idx + 1, total)

        self.finished.emit(total_deleted)


# ═══════════════════════════════════════════════════════════════════════════════
# Table model
# ═══════════════════════════════════════════════════════════════════════════════

class SenderTableModel(QAbstractTableModel):
    HEADERS  = ["", "Sender", "Email", "Emails", "Unsub"]
    COL_CHK  = 0
    COL_NAME = 1
    COL_MAIL = 2
    COL_CNT  = 3
    COL_UNSB = 4

    def __init__(self, senders: list):
        super().__init__()
        self._senders  = senders
        self._checked: set = set()   # set of email strings

    # ── required overrides ───────────────────────────────────────
    def rowCount(self, parent=QModelIndex()):    return len(self._senders)
    def columnCount(self, parent=QModelIndex()): return len(self.HEADERS)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or index.row() >= len(self._senders):
            return None
        s, col = self._senders[index.row()], index.column()

        if role == Qt.CheckStateRole and col == self.COL_CHK:
            return Qt.Checked if s.email in self._checked else Qt.Unchecked

        if role == Qt.DisplayRole:
            if col == self.COL_NAME: return s.name or s.email
            if col == self.COL_MAIL: return s.email
            if col == self.COL_CNT:  return str(s.count)
            if col == self.COL_UNSB: return "✓" if s.unsubscribe else "—"

        if role == Qt.ForegroundRole:
            if col == self.COL_UNSB:
                return QColor("#22c55e") if s.unsubscribe else QColor("#94a3b8")
            if col == self.COL_MAIL:
                return QColor("#64748b")

        if role == Qt.TextAlignmentRole:
            if col in (self.COL_CNT, self.COL_UNSB):
                return Qt.AlignCenter

        if role == Qt.UserRole:
            return s

        return None

    def setData(self, index: QModelIndex, value, role: int = Qt.EditRole):
        if role == Qt.CheckStateRole and index.column() == self.COL_CHK:
            ea = self._senders[index.row()].email
            if value == Qt.Checked:
                self._checked.add(ea)
            else:
                self._checked.discard(ea)
            self.dataChanged.emit(index, index, [Qt.CheckStateRole])
            return True
        return False

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        f = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if index.column() == self.COL_CHK:
            f |= Qt.ItemIsUserCheckable
        return f

    def headerData(self, section: int, orientation: Qt.Orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.HEADERS[section]
        return None

    # ── helpers ──────────────────────────────────────────────────
    def check_visible(self, proxy: QSortFilterProxyModel, checked: bool):
        for row in range(proxy.rowCount()):
            src = proxy.mapToSource(proxy.index(row, self.COL_CHK))
            self.setData(src, Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)

    def checked_count(self) -> int:
        return len(self._checked)

    def get_checked(self) -> list:
        return [s for s in self._senders if s.email in self._checked]


# ═══════════════════════════════════════════════════════════════════════════════
# Screens
# ═══════════════════════════════════════════════════════════════════════════════

def _card(min_w: int = 460) -> QFrame:
    f = QFrame()
    f.setObjectName("card")
    f.setMinimumWidth(min_w)
    return f


def _title(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("title")
    return lbl


def _sub(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("sub")
    return lbl


# ── Account row widget ────────────────────────────────────────────────────────

class AccountRow(QFrame):
    """One Gmail credential pair in the sign-in IMAP section."""
    remove_clicked = Signal(object)   # emits self so the parent can remove it

    def __init__(self, email: str = "", password: str = "", from_env: bool = False):
        super().__init__()
        self._from_env = from_env
        self._build(email, password)

    def _build(self, email: str, password: str):
        self.setObjectName("acctRow")
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        lay.setContentsMargins(12, 10, 12, 10)

        # top bar: env badge + remove ×
        top = QHBoxLayout()
        if self._from_env:
            badge = QLabel("  detected from env  ")
            badge.setStyleSheet(
                "background:#dcfce7; color:#16a34a; border-radius:4px;"
                "padding:1px 7px; font-size:11px; font-weight:600;")
            top.addWidget(badge)
        top.addStretch()
        self._rm_btn = QToolButton()
        self._rm_btn.setText("✕")
        self._rm_btn.setFixedSize(22, 22)
        self._rm_btn.setStyleSheet(
            "QToolButton{border:none;color:#94a3b8;font-size:13px;background:transparent;}"
            "QToolButton:hover{color:#ef4444;}")
        self._rm_btn.clicked.connect(lambda: self.remove_clicked.emit(self))
        top.addWidget(self._rm_btn)
        lay.addLayout(top)

        # email
        self._email_edit = QLineEdit(email)
        self._email_edit.setPlaceholderText("you@gmail.com")
        lay.addWidget(self._email_edit)

        # password + show toggle
        pr = QHBoxLayout()
        self._pwd_edit = QLineEdit(password)
        self._pwd_edit.setPlaceholderText("App Password  (xxxx xxxx xxxx xxxx)")
        self._pwd_edit.setEchoMode(QLineEdit.Password)
        show = QToolButton()
        show.setText("👁")
        show.setFixedSize(36, 36)
        show.setCheckable(True)
        show.toggled.connect(
            lambda on: self._pwd_edit.setEchoMode(
                QLineEdit.Normal if on else QLineEdit.Password))
        pr.addWidget(self._pwd_edit, 1)
        pr.addWidget(show)
        lay.addLayout(pr)

        # per-row status
        self._status_lbl = QLabel("")
        self._status_lbl.setObjectName("sub")
        lay.addWidget(self._status_lbl)

    @property
    def email(self)     -> str:  return self._email_edit.text().strip()
    @property
    def password(self)  -> str:  return self._pwd_edit.text().strip()
    @property
    def is_filled(self) -> bool: return bool(self.email and self.password)

    def set_status(self, msg: str, ok: bool):
        self._status_lbl.setText(msg)
        self._status_lbl.setStyleSheet(
            f"color:{'#22c55e' if ok else '#ef4444'}; font-size:12px;")


# ── Screen 1: Sign-in ────────────────────────────────────────────────────────

class SignInScreen(QWidget):
    go_next = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self._state         = state
        self._workers: list = []
        self._rows:    list = []   # list[AccountRow]
        self._pending        = 0
        self._conn_errors    = 0
        self._build()

    # ── layout ──────────────────────────────────────────────────────
    def _build(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        card = _card(480)
        cl   = QVBoxLayout(card)
        cl.setSpacing(18)
        cl.setContentsMargins(36, 36, 36, 36)

        cl.addWidget(_title(APP_NAME))
        cl.addWidget(_sub("Connect your Gmail account(s)"))
        cl.addSpacing(4)

        # ── auth method radios ──
        method_grp = QGroupBox("Sign-in method")
        ml = QVBoxLayout(method_grp)
        self._oauth_rb = QRadioButton("Sign in with Google  (OAuth — recommended)")
        self._imap_rb  = QRadioButton("App Password + IMAP  (supports multiple accounts)")
        self._oauth_rb.setChecked(True)
        ml.addWidget(self._oauth_rb)
        ml.addWidget(self._imap_rb)
        cl.addWidget(method_grp)

        # ── IMAP section ──
        self._imap_frame = QWidget()
        il = QVBoxLayout(self._imap_frame)
        il.setSpacing(8)
        il.setContentsMargins(0, 0, 0, 0)

        # env detection banner (hidden until populated)
        self._env_banner = QLabel("")
        self._env_banner.setVisible(False)
        il.addWidget(self._env_banner)

        # account rows container
        self._rows_widget = QWidget()
        self._rows_lay    = QVBoxLayout(self._rows_widget)
        self._rows_lay.setSpacing(8)
        self._rows_lay.setContentsMargins(0, 0, 0, 0)
        il.addWidget(self._rows_widget)

        # + Add another account
        add_lay = QHBoxLayout()
        self._add_btn = QPushButton("+ Add another account")
        self._add_btn.setObjectName("secondary")
        self._add_btn.setFixedHeight(34)
        add_lay.addWidget(self._add_btn)
        add_lay.addStretch()
        il.addLayout(add_lay)

        # app-password help link
        hint = QLabel('<a href="https://myaccount.google.com/apppasswords">'
                      'How to get an App Password ↗</a>')
        hint.setOpenExternalLinks(True)
        hint.setObjectName("sub")
        il.addWidget(hint)

        self._imap_frame.setVisible(False)
        cl.addWidget(self._imap_frame)

        # ── error banner ──
        self._err = QLabel("")
        self._err.setObjectName("error")
        self._err.setWordWrap(True)
        self._err.setVisible(False)
        cl.addWidget(self._err)

        # ── action button ──
        self._btn = QPushButton("Connect →")
        self._btn.setFixedHeight(44)
        cl.addWidget(self._btn)

        root.addWidget(card, alignment=Qt.AlignCenter)

        # wire
        self._oauth_rb.toggled.connect(self._toggle_method)
        self._imap_rb.toggled.connect(self._toggle_method)
        self._btn.clicked.connect(self._on_connect)
        self._add_btn.clicked.connect(lambda: self._add_row())

        # populate rows from env (or one blank row)
        self._populate_env_accounts()

    # ── env population ───────────────────────────────────────────────
    def _populate_env_accounts(self):
        env_accts = _detect_gmail_env_accounts()
        if env_accts:
            n = len(env_accts)
            self._env_banner.setText(
                f"  ✓  Found {n} account{'s' if n > 1 else ''} in environment variables "
                f"— passwords pre-filled.")
            self._env_banner.setStyleSheet(
                "background:#dcfce7; color:#16a34a; border-radius:6px; "
                "padding:6px 10px; font-size:12px;")
            self._env_banner.setVisible(True)
            for email, pwd in env_accts:
                self._add_row(email, pwd, from_env=True)
        else:
            self._add_row()   # start with one blank row

    # ── row management ───────────────────────────────────────────────
    def _add_row(self, email: str = "", password: str = "", from_env: bool = False):
        row = AccountRow(email, password, from_env)
        row.remove_clicked.connect(self._remove_row)
        self._rows.append(row)
        self._rows_lay.addWidget(row)
        self._refresh_remove_buttons()

    def _remove_row(self, row: "AccountRow"):
        if len(self._rows) <= 1:
            return   # always keep at least one row
        self._rows.remove(row)
        self._rows_lay.removeWidget(row)
        row.deleteLater()
        self._refresh_remove_buttons()

    def _refresh_remove_buttons(self):
        """Show ✕ only when there are 2+ rows."""
        show = len(self._rows) > 1
        for r in self._rows:
            r._rm_btn.setVisible(show)

    # ── method toggle ────────────────────────────────────────────────
    def _toggle_method(self):
        self._imap_frame.setVisible(self._imap_rb.isChecked())
        self._err.setVisible(False)

    # ── error helper ─────────────────────────────────────────────────
    def _show_err(self, msg: str):
        self._btn.setEnabled(True)
        self._err.setText(msg)
        self._err.setVisible(True)

    # ── connect ──────────────────────────────────────────────────────
    def _on_connect(self):
        self._err.setVisible(False)
        if self._imap_rb.isChecked():
            self._connect_imap()
        else:
            self._connect_oauth()

    def _connect_imap(self):
        filled = [r for r in self._rows if r.is_filled]
        if not filled:
            self._show_err(
                "Please enter at least one Gmail address and App Password.")
            return
        self._err.setVisible(False)
        self._btn.setEnabled(False)
        n = len(filled)
        self._btn.setText(f"Connecting {n} account{'s' if n > 1 else ''}…")
        self._pending     = n
        self._conn_errors = 0
        self._state.imap_conns.clear()   # reset any previous session

        for row in filled:
            w = IMAPAuthWorker(row.email, row.password)
            w.success.connect(lambda email, conn, r=row: self._imap_ok(email, conn, r))
            w.error.connect(  lambda msg,       r=row: self._imap_err(msg, r))
            self._workers.append(w)
            w.start()

    def _imap_ok(self, email: str, conn, row: "AccountRow"):
        self._state.imap_conns[email] = (conn, row.password)
        row.set_status("✓  Connected", True)
        self._pending -= 1
        self._check_done()

    def _imap_err(self, msg: str, row: "AccountRow"):
        short = msg.split("\n")[0][:80]
        row.set_status(f"✗  {short}", False)
        self._conn_errors += 1
        self._pending -= 1
        self._check_done()

    def _check_done(self):
        if self._pending > 0:
            return
        self._btn.setEnabled(True)
        try:
            self._btn.clicked.disconnect()
        except RuntimeError:
            pass

        ok_count = len(self._state.imap_conns)
        if self._conn_errors == 0:
            # All succeeded
            self._state.auth_method = "imap"
            self._btn.setText("Continue →")
            self._btn.clicked.connect(self.go_next.emit)
        elif ok_count > 0:
            # Partial success — let user continue with what connected
            self._state.auth_method = "imap"
            self._show_err(
                f"{self._conn_errors} account(s) failed to connect.  "
                f"Fix above and retry, or continue with the "
                f"{ok_count} successfully connected account(s).")
            self._btn.setText(f"Continue with {ok_count} account(s) →")
            self._btn.clicked.connect(self.go_next.emit)
        else:
            # All failed
            self._show_err(
                "All accounts failed to connect.  "
                "Double-check your Gmail addresses and App Passwords.")
            self._btn.setText("Retry →")
            self._btn.clicked.connect(self._on_connect)

    def _connect_oauth(self):
        if not OAUTH_AVAILABLE:
            self._show_err(
                "OAuth libraries not installed.\n"
                "Run: pip install google-auth google-auth-oauthlib google-api-python-client")
            return
        if not CREDS_FILE.exists():
            self._show_err(
                f"credentials.json not found.\nExpected at: {CREDS_FILE}\n"
                "Download from Google Cloud Console → APIs & Services → Credentials.")
            return
        self._btn.setEnabled(False)
        self._btn.setText("Opening browser…")
        w = OAuthWorker()
        w.success.connect(self._oauth_ok)
        w.error.connect(self._show_err)
        self._workers.append(w)
        w.start()

    def _oauth_ok(self, service):
        self._state.auth_method   = "oauth"
        self._state.oauth_service = service
        self._btn.setText("Continue →")
        self._btn.setEnabled(True)
        try:
            self._btn.clicked.disconnect()
        except RuntimeError:
            pass
        self._btn.clicked.connect(self.go_next.emit)


# ── Screen 2: Scan config ─────────────────────────────────────────────────────

class ConfigScreen(QWidget):
    go_next = Signal()
    go_back = Signal()

    MODE_LABELS = {
        "all_unread": "All unread emails  (catches promos Gmail missed) ← recommended",
        "all_mail":   "All emails — read + unread  (most thorough, slower)",
        "promos":     "Promotions folder only",
        "inbox":      "Inbox unread only",
    }

    def __init__(self, state: AppState):
        super().__init__()
        self._state = state
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        card = _card(500)
        cl   = QVBoxLayout(card)
        cl.setSpacing(20)
        cl.setContentsMargins(36, 36, 36, 36)

        cl.addWidget(_title("Configure Scan"))
        cl.addSpacing(4)

        # scope radios
        scope_grp = QGroupBox("Scan scope")
        sl = QVBoxLayout(scope_grp)
        self._mode_radios: dict = {}
        btn_grp = QButtonGroup(self)
        for i, (key, label) in enumerate(self.MODE_LABELS.items()):
            rb = QRadioButton(label)
            if i == 0:
                rb.setChecked(True)
            self._mode_radios[key] = rb
            btn_grp.addButton(rb)
            sl.addWidget(rb)
        cl.addWidget(scope_grp)

        # max emails
        emails_grp = QGroupBox("Maximum emails to scan per account")
        el = QVBoxLayout(emails_grp)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(100, 10000)
        self._slider.setSingleStep(100)
        self._slider.setPageStep(500)
        self._slider.setValue(1000)
        self._slider_lbl = QLabel("1,000 emails")
        self._slider_lbl.setAlignment(Qt.AlignCenter)
        self._slider_lbl.setObjectName("sub")
        self._slider.valueChanged.connect(
            lambda v: self._slider_lbl.setText(f"{v:,} emails"))
        rng = QHBoxLayout()
        rng.addWidget(QLabel("100"))
        rng.addWidget(self._slider, 1)
        rng.addWidget(QLabel("10,000"))
        el.addLayout(rng)
        el.addWidget(self._slider_lbl)
        cl.addWidget(emails_grp)

        btn_row = QHBoxLayout()
        back = QPushButton("← Back")
        back.setObjectName("secondary")
        scan = QPushButton("Start Scan →")
        btn_row.addWidget(back)
        btn_row.addWidget(scan, 1)
        cl.addLayout(btn_row)

        root.addWidget(card, alignment=Qt.AlignCenter)
        back.clicked.connect(self.go_back.emit)
        scan.clicked.connect(self._on_start)

    def _on_start(self):
        for key, rb in self._mode_radios.items():
            if rb.isChecked():
                self._state.scan_scope = key
                break
        self._state.max_emails = self._slider.value()
        self.go_next.emit()


# ── Screen 3: Scanning progress ───────────────────────────────────────────────

class ScanningScreen(QWidget):
    go_next     = Signal()
    go_back     = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self._state   = state
        self._workers: list = []
        self._pending = 0
        self._all_senders: dict = {}
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        card = _card(540)
        cl   = QVBoxLayout(card)
        cl.setSpacing(16)
        cl.setContentsMargins(36, 36, 36, 36)

        self._title_lbl = _title("Scanning…")
        self._title_lbl.setAlignment(Qt.AlignCenter)
        cl.addWidget(self._title_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        cl.addWidget(self._bar)

        self._stats_lbl = QLabel("Preparing…")
        self._stats_lbl.setAlignment(Qt.AlignCenter)
        self._stats_lbl.setObjectName("sub")
        cl.addWidget(self._stats_lbl)

        self._found_lbl = QLabel("0")
        self._found_lbl.setAlignment(Qt.AlignCenter)
        self._found_lbl.setStyleSheet(
            "font-size: 48px; font-weight: 700; color: #4361ee;")
        cl.addWidget(self._found_lbl)

        cl.addWidget(_sub("unique senders found"))

        cl.addWidget(_sub("Recently found:"))
        self._recent = QListWidget()
        self._recent.setMaximumHeight(140)
        self._recent.setFocusPolicy(Qt.NoFocus)
        cl.addWidget(self._recent)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setObjectName("secondary")
        self._cancel_btn.setFixedWidth(120)
        cl.addWidget(self._cancel_btn, alignment=Qt.AlignCenter)

        root.addWidget(card, alignment=Qt.AlignCenter)
        self._cancel_btn.clicked.connect(self._on_cancel)

    def start(self):
        self._all_senders.clear()
        self._workers.clear()
        self._recent.clear()
        self._bar.setValue(0)
        self._found_lbl.setText("0")
        self._stats_lbl.setText("Connecting…")
        self._title_lbl.setText("Scanning…")
        self._cancel_btn.setEnabled(True)

        if self._state.auth_method == "imap":
            accts = list(self._state.imap_conns.items())
            self._pending = len(accts)
            # Track per-worker progress
            self._worker_progress: dict = {}
            for email, (conn, _) in accts:
                w = ScanWorker(conn, email, self._state.max_emails, self._state.scan_scope)
                self._worker_progress[id(w)] = (0, self._state.max_emails)
                w.progress.connect(self._on_progress)
                w.finished.connect(self._on_worker_done)
                w.error.connect(self._on_error)
                self._workers.append(w)
                w.start()
        else:
            self._pending = 1
            # OAuth scan not yet implemented — placeholder
            QTimer.singleShot(500, lambda: self._on_error("OAuth scan not yet implemented in GUI."))

    def _on_progress(self, current: int, total: int, last: str):
        # Sum across all workers
        w = self.sender()
        if hasattr(self, "_worker_progress") and id(w) in self._worker_progress:
            self._worker_progress[id(w)] = (current, total)
        done_sum  = sum(p[0] for p in self._worker_progress.values())
        total_sum = sum(p[1] for p in self._worker_progress.values())
        pct = int(done_sum / total_sum * 100) if total_sum else 0
        self._bar.setValue(pct)
        self._stats_lbl.setText(f"{done_sum:,} / {total_sum:,} emails processed")
        if last:
            self._all_senders[last] = True
            self._found_lbl.setText(str(len(self._all_senders)))
            item = QListWidgetItem(f"  {last}")
            self._recent.insertItem(0, item)
            if self._recent.count() > 8:
                self._recent.takeItem(8)

    def _on_worker_done(self, senders: list):
        # Merge into state
        for s in senders:
            existing = next((x for x in self._state.senders if x.email == s.email), None)
            if existing:
                existing.count += s.count
                if not existing.unsubscribe and s.unsubscribe:
                    existing.unsubscribe = s.unsubscribe
                for a in s.accounts:
                    if a not in existing.accounts:
                        existing.accounts.append(a)
            else:
                self._state.senders.append(s)

        self._pending -= 1
        if self._pending == 0:
            self._state.senders.sort(key=lambda s: s.count, reverse=True)
            self._bar.setValue(100)
            total = len(self._state.senders)
            self._title_lbl.setText("Scan complete!")
            self._stats_lbl.setText(f"Found {total} unique senders")
            self._found_lbl.setText(str(total))
            self._cancel_btn.setText("Continue →")
            self._cancel_btn.clicked.disconnect()
            self._cancel_btn.clicked.connect(self.go_next.emit)

    def _on_error(self, msg: str):
        QMessageBox.critical(self, "Scan Error", msg)
        self.go_back.emit()

    def _on_cancel(self):
        for w in self._workers:
            try:
                w.stop()
                w.wait(1000)
            except Exception:
                pass
        self._state.senders.clear()
        self.go_back.emit()


# ── Screen 4: Sender list (core) ──────────────────────────────────────────────

class SendersScreen(QWidget):
    go_next = Signal()
    go_back = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self._state = state
        self._model: Optional[SenderTableModel] = None
        self._proxy: Optional[QSortFilterProxyModel] = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        # ── header ──
        hdr = QHBoxLayout()
        self._title_lbl = _title("Senders")
        hdr.addWidget(self._title_lbl)
        hdr.addStretch()
        self._count_lbl = _sub("")
        hdr.addWidget(self._count_lbl)
        root.addLayout(hdr)

        # ── filter row ──
        frow = QHBoxLayout()
        self._filter = QLineEdit()
        self._filter.setPlaceholderText("🔍   Filter by name or email…")
        self._filter.setClearButtonEnabled(True)
        sel_all = QPushButton("Select All")
        sel_all.setObjectName("secondary")
        sel_all.setFixedWidth(100)
        clr = QPushButton("Clear")
        clr.setObjectName("secondary")
        clr.setFixedWidth(70)
        frow.addWidget(self._filter, 1)
        frow.addWidget(sel_all)
        frow.addWidget(clr)
        root.addLayout(frow)

        # ── table ──
        self._table = QTableView()
        self._table.setAlternatingRowColors(True)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(36)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.horizontalHeader().setSortIndicatorShown(True)
        self._table.setSortingEnabled(True)
        self._table.setShowGrid(False)
        root.addWidget(self._table, 1)

        # ── action bar ──
        abar = QHBoxLayout()
        self._sel_lbl = _sub("0 selected")
        abar.addWidget(self._sel_lbl)
        abar.addStretch()

        self._unsub_btn = QPushButton("Unsubscribe")
        self._both_btn  = QPushButton("Unsubscribe + Delete")
        self._both_btn.setObjectName("primary_strong")

        for b in (self._unsub_btn, self._both_btn):
            b.setEnabled(False)
            b.setFixedHeight(40)
            abar.addWidget(b)

        root.addLayout(abar)

        # wire
        self._filter.textChanged.connect(self._on_filter)
        sel_all.clicked.connect(lambda: self._toggle_all(True))
        clr.clicked.connect(lambda: self._toggle_all(False))
        self._unsub_btn.clicked.connect(lambda: self._confirm_action(True, False))
        self._both_btn.clicked.connect( lambda: self._confirm_action(True, True))

        # checkbox interaction — PySide6 proxy doesn't relay CheckStateRole
        # through the delegate reliably, so we toggle manually on click / Space
        self._table.clicked.connect(self._on_row_clicked)
        self._table.installEventFilter(self)

    def load(self):
        """Call every time this screen becomes active."""
        senders = self._state.senders
        self._model = SenderTableModel(senders)
        self._proxy = QSortFilterProxyModel()
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self._proxy.setFilterKeyColumn(-1)
        self._table.setModel(self._proxy)

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.Stretch)
        hdr.setSectionResizeMode(3, QHeaderView.Fixed)
        hdr.setSectionResizeMode(4, QHeaderView.Fixed)
        self._table.setColumnWidth(0, 40)
        self._table.setColumnWidth(3, 70)
        self._table.setColumnWidth(4, 65)

        self._model.dataChanged.connect(self._update_sel)
        has_unsub = sum(1 for s in senders if s.unsubscribe)
        self._title_lbl.setText(f"Senders  ({len(senders)})")
        self._count_lbl.setText(f"{has_unsub} have unsubscribe link  ·  "
                                  f"{len(senders) - has_unsub} do not")
        self._update_sel()

    def _on_filter(self, text: str):
        if self._proxy:
            self._proxy.setFilterRegularExpression(
                QRegularExpression(text,
                                   QRegularExpression.PatternOption.CaseInsensitiveOption))

    def _toggle_all(self, checked: bool):
        if self._model and self._proxy:
            self._model.check_visible(self._proxy, checked)

    def _update_sel(self):
        if not self._model:
            return
        n = self._model.checked_count()
        self._sel_lbl.setText(f"{n} selected")
        on = n > 0
        for b in (self._unsub_btn, self._both_btn):
            b.setEnabled(on)

    # ── checkbox interaction helpers ─────────────────────────────────
    def _toggle_row(self, proxy_index: QModelIndex):
        """Toggle the checkbox for the row at proxy_index (any column)."""
        if not self._model or not self._proxy:
            return
        chk_proxy = self._proxy.index(proxy_index.row(), SenderTableModel.COL_CHK)
        src = self._proxy.mapToSource(chk_proxy)
        curr = self._model.data(src, Qt.CheckStateRole)
        new_val = Qt.Unchecked if curr == Qt.Checked else Qt.Checked
        self._model.setData(src, new_val, Qt.CheckStateRole)

    def _on_row_clicked(self, proxy_index: QModelIndex):
        self._toggle_row(proxy_index)

    def eventFilter(self, obj, event):
        """Space bar toggles the checkbox on the current row."""
        if obj == self._table and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key_Space:
                idx = self._table.currentIndex()
                if idx.isValid():
                    self._toggle_row(idx)
                    return True
        return super().eventFilter(obj, event)

    def _confirm_action(self, do_unsub: bool, do_delete: bool):
        if not self._model:
            return
        checked = self._model.get_checked()
        if not checked:
            return
        actions = []
        if do_unsub:  actions.append("• Send unsubscribe requests")
        if do_delete: actions.append("• Delete all unread emails from them")
        msg = (f"You selected {len(checked)} sender(s).\n\n"
               + "\n".join(actions)
               + "\n\nProceed?")
        if QMessageBox.question(self, "Confirm", msg) != QMessageBox.Yes:
            return
        self._state.senders    = checked
        self._state.do_unsub   = do_unsub
        self._state.do_delete  = do_delete
        self.go_next.emit()


# ── Screen 5a: Processing ─────────────────────────────────────────────────────

class ProcessingScreen(QWidget):
    go_next = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self._state  = state
        self._worker = None
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        card = _card(500)
        cl   = QVBoxLayout(card)
        cl.setSpacing(16)
        cl.setContentsMargins(36, 36, 36, 36)

        self._title_lbl = _title("Processing…")
        self._title_lbl.setAlignment(Qt.AlignCenter)
        cl.addWidget(self._title_lbl)

        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setValue(0)
        self._bar.setTextVisible(False)
        self._bar.setFixedHeight(8)
        cl.addWidget(self._bar)

        self._status_lbl = QLabel("Starting…")
        self._status_lbl.setAlignment(Qt.AlignCenter)
        self._status_lbl.setObjectName("sub")
        cl.addWidget(self._status_lbl)

        self._log = QListWidget()
        self._log.setMaximumHeight(200)
        cl.addWidget(self._log)

        root.addWidget(card, alignment=Qt.AlignCenter)

    def start(self):
        self._log.clear()
        self._bar.setValue(0)
        self._status_lbl.setText("Starting…")
        self._title_lbl.setText("Processing…")
        self._state.unsub_ok.clear()
        self._state.unsub_web.clear()
        self._state.unsub_fail.clear()
        self._state.deleted_count = 0

        self._worker = ActionWorker(
            self._state.senders,
            self._state.imap_conns,
            self._state.do_unsub,
            self._state.do_delete,
        )
        self._worker.item_done.connect(self._on_item)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.start()

    def _on_item(self, email: str, status: str, msg: str):
        icon = {"ok": "✓", "web": "↗", "fail": "✗"}.get(status, "·")
        self._log.insertItem(0, f"  {icon}  {email}  —  {msg}")
        if status == "ok":
            self._state.unsub_ok.append(email)
        elif status == "web":
            self._state.unsub_web.append(email)
        else:
            self._state.unsub_fail.append(email)

    def _on_progress(self, done: int, total: int):
        pct = int(done / total * 100) if total else 0
        self._bar.setValue(pct)
        self._status_lbl.setText(f"{done} / {total} senders processed")

    def _on_done(self, deleted: int):
        self._state.deleted_count = deleted
        self._bar.setValue(100)
        self._title_lbl.setText("Done!")
        self._status_lbl.setText("All done — see results below.")
        QTimer.singleShot(600, self.go_next.emit)


# ── Screen 5b: Results ────────────────────────────────────────────────────────

class ResultsScreen(QWidget):
    scan_again = Signal()

    def __init__(self, state: AppState):
        super().__init__()
        self._state = state
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setAlignment(Qt.AlignCenter)

        card = _card(480)
        cl   = QVBoxLayout(card)
        cl.setSpacing(16)
        cl.setContentsMargins(36, 36, 36, 36)

        self._title = _title("All Done! 🎉")
        self._title.setAlignment(Qt.AlignCenter)
        cl.addWidget(self._title)
        cl.addSpacing(8)

        self._ok_lbl    = QLabel("")
        self._web_lbl   = QLabel("")
        self._fail_lbl  = QLabel("")
        self._del_lbl   = QLabel("")
        for lbl in (self._ok_lbl, self._web_lbl, self._fail_lbl, self._del_lbl):
            lbl.setAlignment(Qt.AlignLeft)
            lbl.setObjectName("result_row")
            cl.addWidget(lbl)

        cl.addSpacing(4)

        # expandable failed list
        self._fail_toggle = QPushButton("▶  Show failed items")
        self._fail_toggle.setObjectName("secondary")
        self._fail_toggle.setCheckable(True)
        self._fail_toggle.toggled.connect(self._toggle_fail)
        cl.addWidget(self._fail_toggle)

        self._fail_list = QListWidget()
        self._fail_list.setMaximumHeight(120)
        self._fail_list.setVisible(False)
        cl.addWidget(self._fail_list)

        cl.addSpacing(8)

        btn_row = QHBoxLayout()
        scan_again = QPushButton("↺  Scan Again")
        scan_again.setObjectName("secondary")
        btn_row.addWidget(scan_again)
        cl.addLayout(btn_row)

        root.addWidget(card, alignment=Qt.AlignCenter)
        scan_again.clicked.connect(self.scan_again.emit)

    def load(self):
        st = self._state
        self._ok_lbl.setText(  f"  ✓  {len(st.unsub_ok)}  unsubscribe links opened in browser")
        self._web_lbl.setVisible(False)
        self._fail_lbl.setText(f"  ✗  {len(st.unsub_fail)}  no unsubscribe link found")
        self._del_lbl.setText( f"  🗑  {st.deleted_count}  unread emails moved to Trash")

        self._ok_lbl.setStyleSheet  ("color: #22c55e; font-size: 15px;")
        self._web_lbl.setStyleSheet ("color: #f59e0b; font-size: 15px;")
        self._fail_lbl.setStyleSheet("color: #ef4444; font-size: 15px;")
        self._del_lbl.setStyleSheet ("color: #4361ee; font-size: 15px;")

        self._fail_list.clear()
        for ea in st.unsub_fail:
            self._fail_list.addItem(f"  {ea}")
        self._fail_toggle.setVisible(bool(st.unsub_fail))
        self._fail_toggle.setChecked(False)
        self._fail_list.setVisible(False)

    def _toggle_fail(self, on: bool):
        self._fail_list.setVisible(on)
        self._fail_toggle.setText(
            "▼  Hide failed items" if on else "▶  Show failed items")


# ═══════════════════════════════════════════════════════════════════════════════
# Main window
# ═══════════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(860, 600)
        self.resize(1020, 700)

        self._state   = AppState()
        self._stack   = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Create screens
        self._signin     = SignInScreen(self._state)
        self._config     = ConfigScreen(self._state)
        self._scanning   = ScanningScreen(self._state)
        self._senders    = SendersScreen(self._state)
        self._processing = ProcessingScreen(self._state)
        self._results    = ResultsScreen(self._state)

        for s in (self._signin, self._config, self._scanning,
                  self._senders, self._processing, self._results):
            self._stack.addWidget(s)

        # Navigation wiring
        self._signin.go_next.connect(    lambda: self._goto(self._config))
        self._config.go_next.connect(    self._start_scan)
        self._config.go_back.connect(    lambda: self._goto(self._signin))
        self._scanning.go_next.connect(  self._show_senders)
        self._scanning.go_back.connect(  lambda: self._goto(self._config))
        self._senders.go_next.connect(   self._start_processing)
        self._senders.go_back.connect(   lambda: self._goto(self._scanning))
        self._processing.go_next.connect(self._show_results)
        self._results.scan_again.connect(self._reset)

        self._goto(self._signin)

    def _goto(self, screen: QWidget):
        self._stack.setCurrentWidget(screen)

    def _start_scan(self):
        self._state.senders.clear()
        self._goto(self._scanning)
        self._scanning.start()

    def _show_senders(self):
        self._senders.load()
        self._goto(self._senders)

    def _start_processing(self):
        self._goto(self._processing)
        self._processing.start()

    def _show_results(self):
        self._results.load()
        self._goto(self._results)

    def _reset(self):
        self._state.senders.clear()
        self._state.unsub_ok.clear()
        self._state.unsub_web.clear()
        self._state.unsub_fail.clear()
        self._state.deleted_count = 0
        self._goto(self._config)


# ═══════════════════════════════════════════════════════════════════════════════
# Stylesheet
# ═══════════════════════════════════════════════════════════════════════════════

STYLESHEET = """
* {
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", Arial, sans-serif;
    font-size: 14px;
    color: #1e293b;
}
QMainWindow, QWidget {
    background-color: #f1f5f9;
}
QFrame#card {
    background-color: #ffffff;
    border-radius: 14px;
    border: 1px solid #e2e8f0;
}
QFrame#acctRow {
    background-color: #f8fafc;
    border: 1.5px solid #e2e8f0;
    border-radius: 8px;
}
QLabel#title {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
}
QLabel#sub {
    font-size: 13px;
    color: #64748b;
}
QLabel#error {
    font-size: 13px;
    color: #ef4444;
    background: #fef2f2;
    border-radius: 6px;
    padding: 8px;
}
QPushButton {
    background-color: #4361ee;
    color: #ffffff;
    border: none;
    border-radius: 8px;
    padding: 8px 18px;
    font-size: 14px;
    font-weight: 500;
    min-height: 36px;
}
QPushButton:hover    { background-color: #3451d1; }
QPushButton:pressed  { background-color: #2b3fb5; }
QPushButton:disabled { background-color: #cbd5e1; color: #94a3b8; }
QPushButton#secondary {
    background-color: transparent;
    color: #4361ee;
    border: 1.5px solid #4361ee;
}
QPushButton#secondary:hover   { background-color: #eef2ff; }
QPushButton#secondary:pressed { background-color: #e0e7ff; }
QPushButton#secondary:disabled{ border-color: #cbd5e1; color: #94a3b8; }
QPushButton#primary_strong {
    background-color: #22c55e;
}
QPushButton#primary_strong:hover   { background-color: #16a34a; }
QPushButton#primary_strong:disabled{ background-color: #cbd5e1; color: #94a3b8; }
QLineEdit {
    border: 1.5px solid #e2e8f0;
    border-radius: 8px;
    padding: 8px 12px;
    background-color: #ffffff;
    min-height: 36px;
}
QLineEdit:focus { border-color: #4361ee; }
QToolButton {
    background-color: transparent;
    border: 1.5px solid #e2e8f0;
    border-radius: 6px;
    color: #64748b;
    font-size: 16px;
}
QToolButton:hover { background-color: #f1f5f9; }
QGroupBox {
    font-weight: 600;
    color: #475569;
    border: 1.5px solid #e2e8f0;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 4px;
    background: #ffffff;
}
QRadioButton { spacing: 8px; }
QRadioButton::indicator {
    width: 16px; height: 16px;
    border-radius: 8px;
    border: 2px solid #cbd5e1;
    background: #ffffff;
}
QRadioButton::indicator:checked {
    border-color: #4361ee;
    background-color: #4361ee;
    image: none;
}
QCheckBox::indicator {
    width: 16px; height: 16px;
    border-radius: 4px;
    border: 2px solid #cbd5e1;
    background: #ffffff;
}
QCheckBox::indicator:checked { border-color: #4361ee; background-color: #4361ee; }
QSlider::groove:horizontal {
    height: 4px; background: #e2e8f0; border-radius: 2px;
}
QSlider::handle:horizontal {
    background: #4361ee; width: 18px; height: 18px;
    margin: -7px 0; border-radius: 9px;
}
QSlider::sub-page:horizontal { background: #4361ee; border-radius: 2px; }
QProgressBar {
    border: none; border-radius: 4px;
    background-color: #e2e8f0; text-align: center;
}
QProgressBar::chunk { background-color: #4361ee; border-radius: 4px; }
QTableView {
    background-color: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: #eef2ff;
    selection-color: #1e293b;
    alternate-background-color: #f8fafc;
    outline: none;
}
QTableView::item { padding: 4px 10px; border-bottom: 1px solid #f1f5f9; }
QTableView::item:selected { background-color: #eef2ff; }
QHeaderView::section {
    background-color: #f8fafc;
    color: #64748b;
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid #e2e8f0;
    font-weight: 600;
    font-size: 12px;
}
QListWidget {
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 8px;
    outline: none;
}
QListWidget::item { padding: 4px 10px; border-bottom: 1px solid #f1f5f9; }
QListWidget::item:hover { background: #eef2ff; }
QScrollBar:vertical {
    background: #f1f5f9; width: 8px; border-radius: 4px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #cbd5e1; border-radius: 4px; min-height: 30px;
}
QScrollBar::handle:vertical:hover { background: #94a3b8; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(APP_VERSION)
    app.setStyle("Fusion")
    app.setStyleSheet(STYLESHEET)

    win = MainWindow()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
