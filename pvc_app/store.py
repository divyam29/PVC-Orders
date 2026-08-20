from __future__ import annotations

import logging
from datetime import datetime, date
import os
from urllib.parse import quote_plus, urlsplit, urlunsplit
from types import SimpleNamespace
from typing import Any

from pymongo.errors import InvalidURI
from pymongo.errors import ServerSelectionTimeoutError
from pymongo import MongoClient

from .extensions import db
from .models import Design, Order, OrderLine

logger = logging.getLogger(__name__)


def _ns(value: Any):
    if isinstance(value, dict):
        return SimpleNamespace(**{k: _ns(v) for k, v in value.items()})
    if isinstance(value, list):
        return [_ns(v) for v in value]
    return value


def _serialize_date(value):
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return value


class BaseStore:
    backend = "sqlalchemy"

    def list_orders(self, include_completed: bool = True, order_desc: bool = True):
        raise NotImplementedError

    def get_order(self, order_id: int):
        raise NotImplementedError

    def create_order(self, order_payload: dict, line_payloads: list[dict]) -> int:
        raise NotImplementedError

    def update_order(self, order_id: int, order_payload: dict, line_payloads: list[dict]) -> None:
        raise NotImplementedError

    def delete_order(self, order_id: int) -> None:
        raise NotImplementedError

    def toggle_order_completion(self, order_id: int) -> bool:
        raise NotImplementedError

    def toggle_line_completion(self, line_id: int) -> bool:
        raise NotImplementedError

    def list_designs(self):
        raise NotImplementedError

    def list_clients(self):
        raise NotImplementedError

    def upsert_client(self, client_name: str):
        raise NotImplementedError

    def clear_all_data(self) -> int:
        raise NotImplementedError


class SqlAlchemyStore(BaseStore):
    backend = "sqlalchemy"

    def list_orders(self, include_completed: bool = True, order_desc: bool = True):
        query = Order.query
        if not include_completed:
            query = query.filter_by(completed=False)
        ordering = Order.created_at.desc() if order_desc else Order.created_at.asc()
        return query.order_by(ordering, Order.id.desc() if order_desc else Order.id.asc()).all()

    def get_order(self, order_id: int):
        return Order.query.get_or_404(order_id)

    def create_order(self, order_payload: dict, line_payloads: list[dict]) -> int:
        order = Order(**order_payload)
        db.session.add(order)
        db.session.flush()
        for line in line_payloads:
            db.session.add(OrderLine(order_id=order.id, **line))
        db.session.commit()
        return order.id

    def update_order(self, order_id: int, order_payload: dict, line_payloads: list[dict]) -> None:
        order = self.get_order(order_id)
        for k, v in order_payload.items():
            setattr(order, k, v)
        OrderLine.query.filter_by(order_id=order.id).delete()
        for line in line_payloads:
            db.session.add(OrderLine(order_id=order.id, **line))
        db.session.commit()

    def delete_order(self, order_id: int) -> None:
        order = self.get_order(order_id)
        db.session.delete(order)
        db.session.commit()

    def toggle_order_completion(self, order_id: int) -> bool:
        order = self.get_order(order_id)
        order.completed = not order.completed
        for line in order.lines:
            line.completed = order.completed
        db.session.commit()
        return order.completed

    def toggle_line_completion(self, line_id: int) -> bool:
        line = OrderLine.query.get_or_404(line_id)
        line.completed = not line.completed
        order = line.order
        order.completed = bool(order.lines) and all(l.completed for l in order.lines)
        db.session.commit()
        return line.completed

    def list_designs(self):
        return Design.query.all()

    def list_clients(self):
        return [
            name
            for (name,) in db.session.query(Order.client_name)
            .distinct()
            .order_by(Order.client_name.asc())
            .all()
            if name
        ]

    def upsert_client(self, client_name: str):
        return None

    def clear_all_data(self) -> int:
        deleted_lines = db.session.query(OrderLine).delete()
        deleted_orders = db.session.query(Order).delete()
        deleted_designs = db.session.query(Design).delete()
        db.session.commit()
        return deleted_lines + deleted_orders + deleted_designs


class MongoStore(BaseStore):
    backend = "mongo"

    def __init__(self, uri: str, db_name: str = "pvc_orders"):
        self.client = self._create_client(uri)
        try:
            self.db = self.client.get_default_database()
        except Exception:
            self.db = None
        if self.db is None:
            self.db = self.client[db_name]
        self.orders = self.db.orders
        self.order_lines = self.db.order_lines
        self.designs = self.db.designs
        self.clients = self.db.clients
        self._indexes_ready = False
        self._ensure_indexes()
        self._verify_connection()

    @staticmethod
    def _escape_credentials(uri: str) -> str:
        parts = urlsplit(uri)
        if "@" not in parts.netloc or ":" not in parts.netloc.split("@", 1)[0]:
            return uri
        userinfo, hostinfo = parts.netloc.rsplit("@", 1)
        username, password = userinfo.split(":", 1)
        return urlunsplit(
            (
                parts.scheme,
                f"{quote_plus(username)}:{quote_plus(password)}@{hostinfo}",
                parts.path,
                parts.query,
                parts.fragment,
            )
        )

    @classmethod
    def _create_client(cls, uri: str):
        try:
            return MongoClient(uri, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)
        except InvalidURI:
            escaped = cls._escape_credentials(uri)
            if escaped == uri:
                raise
            return MongoClient(escaped, serverSelectionTimeoutMS=3000, connectTimeoutMS=3000)

    def _ensure_indexes(self):
        if self._indexes_ready:
            return
        try:
            self.orders.create_index("created_at")
            self.order_lines.create_index("order_id")
            self.clients.create_index("name", unique=True)
            self._indexes_ready = True
        except Exception as exc:
            logger.warning("Mongo index setup failed: %s", exc)

    def _verify_connection(self):
        try:
            self.client.admin.command("ping")
        except ServerSelectionTimeoutError as exc:
            raise ConnectionError(f"MongoDB unavailable: {exc}") from exc
        except Exception as exc:
            raise ConnectionError(f"MongoDB unavailable: {exc}") from exc

    def _next_id(self, collection, field="id") -> int:
        doc = collection.find_one(sort=[(field, -1)], projection={field: 1}) or {}
        return int(doc.get(field, 0)) + 1

    def _normalize_line(self, line: dict, order_id: int) -> dict:
        doc = dict(line)
        doc["id"] = doc.get("id") or self._next_id(self.order_lines)
        doc["order_id"] = order_id
        doc["created_at"] = doc.get("created_at") or datetime.utcnow()
        if "expected_delivery" in doc:
            doc["expected_delivery"] = _serialize_date(doc["expected_delivery"])
        return doc

    def _order_doc(self, order_id: int):
        order = self.orders.find_one({"id": order_id})
        if not order:
            return None
        lines = list(self.order_lines.find({"order_id": order_id}).sort("id", 1))
        order["lines"] = lines
        return _ns(order)

    def list_orders(self, include_completed: bool = True, order_desc: bool = True):
        self._ensure_indexes()
        query = {}
        if not include_completed:
            query["completed"] = False
        cursor = self.orders.find(query).sort("created_at", -1 if order_desc else 1).sort("id", -1 if order_desc else 1)
        orders = []
        for order in cursor:
            order["lines"] = list(self.order_lines.find({"order_id": order["id"]}).sort("id", 1))
            orders.append(_ns(order))
        return orders

    def get_order(self, order_id: int):
        order = self._order_doc(order_id)
        if not order:
            raise KeyError(order_id)
        return order

    def create_order(self, order_payload: dict, line_payloads: list[dict]) -> int:
        self._ensure_indexes()
        order_id = self._next_id(self.orders)
        order = dict(order_payload)
        order["id"] = order_id
        order["created_at"] = order.get("created_at") or datetime.utcnow()
        if "expected_delivery" in order:
            order["expected_delivery"] = _serialize_date(order["expected_delivery"])
        self.orders.insert_one(order)
        for line in line_payloads:
            self.order_lines.insert_one(self._normalize_line(line, order_id))
        return order_id

    def update_order(self, order_id: int, order_payload: dict, line_payloads: list[dict]) -> None:
        self._ensure_indexes()
        order_doc = dict(order_payload)
        if "expected_delivery" in order_doc:
            order_doc["expected_delivery"] = _serialize_date(order_doc["expected_delivery"])
        self.orders.update_one({"id": order_id}, {"$set": order_doc})
        self.order_lines.delete_many({"order_id": order_id})
        for line in line_payloads:
            self.order_lines.insert_one(self._normalize_line(line, order_id))

    def delete_order(self, order_id: int) -> None:
        self._ensure_indexes()
        self.orders.delete_one({"id": order_id})
        self.order_lines.delete_many({"order_id": order_id})

    def toggle_order_completion(self, order_id: int) -> bool:
        self._ensure_indexes()
        order = self.orders.find_one({"id": order_id}) or {}
        new_state = not bool(order.get("completed"))
        self.orders.update_one({"id": order_id}, {"$set": {"completed": new_state}})
        self.order_lines.update_many({"order_id": order_id}, {"$set": {"completed": new_state}})
        return new_state

    def toggle_line_completion(self, line_id: int) -> bool:
        self._ensure_indexes()
        line = self.order_lines.find_one({"id": line_id}) or {}
        new_state = not bool(line.get("completed"))
        self.order_lines.update_one({"id": line_id}, {"$set": {"completed": new_state}})
        order_id = line.get("order_id")
        if order_id is not None:
            lines = list(self.order_lines.find({"order_id": order_id}))
            order_completed = bool(lines) and all(bool(l.get("completed")) for l in lines)
            self.orders.update_one({"id": order_id}, {"$set": {"completed": order_completed}})
        return new_state

    def list_designs(self):
        self._ensure_indexes()
        return [_ns(doc) for doc in self.designs.find().sort([("coating_type", 1), ("name", 1)])]

    def list_clients(self):
        self._ensure_indexes()
        return [doc["name"] for doc in self.clients.find({}, {"name": 1, "_id": 0}).sort("name", 1) if doc.get("name")]

    def upsert_client(self, client_name: str):
        self._ensure_indexes()
        client_name = (client_name or "").strip()
        if not client_name:
            return None
        self.clients.update_one(
            {"name": client_name},
            {"$setOnInsert": {"id": self._next_id(self.clients), "name": client_name}},
            upsert=True,
        )
        return client_name

    def clear_all_data(self) -> int:
        deleted = self.orders.delete_many({}).deleted_count
        deleted += self.order_lines.delete_many({}).deleted_count
        deleted += self.designs.delete_many({}).deleted_count
        deleted += self.clients.delete_many({}).deleted_count
        return deleted


def get_store(app=None):
    if app is None:
        from flask import current_app

        app = current_app
    cached = app.extensions.get("pvc_store")
    if cached is not None:
        return cached
    mongo_uri = app.config.get("MONGODB_URI") or os.environ.get("MONGODB_URI")
    if mongo_uri:
        try:
            store = MongoStore(mongo_uri, app.config.get("MONGODB_DB_NAME", "pvc_orders"))
        except Exception as exc:
            raise RuntimeError(f"Mongo store initialization failed: {exc}") from exc
    else:
        raise RuntimeError("MONGODB_URI is required. SQLite fallback has been removed.")
    app.extensions["pvc_store"] = store
    return store
