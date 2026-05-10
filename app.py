
from flask import Flask, render_template, request, redirect, url_for
from models import db, User, MenuItem, Table, Reservation, Order, OrderItem, Payment
from werkzeug.utils import secure_filename
from dotenv import load_dotenv
# --- Flask setup and database configuration ---
# We’re wiring up Flask with SQLAlchemy and pointing it to our SQLite hotel DB.
app = Flask(__name__)
import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('SQLALCHEMY_DATABASE_URI', f'sqlite:///{os.path.join(BASE_DIR, "hxd_hotel.db")}')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY']=os.getenv('SECRET_KEY')
db.init_app(app)


import requests
import base64
from datetime import datetime

# M-Pesa credentials (replace with your sandbox/production keys)
# --- M-Pesa integration ---
# These credentials are for sandbox testing. Replace with production keys when going live.
# generate_token() grabs an access token from Safaricom.
# stk_push() triggers an STK push to the customer’s phone for payment.
MPESA_CONSUMER_KEY = os.getenv("MPESA_CONSUMER_KEY")
MPESA_CONSUMER_SECRET = os.getenv("MPESA_CONSUMER_SECRET")
MPESA_SHORTCODE =  os.getenv("MPESA_SHORTCODE")
MPESA_PASSKEY = os.getenv("MPESA_PASSKEY")
MPESA_BASE_URL = os.getenv("MPESA_BASE_URL")

def generate_token():
    url = f"{MPESA_BASE_URL}/oauth/v1/generate?grant_type=client_credentials"
    response = requests.get(url, auth=(MPESA_CONSUMER_KEY, MPESA_CONSUMER_SECRET))
    return response.json()['access_token']

def stk_push(phone_number, amount, order_id):
    token = generate_token()
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    password = base64.b64encode((MPESA_SHORTCODE + MPESA_PASSKEY + timestamp).encode()).decode()

    payload = {
        "BusinessShortCode": MPESA_SHORTCODE,
        "Password": password,
        "Timestamp": timestamp,
        "TransactionType": "CustomerPayBillOnline",
        "Amount": amount,
        "PartyA": phone_number,
        "PartyB": MPESA_SHORTCODE,
        "PhoneNumber": phone_number,
        "CallBackURL": "https://yourdomain.com/mpesa/callback",
        "AccountReference": f"Order{order_id}",
        "TransactionDesc": "Payment for Hotel X Design"
    }

    headers = {"Authorization": f"Bearer {token}"}
    url = f"{MPESA_BASE_URL}/mpesa/stkpush/v1/processrequest"
    response = requests.post(url, json=payload, headers=headers)
    return response.json()
from werkzeug.security import generate_password_hash, check_password_hash
from flask import session

# --- User signup with role restrictions ---
# Only whitelisted emails can register as Manager, Receptionist, or Waiter.
# This prevents random people from creating privileged accounts.
ALLOWED_MANAGER_EMAILS = ["boss@company.com","owner@company.com"]
ALLOWED_RECEPTIONIST_EMAILS = ["frontdesk@hotel.com"]
ALLOWED_WAITER_EMAILS = ["waiter@hotel.com"]

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        role = request.form['role']
        if role == "Manager" and email not in ALLOWED_MANAGER_EMAILS:
            return "unauthorized: only specific emails can register as Manager"
        if role == "Receptionist" and email not in ALLOWED_RECEPTIONIST_EMAILS:
            return "unauthorized: only specific emails can register as Receptionist"
        if role == "Waiter" and email not in ALLOWED_WAITER_EMAILS:
            return "unauthorized: only specific emails can register as Waiter"
        user = User(name=name, email=email, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template('signup.html')


# --- Login / Logout ---
# Standard login flow: check hashed password, set session role.
# Logout clears the session completely.
@app.route('/login', methods=['GET', 'POST'])

def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            session['role'] = user.role
            return redirect(url_for('home'))
        else:
            return render_template('login.html', error="Invalid credentials")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

from functools import wraps
from flask import session, redirect, url_for, flash


# --- Role-based access decorator ---
# Use @role_required([...]) to lock down routes.
# If user’s role isn’t in the allowed list, they get bounced back home.
def role_required(roles):
    def wrapper(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if 'role' not in session:
                flash("You must log in to access this page.", "error")
                return redirect(url_for('login'))
            if session['role'] not in roles:
                flash("Access denied: insufficient permissions.", "error")
                return redirect(url_for('home'))
            return f(*args, **kwargs)
        return decorated_function
    return wrapper



@app.route('/')
def home():
    return render_template('home.html')


import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = os.path.join(app.root_path, 'static/images/food')
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# --- Menu management ---
# Managers and Chefs can add new menu items.
# Guests and Waiters can only view the menu.

@app.route('/menu/new', methods=['POST'])
@role_required(['Manager', 'Chef'])
def menu_new():
    name = request.form.get('name')
    description = request.form.get('description')
    price = request.form.get('price')
    section = request.form.get('section')
    image = request.files.get('image')

    filename = None
    if image and image.filename != '':
        filename = secure_filename(image.filename)
        image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

    # Validation
    if not all([name, description, price, section]):
        flash("All fields are required.", "error")
        return redirect(url_for('menu_manage'))

    try:
        item = MenuItem(
            name=name,
            description=description,
            price=float(price),
            section=section,
            image_url=filename  # store only filename
        )
        db.session.add(item)
        db.session.commit()
        flash("Menu item added successfully!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Error adding item: {str(e)}", "error")

    return redirect(url_for('menu'))

@app.route('/menu/delete/<int:item_id>', methods=['POST'])
@role_required(['Manager', 'Chef'])
def menu_delete(item_id):
    item = MenuItem.query.get_or_404(item_id)
    db.session.delete(item)
    db.session.commit()
    flash("Menu item deleted.", "success")
    return redirect(url_for('menu'))

@app.route('/menu/edit/<int:item_id>', methods=['GET', 'POST'])
@role_required(['Manager', 'Chef'])
def menu_edit(item_id):
    item = MenuItem.query.get_or_404(item_id)
    if request.method == 'POST':
        item.name = request.form.get('name')
        item.description = request.form.get('description')
        item.price = request.form.get('price')
        item.section = request.form.get('section')
        db.session.commit()
        flash("Menu item updated.", "success")
        return redirect(url_for('menu_view'))
    return render_template('menu_edit.html', item=item)


@app.route('/menu', methods=['GET'])
#@role_required(['Guest', 'Waiter'])
def menu():
    items = MenuItem.query.all()
    return render_template('menu_guest.html', items=items)

@app.route('/menu/manage', methods=['GET', 'POST'])
@role_required(['Manager','Chef'])
def menu_manage():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        price = request.form['price']
        section = request.form['section']
        image = request.files.get('image')

        filename = None
        if image and image.filename != '':
            filename = secure_filename(image.filename)
            image.save(os.path.join(app.config['UPLOAD_FOLDER'], filename))

        item = MenuItem(
            name=name,
            description=description,
            price=float(price),
            section=section,
            image_url=filename
        )
        db.session.add(item)
        db.session.commit()
        return redirect(url_for('menu'))

    items = MenuItem.query.all()
    return render_template('menu.html', items=items)
# --- Reservations ---
# Receptionists handle reservations, but Guests and Waiters can also interact.
@app.route('/reservations', methods=['GET', 'POST'])
@role_required(['Receptionist', 'Guest','Waiter'])
def reservations():
    if request.method == 'POST':
        table_id = request.form['table_id']
        guest_name = request.form['guest_name']
        party_size = request.form['party_size']
        date = request.form['date']
        time = request.form['time']

        reservation = Reservation(
            user_id=1,  # demo user
            table_id=table_id,
            date=date,
            time=time,
            status="active"
        )
        db.session.add(reservation)
        db.session.commit()
        return redirect(url_for('reservations'))

    reservations = Reservation.query.all()
    tables = Table.query.all()
    return render_template('reservations.html', reservations=reservations, tables=tables)

@app.route('/reservations/cancel/<int:id>', methods=['POST'])
def cancel_reservation(id):
    reservation = Reservation.query.get_or_404(id)
    reservation.status = "cancelled"
    db.session.commit()
    return redirect(url_for('reservations'))


@app.route('/orders', methods=['GET', 'POST'])
@role_required(['Waiter','Guest','Manager'])
def orders():
    if request.method == 'POST':
        table_id = request.form['table_id']
        menu_item_id = request.form['menu_item_id']
        quantity = request.form['quantity']

        order = Order(table_id=table_id, waiter_id=1, status="pending", total_amount=0)
        db.session.add(order)
        db.session.commit()

        menu_item = MenuItem.query.get(menu_item_id)

        order_item = OrderItem(order_id=order.id, menu_item_id=menu_item_id, quantity=quantity)
        db.session.add(order_item)
        
        order.total_amount += menu_item.price * int(quantity)
        db.session.commit()

        flash("Order placed successfully!", "success")
        return redirect(url_for('orders'))

    orders = Order.query.all()
    tables = Table.query.all()
    items = MenuItem.query.all()
    return render_template('orders.html', orders=orders, tables=tables, items=items)

def recalc_total(order):
    total = sum(item.menu_item.price * item.quantity for item in order.items)
    order.total_amount = total
    db.session.commit()

# --- Reports ---
# Managers and Receptionists can view sales and order status reports.
@app.route('/reports')
@role_required (['Manager','Receptionist'])
def reports():
    # Example queries
    monthly_sales = db.session.query(
        db.func.strftime('%Y-%m', Payment.date_time),
        db.func.sum(Payment.amount)
    ).group_by(db.func.strftime('%Y-%m', Payment.date_time)).all()

    yearly_sales = db.session.query(
        db.func.strftime('%Y', Payment.date_time),
        db.func.sum(Payment.amount)
    ).group_by(db.func.strftime('%Y', Payment.date_time)).all()

    orders_status = db.session.query(Order.status, db.func.count(Order.id)).group_by(Order.status).all()

    # Prepare arrays for charts
    monthly_labels = [m for m, _ in monthly_sales]
    monthly_values = [s for _, s in monthly_sales]

    yearly_labels = [y for y, _ in yearly_sales]
    yearly_values = [s for _, s in yearly_sales]

    status_labels = [st for st, _ in orders_status]
    status_values = [c for _, c in orders_status]

    return render_template(
        "reports.html",
        daily_sales=0,  # example
        guests_served=0,  # example
        monthly_labels=monthly_labels,
        monthly_values=monthly_values,
        yearly_labels=yearly_labels,
        yearly_values=yearly_values,
        status_labels=status_labels,
        status_values=status_values
    )

# --- Payments ---
# Guests pay via M-Pesa, Managers can view all payments.
@app.route('/payments', methods=['GET'])
@role_required(['Manager', 'Guest'])
def payments():
    payments = Payment.query.all()
    return render_template('payments.html', payments=payments)


@app.route('/pay', methods=['POST'])
def pay():
    phone = request.form['phone']
    amount = request.form['amount']
    order_id = request.form['order_id']

    result = stk_push(phone, amount, order_id)  # M-Pesa integration

    payment = Payment(order_id=order_id, amount=amount, method="mpesa", status="pending")
    db.session.add(payment)
    db.session.commit()

    return redirect(url_for('payments'))
# --- Staff management ---
# Only Managers can view staff list.
# add_staff/remove_staff currently lack role checks — should be restricted!
@app.route('/staff', methods=['GET'])
@role_required(['Manager'])
def staff():
    staff = User.query.all()
    return render_template('staff.html', staff=staff)

@app.route('/staff/new', methods=['POST'])
def add_staff():
    name = request.form['name']
    role = request.form['role']
    contact = request.form['contact']

    user = User(name=name, role=role, contact=contact)
    db.session.add(user)
    db.session.commit()
    return redirect(url_for('staff'))

@app.route('/staff/remove/<int:id>', methods=['POST'])
def remove_staff(id):
    user = User.query.get_or_404(id)
    db.session.delete(user)
    db.session.commit()
    return redirect(url_for('staff'))

@app.route('/debug/db')
def debug_db():
    return {
        "tables": db.metadata.tables.keys()
    }

# --- Tables ---
# Managers and Receptionists can add tables.
# Everyone can view the tables list.
@app.route('/tables', methods=['GET', 'POST'])
def tables_list():
    if request.method == 'POST':
        branch_id = request.form.get('branch_id')
        capacity = request.form.get('capacity')
        status = request.form.get('status')

        new_table = Table(branch_id=branch_id, capacity=capacity, status=status)
        db.session.add(new_table)
        db.session.commit()
        flash("Table added successfully!", "success")
        return redirect(url_for('tables_list'))

    tables = Table.query.all()
    return render_template('tables_list.html', tables=tables)

@app.route('/orders/update/<int:order_id>/<status>', methods=['POST'])
def update_order(order_id, status):
    order = Order.query.get_or_404(order_id)
    order.status = status
    db.session.commit()
    flash(f"Order {order_id} marked as {status}.", "info")
    return redirect(url_for('orders'))

@app.route('/orders/delete/<int:order_id>', methods=['POST'])
def delete_order(order_id):
    order = Order.query.get_or_404(order_id)
    db.session.delete(order)
    db.session.commit()
    flash(f"Order {order_id} deleted.", "danger")
    return redirect(url_for('orders'))

@app.route('/orders/payment/<int:order_id>', methods=['POST'])
def link_payment(order_id):
    order = Order.query.get_or_404(order_id)
    payment = Payment(order_id=order.id, amount=order.total_amount, method="M-Pesa", status="paid")
    db.session.add(payment)
    db.session.commit()
    flash(f"Payment recorded for Order {order_id}.", "success")
    return redirect(url_for('orders'))


@app.route('/tables/add', methods=['GET', 'POST'])
@role_required(['Manager', 'Receptionist'])
def add_table():
    if request.method == 'POST':
        branch_id = request.form.get('branch_id')
        capacity = request.form.get('capacity')
        status = request.form.get('status')

        new_table = Table(branch_id=branch_id, capacity=capacity, status=status)
        db.session.add(new_table)
        db.session.commit()
        flash("Table added successfully!", "success")
        return redirect(url_for('tables_list'))

    return render_template('add_table.html')


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
