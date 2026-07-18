import os
import sys
import time
import logging
from pathlib import Path
import pytest

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pvc_app import create_app
from pvc_app.extensions import db

logger = logging.getLogger("tests.autolog")


def _model_counts():
    counts = {}
    # Iterate registered model classes
    for m in db.Model._sa_registry.mappers:
        Model = m.class_
        try:
            counts[Model.__name__] = db.session.query(Model).count()
        except Exception:
            # if a table isn't created skip
            counts[Model.__name__] = None
    return counts


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "SQLALCHEMY_TRACK_MODIFICATIONS": False,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def runner(app):
    return app.test_cli_runner()


@pytest.fixture(autouse=True)
def autolog_test(app, request):
    # Log test start + params
    nodeid = request.node.nodeid
    params = {}
    callspec = getattr(request.node, "callspec", None)
    if callspec:
        params = dict(callspec.params)
    start = time.perf_counter()
    with app.app_context():
        before = _model_counts()
    logger.info("TEST START %s params=%s DB=%s", nodeid, params, before)
    yield
    # After
    duration = time.perf_counter() - start
    with app.app_context():
        after = _model_counts()
    logger.info("TEST END   %s duration=%.4fs DB=%s", nodeid, duration, after)


@pytest.fixture(autouse=True)
def schedule_timer(monkeypatch):
    # Wrap build_production_schedule to log timing and summary
    try:
        from pvc_app import scheduling as sched
    except Exception:
        yield
        return

    original = sched.build_production_schedule

    def timed(orders, daily_capacity=40000, *args, **kwargs):
        t0 = time.perf_counter()
        schedule, summary = original(orders, daily_capacity, *args, **kwargs)
        dt = time.perf_counter() - t0
        total_kgs = sum(d["total_kgs"] for d in schedule) if schedule else 0.0
        logger.info(
            "build_production_schedule: orders=%d capacity=%s days=%d total_kgs=%.2f duration=%.4fs",
            len(orders), daily_capacity, len(schedule), total_kgs, dt,
        )
        return schedule, summary

    monkeypatch.setattr(sched, "build_production_schedule", timed)
    yield
    # no explicit unpatch needed; monkeypatch fixture handles it

