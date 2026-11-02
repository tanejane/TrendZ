# Security and responsible disclosure

TrendZ is a **single-user local research prototype**. It is not hardened for public deployment or use with confidential commercial data. Do not expose the Flask development server to the internet.

- Keep source API tokens in local environment variables, never repository files.
- Do not publish source-response dumps, private SQLite review stores, secrets or restricted third-party datasets.
- Browser and internal tool boundaries should not be treated as an authentication system.
- Report suspected weaknesses privately to the repository owner using GitHub's private vulnerability reporting feature if enabled; otherwise request a private contact channel without posting exploit or token details publicly.

No production security guarantee or public bug-bounty program is offered.
