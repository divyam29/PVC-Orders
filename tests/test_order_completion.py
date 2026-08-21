from datetime import datetime

from pvc_app.extensions import db
from pvc_app.models import Order, OrderLine
from pvc_app.store import SqlAlchemyStore


def test_completing_order_completes_all_lines(app):
    with app.app_context():
        order = Order(
            client_name="Completion Client",
            quantity_kgs=20,
            machine_type="fresh_garden",
            color="Blue",
            resin_amount=0,
            cpw_amount=0,
            dpp_amount=0,
            size_inches="1",
            expected_delivery=datetime(2099, 1, 1).date(),
            completed=False,
        )
        db.session.add(order)
        db.session.flush()
        db.session.add_all(
            [
                OrderLine(
                    order_id=order.id,
                    pipe_type="garden",
                    machine_type="fresh_garden",
                    color="Blue",
                    size_inches="1",
                    quantity_kgs=10,
                    quantity_pcs=1,
                    weight_per_piece_kg=10,
                    expected_delivery=datetime(2099, 1, 1).date(),
                    completed=False,
                ),
                OrderLine(
                    order_id=order.id,
                    pipe_type="garden",
                    machine_type="fresh_garden",
                    color="Red",
                    size_inches="1",
                    quantity_kgs=10,
                    quantity_pcs=1,
                    weight_per_piece_kg=10,
                    expected_delivery=datetime(2099, 1, 1).date(),
                    completed=False,
                ),
            ]
        )
        db.session.commit()
        order_id = order.id
        line_ids = [line.id for line in order.lines]

    with app.app_context():
        store = SqlAlchemyStore()
        completed_count = store.complete_order_lines(order_id, [line_ids[0]])
        order = db.session.get(Order, order_id)
        assert completed_count == 1
        assert order.completed is False
        assert order.lines[0].completed is True
        assert order.lines[1].completed is False

        completed_count = store.complete_order_lines(order_id, [line_ids[1]])
        db.session.refresh(order)
        assert completed_count == 1
        assert order.completed is True
        assert all(line.completed for line in order.lines)