# Projects

This directory is reserved for future standalone data science or exploratory work.

## Recommended Layout

Use one folder per project:

```text
projects/
  <project-name>/
    README.md
    requirements.txt or pyproject.toml
    src/ or notebooks/
    outputs/ (optional, not committed if large)
```

## Minimum Standards Per Project

- Include a `README.md` with:
  - purpose
  - input data
  - exact run commands
  - expected outputs
- Keep scripts reproducible from a clean checkout.
- Do not depend on undocumented manual steps.
- Keep secrets out of committed files.

## Repo Boundary

Projects can read shared dataset outputs, but should not silently mutate production app state.
