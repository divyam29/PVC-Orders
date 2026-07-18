import logging
from pvc_app.extensions import db
from pvc_app.models import Order
from pvc_app.cli import generate_test_orders_impl

logger = logging.getLogger("tests.cli")

def test_generate_test_orders_command(app, caplog):
    caplog.set_level(logging.INFO)
    with app.app_context():
        before = Order.query.count()
        # Call the pure implementation directly (no click/with_appcontext)
        count = generate_test_orders_impl()
        after = Order.query.count()
    logger.info("generate_test_orders created %d rows", after - before)
    assert after > before
    # Optional: confirm our CLI logger emitted a summary line
    assert any("Generated" in rec.getMessage() for rec in caplog.records)

