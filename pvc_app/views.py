from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for
from .extensions import db
from .models import Order, OrderLine, Design
from .constants import SIZES
from .scheduling import build_production_schedule, existing_designs_by_coating


bp = Blueprint("main", __name__, template_folder="templates")


def _auto_machine_for_line(pipe_type: str, preferred_machine: str | None, size_inches: str) -> str:
    if (pipe_type or "").lower() == "braided":
        # Auto-balance braided lines across the two braided machines.
        braided_count_1 = db.session.query(db.func.count(OrderLine.id)).filter_by(machine_type="braided_1").scalar() or 0
        braided_count_2 = db.session.query(db.func.count(OrderLine.id)).filter_by(machine_type="braided_2").scalar() or 0
        return "braided_1" if braided_count_1 <= braided_count_2 else "braided_2"
    return preferred_machine or "fresh_garden"


def _parse_lines(form):
    rows = []
    line_count = int(form.get("line_count", 0) or 0)
    for idx in range(line_count):
        pipe_type = (form.get(f"pipe_type_{idx}") or "").strip()
        if not pipe_type:
            continue
        size_inches = (form.get(f"size_inches_{idx}") or "").strip()
        quantity_kgs = float(form.get(f"quantity_kgs_{idx}") or 0)
        if quantity_kgs <= 0:
            continue
        machine_type = _auto_machine_for_line(pipe_type, form.get(f"machine_type_{idx}"), size_inches)
        coating_type = (form.get(f"coating_type_{idx}") or "").strip() or None
        design = (form.get(f"design_{idx}") or "").strip() or None
        color = (form.get(f"color_{idx}") or "").strip()
        resin_amount = float(form.get(f"resin_amount_{idx}") or 0)
        cpw_amount = float(form.get(f"cpw_amount_{idx}") or 0)
        dpp_amount = float(form.get(f"dpp_amount_{idx}") or 0)
        expected_delivery = datetime.strptime(form.get(f"expected_delivery_{idx}"), "%Y-%m-%d").date()
        rows.append({
            "pipe_type": pipe_type,
            "machine_type": machine_type,
            "color": color,
            "coating_type": coating_type,
            "design": design,
            "resin_amount": resin_amount,
            "cpw_amount": cpw_amount,
            "dpp_amount": dpp_amount,
            "size_inches": size_inches,
            "quantity_kgs": quantity_kgs,
            "expected_delivery": expected_delivery,
        })
    return rows


@bp.route("/")
def dashboard():
    total_pending = (
        db.session.query(db.func.sum(Order.quantity_kgs)).filter_by(completed=False).scalar() or 0
    )
    total_completed = (
        db.session.query(db.func.sum(Order.quantity_kgs)).filter_by(completed=True).scalar() or 0
    )
    total_orders = Order.query.count()
    return render_template(
        "dashboard.html",
        total_pending=total_pending,
        total_completed=total_completed,
        total_orders=total_orders,
    )


@bp.route("/orders", methods=["GET"])
def view_orders():
    size_filter = request.args.get("size")
    date_filter = request.args.get("date")
    completed_filter = request.args.get("completed")  # "true" | "false" | None/""
    field = request.args.get("field")  # generic field name
    value = request.args.get("value")  # generic filter value
    sort_by = request.args.get("sort_by")
    sort_dir = request.args.get("sort_dir", "asc")

    query = Order.query

    # Simple filters
    if size_filter:
        query = query.filter_by(size_inches=size_filter)
    if date_filter:
        try:
            date_obj = datetime.strptime(date_filter, "%Y-%m-%d").date()
            query = query.filter_by(expected_delivery=date_obj)
        except ValueError:
            pass
    if completed_filter in ("true", "false"):
        query = query.filter_by(completed=(completed_filter == "true"))

    # Generic field filter
    allowed_fields = {
        "id": Order.id,
        "client_name": Order.client_name,
        "quantity_kgs": Order.quantity_kgs,
        "machine_type": Order.machine_type,
        "color": Order.color,
        "coating_type": Order.coating_type,
        "design": Order.design,
        "resin_amount": Order.resin_amount,
        "cpw_amount": Order.cpw_amount,
        "dpp_amount": Order.dpp_amount,
        "size_inches": Order.size_inches,
        "expected_delivery": Order.expected_delivery,
        "completed": Order.completed,
    }

    if field in allowed_fields and value not in (None, ""):
        col = allowed_fields[field]
        # String-like fields use ilike; numeric/date/bool use equality parsing
        string_fields = {"client_name", "machine_type", "color", "coating_type", "design", "size_inches"}
        numeric_fields = {"quantity_kgs", "resin_amount", "cpw_amount", "dpp_amount", "id"}
        if field in string_fields:
            query = query.filter(col.ilike(f"%{value}%"))
        elif field == "expected_delivery":
            try:
                dt = datetime.strptime(value, "%Y-%m-%d").date()
                query = query.filter(col == dt)
            except ValueError:
                pass
        elif field == "completed":
            if value.lower() in ("true", "false"):
                query = query.filter(col == (value.lower() == "true"))
        elif field in numeric_fields:
            try:
                num = float(value)
                query = query.filter(col == num)
            except ValueError:
                pass

    # Sorting
    if sort_by in allowed_fields:
        sort_col = allowed_fields[sort_by]
        if sort_dir == "desc":
            query = query.order_by(sort_col.desc())
        else:
            query = query.order_by(sort_col.asc())
    else:
        # default sort by id
        query = query.order_by(Order.id.asc())

    orders = query.all()

    # Data for form selects
    sort_fields = [
        ("id", "ID"),
        ("client_name", "Client"),
        ("quantity_kgs", "Quantity (kgs)"),
        ("machine_type", "Machine"),
        ("color", "Color"),
        ("coating_type", "Coating Type"),
        ("design", "Design"),
        ("size_inches", "Size"),
        ("expected_delivery", "Delivery Date"),
        ("completed", "Completed"),
    ]
    any_fields = [
        ("client_name", "Client"),
        ("machine_type", "Machine"),
        ("color", "Color"),
        ("coating_type", "Coating Type"),
        ("design", "Design"),
        ("size_inches", "Size"),
        ("quantity_kgs", "Quantity (kgs)"),
        ("resin_amount", "Resin"),
        ("cpw_amount", "CPW"),
        ("dpp_amount", "DPP"),
        ("expected_delivery", "Delivery Date"),
        ("completed", "Completed"),
        ("id", "ID"),
    ]

    return render_template(
        "orders.html",
        orders=orders,
        sizes=SIZES,
        sort_fields=sort_fields,
        any_fields=any_fields,
    )


@bp.route("/add", methods=["GET", "POST"])
def add_order():
    if request.method == "POST":
        lines = _parse_lines(request.form)
        for line in lines:
            if line["coating_type"] and line["design"]:
                existing = Design.query.filter_by(coating_type=line["coating_type"], name=line["design"]).first()
                if not existing:
                    db.session.add(Design(coating_type=line["coating_type"], name=line["design"]))
        new_order = Order(
            client_name=request.form["client_name"],
            quantity_kgs=sum(line["quantity_kgs"] for line in lines),
            machine_type=lines[0]["machine_type"] if lines else "fresh_garden",
            color=lines[0]["color"] if lines else "",
            coating_type=lines[0]["coating_type"] if lines else None,
            design=lines[0]["design"] if lines else None,
            resin_amount=sum(line["resin_amount"] for line in lines),
            cpw_amount=sum(line["cpw_amount"] for line in lines),
            dpp_amount=sum(line["dpp_amount"] for line in lines),
            size_inches=lines[0]["size_inches"] if lines else SIZES[0],
            expected_delivery=min((line["expected_delivery"] for line in lines), default=datetime.now().date()),
            completed="completed" in request.form,
        )
        db.session.add(new_order)
        db.session.commit()
        for line in lines:
            db.session.add(OrderLine(order_id=new_order.id, completed=False, **line))
        db.session.commit()
        return redirect(url_for("main.view_orders"))
    return render_template(
        "add_order.html",
        coating_designs=existing_designs_by_coating(Design.query.all()),
    )


@bp.route("/edit/<int:order_id>", methods=["GET", "POST"])
def edit_order(order_id):
    order = Order.query.get_or_404(order_id)
    if request.method == "POST":
        lines = _parse_lines(request.form)
        for line in lines:
            if line["coating_type"] and line["design"]:
                existing = Design.query.filter_by(coating_type=line["coating_type"], name=line["design"]).first()
                if not existing:
                    db.session.add(Design(coating_type=line["coating_type"], name=line["design"]))
        order.client_name = request.form["client_name"]
        order.quantity_kgs = sum(line["quantity_kgs"] for line in lines)
        order.machine_type = lines[0]["machine_type"] if lines else "fresh_garden"
        order.color = lines[0]["color"] if lines else ""
        order.coating_type = lines[0]["coating_type"] if lines else None
        order.design = lines[0]["design"] if lines else None
        order.resin_amount = sum(line["resin_amount"] for line in lines)
        order.cpw_amount = sum(line["cpw_amount"] for line in lines)
        order.dpp_amount = sum(line["dpp_amount"] for line in lines)
        order.size_inches = lines[0]["size_inches"] if lines else SIZES[0]
        order.expected_delivery = min((line["expected_delivery"] for line in lines), default=datetime.now().date())
        order.completed = "completed" in request.form
        OrderLine.query.filter_by(order_id=order.id).delete()
        for line in lines:
            db.session.add(OrderLine(order_id=order.id, completed=False, **line))
        db.session.commit()
        return redirect(url_for("main.view_orders"))
    return render_template(
        "edit_order.html",
        order=order,
        coating_designs=existing_designs_by_coating(Design.query.all()),
    )


@bp.route("/delete/<int:order_id>")
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    return redirect(url_for("main.view_orders"))


@bp.route("/production_schedule")
def production_schedule():
    orders = Order.query.filter_by(completed=False).all()
    schedule, summary = build_production_schedule(orders)

    def mk_label(mk):
        machine, coating, design, color, size = mk
        return f"{machine} | {coating or '-'} | {design or '-'} | {color} | {size}"

    return render_template(
        "production_schedule.html",
        schedule=schedule,
        summary=summary,
        mk_label=mk_label,
    )
