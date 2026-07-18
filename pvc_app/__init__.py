from flask import Flask
from sqlalchemy import inspect, text
from .extensions import db
from .urls import register_urls
from .cli import clear_all_data, generate_schedule_stress_data, generate_test_orders


def create_app(test_config: dict | None = None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    # default config
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///pvc.db"
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    if test_config:
        app.config.update(test_config)

    # init extensions
    db.init_app(app)

    # blueprints / urls
    register_urls(app)

    # CLI
    app.cli.add_command(generate_test_orders)
    app.cli.add_command(generate_schedule_stress_data)
    app.cli.add_command(clear_all_data)

    # create tables on startup (skip when testing; tests control schema lifecycle)
    if not app.config.get("TESTING"):
        with app.app_context():
            db.create_all()
            _sync_sqlite_schema()

    return app


def _sync_sqlite_schema():
    """Add new columns/tables to the legacy SQLite DB without dropping data."""
    if not db.engine.url.get_backend_name().startswith("sqlite"):
        return

    inspector = inspect(db.engine)
    existing_tables = set(inspector.get_table_names())

    # Create new tables first if they are missing.
    db.create_all()

    if "order" not in existing_tables:
        return

    columns = {col["name"] for col in inspector.get_columns("order")}
    alterations = []

    if "machine_type" not in columns:
        alterations.append("ALTER TABLE \"order\" ADD COLUMN machine_type VARCHAR(40) DEFAULT 'fresh_garden' NOT NULL")
    if "coating_type" not in columns:
        alterations.append("ALTER TABLE \"order\" ADD COLUMN coating_type VARCHAR(50)")
    if "design" not in columns:
        alterations.append("ALTER TABLE \"order\" ADD COLUMN design VARCHAR(120)")

    if "order_line" in existing_tables:
        line_columns = {col["name"] for col in inspector.get_columns("order_line")}
        if "length" not in line_columns:
            alterations.append("ALTER TABLE order_line ADD COLUMN length VARCHAR(50)")
        if "quantity_pcs" not in line_columns:
            alterations.append("ALTER TABLE order_line ADD COLUMN quantity_pcs INTEGER DEFAULT 0 NOT NULL")
        if "weight_per_piece_kg" not in line_columns:
            alterations.append("ALTER TABLE order_line ADD COLUMN weight_per_piece_kg FLOAT DEFAULT 0 NOT NULL")

    with db.engine.begin() as conn:
        for stmt in alterations:
            conn.execute(text(stmt))
