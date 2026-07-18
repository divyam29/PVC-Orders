from datetime import date, timedelta

from pvc_app.extensions import db
from pvc_app.models import Order, OrderLine
from pvc_app.scheduling import build_production_schedule


def make_order(name):
    order = Order(
        client_name=name,
        quantity_kgs=0,
        machine_type="fresh_garden",
        color="Red",
        coating_type="Without Coating",
        design="Design A",
        resin_amount=0,
        cpw_amount=0,
        dpp_amount=0,
        size_inches="1",
        expected_delivery=date.today() + timedelta(days=5),
        completed=False,
    )
    db.session.add(order)
    db.session.flush()
    return order


def add_line(order, **kwargs):
    line = OrderLine(order_id=order.id, completed=False, **kwargs)
    db.session.add(line)
    return line


def _allocations(schedule):
    for day in schedule:
        for batch in day["batches"]:
            for al in batch["orders"]:
                yield day, batch, al


def test_schedule_allocates_exact_total_weight(app):
    order = make_order("A")
    add_line(order, pipe_type="garden", machine_type="fresh_garden", color="Blue", length="10", coating_type="Single Coating", design="Design D", quantity_pcs=20, weight_per_piece_kg=2.5, size_inches="1", quantity_kgs=50.0, expected_delivery=date.today() + timedelta(days=5))
    add_line(order, pipe_type="garden", machine_type="fresh_garden", color="Blue", length="12", coating_type="Single Coating", design="Design D", quantity_pcs=30, weight_per_piece_kg=1.5, size_inches="1", quantity_kgs=45.0, expected_delivery=date.today() + timedelta(days=5))
    db.session.commit()

    schedule, summary = build_production_schedule([order])
    total = sum(al["kgs"] for _, _, al in _allocations(schedule))
    assert total == 95.0
    assert summary[order.lines[0].id]["scheduled_total"] == 50.0
    assert summary[order.lines[1].id]["scheduled_total"] == 45.0


def test_deadlines_are_respected_when_feasible(app):
    order = make_order("A")
    add_line(order, pipe_type="braided", machine_type="braided_1", color="Black", length="20", coating_type=None, design=None, quantity_pcs=10, weight_per_piece_kg=1.0, size_inches='1/2"', quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=5))
    add_line(order, pipe_type="braided", machine_type="braided_1", color="Black", length="20", coating_type=None, design=None, quantity_pcs=10, weight_per_piece_kg=1.0, size_inches='1/2"', quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=6))
    db.session.commit()

    _, summary = build_production_schedule([order])
    assert not summary[order.lines[0].id]["late"]
    assert not summary[order.lines[1].id]["late"]


def test_completed_order_lines_are_ignored(app):
    order = make_order("A")
    add_line(order, pipe_type="braided", machine_type="braided_2", color="Red", length="15", coating_type=None, design=None, quantity_pcs=5, weight_per_piece_kg=2.0, size_inches='3/4"', quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=5))
    completed_order = make_order("B")
    completed_order.completed = True
    add_line(completed_order, pipe_type="braided", machine_type="braided_2", color="Red", length="15", coating_type=None, design=None, quantity_pcs=5, weight_per_piece_kg=2.0, size_inches='3/4"', quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=5))
    db.session.commit()

    schedule, _ = build_production_schedule([order, completed_order])
    total = sum(al["kgs"] for _, _, al in _allocations(schedule))
    assert total == 10.0
