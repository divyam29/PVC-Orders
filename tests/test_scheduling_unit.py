from datetime import date, timedelta

from pvc_app.extensions import db
from pvc_app.models import Order, OrderLine
from pvc_app.scheduling import build_production_schedule, material_key


def create_order(client_name, completed=False):
    order = Order(
        client_name=client_name,
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
        completed=completed,
    )
    db.session.add(order)
    db.session.flush()
    return order


def add_line(order, **kwargs):
    line = OrderLine(order_id=order.id, completed=False, **kwargs)
    db.session.add(line)
    return line


def test_weight_is_computed_from_pcs_times_piece_weight(app):
    order = create_order("A")
    add_line(
        order,
        pipe_type="garden",
        machine_type="fresh_garden",
        color="Blue",
        length="15",
        coating_type="Single Coating",
        design="Design D",
        quantity_pcs=25,
        weight_per_piece_kg=2.4,
        size_inches="1",
        quantity_kgs=60.0,
        expected_delivery=date.today() + timedelta(days=5),
    )
    db.session.commit()

    schedule, summary = build_production_schedule([order])
    assert summary[next(iter(summary))]["scheduled_total"] == 60.0
    assert schedule[0]["total_kgs"] == 60.0


def test_garden_lines_group_by_setup_order(app):
    o1 = create_order("A")
    o2 = create_order("B")
    add_line(o1, pipe_type="garden", machine_type="fresh_garden", color="Blue", length="10", coating_type="Single Coating", design="Design D", quantity_pcs=10, weight_per_piece_kg=1.0, size_inches="1", quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=5))
    add_line(o2, pipe_type="garden", machine_type="fresh_garden", color="Blue", length="12", coating_type="Single Coating", design="Design D", quantity_pcs=10, weight_per_piece_kg=1.0, size_inches="1", quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=6))
    add_line(o2, pipe_type="garden", machine_type="fresh_garden", color="Green", length="12", coating_type="Double Coating", design="Design F", quantity_pcs=10, weight_per_piece_kg=1.0, size_inches="1", quantity_kgs=10.0, expected_delivery=date.today() + timedelta(days=6))
    db.session.commit()

    schedule, _ = build_production_schedule([o1, o2])
    day_batches = schedule[0]["batches"]
    assert any(batch["material_key"] == material_key(o1.lines[0]) for batch in day_batches)


def test_braided_machine_is_auto_assigned(app):
    o1 = create_order("A")
    o2 = create_order("B")
    l1 = add_line(o1, pipe_type="braided", machine_type="braided_1", color="Black", length="20", coating_type=None, design=None, quantity_pcs=50, weight_per_piece_kg=2.0, size_inches='1/2"', quantity_kgs=100.0, expected_delivery=date.today() + timedelta(days=5))
    l2 = add_line(o2, pipe_type="braided", machine_type="braided_2", color="Black", length="20", coating_type=None, design=None, quantity_pcs=50, weight_per_piece_kg=2.0, size_inches='3/4"', quantity_kgs=100.0, expected_delivery=date.today() + timedelta(days=5))
    db.session.commit()

    schedule, _ = build_production_schedule([o1, o2])
    machines = {batch["machine"] for day in schedule for batch in day["batches"]}
    assert machines <= {"braided_1", "braided_2"}
    assert any(batch["material_key"][0] in {"braided_1", "braided_2"} for day in schedule for batch in day["batches"])
