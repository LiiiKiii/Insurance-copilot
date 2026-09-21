# Git Commit Guidelines

To keep the project history clear and consistent, please follow the commit message format below.

## Format

```text
<type>: <short description>
```

Example:

```text
feat: add performance gap analysis
```

## Commit Types

| Type | Usage | Example |
|---|---|---|
| `feat` | Add a new feature | `feat: add target feasibility analysis` |
| `fix` | Fix a bug | `fix: handle missing performance data` |
| `docs` | Documentation changes | `docs: update API documentation` |
| `test` | Add or update tests | `test: add reasoning layer tests` |
| `refactor` | Restructure code without changing behaviour | `refactor: simplify rule evaluation` |
| `chore` | Project setup, configuration, or maintenance | `chore: update project dependencies` |

## Rules

- Use lowercase commit types.
- Keep the description short and clear.
- Describe what the commit changes.
- Keep one commit focused on one logical change.
- Avoid vague messages such as `update`, `changes`, or `fix stuff`.
- Do not end the commit message with a period.

## Recommended Examples

```text
chore: add repository skeleton
feat: add performance data models
feat: implement gap analysis rules
fix: handle invalid target period
test: add feasibility assessment tests
docs: update system architecture
```
