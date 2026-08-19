from datetime import datetime

from pvc_app.extensions import db
from pvc_app.models import Order, OrderLine


def test_brand_name_is_stored_on_order_line(app):
    with app.app_context():
        order = Order(
            client_name="Brand Client",
            quantity_kgs=10,
            machine_type="fresh_garden",
            color="Blue",
            resin_amount=0,
            cpw_amount=0,
            dpp_amount=0,
            size_inches="1",
            expected_delivery=datetime(2099, 1, 1).date(),
        )
        db.session.add(order)
        db.session.flush()
        line = OrderLine(
            order_id=order.id,
            pipe_type="garden",
            machine_type="fresh_garden",
            color="Blue",
            brand_name="Acme",
            size_inches="1",
            quantity_kgs=10,
            quantity_pcs=1,
            weight_per_piece_kg=10,
            expected_delivery=datetime(2099, 1, 1).date(),
        )
        db.session.add(line)
        db.session.commit()

        assert OrderLine.query.one().brand_name == "Acme"
