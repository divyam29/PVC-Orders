from collections import defaultdict
from datetime import date, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .models import Design, Order, OrderLine

MachineName = str
ScheduleKey = Tuple[str, ...]

GARDEN_MACHINES = ("fresh_garden", "recycled_garden")
BRAIDED_MACHINES = ("braided_1", "braided_2")
ALL_MACHINES = GARDEN_MACHINES + BRAIDED_MACHINES
DAY_SHIFT_HOURS = 11
NIGHT_SHIFT_HOURS = 11

BRAIDED_RATE_BY_SIZE = {
    "0.25": 45.0,
    "1.25": 95.0,
    "1/2": 45.0,
    '1/2"': 45.0,
    "6mm": 45.0,
    "8mm": 45.0,
    "10mm": 45.0,
    "3/4": 75.0,
    '3/4"': 75.0,
    "1": 85.0,
    '1"': 85.0,
    "1 1/4": 95.0,
    '1 1/4"': 95.0,
    "1 1/2": 100.0,
    '1 1/2"': 100.0,
}


def _item(obj, name, default=None):
    return getattr(obj, name, default)


def material_key(item) -> ScheduleKey:
    return (
        _item(item, "machine_type") or "",
        _item(item, "coating_type") or "",
        _item(item, "design") or "",
        _item(item, "color") or "",
        _item(item, "size_inches") or "",
    )


def machine_hourly_rate(item) -> float:
    machine = _item(item, "machine_type")
    coating = (_item(item, "coating_type") or "").strip().lower()
    if machine == "fresh_garden":
        return 85.0
    if machine == "recycled_garden":
        return 90.0 if coating == "without coating" else 100.0
    if machine in BRAIDED_MACHINES:
        return BRAIDED_RATE_BY_SIZE.get((_item(item, "size_inches") or "").strip(), 0.0)
    return 0.0


def _group_priority(a, b) -> Tuple[int, int, int, int, int]:
    same_coating = int((_item(a, "coating_type") or "") == (_item(b, "coating_type") or ""))
    same_design = int((_item(a, "design") or "") == (_item(b, "design") or ""))
    same_color = int((_item(a, "color") or "") == (_item(b, "color") or ""))
    same_size = int((_item(a, "size_inches") or "") == (_item(b, "size_inches") or ""))
    deadline_gap = abs((_item(a, "expected_delivery") - _item(b, "expected_delivery")).days)
    return (same_coating, same_design, same_color, same_size, -deadline_gap)


def _braided_priority(a, b) -> Tuple[int, int, int]:
    same_color = int((_item(a, "color") or "") == (_item(b, "color") or ""))
    same_size = int((_item(a, "size_inches") or "") == (_item(b, "size_inches") or ""))
    deadline_gap = abs((_item(a, "expected_delivery") - _item(b, "expected_delivery")).days)
    return (same_color, same_size, -deadline_gap)


def _pick_next_item(remaining: Dict[int, float], candidates: List, current_day: date, last_item: Optional[Any], hard_deadline_bias: bool):
    active = [o for o in candidates if remaining[o.id] > 1e-9]
    if not active:
        return None
    due_now = [o for o in active if _item(o, "expected_delivery") <= current_day]
    pool = due_now or active
    if last_item is None:
        return min(pool, key=lambda o: (_item(o, "expected_delivery"), o.id))

    if _item(last_item, "machine_type") in GARDEN_MACHINES:
        chosen = max(pool, key=lambda o: _group_priority(last_item, o))
        if hard_deadline_bias and due_now:
            return min(due_now, key=lambda o: (_item(o, "expected_delivery"), -_group_priority(last_item, o)[0], -_group_priority(last_item, o)[1], -_group_priority(last_item, o)[2], -_group_priority(last_item, o)[3], o.id))
        return chosen

    if _item(last_item, "machine_type") in BRAIDED_MACHINES:
        chosen = max(pool, key=lambda o: _braided_priority(last_item, o))
        if hard_deadline_bias and due_now:
            return min(due_now, key=lambda o: (_item(o, "expected_delivery"), -_braided_priority(last_item, o)[0], -_braided_priority(last_item, o)[1], o.id))
        return chosen

    return min(pool, key=lambda o: (_item(o, "expected_delivery"), o.id))


def line_items_for_scheduling(orders: List[Order]) -> List[OrderLine]:
    items: List[OrderLine] = []
    for order in orders:
        if _item(order, "completed"):
            continue
        for line in getattr(order, "lines", []):
            if not line.completed:
                items.append(line)
    return items


def build_production_schedule(orders: List[Order], *_, **__):
    if not orders:
        return [], {}

    pending = line_items_for_scheduling(orders)
    if not pending:
        return [], {}

    buckets: Dict[MachineName, List] = {m: [] for m in ALL_MACHINES}
    for item in pending:
        machine = (_item(item, "machine_type") or "").strip()
        if machine in buckets:
            buckets[machine].append(item)
    for machine in buckets:
        buckets[machine].sort(key=lambda o: (_item(o, "expected_delivery"), o.id))

    remaining = {o.id: float(o.quantity_kgs) for o in pending}
    summary: Dict[int, Dict[str, Any]] = {
        o.id: {
            "last_day": None,
            "late": False,
            "scheduled_total": 0.0,
            "machine": _item(o, "machine_type"),
            "order_id": _item(o, "order_id"),
        }
        for o in pending
    }

    schedule = []
    current_day = date.today()
    machine_state = {m: None for m in ALL_MACHINES}

    def all_done():
        return all(v <= 1e-9 for v in remaining.values())

    while not all_done():
        day_plan = {"day": current_day, "shifts": [], "batches": [], "total_kgs": 0.0}
        for shift_name, shift_hours, is_night in (("day", DAY_SHIFT_HOURS, False), ("night", NIGHT_SHIFT_HOURS, True)):
            shift_plan = {"shift": shift_name, "machines": [], "total_kgs": 0.0}
            used = False
            for machine in ALL_MACHINES:
                if all_done():
                    break
                active = [o for o in buckets[machine] if remaining[o.id] > 1e-9]
                if not active:
                    continue
                hours_left = float(shift_hours)
                machine_plan = {"machine": machine, "batches": []}
                while hours_left > 1e-9 and active:
                    next_item = _pick_next_item(remaining, active, current_day, machine_state[machine], hard_deadline_bias=not is_night)
                    if not next_item:
                        break
                    rate = machine_hourly_rate(next_item)
                    if rate <= 0:
                        break
                    capacity_kgs = rate * hours_left
                    if capacity_kgs <= 1e-9:
                        break
                    key = material_key(next_item)
                    if not machine_plan["batches"] or machine_plan["batches"][-1]["material_key"] != key:
                        machine_plan["batches"].append({"machine": machine, "material_key": key, "orders": []})
                    alloc = min(remaining[next_item.id], capacity_kgs)
                    if alloc <= 1e-9:
                        break
                    if alloc > remaining[next_item.id] - 1e-9:
                        alloc = remaining[next_item.id]
                    machine_plan["batches"][-1]["orders"].append({"item": next_item, "order": getattr(next_item, "order", None), "kgs": float(alloc)})
                    remaining[next_item.id] -= alloc
                    if remaining[next_item.id] < 1e-6:
                        remaining[next_item.id] = 0.0
                    hours_left -= alloc / rate
                    shift_plan["total_kgs"] += alloc
                    day_plan["total_kgs"] += alloc
                    machine_state[machine] = next_item
                    summary[next_item.id]["last_day"] = current_day
                    summary[next_item.id]["scheduled_total"] += alloc
                    used = True
                    active = [o for o in buckets[machine] if remaining[o.id] > 1e-9]
                if machine_plan["batches"]:
                    shift_plan["machines"].append(machine_plan)
                    day_plan["batches"].extend(machine_plan["batches"])
            if used:
                day_plan["shifts"].append(shift_plan)
        schedule.append(day_plan)
        current_day = current_day + timedelta(days=1)

    for item in pending:
        last = summary[item.id]["last_day"]
        if last and last > _item(item, "expected_delivery"):
            summary[item.id]["late"] = True

    return schedule, summary


def existing_designs_by_coating(designs: List[Design]):
    grouped = defaultdict(set)
    for design in designs:
        if design.coating_type and design.name:
            grouped[design.coating_type].add(design.name)
    return {k: sorted(v) for k, v in grouped.items()}
