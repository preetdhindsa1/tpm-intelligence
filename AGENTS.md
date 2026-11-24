# Rules for every coding agent (Claude Code, Cursor) and the human owner

- Never push to `main`. One issue, one branch, one pull request.
- Branch prefix by lane: `claude/<issue>-<slug>`, `cursor/<issue>-<slug>`, `harpreet/<issue>-<slug>`.
- Pull request description: `Fixes #<issue>`, the Lane line, and an AI-assistance statement.
- Keep pull requests small: aim for under 400 changed lines; split bigger work.
- Pick only issues labeled for your lane (`claude-agent`, `cursor-agent`, or `harpreet`). Do not edit files another open pull request is changing unless the issue says so.
- Run `make test` before opening a pull request. Respond to review comments yourself, then push.
- Do not classify work by the GitHub contributor login. `dependabot[bot]` is Dependabot, not Cursor. The Cursor lane is the label `cursor-agent` or a `cursor/` branch.
