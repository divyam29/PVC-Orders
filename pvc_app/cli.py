import logging
import random
from datetime import datetime, timedelta
import click
from flask.cli import with_appcontext
from .extensions import db
from .models import Design, Order, OrderLine
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


def generate_schedule_stress_data_impl(
    orders_count: int = 50,
    min_lines_per_order: int = 2,
    max_lines_per_order: int = 5,
) -> tuple[int, int]:
    """Generate grouped order/line data that exercises the scheduler heavily."""
    colors = COLORS
    sizes = SIZES
    coatings = ["Without Coating", "Single Coating", "Double Coating"]
    designs_by_coating = {
        "Without Coating": ["Design A", "Design B", "Design C"],
        "Single Coating": ["Design D", "Design E"],
        "Double Coating": ["Design F", "Design G"],
    }
    machines = ["fresh_garden", "recycled_garden", "braided_1", "braided_2"]
    braided_sizes = ["6mm", "8mm", "10mm", '1/2"', '3/4"', '1"', '1 1/4"', '1 1/2"']
    garden_sizes = sizes

    order_count = 0
    line_count = 0
    today = datetime.now().date()

    for idx in range(orders_count):
        machine_type = random.choice(machines)
        pipe_type = "braided" if machine_type.startswith("braided") else "garden"
        order = Order(
            client_name=f"StressClient_{idx + 1}",
            quantity_kgs=0,
            machine_type=machine_type,
            color=random.choice(colors),
            coating_type=None,
            design=None,
            resin_amount=0,
            cpw_amount=0,
            dpp_amount=0,
            size_inches=random.choice(braided_sizes if pipe_type == "braided" else garden_sizes),
            expected_delivery=today + timedelta(days=random.randint(1, 6)),
            completed=False,
        )
        db.session.add(order)
        db.session.flush()

        group_count = random.randint(min_lines_per_order, max_lines_per_order)
        order_total = 0.0
        for _ in range(group_count):
            if pipe_type == "braided":
                size_inches = random.choice(braided_sizes)
                coating_type = None
                design = None
            else:
                coating_type = random.choice(coatings)
                design = random.choice(designs_by_coating[coating_type])
                size_inches = random.choice(garden_sizes)

            quantity_pcs = random.randint(20, 250)
            weight_per_piece = round(random.uniform(1.5, 5.5), 2)
            quantity_kgs = round(quantity_pcs * weight_per_piece, 2)
            length = random.choice(["30", "36", "40", "45"])

            line = OrderLine(
                order_id=order.id,
                pipe_type=pipe_type,
                machine_type=machine_type if pipe_type == "garden" else random.choice(["braided_1", "braided_2"]),
                color=order.color,
                length=length,
                coating_type=coating_type,
                design=design,
                quantity_pcs=quantity_pcs,
                weight_per_piece_kg=weight_per_piece,
                resin_amount=0,
                cpw_amount=0,
                dpp_amount=0,
                size_inches=size_inches,
                quantity_kgs=quantity_kgs,
                expected_delivery=order.expected_delivery,
                completed=False,
            )
            db.session.add(line)
            order_total += quantity_kgs
            line_count += 1

        order.quantity_kgs = round(order_total, 2)
        if pipe_type == "garden":
            order.coating_type = coating_type
            order.design = design
        order_count += 1

    db.session.commit()
    logger.info("Generated %d stress orders and %d order lines", order_count, line_count)
    return order_count, line_count


def clear_all_data_impl() -> int:
    """Delete all app data while respecting FK dependencies."""
    deleted_lines = db.session.query(OrderLine).delete()
    deleted_orders = db.session.query(Order).delete()
    deleted_designs = db.session.query(Design).delete()
    db.session.commit()
    logger.info("Deleted %d order lines, %d orders, %d designs", deleted_lines, deleted_orders, deleted_designs)
    return deleted_lines + deleted_orders + deleted_designs


@click.command("generate_test_orders")
@with_appcontext
def generate_test_orders():
    """Generate random test orders with some duplicates and variations."""
    count = generate_test_orders_impl()
    click.echo(f"✅ {count} test orders generated successfully!")


@click.command("generate_schedule_stress_data")
@click.option("--orders", default=50, show_default=True, type=click.IntRange(min=1))
@click.option("--min-lines", default=2, show_default=True, type=click.IntRange(min=1))
@click.option("--max-lines", default=5, show_default=True, type=click.IntRange(min=1))
@with_appcontext
def generate_schedule_stress_data(orders: int, min_lines: int, max_lines: int):
    """Generate large grouped data for scheduler testing."""
    if min_lines > max_lines:
        raise click.BadParameter("--min-lines cannot be greater than --max-lines")
    order_count, line_count = generate_schedule_stress_data_impl(orders, min_lines, max_lines)
    click.echo(f"✅ Generated {order_count} orders and {line_count} order lines")


@click.command("clear_all_data")
@click.option("--yes", is_flag=True, help="Skip the confirmation prompt.")
@with_appcontext
def clear_all_data(yes: bool):
    """Delete all application data."""
    if not yes and not click.confirm("Delete all orders, order lines, and designs?"):
        click.echo("Aborted.")
        return
    deleted = clear_all_data_impl()
    click.echo(f"✅ Deleted {deleted} records")
