import logging
from datetime import date, timedelta
import random
from pvc_app.extensions import db
from pvc_app.models import Order
from pvc_app.scheduling import build_production_schedule

logger = logging.getLogger("tests.system")


def test_system_schedule_end_to_end(app, client, caplog):
    caplog.set_level(logging.INFO)
    today = date.today()
    # Seed a variety of orders
    for i in range(50):
        order = Order(
            client_name=f"Client_{i}",
            quantity_kgs=random.randint(5, 80) * 100,
            machine_type=random.choice(["fresh_garden", "recycled_garden", "braided_1", "braided_2"]),
            color=random.choice(["Red", "Blue", "Green"]),
            coating_type=random.choice(["Without Coating", "Single Coating", "Double Coating"]),
            design=random.choice(["Design A", "Design B", "Design C", "Design D"]),
            resin_amount=round(random.uniform(20, 50), 2),
            cpw_amount=round(random.uniform(10, 50), 2),
            dpp_amount=round(random.uniform(1, 10), 2),
            size_inches=random.choice(["0.25", "0.5", "0.75", "1", "1.25"]),
            expected_delivery=today + timedelta(days=random.randint(1, 14)),
            completed=False,
        )
        logger.info("Seeding order %s qty=%s due=%s", order.client_name, order.quantity_kgs, order.expected_delivery)
        db.session.add(order)
    db.session.commit()

    # Hit pages
    r_dash = client.get("/")
    logger.info("Dashboard status=%s", r_dash.status_code)
    assert r_dash.status_code == 200

    r_orders = client.get("/orders")
    logger.info("Orders status=%s count=%d", r_orders.status_code, Order.query.count())
    assert r_orders.status_code == 200

    r_sched = client.get("/production_schedule")
    logger.info("Schedule status=%s", r_sched.status_code)
    assert r_sched.status_code == 200

    # Build schedule directly
    orders = Order.query.filter_by(completed=False).all()
    schedule, summary = build_production_schedule(orders, daily_capacity=40000)
    logger.info("Built schedule days=%d total_kgs=%.2f", len(schedule), sum(day["total_kgs"] for day in schedule))
    assert sum(day["total_kgs"] for day in schedule) >= 0


def test_load_schedule_large_dataset(app, caplog):
    caplog.set_level(logging.INFO)
    today = date.today()
    total_orders = 400
    for i in range(total_orders):
        db.session.add(
            Order(
                client_name=f"Load_{i}",
                quantity_kgs=random.randint(10, 100) * 100,
                machine_type=random.choice(["fresh_garden", "recycled_garden", "braided_1", "braided_2"]),
                color=random.choice(["Red", "Blue", "Green", "Yellow"]),
                coating_type=random.choice(["Without Coating", "Single Coating", "Double Coating"]),
                design=random.choice(["Design A", "Design B", "Design C", "Design D"]),
                resin_amount=round(random.uniform(20, 50), 2),
                cpw_amount=round(random.uniform(10, 50), 2),
                dpp_amount=round(random.uniform(1, 10), 2),
                size_inches=random.choice(["0.25", "0.5", "0.75", "1", "1.25"]),
                expected_delivery=today + timedelta(days=random.randint(1, 21)),
                completed=False,
            )
        )
    db.session.commit()
    logger.info("Load test seeded %d orders", total_orders)

    orders = Order.query.filter_by(completed=False).all()
    schedule, summary = build_production_schedule(orders, daily_capacity=40000)
    scheduled_total = sum(al["kgs"] for day in schedule for batch in day["batches"] for al in batch["orders"])
    total = sum(o.quantity_kgs for o in orders)
    logger.info("Load schedule result: days=%d batches=%d scheduled_total=%.2f total=%.2f",
                len(schedule), sum(len(d["batches"]) for d in schedule), scheduled_total, total)
    assert scheduled_total == total
