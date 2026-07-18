import logging
import random
from datetime import datetime, timedelta
import click
from flask.cli import with_appcontext
from .extensions import db
from .models import Order
from .constants import COLORS, SIZES

logger = logging.getLogger("pvc_app.cli")


def generate_test_orders_impl() -> int:
    """Core implementation to generate test orders (pure function for tests)."""
    colors = COLORS
    sizes = SIZES

    orders_data = []

    # Base orders
    for _ in range(5):
        base_order = {
            "client_name": f"Client_{random.randint(1, 20)}",
            "quantity_kgs": random.randint(5, 80) * 100,
            "machine_type": random.choice(["fresh_garden", "recycled_garden", "braided_1", "braided_2"]),
            "color": random.choice(colors),
            "coating_type": random.choice(["Without Coating", "Single Coating", "Double Coating", None]),
            "design": random.choice(["Design A", "Design B", "Design C", "Design D", None]),
            "resin_amount": round(random.randint(20, 50)),
            "cpw_amount": round(random.randint(10, 50)),
            "dpp_amount": round(random.randint(1, 10)),
            "size_inches": random.choice(sizes),
            "expected_delivery": datetime.now().date() + timedelta(days=random.randint(1, 10)),
            "completed": False,
        }
        orders_data.append(base_order)

    # Duplicates with variations
    base_orders = list(orders_data)
    for base in base_orders:
        n_dups = random.randint(1, 3)
        for j in range(n_dups):
            duplicate = base.copy()
            duplicate["client_name"] = f"{base['client_name']}_dup{j+1}"
            alt_sizes = [s for s in sizes if s != base["size_inches"]]
            if alt_sizes:
                duplicate["size_inches"] = random.choice(alt_sizes)
            shift = random.randint(0, 5)
            new_date = base["expected_delivery"] + timedelta(days=shift)
            today = datetime.now().date()
            if new_date < today:
                new_date = today
            duplicate["expected_delivery"] = new_date
            if random.random() < 0.25:
                duplicate["completed"] = not base["completed"]
            orders_data.append(duplicate)

    # Random unique orders
    for _ in range(10):
        orders_data.append(
            {
                "client_name": f"Client_{random.randint(21, 100)}",
                "quantity_kgs": random.randint(5, 80) * 100,
                "machine_type": random.choice(["fresh_garden", "recycled_garden", "braided_1", "braided_2"]),
                "color": random.choice(colors),
                "coating_type": random.choice(["Without Coating", "Single Coating", "Double Coating", None]),
                "design": random.choice(["Design A", "Design B", "Design C", "Design D", None]),
                "resin_amount": round(random.randint(20, 50)),
                "cpw_amount": round(random.randint(10, 50)),
                "dpp_amount": round(random.randint(1, 10)),
                "size_inches": random.choice(sizes),
                "expected_delivery": datetime.now().date() + timedelta(days=random.randint(1, 10)),
                "completed": bool(random.getrandbits(1)),
            }
        )

    for data in orders_data:
        db.session.add(Order(**data))
    db.session.commit()
    logger.info("Generated %d test orders", len(orders_data))
    return len(orders_data)


@click.command("generate_test_orders")
@with_appcontext
def generate_test_orders():
    """Generate random test orders with some duplicates and variations."""
    count = generate_test_orders_impl()
    click.echo(f"✅ {count} test orders generated successfully!")
