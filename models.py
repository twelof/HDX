from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    role = db.Column(db.String(50))  # receptionist, waiter, chef, manager
    contact = db.Column(db.String(100))
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)  # hashed

class MenuItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)
    description = db.Column(db.String(200))
    section = db.Column(db.String(50))
    image_url = db.Column(db.String(200))

class Table(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    branch_id = db.Column(db.Integer)
    capacity = db.Column(db.Integer)
    status = db.Column(db.String(50))  # available, reserved, occupied

class Reservation(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'))
    date = db.Column(db.String(50))
    time = db.Column(db.String(50))
    status = db.Column(db.String(50))  # active, cancelled

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'))
    waiter_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    status = db.Column(db.String(50))  # pending, served
    total_amount = db.Column(db.Float)
    created_at = db.Column(db.DateTime)
    items = db.relationship('OrderItem', backref='order', lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    menu_item_id = db.Column(db.Integer, db.ForeignKey('menu_item.id'))
    quantity = db.Column(db.Integer)
    menu_item = db.relationship('MenuItem',backref='order_items', lazy=True)

from datetime import datetime

class Payment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    amount = db.Column(db.Float)
    method = db.Column(db.String(50))  # cash, card, mpesa
    status = db.Column(db.String(50))  # success, failed
    date_time = db.Column(db.DateTime, default=datetime.utcnow)  # NEW
