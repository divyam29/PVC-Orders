from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from .extensions import db


class Design(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    coating_type = db.Column(db.String(50), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)

    __table_args__ = (
        db.UniqueConstraint("coating_type", "name", name="uq_design_coating_name"),
    )

    def __repr__(self) -> str:
        return f"<Design {self.coating_type}:{self.name}>"


class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    client_name = db.Column(db.String(100), nullable=False)
    quantity_kgs = db.Column(db.Float, nullable=False)
    machine_type = db.Column(db.String(40), nullable=False, default="fresh_garden", index=True)
    color = db.Column(db.String(50), nullable=False)
    coating_type = db.Column(db.String(50), nullable=True, index=True)
    design = db.Column(db.String(120), nullable=True, index=True)
    resin_amount = db.Column(db.Float, nullable=False)
    cpw_amount = db.Column(db.Float, nullable=False)
    dpp_amount = db.Column(db.Float, nullable=False)
    size_inches = db.Column(db.String(10), nullable=False)
    expected_delivery = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return f"<Order {self.id} - {self.client_name}>"


class OrderLine(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    pipe_type = db.Column(db.String(40), nullable=False, default="garden")
    machine_type = db.Column(db.String(40), nullable=False, index=True)
    color = db.Column(db.String(50), nullable=False)
    length = db.Column(db.String(50), nullable=True)
    coating_type = db.Column(db.String(50), nullable=True, index=True)
    design = db.Column(db.String(120), nullable=True, index=True)
    quantity_pcs = db.Column(db.Integer, nullable=False, default=0)
    weight_per_piece_kg = db.Column(db.Float, nullable=False, default=0)
    resin_amount = db.Column(db.Float, nullable=False, default=0)
    cpw_amount = db.Column(db.Float, nullable=False, default=0)
    dpp_amount = db.Column(db.Float, nullable=False, default=0)
    size_inches = db.Column(db.String(10), nullable=False)
    quantity_kgs = db.Column(db.Float, nullable=False)
    expected_delivery = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, index=True)

    order = db.relationship("Order", backref=db.backref("lines", cascade="all, delete-orphan"))

    def __repr__(self) -> str:
        return f"<OrderLine {self.id} order={self.order_id}>"
