import logging
import random
from datetime import date, timedelta

from pvc_app.extensions import db
from pvc_app.models import Order, OrderLine
from pvc_app.scheduling import build_production_schedule

logger = logging.getLogger("tests.system")


def _make_order(idx: int):
    order = Order(
        client_name=f"Client_{idx}",
        quantity_kgs=0,
        machine_type="fresh_garden",
        color=random.choice(["Red", "Blue", "Green"]),
        coating_type="Without Coating",
        design="Design A",
        resin_amount=0,
        cpw_amount=0,
        dpp_amount=0,
        size_inches="1",
        expected_delivery=date.today() + timedelta(days=random.randint(5, 6)),
        completed=False,
    )
    db.session.add(order)
    db.session.flush()
    return order


def _add_line(order, *, pipe_type, machine_type, color, size_inches, pcs, wpp, length, coating_type, design, due_days):
    db.session.add(
        OrderLine(
            order_id=order.id,
            pipe_type=pipe_type,
            machine_type=machine_type,
            color=color,
            length=length,
            coating_type=coating_type,
            design=design,
            quantity_pcs=pcs,
            weight_per_piece_kg=wpp,
            resin_amount=0,
            cpw_amount=0,
            dpp_amount=0,
            size_inches=size_inches,
            quantity_kgs=pcs * wpp,
            expected_delivery=date.today() + timedelta(days=due_days),
            completed=False,
        )
    )


def test_system_schedule_end_to_end(app, client, caplog):
    caplog.set_level(logging.INFO)
    for i in range(10):
        order = _make_order(i)
        _add_line(
            order,
            pipe_type="garden",
            machine_type="fresh_garden",
            color=random.choice(["Red", "Blue"]),
            size_inches="1",
            pcs=10 + i,
            wpp=2.0,
            length="15",
            coating_type="Without Coating",
            design="Design A",
            due_days=5,
        )
        _add_line(
            order,
            pipe_type="braided",
            machine_type="braided_1",
            color=random.choice(["Red", "Blue"]),
            size_inches='1/2"',
            pcs=5 + i,
            wpp=1.5,
            length="20",
            coating_type=None,
            design=None,
            due_days=6,
        )
    db.session.commit()

    assert client.get("/").status_code == 200
    assert client.get("/orders").status_code == 200
    assert client.get("/production_schedule").status_code == 200

    schedule, summary = build_production_schedule(Order.query.all())
    assert sum(day["total_kgs"] for day in schedule) > 0
    assert len(summary) == 20


def test_load_schedule_large_dataset(app):
    today = date.today()
    for i in range(100):
        order = Order(
            client_name=f"Load_{i}",
            quantity_kgs=0,
            machine_type="fresh_garden",
            color=random.choice(["Red", "Blue", "Green", "Yellow"]),
            coating_type="Without Coating",
            design="Design A",
            resin_amount=0,
            cpw_amount=0,
            dpp_amount=0,
            size_inches="1",
            expected_delivery=today + timedelta(days=random.randint(5, 6)),
            completed=False,
        )
        db.session.add(order)
        db.session.flush()
        _add_line(
            order,
            pipe_type="garden",
            machine_type=random.choice(["fresh_garden", "recycled_garden"]),
            color=random.choice(["Red", "Blue", "Green", "Yellow"]),
            size_inches=random.choice(["1", '1/2"', '3/4"', "1 1/4"]),
            pcs=random.randint(10, 100),
            wpp=random.uniform(0.5, 3.0),
            length="15",
            coating_type="Single Coating",
            design="Design D",
            due_days=random.randint(5, 6),
        )
    db.session.commit()

    schedule, summary = build_production_schedule(Order.query.all())
    scheduled = sum(al["kgs"] for day in schedule for batch in day["batches"] for al in batch["orders"])
    total = sum(line.quantity_kgs for line in OrderLine.query.all())
    assert abs(scheduled - total) < 1e-6
    assert len(summary) == 100
