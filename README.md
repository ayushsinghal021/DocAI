# docai

Automate and sync documentation with your Python codebase on every git commit.

## Install

From the project root:

```bash
pip install -e .
```

Optional Gemini support:

```bash
pip install -e .[gemini]
# Set GOOGLE_API_KEY env var
```

## Usage

- Initial run:

```bash
docai run
```

- Install git pre-commit hook:

```bash
docai install-hook
```

- Manual commands:

```bash
docai scan           # produce repo_info.json
docai update-docs    # update docs/ based on repo_info.json
docai generate-docs  # generate initial docs (uses Gemini if available)
```

On commit, the hook will:
- Scan the repo and (if needed) update or generate docs.
- Abort the commit if any docs changed so you can review changes.

## Configuration

- Place your project under a git repository.
- Optional: Set `GOOGLE_API_KEY` for Gemini-backed initial docs.

## Notes

- The tool parses Python files with `ast`. It does not execute your code.
- It ignores common directories: `.git`, `venv`, `.venv`, `__pycache__`, `build`, `dist`.
