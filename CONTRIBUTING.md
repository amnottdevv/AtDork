# Contributing to AtDork

Thank you for considering a contribution.  
AtDork is an ethical OSINT tool – please make sure every change aligns with that principle.

## Getting Started

1. **Fork** the repository.
2. **Clone** your fork locally.
3. Create a new branch from `main`:
   ```
   git checkout -b feature/your-feature
   ```
4. Make your changes and test them thoroughly.

## Development Setup

```bash
pip install -r requirements.txt
pip install pytest   # for running tests
```

## Running Tests

All new code should be covered by tests.

```bash
pytest tests/ -v
```

## Pull Request Process

1. Ensure your branch is up to date with `main`.
2. Run the full test suite and confirm nothing is broken.
3. Write clear commit messages (one feature per commit).
4. Open a pull request with a descriptive title and a summary of changes.
5. Link any related issues (e.g., `Closes #12`).

A maintainer will review your PR. Small, focused pull requests are reviewed faster.

## Code Style

- Follow [PEP 8](https://peps.python.org/pep-0008/) for Python code.
- Use `black` for automatic formatting (line length 88 is fine).
- Add docstrings to new public functions.
- Keep modules focused – one responsibility per file.

## Ethical Standards

AtDork is designed for **legal, authorised security testing only**.  
When contributing:

- Do **not** add features that encourage illegal activity or unauthorised access.
- Do **not** include hardcoded credentials, malware, or spyware.
- Respect user privacy and data protection laws.

Violations of these standards will result in immediate removal of contributions and may be reported.

## Questions?

Open a [discussion](https://github.com/amnottdevv/atdork/discussions) or email the maintainer.
