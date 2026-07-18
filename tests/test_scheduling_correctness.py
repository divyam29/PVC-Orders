from datetime import date, timedelta
from pvc_app.extensions import db
from pvc_app.models import Order
from pvc_app.scheduling import build_production_schedule, material_key


def add_order(**kwargs):
    o = Order(**kwargs)
    db.session.add(o)
    return o


def _allocations(schedule):
    for day in schedule:
        for batch in day["batches"]:
            for al in batch["orders"]:
                yield day, batch, al


def test_per_day_capacity_and_per_order_totals(app):
    today = date.today()
    orders = [
        add_order(client_name="A", quantity_kgs=15000, machine_type="fresh_garden", color="Red", coating_type="Without Coating", design="Design A", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=False),
        add_order(client_name="B", quantity_kgs=25000, machine_type="recycled_garden", color="Blue", coating_type="Single Coating", design="Design D", resin_amount=32, cpw_amount=11, dpp_amount=6, size_inches="1", expected_delivery=today + timedelta(days=3), completed=False),
        add_order(client_name="C", quantity_kgs=5000, machine_type="fresh_garden", color="Red", coating_type="Without Coating", design="Design A", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=1), completed=False),
    ]
    db.session.commit()

    schedule, summary = build_production_schedule(orders, daily_capacity=30000)

    # Per-day capacity
    for day in schedule:
        assert day["total_kgs"] <= 30000

    # Per-order allocation sum equals requested
    per_order_sum = {}
    for _, _, al in _allocations(schedule):
        oid = al["order"].id
        per_order_sum[oid] = per_order_sum.get(oid, 0) + al["kgs"]
    for o in orders:
        assert abs(per_order_sum.get(o.id, 0) - o.quantity_kgs) < 1e-6


def test_feasible_deadlines_no_lateness(app):
    today = date.today()
    orders = [
        add_order(client_name="A", quantity_kgs=500, machine_type="fresh_garden", color="Red", coating_type="Without Coating", design="Design A", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=1), completed=False),
        add_order(client_name="B", quantity_kgs=500, machine_type="fresh_garden", color="Red", coating_type="Without Coating", design="Design A", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=False),
    ]
    db.session.commit()

    schedule, summary = build_production_schedule(orders, daily_capacity=40000)
    for o in orders:
        assert not summary[o.id]["late"], f"Order {o.id} should not be late"


def test_infeasible_deadlines_marked_late(app):
    today = date.today()
    # Two orders both due today, total qty exceeds capacity
    orders = [
        add_order(client_name="A", quantity_kgs=30000, machine_type="braided_1", color="Red", coating_type=None, design=None, resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today, completed=False),
        add_order(client_name="B", quantity_kgs=20000, machine_type="braided_1", color="Red", coating_type=None, design=None, resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today, completed=False),
    ]
    db.session.commit()

    schedule, summary = build_production_schedule(orders, daily_capacity=40000)
    # One of them should end after the due date
    late_flags = [summary[o.id]["late"] for o in orders]
    assert any(late_flags)


def test_grouping_contiguity_prefers_same_material(app):
    today = date.today()
    # Three orders: two share recipe, one different; ample capacity
    o1 = add_order(client_name="A", quantity_kgs=200, machine_type="fresh_garden", color="Blue", coating_type="Single Coating", design="Design D", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=False)
    o2 = add_order(client_name="B", quantity_kgs=200, machine_type="fresh_garden", color="Blue", coating_type="Single Coating", design="Design D", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=3), completed=False)
    o3 = add_order(client_name="C", quantity_kgs=200, machine_type="fresh_garden", color="Green", coating_type="Double Coating", design="Design F", resin_amount=35, cpw_amount=12, dpp_amount=6, size_inches="1", expected_delivery=today + timedelta(days=4), completed=False)
    db.session.commit()

    schedule, _ = build_production_schedule([o1, o2, o3], daily_capacity=40000)
    day0_batches = schedule[0]["batches"]
    # Expect at least one contiguous batch for the shared material
    shared_mk = material_key(o1)
    assert any(batch["material_key"] == shared_mk and len(batch["orders"]) >= 2 for batch in day0_batches)


def test_tie_breaking_and_completed_ignored(app):
    today = date.today()
    # Completed order should be ignored; two others with same deadline tie
    completed = add_order(client_name="Z", quantity_kgs=300, machine_type="braided_2", color="Red", coating_type=None, design=None, resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=True)
    o1 = add_order(client_name="A", quantity_kgs=300, machine_type="braided_2", color="Red", coating_type=None, design=None, resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=False)
    o2 = add_order(client_name="B", quantity_kgs=300, machine_type="braided_2", color="Red", coating_type=None, design=None, resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=False)
    db.session.commit()

    schedule, summary = build_production_schedule([completed, o1, o2], daily_capacity=40000)

    # Completed should have no allocations
    totals = {}
    for _, _, al in _allocations(schedule):
        oid = al["order"].id
        totals[oid] = totals.get(oid, 0) + al["kgs"]
    assert completed.id not in totals

    # Both pending tied jobs should be fully scheduled and not late
    assert totals[o1.id] == o1.quantity_kgs
    assert totals[o2.id] == o2.quantity_kgs
    assert not summary[o1.id]["late"]
    assert not summary[o2.id]["late"]
