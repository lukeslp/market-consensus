# Repository Guidelines

## Project Structure & Module Organization
- `app/` contains Flask application code: `routes/` for HTTP endpoints, `services/` for stock/prediction logic, `worker.py` for cycle execution, and `config.py` for environment-driven settings.
- `db.py` is the core SQLite layer (`ForesightDB`), integrated into Flask via `app/database.py`.
- `static/` contains frontend assets: `js/` (D3 dashboard modules) and `css/` (layout, style, animations).
- `tests/` holds pytest suites (`test_api.py`, `test_services.py`, `test_integration.py`, `test_db_extended.py`) plus shared fixtures in `tests/conftest.py`.
- Runtime artifacts (`foresight.db`, `foresight.log`, `htmlcov/`) should not be treated as source.

## Build, Test, and Development Commands
- `python -m venv venv && source venv/bin/activate` creates/activates the local environment.
- `pip install -r requirements.txt` installs Python dependencies.
- `export PYTHONPATH=/home/coolhand/shared:$PYTHONPATH` enables shared provider library imports.
- `python run.py` starts the app locally (default: `http://localhost:5062`).
- `./run_tests.sh all` runs the full test suite.
- `./run_tests.sh fast` runs all tests except `slow` markers.
- `./run_tests.sh coverage` generates terminal + `htmlcov/` coverage reports.

## Coding Style & Naming Conventions
- Python: PEP 8 style, 4-space indentation, descriptive `snake_case` for functions/variables, `PascalCase` for classes, and concise docstrings on public modules/functions.
- JavaScript (`static/js`): maintain existing class-based structure and 2-space indentation.
- Tests: file names `test_*.py`, test functions `test_*`, and grouped `Test*` classes for related behavior.
- Keep API payload keys and DB field names consistent with existing endpoint/database contracts.

## Testing Guidelines
- Framework: `pytest` with strict markers (`unit`, `integration`, `api`, `database`, `slow`) configured in `pytest.ini`.
- Prefer deterministic tests: mock provider/network calls using fixtures in `tests/conftest.py`.
- Run targeted suites while developing (example: `./run_tests.sh api`) and run `./run_tests.sh all` before opening a PR.

## Commit & Pull Request Guidelines
- Recent history uses short, scoped subjects (example: `perf: incremental SSE updates...`) plus frequent `session checkpoint: YYYY-MM-DD HH:MM` commits.
- Preferred format: `<type>: <concise imperative summary>` (`feat`, `fix`, `perf`, `test`, `docs`, `chore`).
- PRs should include: purpose, key changes, test evidence (command + result), and screenshots/GIFs for dashboard UI updates.
- Link related issues/tasks and note config or migration impacts (DB schema, env vars, provider setup).

## Security & Configuration Tips
- Never commit API keys; set them via environment variables (`XAI_API_KEY`, `ANTHROPIC_API_KEY`, etc.).
- Validate changes touching cycle timing, provider selection, or database paths through `app/config.py` defaults before deployment.
