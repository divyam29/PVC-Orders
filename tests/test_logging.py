import logging
from datetime import date, timedelta
from pvc_app.extensions import db
from pvc_app.models import Order

logger = logging.getLogger("tests")


def test_verbose_logging_for_dataset(app, caplog):
    caplog.set_level(logging.INFO)

    # Seed dataset
    today = date.today()
    orders = []
    for i in range(10):
        o = Order(
            client_name=f"Log_{i}",
            quantity_kgs=1000 + i * 100,
            machine_type="fresh_garden",
            color="Red" if i % 2 == 0 else "Blue",
            coating_type="Without Coating",
            design="Design A",
            resin_amount=30 + i % 3,
            cpw_amount=10 + i % 4,
            dpp_amount=5 + i % 2,
            size_inches="1",
            expected_delivery=today + timedelta(days=i % 5 + 1),
            completed=False,
        )
        orders.append(o)
    db.session.add_all(orders)
    db.session.commit()

    logger.info("Seeded %d orders", len(orders))
    for o in orders:
        logger.info(
            "Order id?=%s client=%s qty=%.2f color=%s resin=%.2f cpw=%.2f dpp=%.2f size=%s due=%s",
            getattr(o, 'id', None), o.client_name, o.quantity_kgs, o.color, o.resin_amount, o.cpw_amount, o.dpp_amount, o.size_inches, o.expected_delivery,
        )

    # Assert that logs captured our dataset overview
    assert any("Seeded 10 orders" in rec.getMessage() for rec in caplog.records)
