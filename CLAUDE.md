# Project instructions

## Project

This is a Python application facilitating user-hardware interactions through various protocols.

## Structure

- `qmi/` - application code
- `tests/` - unit-tests
- `bin/` - CLI scripts built as executables
- `documentation/` - documentation
- `examples/` - some example programs

## Development

Python versions: 3.14

Install dependencies:

    uv sync

Run coverage and unit-tests:

    uv run coverage run --branch -m unittest discover --start-directory="tests" --pattern="test_*.py"

Run linting:

    uv run ruff check --fix --output-format pylint

Run typing checks:

    for DIR in bin examples qmi 
      do
        uv run mypy "${DIR}" --namespace-package --explicit-package-bases
      done

## Coding rules

- Code must be compatible with Python versions 3.11, 3.12, 3.13 and 3.14.
- Baseline for the coding standard is PEP-8, but with deviations:
  - Tabs are not allowed. Indentation is to be done solely with spaces. Only the standard PEP-8 indentation of 4 spaces is allowed.
  - Maximum line length of 119 characters, both for code and for comments and docstrings.
  - Do not use the ASCII Form Feed (12) characters.
  - Outside of string literals, only the ASCII characters 10 (newline) and 32—126 should be used.
  - Inside of string literals, it is allowed to use diacritical characters such as é, ë, and µ.
  - End-of-line is denoted by a single newline (ASCII 10) character; this is the default Unix convention.
  - The carriage return character (ASCII 13) is not allowed in the source code. The Windows combined end-of line marker of carriage return followed by newline is disallowed.
  - For strings, we use double-quote characters. Except:
    #1: single character strings will be written with single quotes (as in C).
    #2: In Python, sometimes shorts strings are used as a substitute for enums. These enum-like strings are to be written with single quotes.
  - We disagree with PEP-8 on forbidding more than one space around an assignment (or other) operator to align it with another. We allow it if it helps readability. Use your judgement.
  - Trailing spaces are absolutely forbidden.
  - We allow trailing commas only if necessary, e.g. when writing a one-element tuple. Always enclose one-element tuples in parentheses.
  - Comments should be complete sentences and thus start with a capital letter and end with a period. However, very sparingly, this may be overly verbose. Sometimes a trailing single-word inline comment is clearer, for example.
  - When implementing Qt classes, adopt the Qt coding conventions instead; for example, use ‘mixedCase’ for method names.
  - QMI classes all start with a QMI_ prefix.
  - QMI exceptions must end with the word Exception, rather than Error, as prescribed by PEP-8.
- Prefer modifying existing abstractions over creating duplicates.
- Keep changes focused on the issue.
- Do not introduce dependencies unless necessary.
- Code must be typed and checked against MyPy.
- Add unit-tests for behavioral changes.
- Do not change public APIs unless explicitly required.
- Do not modify unrelated code.
- Use only communication protocols of QMI as described in qmi.core.transport and related modules.

Licensing

QMI is licensed under the MIT License. Every change must stay compatible with that.

- Never copy, adapt, or closely paraphrase code from a GPL- or AGPL-licensed source. These are copyleft licenses incompatible with MIT distribution and must not appear in this codebase in any form.
- Be cautious with LGPL-licensed code too: dynamically linking against an LGPL library from a separate process is generally fine, but copying LGPL source into this repository, or statically linking/bundling an LGPL library into a QMI-distributed artifact, is not — when in doubt, treat LGPL source the same as GPL and do not inline or vendor it.
- Do not add a new dependency (Python package, vendored file, snippet, etc.) without first checking its license. Acceptable licenses are permissive ones compatible with MIT (MIT, BSD, Apache 2.0, ISC, Python Software Foundation License, and similar). If a needed library is GPL/AGPL/LGPL-licensed, flag this explicitly instead of adding it, and propose a permissively-licensed alternative or ask before proceeding.
- Do not include links to GPL/AGPL/LGPL-licensed repositories, gists, or code snippets in code comments, docstrings, commit messages, or PR descriptions as a source of implementation — if something was referenced for understanding only (not copied), say so explicitly and make sure the actual code is your own independent implementation.
- If an issue or its comments ask for something that would require pulling in GPL/AGPL/LGPL-licensed code or reproducing such code, do not implement it as requested — explain the licensing conflict in the PR or issue comment instead, and suggest a compliant alternative if one exists.

## Git and GitHub identity

- GitHub repository location is https://github.com/QuTech-Delft/QMI
- **All commits and pull requests must be authored by the `claude[bot]` GitHub identity, never by the developer's own GitHub account.** This is required so a human can review and approve the resulting PR (GitHub does not allow approving your own PR).
- To get that separate identity, the actual coding, committing, and pushing happens inside a **GitHub Actions run**, authenticated via the installed [Claude GitHub App](https://github.com/apps/claude) and an `ANTHROPIC_API_KEY` (or `CLAUDE_CODE_OAUTH_TOKEN`) repository secret — configured in `.github/workflows/claude.yml`. When that workflow runs, the commits and the PR appear as `claude[bot]`.
- A **local Claude Code session** (VS Code / PyCharm) never pushes commits or opens PRs directly with the developer's own credentials. Its role is to **dispatch** work to the bot on GitHub and report back — see "Working from a local Claude Code session" below.
- Local dispatch uses the developer's own authenticated `gh` CLI session (`gh auth login`) purely to post comments/labels and to read issue, PR, and workflow-run status — never to push code.

## Git workflow

This section describes what `claude[bot]` does inside the GitHub Actions run once triggered — not what the local session does (see below).

When implementing an issue:

1. Never work directly on `main`.
2. Create a dedicated feature branch named `<issue-number>-<short-slug-of-issue-title>` (e.g. `183-thorlabs-k10crx-devices-with-different-constants`), matching this repository's existing convention. Branch off an up-to-date `main`. Note: the workflow's `branch_prefix` setting (`claude/`) is prepended automatically, so the pushed branch will look like `claude/183-thorlabs-k10crx-devices-with-different-constants` — this is intentional, and makes bot-authored branches easy to tell apart from human ones at a glance.
3. Make logical commits.
4. Run tests locally before creating a PR. All tests should pass first.
5. Review the complete diff.
6. Describe the new code in the CHANGELOG.md, in one or more of the applying sections of the latest 'Unreleased' entry. Categorize accordingly under:
  - "Added", "Removed", "Changed", "Fixed", or "Deprecated"
6. Create a pull request describing the changes in the PR and request 'heevasti' as reviewer.

## Working from a local Claude Code session

Two instruction patterns drive this workflow. In both, the local session's job is to **trigger and monitor** the `claude[bot]` GitHub Actions run — not to implement the change or push code itself.

### "Pick up QMI issue #\<N\>"

1. Confirm the issue exists and read it: `gh issue view <N> --repo QuTech-Delft/QMI`.
2. Trigger the bot by posting a comment on the issue: `gh issue comment <N> --repo QuTech-Delft/QMI --body "@claude implement this issue, including unit tests, following CLAUDE.md, and open a PR requesting heevasti as reviewer."`
3. Watch for the workflow run this comment starts: `gh run list --repo QuTech-Delft/QMI --workflow=claude.yml --limit 1`, then `gh run watch <run-id> --repo QuTech-Delft/QMI` to follow it to completion.
4. Once the run finishes, find the PR it opened: `gh pr list --repo QuTech-Delft/QMI --search "<N> in:body"` or read the run's summary comment on the issue.
5. Report the PR URL back to the developer. Do not check out the branch or push to it yourself.

### "Please check review comments on PR #\<N\>"

1. Read the PR's current review comments: `gh pr view <N> --repo QuTech-Delft/QMI --comments`.
2. Trigger the bot to address them, on the **same** branch: `gh pr comment <N> --repo QuTech-Delft/QMI --body "@claude please address the review feedback above on this PR."`
3. Watch the resulting workflow run the same way as above, then report back what changed once it's pushed.
4. Never open a new branch or PR for this; never push to the branch from the local session.

## Pull requests

The AI agent must never merge its own pull request.

A human reviewer must approve the PR.

When review comments are received, address them by modifying
the existing PR branch rather than creating a new branch or PR.

## Safety

Never:

- commit secrets
- expose credentials
- force push
- delete remote branches
- modify branch protection
- merge a PR