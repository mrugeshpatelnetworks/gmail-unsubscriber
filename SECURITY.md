# Security Policy

## Supported Versions

Only the latest version on the `main` branch receives security fixes.

| Version | Supported |
|---------|-----------|
| Latest (main) | ✅ |
| Older commits | ❌ |

## Credential Handling

Gmail Unsubscriber **never stores your credentials on disk or sends them anywhere**. Credentials are:

- Read from environment variables (`GMAIL_EMAIL`, `GMAIL_APP_PASSWORD`) or typed into the GUI
- Held in memory only for the duration of the session
- Used exclusively to open an IMAP connection to `imap.gmail.com:993`
- Discarded when the app closes

**Always use a Gmail App Password** (not your main Google account password). App Passwords can be revoked at any time from [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords) without changing your main password.

## Reporting a Vulnerability

If you discover a security vulnerability, **please do not open a public GitHub issue**.

Instead, report it privately:

1. Go to the **Security** tab of this repository
2. Click **"Report a vulnerability"** (GitHub Private Security Advisories)
3. Describe the issue, steps to reproduce, and potential impact

You can expect an acknowledgment within **72 hours** and a fix or mitigation plan within **14 days** for confirmed issues.

We appreciate responsible disclosure and will credit researchers in the fix unless they prefer to remain anonymous.
