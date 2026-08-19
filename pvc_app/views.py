from datetime import datetime
from datetime import date, timedelta
import hmac
from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app, session
from .extensions import db
from .models import Order, OrderLine, Design
from .constants import SIZES
from .scheduling import build_production_schedule, existing_designs_by_coating
from .store import get_store


bp = Blueprint("main", __name__, template_folder="templates")


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        configured_username = current_app.config.get("AUTH_USERNAME") or ""
        configured_password = current_app.config.get("AUTH_PASSWORD") or ""
        if (
            configured_username
            and configured_password
            and hmac.compare_digest(username, configured_username)
            and hmac.compare_digest(password, configured_password)
        ):
            session.clear()
            session["authenticated"] = True
            next_url = request.args.get("next", "")
            if not next_url.startswith("/") or next_url.startswith("//"):
                next_url = url_for("main.dashboard")
            return redirect(next_url)
        flash("Invalid username or password.", "danger")
    return render_template("login.html", page_title="Sign in")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("main.login"))


def _auto_machine_for_line(pipe_type: str, preferred_machine: str | None, size_inches: str) -> str:
    if (pipe_type or "").lower() == "braided":
        # Auto-balance braided lines across the two braided machines.
        store = get_store(current_app)
        braided_count_1 = 0
        braided_count_2 = 0
        for order in store.list_orders(include_completed=True, order_desc=False):
            for line in getattr(order, "lines", []):
                if line.machine_type == "braided_1":
                    braided_count_1 += 1
                elif line.machine_type == "braided_2":
                    braided_count_2 += 1
        return "braided_1" if braided_count_1 <= braided_count_2 else "braided_2"
    return preferred_machine or "fresh_garden"


def _auto_deadline(pipe_type: str, size_inches: str, quantity_kgs: float) -> date:
    days = 5
    if (pipe_type or "").lower() == "braided" and float(quantity_kgs) > 500:
        days = 6
    return datetime.now().date() + timedelta(days=days)


def _parse_lines(form):
    rows = []
    line_count = int(form.get("line_count", 0) or 0)
    for idx in range(line_count):
        pipe_type = (form.get(f"pipe_type_{idx}") or "").strip()
        if not pipe_type:
            continue
        color = (form.get(f"color_{idx}") or "").strip()
        machine_type = (form.get(f"machine_type_{idx}") or "").strip() or "fresh_garden"
        coating_type = (form.get(f"coating_type_{idx}") or "").strip() or "Without Coating"
        design = (form.get(f"design_{idx}") or "").strip() or None
        sub_count = int(form.get(f"sub_count_{idx}", 0) or 0)
        for sub_idx in range(sub_count):
            size_inches = (form.get(f"size_inches_{idx}_{sub_idx}") or "").strip()
            quantity_pcs = int(float(form.get(f"quantity_pcs_{idx}_{sub_idx}") or 0))
            if quantity_pcs <= 0:
                continue
            length = (form.get(f"length_{idx}_{sub_idx}") or "").strip() or None
            weight_per_piece = float(form.get(f"bundle_weight_{idx}_{sub_idx}") or 0)
            effective_machine = machine_type
            if pipe_type.lower() == "braided":
                effective_machine = _auto_machine_for_line(pipe_type, None, size_inches)
                coating_type = None
            rows.append({
                "pipe_type": pipe_type,
                "machine_type": effective_machine,
                "color": color,
                "length": length,
                "coating_type": coating_type,
                "design": design,
                "resin_amount": 0,
                "cpw_amount": 0,
                "dpp_amount": 0,
                "size_inches": size_inches,
                "quantity_pcs": quantity_pcs,
                "weight_per_piece_kg": weight_per_piece,
                "quantity_kgs": quantity_pcs * weight_per_piece,
                "expected_delivery": _auto_deadline(pipe_type, size_inches, quantity_pcs * weight_per_piece),
            })
    return rows


def _order_lines_payload(order: Order):
    groups = {}
    for idx, line in enumerate(order.lines):
        group = groups.setdefault(
            (line.pipe_type, line.color, line.machine_type, line.coating_type or "", line.design or ""),
            {
                "pipe_type": line.pipe_type,
                "color": line.color,
                "machine_type": line.machine_type,
                "coating_type": line.coating_type or "Without Coating",
                "design": line.design or "",
                "subrows": [],
            },
        )
        group["subrows"].append({
            "idx": idx,
            "size_inches": line.size_inches,
            "quantity_pcs": line.quantity_pcs,
            "weight_per_piece_kg": line.weight_per_piece_kg,
            "quantity_kgs": line.quantity_kgs,
            "length": line.length or "",
        })
    return list(groups.values())


def _designs_by_coating_from_store(store):
    grouped = {}
    for design in store.list_designs():
        coating = getattr(design, "coating_type", None)
        name = getattr(design, "name", None)
        if coating and name:
            grouped.setdefault(coating, set()).add(name)
    return {k: sorted(v) for k, v in grouped.items()}


def _client_names_from_store(store):
    try:
        return sorted({name for name in store.list_clients() if name})
    except Exception:
        return []


def _sync_order_completion(order: Order) -> bool:
    lines = list(order.lines)
    if not lines:
        changed = not order.completed
        order.completed = True
        return changed
    new_state = all(line.completed for line in lines)
    changed = order.completed != new_state
    order.completed = new_state
    return changed


def _group_order_lines_for_view(orders):
    def _line_kgs(line):
        quantity_kgs = float(line.quantity_kgs or 0)
        if quantity_kgs > 0:
            return quantity_kgs
        return float((line.quantity_pcs or 0) * (line.weight_per_piece_kg or 0))

    grouped = {}
    for order in orders:
        if order.completed:
            continue
        for line in getattr(order, "lines", []):
            if line.completed:
                continue
            if (line.machine_type or "").startswith("braided"):
                braided_group = grouped.setdefault("braided", {})
                size_group = braided_group.setdefault(line.size_inches or "-", {"items": [], "total_kgs": 0.0, "total_pcs": 0})
                size_group["items"].append({"order": order, "line": line})
                size_group["total_kgs"] += _line_kgs(line)
                size_group["total_pcs"] += int(line.quantity_pcs or 0)
                continue

            machine = line.machine_type or ""
            coating = line.coating_type or "Without Coating"
            design = line.design or "-"
            machine_group = grouped.setdefault(machine, {})
            coating_group = machine_group.setdefault(coating, {"groups": {}, "total_kgs": 0.0, "total_pcs": 0})
            design_group = coating_group["groups"].setdefault(design, {"items": [], "total_kgs": 0.0, "total_pcs": 0})
            design_group["items"].append({"order": order, "line": line})
            line_kgs = _line_kgs(line)
            design_group["total_kgs"] += line_kgs
            design_group["total_pcs"] += int(line.quantity_pcs or 0)
            coating_group["total_kgs"] += line_kgs
            coating_group["total_pcs"] += int(line.quantity_pcs or 0)
    return grouped


@bp.route("/")
def dashboard():
    store = get_store(current_app)
    orders = store.list_orders(include_completed=True, order_desc=True)
    open_orders = [order for order in orders if not order.completed]
    total_orders = len(open_orders)
    total_completed_orders = 0
    total_pending_orders = total_orders
    return render_template(
        "dashboard.html",
        orders=open_orders,
        total_orders=total_orders,
        total_completed_orders=total_completed_orders,
        total_pending_orders=total_pending_orders,
        page_title="Dashboard",
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

    store = get_store(current_app)
    orders = store.list_orders(include_completed=True, order_desc=False)

    if size_filter:
        orders = [o for o in orders if o.size_inches == size_filter]
    if date_filter:
        try:
            date_obj = datetime.strptime(date_filter, "%Y-%m-%d").date()
            orders = [o for o in orders if getattr(o, "expected_delivery", None) == date_obj]
        except ValueError:
            pass
    if completed_filter in ("true", "false"):
        wanted = completed_filter == "true"
        orders = [o for o in orders if bool(o.completed) == wanted]
    if field and value not in (None, ""):
        string_fields = {"client_name", "machine_type", "color", "coating_type", "design", "size_inches"}
        if field in string_fields:
            orders = [o for o in orders if value.lower() in str(getattr(o, field, "")).lower()]
        elif field == "completed" and value.lower() in ("true", "false"):
            orders = [o for o in orders if bool(o.completed) == (value.lower() == "true")]
        elif field == "id":
            try:
                wanted = int(value)
                orders = [o for o in orders if int(o.id) == wanted]
            except ValueError:
                pass
    if sort_by:
        reverse = sort_dir == "desc"
        orders.sort(key=lambda o: getattr(o, sort_by, None), reverse=reverse)

    open_orders = [o for o in orders if not o.completed]
    completed_orders = [o for o in orders if o.completed]

    grouped_lines = _group_order_lines_for_view(open_orders)
    total_grouped_kgs = 0.0
    total_grouped_pcs = 0
    for order in open_orders:
        if order.completed:
            continue
        for line in getattr(order, "lines", []):
            if line.completed:
                continue
            line_kgs = float(line.quantity_kgs or 0)
            if line_kgs <= 0:
                line_kgs = float((line.quantity_pcs or 0) * (line.weight_per_piece_kg or 0))
            total_grouped_kgs += line_kgs
            total_grouped_pcs += int(line.quantity_pcs or 0)

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
        ("completed", "Completed"),
        ("id", "ID"),
    ]

    return render_template(
        "orders.html",
        orders=orders,
        open_orders=open_orders,
        completed_orders=completed_orders,
        sizes=SIZES,
        sort_fields=sort_fields,
        any_fields=any_fields,
        grouped_lines=grouped_lines,
        total_grouped_kgs=total_grouped_kgs,
        total_grouped_pcs=total_grouped_pcs,
    )


@bp.route("/add", methods=["GET", "POST"])
def add_order():
    if request.method == "POST":
        lines = _parse_lines(request.form)
        store = get_store(current_app)
        for line in lines:
            if line["coating_type"] and line["design"]:
                if store.backend == "sqlalchemy":
                    existing = Design.query.filter_by(coating_type=line["coating_type"], name=line["design"]).first()
                    if not existing:
                        db.session.add(Design(coating_type=line["coating_type"], name=line["design"]))
                else:
                    if not store.designs.find_one({"coating_type": line["coating_type"], "name": line["design"]}):
                        store.designs.insert_one({"id": store._next_id(store.designs), "coating_type": line["coating_type"], "name": line["design"]})
        client_name = request.form["client_name"].strip()
        if client_name:
            store.upsert_client(client_name)
        new_order_payload = dict(
            client_name=client_name,
            quantity_kgs=sum(line["quantity_kgs"] for line in lines),
            machine_type=lines[0]["machine_type"] if lines else "fresh_garden",
            color=lines[0]["color"] if lines else "",
            coating_type=lines[0]["coating_type"] if lines else None,
            design=lines[0]["design"] if lines else None,
            resin_amount=0,
            cpw_amount=0,
            dpp_amount=0,
            size_inches=lines[0]["size_inches"] if lines else SIZES[0],
            expected_delivery=min((line["expected_delivery"] for line in lines), default=datetime.now().date()),
            completed="completed" in request.form,
        )
        store.create_order(new_order_payload, [dict(line, completed=False) for line in lines])
        return redirect(url_for("main.view_orders"))
    return render_template(
        "add_order.html",
        coating_designs=_designs_by_coating_from_store(get_store(current_app)),
        client_names=_client_names_from_store(get_store(current_app)),
        sizes=SIZES,
    )


@bp.route("/edit/<int:order_id>", methods=["GET", "POST"])
def edit_order(order_id):
    store = get_store(current_app)
    order = store.get_order(order_id)
    if request.method == "POST":
        lines = _parse_lines(request.form)
        for line in lines:
            if line["coating_type"] and line["design"]:
                if store.backend == "sqlalchemy":
                    existing = Design.query.filter_by(coating_type=line["coating_type"], name=line["design"]).first()
                    if not existing:
                        db.session.add(Design(coating_type=line["coating_type"], name=line["design"]))
                else:
                    if not store.designs.find_one({"coating_type": line["coating_type"], "name": line["design"]}):
                        store.designs.insert_one({"id": store._next_id(store.designs), "coating_type": line["coating_type"], "name": line["design"]})
        client_name = request.form["client_name"].strip()
        if client_name:
            store.upsert_client(client_name)
        store.update_order(order.id, {
            "client_name": client_name,
            "quantity_kgs": sum(line["quantity_kgs"] for line in lines),
            "machine_type": lines[0]["machine_type"] if lines else "fresh_garden",
            "color": lines[0]["color"] if lines else "",
            "coating_type": lines[0]["coating_type"] if lines else None,
            "design": lines[0]["design"] if lines else None,
            "resin_amount": 0,
            "cpw_amount": 0,
            "dpp_amount": 0,
            "size_inches": lines[0]["size_inches"] if lines else SIZES[0],
            "expected_delivery": min((line["expected_delivery"] for line in lines), default=datetime.now().date()),
            "completed": "completed" in request.form,
        }, [dict(line, completed=False) for line in lines])
        return redirect(url_for("main.view_orders"))
    return render_template(
        "edit_order.html",
        order=order,
        coating_designs=_designs_by_coating_from_store(store),
        client_names=_client_names_from_store(store),
        sizes=SIZES,
        lines=_order_lines_payload(order),
    )


@bp.route("/delete/<int:order_id>")
def delete_order(order_id):
    store = get_store(current_app)
    store.delete_order(order_id)
    return redirect(url_for("main.view_orders"))


@bp.route("/toggle-line/<int:line_id>", methods=["POST"])
def toggle_line_completion(line_id):
    store = get_store(current_app)
    line_completed = store.toggle_line_completion(line_id)
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/toggle-order/<int:order_id>", methods=["POST"])
def toggle_order_completion(order_id):
    store = get_store(current_app)
    completed = store.toggle_order_completion(order_id)
    flash(
        f"Order #{order_id} marked as {'completed' if completed else 'inactive'}.",
        "success",
    )
    return redirect(request.referrer or url_for("main.dashboard"))


@bp.route("/production_schedule")
def production_schedule():
    store = get_store(current_app)
    orders = [order for order in store.list_orders(include_completed=True, order_desc=False) if not order.completed]
    include_sundays = request.args.get("include_sundays") == "1"
    schedule, summary = build_production_schedule(orders, include_sundays=include_sundays)

    def mk_label(mk):
        machine, coating, design, color, size = mk
        return f"{machine} | {coating or '-'} | {design or '-'} | {color} | {size}"

    return render_template(
        "production_schedule.html",
        total_pending=sum(float(order.quantity_kgs or 0) for order in store.list_orders(include_completed=True, order_desc=False) if not order.completed),
        total_completed=sum(float(order.quantity_kgs or 0) for order in store.list_orders(include_completed=True, order_desc=False) if order.completed),
        total_orders=len(store.list_orders(include_completed=True, order_desc=False)),
        schedule=schedule,
        summary=summary,
        mk_label=mk_label,
        page_title="Production Schedule",
        include_sundays=include_sundays,
    )


@bp.route("/grouped-lines")
def grouped_lines():
    store = get_store(current_app)
    orders = store.list_orders(include_completed=True, order_desc=False)
    grouped_lines = _group_order_lines_for_view(orders)
    total_pending_kgs = 0.0
    total_pending_pcs = 0
    for order in orders:
        if order.completed:
            continue
        for line in order.lines:
            if line.completed:
                continue
            line_kgs = float(line.quantity_kgs or 0)
            if line_kgs <= 0:
                line_kgs = float((line.quantity_pcs or 0) * (line.weight_per_piece_kg or 0))
            total_pending_kgs += line_kgs
            total_pending_pcs += int(line.quantity_pcs or 0)
    return render_template(
        "grouped_lines.html",
        grouped_lines=grouped_lines,
        total_orders=len(orders),
        total_lines=sum(len(getattr(order, "lines", [])) for order in orders),
        total_pending_kgs=total_pending_kgs,
        total_pending_pcs=total_pending_pcs,
        page_title="Grouped Lines",
    )
