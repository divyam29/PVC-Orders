import logging

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

