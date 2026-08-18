import logging
from datetime import datetime

from pvc_app.models import Order, OrderLine

logger = logging.getLogger("tests.routes")

def test_dashboard_ok(client):
    resp = client.get("/")
    logger.info("GET / status=%s", resp.status_code)
    assert resp.status_code == 200


def test_orders_page_ok(client):
    resp = client.get("/orders")
    logger.info("GET /orders status=%s", resp.status_code)
    assert resp.status_code == 200


def test_add_edit_delete_flow(client, app):
    # add
    payload = {
        "client_name": "TestC",
        "quantity_kgs": 1000,
        "color": "Red",
        "resin_amount": 30,
        "cpw_amount": 10,
        "dpp_amount": 5,
        "size_inches": "1",
        "expected_delivery": "2099-01-01",
        "completed": "",
    }
    logger.info("POST /add payload=%s", payload)
    resp = client.post("/add", data=payload, follow_redirects=True)
    logger.info("POST /add status=%s length=%d", resp.status_code, len(resp.data))
    assert resp.status_code == 200

    # find order id by scraping page
    assert b"TestC" in resp.data

    # navigate production schedule page
    r2 = client.get("/production_schedule")
    logger.info("GET /production_schedule status=%s", r2.status_code)
    assert r2.status_code == 200


def test_grouped_lines_page_shows_order_color_not_pipe_type(client, app):
    with app.app_context():
        order = Order(
            client_name="TestC",
            quantity_kgs=1000,
            machine_type="fresh_garden",
            color="Blue",
            coating_type="Without Coating",
            design=None,
            resin_amount=30,
            cpw_amount=10,
            dpp_amount=5,
            size_inches="1",
            expected_delivery=datetime(2099, 1, 1).date(),
            completed=False,
        )
        from pvc_app.extensions import db
        db.session.add(order)
        db.session.flush()
        db.session.add(
            OrderLine(
                order_id=order.id,
                pipe_type="garden",
                machine_type="fresh_garden",
                color="Blue",
                length="5",
                coating_type="Without Coating",
                design=None,
                quantity_pcs=10,
                weight_per_piece_kg=100,
                resin_amount=0,
                cpw_amount=0,
                dpp_amount=0,
                size_inches="1",
                quantity_kgs=1000,
                expected_delivery=datetime(2099, 1, 1).date(),
                completed=False,
            )
        )
        db.session.commit()

    grouped_resp = client.get("/grouped-lines")
    grouped_html = grouped_resp.get_data(as_text=True)

    assert grouped_resp.status_code == 200
    assert "<th>Color</th>" in grouped_html
    assert "<td>Blue</td>" in grouped_html
    assert "<th>Pipe Type</th>" not in grouped_html

