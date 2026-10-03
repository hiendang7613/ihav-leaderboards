# Security

Report a vulnerability privately through GitHub security advisories on this repository.

- The Python core reads and writes JSON inside `.ihav_space/ihav-leaderboards/` and makes no network call.
- The agent-driven steps fetch public pages. They stop on HTTP 401, 403, 429, a captcha or a bot wall and never try to bypass them.
- The plugin stores no credentials. Chatbot sign-ins belong to ihav-web-chat.
