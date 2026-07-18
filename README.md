## PVC Production Management App

A Flask-based production management application for a PVC pipe manufacturing plant. It tracks and optimizes order processing, visualizes pending vs. completed production, and generates a capacity-aware production schedule while grouping orders by raw-material recipe to reduce changeovers.

### Key features
- Orders: client, quantity (kg), color, resin/CPW/DPP, size (inches), expected delivery, completed flag
- Dashboard: totals of pending and completed kgs, total orders
- Orders page: rich filtering (size, date, completed, any field), sorting, responsive table, edit/delete; hover tooltip reveals raw-materials (Resin/CPW/DPP)
- Modern minimal UI theme with a dark, sleek palette and improved usability
- Production schedule: capacity-aware (default 40,000 kg/day), EDF-style scheduling with raw-material grouping
- CLI: generate realistic test data with duplicates that vary size and delivery dates
- Test suite: unit, smoke/system, load tests with detailed logging

---

## Project layout
- app.py — minimal entrypoint using the factory
- pvc_app/
  - __init__.py — create_app factory, blueprint/CLI registration
  - extensions.py — SQLAlchemy db instance
  - models.py — Order model
  - constants.py — COLORS, SIZES, DEFAULT_DAILY_CAPACITY
  - scheduling.py — material_key and build_production_schedule
  - views.py — Flask Blueprint with all routes
  - urls.py — blueprint registration
  - cli.py — generate_test_orders CLI + implementation
  - templates/ — all Jinja templates (moved inside package)
- tests/
  - conftest.py — fixtures, autologging plugin, schedule timing wrapper
  - test_scheduling_unit.py — unit tests for core algorithm
  - test_scheduling_correctness.py — enhanced correctness tests
  - test_routes_smoke.py — page smoke and basic CRUD flow
  - test_system_and_load.py — system/load tests
  - test_cli.py — CLI generation test (calls pure implementation)

---

## Requirements
- Python 3.10+
- Recommended: a virtualenv
- Dependencies (installed via pip):
  - flask, flask_sqlalchemy, click
  - pytest (for tests)

If you use a requirements/lock file, install that instead. Example quick setup:

- python3 -m venv venv
- source venv/bin/activate
- pip install flask flask_sqlalchemy click pytest

---

## Configuration
- Database: SQLite file pvc.db in the project root by default
- Daily capacity: 40,000 kg/day (override via query parameter on /production_schedule?capacity=35000)

create_app accepts overrides (used by tests), e.g.:
- TESTING=True
- SQLALCHEMY_DATABASE_URI="sqlite:///:memory:"

---

## Running the app
1) Activate your virtualenv
2) From project root, set FLASK_APP and run:
- export FLASK_APP=app
- flask run

Or run directly:
- python3 app.py

App will be available at http://127.0.0.1:5000

### Routes
- / — Dashboard
- /orders — View orders with filters
- /add — Add order (GET/POST)
- /edit/<id> — Edit order
- /delete/<id> — Delete order
- /production_schedule — View computed schedule (optional ?capacity=NNN)

---

## CLI commands
- Generate test orders:
  - flask generate_test_orders
  - Output example: "✅ 27 test orders generated successfully!"

Notes:
- Test data includes base orders, duplicates with varied sizes/dates/completion, and unique random orders
- Duplicates never get past dates; delivery shift is within 0..+5 days from base

---

## Scheduling algorithm (overview)
- Only considers pending (completed=False) orders
- Sorts by expected_delivery (Earliest Deadline First), then by id
- Capacity window per day; fills by choosing:
  - Urgent jobs (due today or overdue)
  - Otherwise, prefers continuing the same raw-material recipe to reduce changeovers, while respecting earliest deadlines
- Produces:
  - schedule: list of days {day, batches, total_kgs}
  - summary: per order {last_day, late flag, scheduled_total}

---

## Testing
The test suite uses pytest with verbose output and live logging.

### Run all tests
- pytest

### Useful options
- Verbose names and logs (already configured in pytest.ini):
  - -vv (verbose) and log_cli=true at INFO level
- Change log level per run:
  - pytest -o log_cli_level=DEBUG
- Run a subset by keyword:
  - pytest -k scheduling

### What tests cover
- Unit: capacity/order ordering and material grouping preference
- Correctness: per-day capacity, per-order allocation equality, feasible/infeasible lateness, grouping contiguity, ties, completed ignored
- Routes: page smoke tests and basic add flow
- System/Load: builds schedules for many orders and validates conservation
- CLI: verifies data generation via implementation function

### Notes about CLI tests
- To avoid Click isolation quirks in some environments, tests call the pure implementation (generate_test_orders_impl) within an app context and assert DB/log effects. The actual Click command (flask generate_test_orders) remains available for interactive use.

---

## Developer workflow
- Inspect routes:
  - flask routes
- Use shell with context:
  - flask shell
- Reset DB (ad-hoc):
  - Stop the app and delete pvc.db, or run a short script in flask shell:
    - from pvc_app.extensions import db; db.drop_all(); db.create_all()

### Troubleshooting
- TemplateNotFound after refactor:
  - Templates were moved into pvc_app/templates; ensure you’re on current code and restarted the server
- ModuleNotFoundError pvc_app during tests:
  - Run pytest from the project root (we also inject project root into sys.path in tests/conftest.py)
- Click runner I/O ValueError in tests:
  - Addressed by directly calling the CLI implementation in tests

---

## Production considerations
- For production, use a real database and migrations (Flask-Migrate/Alembic)
- Consider worker queues for heavy scheduling runs
- Add authentication/authorization as needed

---

## License
Internal/Proprietary (update as appropriate)

