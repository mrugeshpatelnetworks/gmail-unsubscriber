# Contributing to Gmail Unsubscriber

Thanks for taking the time to contribute! This project was born out of a real-world need — cleaning up an inbox flooded with years of promotional emails — and any improvement that makes it more reliable or easier to use is genuinely welcome.

## Before You Start

- Check the [open issues](../../issues) to see if your idea or bug is already tracked.
- For large changes (new features, architectural changes), open an issue first to discuss it before writing code.
- All contributions must work on **Windows, macOS, and Linux**.

## How to Set Up Locally

```bash
git clone https://github.com/mrugeshpatelnetworks/gmail-unsubscriber.git
cd gmail-unsubscriber

# Mac/Linux
bash setup.sh

# Windows
setup.bat
```

The setup scripts create a `.venv/` and install all dependencies automatically.

## Making Changes

1. Fork the repo and create a branch: `git checkout -b fix/your-fix-name`
2. Make your changes inside the virtual environment
3. Test manually with at least one real Gmail account using an App Password
4. Keep changes focused — one fix or feature per pull request

## Pull Request Guidelines

- Describe **what** changed and **why** in the PR description
- If it fixes a bug, reference the issue number (`Fixes #123`)
- Screenshots or screen recordings are very welcome for UI changes
- Keep the PR small and reviewable — giant PRs take forever to review

## Code Style

- Follow the existing style in `gmail_unsubscriber.py` (PySide6, type hints, docstrings on public functions)
- No new external dependencies unless absolutely necessary — stdlib and PySide6 only
- No SMTP / email sending — this app only reads and unsubscribes, never sends

## Reporting Bugs

Use the **Bug Report** issue template. Please include:
- Your OS and Python version
- Steps to reproduce
- What you expected vs what actually happened
- Any error output from the terminal

## Security Issues

Do **not** open a public issue for security vulnerabilities. See [SECURITY.md](SECURITY.md) for the responsible disclosure process.

## License

By contributing you agree that your contributions will be licensed under the [MIT License](LICENSE).
