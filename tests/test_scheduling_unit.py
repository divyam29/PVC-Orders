from datetime import date, timedelta
from pvc_app.models import Order
from pvc_app.extensions import db
from pvc_app.scheduling import build_production_schedule, material_key


def make_order(**kwargs):
    return Order(**kwargs)


def test_schedule_respects_capacity_and_deadlines(app):
    today = date.today()
    o1 = make_order(client_name="A", quantity_kgs=20000, machine_type="fresh_garden", color="Red", coating_type="Without Coating", design="Design A", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=1), completed=False)
    o2 = make_order(client_name="B", quantity_kgs=30000, machine_type="fresh_garden", color="Red", coating_type="Without Coating", design="Design A", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=2), completed=False)
    db.session.add_all([o1, o2])
    db.session.commit()

    schedule, summary = build_production_schedule([o1, o2], daily_capacity=40000)

    assert len(schedule) >= 2
    assert schedule[0]["total_kgs"] <= 40000
    assert summary[o1.id]["last_day"] <= summary[o2.id]["last_day"]


def test_material_grouping_prefers_same_recipe(app):
    today = date.today()
    o1 = make_order(client_name="A", quantity_kgs=10000, machine_type="fresh_garden", color="Blue", coating_type="Single Coating", design="Design D", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=3), completed=False)
    o2 = make_order(client_name="B", quantity_kgs=10000, machine_type="fresh_garden", color="Blue", coating_type="Single Coating", design="Design D", resin_amount=30, cpw_amount=10, dpp_amount=5, size_inches="1", expected_delivery=today + timedelta(days=4), completed=False)
    o3 = make_order(client_name="C", quantity_kgs=10000, machine_type="fresh_garden", color="Green", coating_type="Double Coating", design="Design F", resin_amount=35, cpw_amount=12, dpp_amount=6, size_inches="1", expected_delivery=today + timedelta(days=5), completed=False)
    db.session.add_all([o1, o2, o3])
    db.session.commit()

    schedule, _ = build_production_schedule([o1, o2, o3], daily_capacity=40000)

    day0_batches = schedule[0]["batches"]
    assert len(day0_batches) >= 1
    # expect first batch material_key equals o1/o2 recipe
    mk = material_key(o1)
    assert any(batch["material_key"] == mk for batch in day0_batches)
