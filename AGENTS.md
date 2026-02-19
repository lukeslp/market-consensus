# Repository Guidelines

## /init Checklist
1. Confirm repo root: `pwd` should be the cloned `foresight` directory.
2. Read `README.md`, `app/config.py`, and `run_tests.sh` before making changes.
3. Activate env and install deps:
   `python -m venv venv && source venv/bin/activate`
   `pip install -r requirements.txt`
   (llm_providers is bundled in the repo — no external PYTHONPATH needed)
4. Check workspace state with `git status --short` and do not revert unrelated user changes.

## Project Structure & Module Organization
- `app/` is the Flask app: `routes/` (HTTP + SSE), `services/` (stock + prediction logic), `worker.py` (background cycle runner), `config.py` (env-driven settings), `database.py` (Flask DB bridge).
- `db.py` is the core SQLite layer (`ForesightDB`) and owns schema/events/indexes.
- `static/` contains dashboard assets: `js/` (D3 modules) and `css/` (layout/style/animations).
- `tests/` contains pytest suites (`test_api.py`, `test_services.py`, `test_integration.py`, `test_db_extended.py`) and shared fixtures in `tests/conftest.py`.
- Runtime artifacts (`foresight.db`, `foresight.log`, `htmlcov/`, `.pytest_cache/`) are not source files.

## Build, Test, and Development Commands
- `python run.py` starts the app locally on `http://localhost:5062` by default.
- `./run_tests.sh all` runs all tests.
- `./run_tests.sh fast` runs all tests except `slow`.
- `./run_tests.sh unit|integration|api` runs marker-targeted suites.
- `./run_tests.sh coverage` generates terminal and `htmlcov/` reports.
- For DB-only tests, prefer `pytest -m database -v` (the `run_tests.sh db` path includes a legacy `test_db.py` call that may not exist).

## Coding Style & Naming Conventions
- Python: PEP 8, 4-space indentation, `snake_case` for functions/variables, `PascalCase` for classes, concise docstrings on public modules/functions.
- JavaScript in `static/js`: keep existing class-based organization and 2-space indentation.
- Tests: `test_*.py` files, `test_*` functions, `Test*` classes for grouped behavior.
- Keep API payload keys and DB field names aligned with current endpoint/database contracts.

## Testing Guidelines
- Framework: `pytest` with strict markers in `pytest.ini` (`unit`, `integration`, `api`, `database`, `slow`).
- Keep tests deterministic by mocking provider/network calls via fixtures in `tests/conftest.py`.
- During development run focused suites first, then `./run_tests.sh all` before PR/merge.

## Commit & Pull Request Guidelines
- Use scoped commit subjects: `<type>: <concise imperative summary>` (`feat`, `fix`, `perf`, `test`, `docs`, `chore`).
- Session checkpoints are acceptable when batching work: `session checkpoint: YYYY-MM-DD HH:MM`.
- PRs should include purpose, key changes, test evidence, and UI screenshots/GIFs when dashboard behavior changes.
- Call out migration/config impacts explicitly (DB schema, env vars, provider wiring, cycle timing).

## Security & Configuration Tips
- Never commit API keys; use environment variables (`XAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.).
- Review defaults in `app/config.py` when changing provider selection, cycle intervals, model overrides, or DB path behavior.
- Preserve WAL/concurrency assumptions in `db.py` and worker lock behavior in `app/__init__.py` for multi-process safety.
