from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_mail import Mail, Message as MailMessage
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import urllib.parse
import uuid
from datetime import datetime
import os
import pymysql
pymysql.install_as_MySQLdb()

# Optional Twilio SMS support
try:
    from twilio.rest import Client as TwilioClient
    TWILIO_AVAILABLE = True
except ImportError:
    TWILIO_AVAILABLE = False

app = Flask(__name__)
app.secret_key = 'farmdirect-super-secret-key-2024'
app.config['SECRET_KEY'] = app.secret_key
app.config['SESSION_COOKIE_NAME'] = 'farmdirect_session'
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24 hours

# ── Flask-Mail (Email Notifications) ──────────────────────────────────────────
# Set these environment variables in your deployment:
#   MAIL_SERVER, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_USE_TLS
# Example for Gmail: MAIL_SERVER=smtp.gmail.com, MAIL_PORT=587, MAIL_USE_TLS=True
app.config['MAIL_SERVER']   = os.environ.get('MAIL_SERVER',   'smtp.gmail.com')
app.config['MAIL_PORT']     = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS']  = os.environ.get('MAIL_USE_TLS',  'true').lower() == 'true'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME', '')   # your sender email
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD', '')   # your email/app password
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_USERNAME', 'noreply@farmdirect.com')

# ── Twilio (SMS Notifications) ─────────────────────────────────────────────────
# Set these environment variables:
#   TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER
TWILIO_ACCOUNT_SID  = os.environ.get('TWILIO_ACCOUNT_SID', '')
TWILIO_AUTH_TOKEN   = os.environ.get('TWILIO_AUTH_TOKEN', '')
TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')  # e.g. +1234567890

database_url = os.environ.get('DATABASE_URL') or os.environ.get('SQLALCHEMY_DATABASE_URI')
if not database_url:
    db_user = urllib.parse.quote_plus(os.environ.get('DB_USER', 'root'))
    db_password = urllib.parse.quote_plus(os.environ.get('DB_PASSWORD', 'Karthik@2004'))
    db_host = os.environ.get('DB_HOST', 'localhost')
    db_name = os.environ.get('DB_NAME', 'farmdirect')
    database_url = f'mysql+pymysql://{db_user}:{db_password}@{db_host}/{db_name}'

# Resolve SQLite relative paths against the application directory.
if database_url.startswith('sqlite:///') and not database_url.startswith('sqlite:////'):
    sqlite_path = database_url[len('sqlite:///'):]
    if not os.path.isabs(sqlite_path):
        base_dir = os.path.abspath(os.path.dirname(__file__))
        sqlite_path = os.path.join(base_dir, sqlite_path)
        sqlite_path = os.path.abspath(sqlite_path)
        database_url = 'sqlite:///' + sqlite_path.replace('\\', '/')

app.config['SQLALCHEMY_DATABASE_URI'] = database_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'echo': True,
    'pool_pre_ping': True,
    'pool_recycle': 3600,
}
print(f"\n### FLASK APP USING DATABASE: {app.config['SQLALCHEMY_DATABASE_URI']}\n")

db = SQLAlchemy(app)
mail = Mail(app)

# Ensure upload folder exists
UPLOADS_DIR = os.path.join(app.static_folder, 'uploads')
os.makedirs(UPLOADS_DIR, exist_ok=True)
 
# ─────────────────────────── MODELS ───────────────────────────
 
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    role = db.Column(db.String(10), nullable=False)  # 'farmer' or 'customer'
    phone = db.Column(db.String(15))
    location = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    products = db.relationship('Product', backref='farmer', lazy=True)
    orders = db.relationship('Order', backref='customer', lazy=True)
    reviews = db.relationship('Review', backref='reviewer', lazy=True)
 
 
class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), nullable=False)  # kg, dozen, piece, etc.
    quantity_available = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    image_url = db.Column(db.String(200), default='')
    farmer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    order_items = db.relationship('OrderItem', backref='product', lazy=True)
    reviews = db.relationship('Review', backref='product', lazy=True)
 
    @property
    def avg_rating(self):
        if not self.reviews:
            return 0
        return round(sum(r.rating for r in self.reviews) / len(self.reviews), 1)
 
    @property
    def review_count(self):
        return len(self.reviews)
 
 
class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    total_amount = db.Column(db.Float, nullable=False)
    status = db.Column(db.String(20), default='pending')  # pending, confirmed, delivered, cancelled
    delivery_address = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', lazy=True)
 
 
class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    price_at_purchase = db.Column(db.Float, nullable=False)
 
 
class Review(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1-5
    comment = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class Notification(db.Model):
    """In-website notification bell entries."""
    id         = db.Column(db.Integer, primary_key=True)
    user_id    = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    message    = db.Column(db.Text, nullable=False)
    is_read    = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    link       = db.Column(db.String(200), default='')  # optional URL to link to

    user = db.relationship('User', backref=db.backref('notifications', lazy=True))
 
 
# ─────────────────────────── HELPERS ───────────────────────────
 
def get_cart():
    return session.get('cart', {})
 
def save_cart(cart):
    session['cart'] = cart
 
def cart_total():
    cart = get_cart()
    total = 0
    for pid, item in cart.items():
        total += item['price'] * item['quantity']
    return round(total, 2)
 
def cart_count():
    return sum(item['quantity'] for item in get_cart().values())
 
def unread_notification_count():
    """Returns unread notification count for the logged-in user (used in templates)."""
    uid = session.get('user_id')
    if not uid:
        return 0
    return Notification.query.filter_by(user_id=uid, is_read=False).count()

app.jinja_env.globals.update(
    cart_count=cart_count,
    cart_total=cart_total,
    unread_notification_count=unread_notification_count,
)


# ─────────────────────────── NOTIFICATION HELPERS ─────────────────────────────

def create_notification(user_id, message, link=''):
    """Save an in-website notification for a user."""
    notif = Notification(user_id=user_id, message=message, link=link)
    db.session.add(notif)
    # We don't commit here — caller commits alongside the main transaction.


def send_email_notification(to_email, subject, body_html):
    """Send an HTML email. Silently fails if mail is not configured."""
    if not app.config.get('MAIL_USERNAME'):
        print(f"[MAIL] Skipped (not configured) → {subject}")
        return
    try:
        msg = MailMessage(subject=subject, recipients=[to_email], html=body_html)
        mail.send(msg)
        print(f"[MAIL] Sent '{subject}' → {to_email}")
    except Exception as e:
        print(f"[MAIL] Failed to send email: {e}")


def send_sms_notification(to_phone, body):
    """Send an SMS via Twilio. Silently fails if Twilio is not configured."""
    if not (TWILIO_AVAILABLE and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER):
        print(f"[SMS] Skipped (not configured) → {body[:60]}")
        return
    if not to_phone:
        return
    try:
        client = TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        client.messages.create(body=body, from_=TWILIO_PHONE_NUMBER, to=to_phone)
        print(f"[SMS] Sent to {to_phone}")
    except Exception as e:
        print(f"[SMS] Failed: {e}")


def notify_order_placed(order):
    """
    Triggered when a customer places an order.
    Notifies: the customer (confirmation) + every farmer whose product is in the order.
    """
    customer = User.query.get(order.customer_id)

    # ── 1. Notify the customer ──────────────────────────────────────────────
    customer_msg = f"✅ Your order #{order.id} has been placed! Total: ₹{order.total_amount:.2f}. We'll notify you when the farmer accepts."
    create_notification(customer.id, customer_msg, link='/orders')

    send_email_notification(
        customer.email,
        f"FarmDirect – Order #{order.id} Placed Successfully 🌿",
        f"""
        <h2>Hi {customer.name},</h2>
        <p>Your order <strong>#{order.id}</strong> has been placed successfully!</p>
        <p><strong>Total Amount:</strong> ₹{order.total_amount:.2f}</p>
        <p><strong>Delivery Address:</strong> {order.delivery_address}</p>
        <p>You will receive another notification once the farmer accepts your order.</p>
        <br><p>Thank you for shopping with <strong>FarmDirect</strong>! 🌾</p>
        """
    )

    send_sms_notification(
        customer.phone,
        f"FarmDirect: Order #{order.id} placed! Total ₹{order.total_amount:.2f}. You'll be notified when the farmer accepts."
    )

    # ── 2. Notify each farmer whose products are in this order ──────────────
    farmer_ids_notified = set()
    for item in order.items:
        product = Product.query.get(item.product_id)
        if not product:
            continue
        farmer = User.query.get(product.farmer_id)
        if not farmer or farmer.id in farmer_ids_notified:
            continue
        farmer_ids_notified.add(farmer.id)

        farmer_msg = f"🛒 New order #{order.id} received for your products from {customer.name}! Please accept or reject it."
        create_notification(farmer.id, farmer_msg, link='/farmer/orders')

        send_email_notification(
            farmer.email,
            f"FarmDirect – New Order #{order.id} Received 📦",
            f"""
            <h2>Hi {farmer.name},</h2>
            <p>You have received a <strong>new order #{order.id}</strong> from <strong>{customer.name}</strong>.</p>
            <p><strong>Total:</strong> ₹{order.total_amount:.2f}</p>
            <p>Please log in to your dashboard to accept or manage the order.</p>
            <br><p><strong>FarmDirect</strong> – Connecting Farmers to Customers 🌾</p>
            """
        )

        send_sms_notification(
            farmer.phone,
            f"FarmDirect: New order #{order.id} from {customer.name} (₹{order.total_amount:.2f}). Login to accept: farmdirect.com/farmer/orders"
        )


def notify_order_status_changed(order, new_status):
    """
    Triggered when the farmer updates the order status (confirmed, delivered, cancelled).
    Notifies: the customer.
    """
    customer = User.query.get(order.customer_id)
    if not customer:
        return

    status_labels = {
        'confirmed':  ('✅ Order Accepted', 'accepted and confirmed'),
        'delivered':  ('📦 Order Delivered', 'marked as delivered'),
        'cancelled':  ('❌ Order Cancelled', 'cancelled'),
    }
    label, verb = status_labels.get(new_status, ('📋 Order Updated', f'updated to {new_status}'))

    customer_msg = f"{label} – Your order #{order.id} has been {verb} by the farmer."
    create_notification(customer.id, customer_msg, link='/orders')

    send_email_notification(
        customer.email,
        f"FarmDirect – Order #{order.id} {label}",
        f"""
        <h2>Hi {customer.name},</h2>
        <p>Your order <strong>#{order.id}</strong> has been <strong>{verb}</strong> by the farmer.</p>
        <p><strong>Total Amount:</strong> ₹{order.total_amount:.2f}</p>
        {"<p>Your items are on their way! 🚚</p>" if new_status == 'confirmed' else ""}
        {"<p>Your order has been delivered. Enjoy your fresh produce! 🌿</p>" if new_status == 'delivered' else ""}
        {"<p>We're sorry your order was cancelled. Please try again or contact support.</p>" if new_status == 'cancelled' else ""}
        <br><p>Thank you for using <strong>FarmDirect</strong>! 🌾</p>
        """
    )

    send_sms_notification(
        customer.phone,
        f"FarmDirect: Order #{order.id} has been {verb}. Check details: farmdirect.com/orders"
    )
 
 
# ─────────────────────────── AUTH ROUTES ───────────────────────────
@app.route('/debug/db-check', methods=['GET'])
def debug_db_check():
    """Debug endpoint to check which database is being used"""
    with app.app_context():
        # Check the configured engine
        print(f"Engine URL: {db.engine.url}")
        print(f"Engine Dialect: {db.engine.dialect.name}")
        print(f"Engine Pool: {db.engine.pool}")
        
        # Try to execute a query
        from sqlalchemy import text
        try:
            result = db.session.execute(text("SELECT COUNT(*) FROM user"))
            count = result.scalar()
            return jsonify({
                "status": "OK",
                "configured_uri": app.config['SQLALCHEMY_DATABASE_URI'],
                "engine_url": str(db.engine.url),
                "engine_dialect": db.engine.dialect.name,
                "user_count": count
            })
        except Exception as e:
            return jsonify({
                "status": "ERROR",
                "error": str(e)
            }), 500


@app.route('/')
def index():
    products = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(8).all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template('customer/index.html', products=products, categories=categories)
 
 
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        password = request.form['password']
        role = request.form['role']
        phone = request.form.get('phone', '')
        location = request.form.get('location', '')

        print(f"\n--- REGISTRATION ATTEMPT ---")
        print(f"Config Database URI: {app.config['SQLALCHEMY_DATABASE_URI']}")
        print(f"Engine URL: {db.engine.url}")
        print(f"Engine Dialect: {db.engine.dialect.name}")
 
        if User.query.filter_by(email=email).first():
            flash('Email already registered!', 'danger')
            return redirect(url_for('register'))
 
        try:
            user = User(
                name=name, email=email,
                password=generate_password_hash(password, method='pbkdf2:sha256'),
                role=role, phone=phone, location=location
            )
            print(f"User object created: {user.name}, {user.email}, {user.role}")
            db.session.add(user)
            print(f"User added to session")
            db.session.commit()
            print(f"Session committed. New user ID: {user.id}")
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            print(f"ERROR during registration: {str(e)}")
            import traceback
            traceback.print_exc()
            flash(f'Registration failed: {str(e)}', 'danger')
            return redirect(url_for('register'))
    return render_template('customer/register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):

            session.permanent = True
            session['user_id'] = user.id
            session['user_name'] = user.name
            session['user_role'] = user.role
            # ADD THESE 2 DEBUG LINES:
            print(f"✅ SESSION SET: {dict(session)}")
            print(f"✅ REDIRECTING TO: {user.role}")

            flash(f'Welcome, {user.name}!', 'success')

            if user.role == 'farmer':
                return redirect(url_for('farmer_dashboard'))
            else:
                return redirect(url_for('index'))

        flash('Invalid email or password.', 'danger')

    return render_template('customer/login.html')
@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out successfully.', 'info')
    return redirect(url_for('index'))
 
 
# ─────────────────────────── FARMER ROUTES ───────────────────────────
 
@app.route('/farmer/dashboard')
def farmer_dashboard():
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))

    farmer = User.query.get(session['user_id'])

    if not farmer:
        session.clear()
        flash('Please login again.', 'warning')
        return redirect(url_for('login'))

    products = Product.query.filter_by(farmer_id=farmer.id).all()

    farmer_product_ids = [p.id for p in products]
    order_items = OrderItem.query.filter(
        OrderItem.product_id.in_(farmer_product_ids)
    ).all() if farmer_product_ids else []

    total_revenue = sum(
        oi.price_at_purchase * oi.quantity
        for oi in order_items
    )

    return render_template(
        'farmer/farmer_dashboard.html',
        farmer=farmer,
        products=products,
        order_items=order_items,
        total_revenue=total_revenue
    )
 
 
@app.route('/farmer/product/add', methods=['GET', 'POST'])
def add_product():
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))
    if request.method == 'POST':
        # Handle uploaded image (preferred) or fallback to image_url
        image = request.files.get('image')
        image_url = request.form.get('image_url', '')
        if image and image.filename:
            filename = secure_filename(image.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(UPLOADS_DIR, unique_name)
            image.save(save_path)
            image_url = f"/static/uploads/{unique_name}"

        product = Product(
            name=request.form['name'],
            description=request.form['description'],
            price=float(request.form['price']),
            unit=request.form['unit'],
            quantity_available=float(request.form['quantity']),
            category=request.form['category'],
            image_url=image_url,
            farmer_id=session['user_id']
        )
        db.session.add(product)
        db.session.commit()
        flash('Product listed successfully!', 'success')
        return redirect(url_for('farmer_dashboard'))
    return render_template('farmer/add_product.html')

 
@app.route('/farmer/product/edit/<int:pid>', methods=['GET', 'POST'])
def edit_product(pid):
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))
    product = Product.query.get_or_404(pid)
    if product.farmer_id != session['user_id']:
        flash('Unauthorized!', 'danger')
        return redirect(url_for('farmer_dashboard'))
    if request.method == 'POST':
        product.name = request.form['name']
        product.description = request.form['description']
        product.price = float(request.form['price'])
        product.unit = request.form['unit']
        product.quantity_available = float(request.form['quantity'])
        product.category = request.form['category']
        # Handle optional image upload for edit
        image = request.files.get('image')
        if image and image.filename:
            filename = secure_filename(image.filename)
            unique_name = f"{uuid.uuid4().hex}_{filename}"
            save_path = os.path.join(UPLOADS_DIR, unique_name)
            image.save(save_path)
            product.image_url = f"/static/uploads/{unique_name}"
        product.is_active = 'is_active' in request.form
        db.session.commit()
        flash('Product updated!', 'success')
        return redirect(url_for('farmer_dashboard'))
    return render_template('farmer/edit_product.html', product=product)
 
 
@app.route('/farmer/product/delete/<int:pid>')
def delete_product(pid):
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))

    product = Product.query.get_or_404(pid)

    if product.farmer_id == session['user_id']:

        OrderItem.query.filter_by(product_id=pid).delete()

        db.session.delete(product)
        db.session.commit()

        flash('Product removed.', 'info')

    return redirect(url_for('farmer_dashboard'))
 
 
@app.route('/farmer/orders')
def farmer_orders():
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))
    farmer = User.query.get(session['user_id'])
    if not farmer:
        return redirect(url_for('login'))

    product_ids = [p.id for p in farmer.products] if farmer.products else []

    if not product_ids:
        orders = []
    else:
        orders = Order.query.join(OrderItem).filter(
            OrderItem.product_id.in_(product_ids)
        ).order_by(Order.created_at.desc()).distinct().all()

    return render_template('farmer/farmer_orders.html', orders=orders)
 
 
# ─────────────────────────── PRODUCT / SHOP ROUTES ───────────────────────────
 
@app.route('/shop')
def shop():
    category = request.args.get('category', '')
    search = request.args.get('search', '')
    query = Product.query.filter_by(is_active=True)
    if category:
        query = query.filter_by(category=category)
    if search:
        query = query.filter(Product.name.ilike(f'%{search}%'))
    products = query.order_by(Product.created_at.desc()).all()
    categories = db.session.query(Product.category).distinct().all()
    categories = [c[0] for c in categories]
    return render_template('customer/shop.html', products=products, categories=categories,
                           selected_category=category, search=search)
 
 
@app.route('/product/<int:pid>')
def product_detail(pid):
    product = Product.query.get_or_404(pid)
    reviews = Review.query.filter_by(product_id=pid).order_by(Review.created_at.desc()).all()
    user_reviewed = False
    if session.get('user_id'):
        user_reviewed = Review.query.filter_by(product_id=pid, user_id=session['user_id']).first() is not None
    return render_template('customer/product_detail.html', product=product, reviews=reviews, user_reviewed=user_reviewed)
 
 
# ─────────────────────────── CART ROUTES ───────────────────────────
 
@app.route('/cart/add/<int:pid>', methods=['POST'])
def add_to_cart(pid):
    product = Product.query.get_or_404(pid)
    qty = float(request.form.get('quantity', 1))
    cart = get_cart()
    key = str(pid)
    if key in cart:
        cart[key]['quantity'] += qty
    else:
        cart[key] = {
            'name': product.name,
            'price': product.price,
            'unit': product.unit,
            'quantity': qty,
            'farmer': product.farmer.name
        }
    save_cart(cart)
    flash(f'{product.name} added to cart!', 'success')
    return redirect(request.referrer or url_for('shop'))
 
 
@app.route('/cart')
def cart():
    cart = get_cart()
    items = []
    for pid, item in cart.items():
        product = Product.query.get(int(pid))
        if product:
            items.append({'pid': pid, 'product': product, **item})
    return render_template('customer/cart.html', items=items)
 
 
@app.route('/cart/remove/<pid>')
def remove_from_cart(pid):
    cart = get_cart()
    cart.pop(pid, None)
    save_cart(cart)
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart'))
 
 
@app.route('/cart/update', methods=['POST'])
def update_cart():
    cart = get_cart()
    for key in list(cart.keys()):
        qty = request.form.get(f'qty_{key}')
        if qty:
            new_qty = float(qty)
            if new_qty <= 0:
                cart.pop(key)
            else:
                cart[key]['quantity'] = new_qty
    save_cart(cart)
    flash('Cart updated!', 'success')
    return redirect(url_for('cart'))
 
 
# ─────────────────────────── CHECKOUT / ORDER ROUTES ───────────────────────────
 
@app.route('/checkout', methods=['GET', 'POST'])
def checkout():
    if not session.get('user_id'):
        flash('Please login to checkout.', 'warning')
        return redirect(url_for('login'))
    if session.get('user_role') == 'farmer':
        flash('Farmers cannot place orders.', 'warning')
        return redirect(url_for('shop'))
    cart = get_cart()
    if not cart:
        flash('Your cart is empty!', 'warning')
        return redirect(url_for('shop'))
    if request.method == 'POST':
        address = request.form['address']
        order = Order(
            customer_id=session['user_id'],
            total_amount=cart_total(),
            delivery_address=address
        )
        db.session.add(order)
        db.session.flush()
        for pid, item in cart.items():
            product = Product.query.get(int(pid))
            if product:
                oi = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=item['quantity'],
                    price_at_purchase=item['price']
                )
                db.session.add(oi)
                product.quantity_available = max(0, product.quantity_available - item['quantity'])
        notify_order_placed(order)   # ← in-site + email + SMS notifications
        db.session.commit()          # commit notifications together
        session['cart'] = {}
        flash(f'Order #{order.id} placed successfully!', 'success')
        return redirect(url_for('my_orders'))
    user = User.query.get(session['user_id'])
    return render_template('customer/checkout.html', cart=cart, user=user)
 
 
@app.route('/orders')
def my_orders():
    if not session.get('user_id'):
        return redirect(url_for('login'))

    orders = Order.query.filter(
        Order.customer_id == session['user_id'],
        Order.status != 'cancelled'
    ).order_by(Order.created_at.desc()).all()

    user = User.query.get(session['user_id'])

    return render_template(
        'customer/my_orders.html',
        orders=orders,
        user=user
    )
 
 
@app.route('/order/<int:oid>/update', methods=['POST'])
def update_order_status(oid):
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))
    order = Order.query.get_or_404(oid)
    new_status = request.form['status']
    order.status = new_status
    notify_order_status_changed(order, new_status)   # ← in-site + email + SMS
    db.session.commit()
    flash('Order status updated!', 'success')
    return redirect(url_for('farmer_orders'))


@app.route('/farmer/active-products')
def active_products():
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))

    products = Product.query.filter_by(
        farmer_id=session['user_id'],
        is_active=True
    ).all()

    return render_template(
        'farmer/active_products.html',
        products=products
    )

@app.route('/farmer/revenue')
def revenue_details():
    if session.get('user_role') != 'farmer':
        return redirect(url_for('login'))

    farmer_products = Product.query.filter_by(
        farmer_id=session['user_id']
    ).all()

    product_ids = [p.id for p in farmer_products]

    order_items = OrderItem.query.filter(
        OrderItem.product_id.in_(product_ids)
    ).all() if product_ids else []

    total_revenue = sum(
        oi.price_at_purchase * oi.quantity
        for oi in order_items
    )

    return render_template(
        'farmer/revenue.html',
        total_revenue=total_revenue
    )


@app.route('/order/cancel/<int:oid>')
def cancel_order(oid):
    if not session.get('user_id'):
        return redirect(url_for('login'))

    order = Order.query.get_or_404(oid)

    # Only the customer who placed the order can cancel it
    if order.customer_id != session['user_id']:
        flash('Unauthorized action!', 'danger')
        return redirect(url_for('my_orders'))

    order.status = 'cancelled'
    db.session.commit()

    flash('Order cancelled successfully!', 'success')
    return redirect(url_for('my_orders'))
 
 
# ─────────────────────────── NOTIFICATION ROUTES ──────────────────────────────

@app.route('/notifications')
def notifications_page():
    """Shows all notifications for the logged-in user."""
    if not session.get('user_id'):
        return redirect(url_for('login'))
    notifs = Notification.query.filter_by(user_id=session['user_id']) \
                               .order_by(Notification.created_at.desc()).all()
    # Mark all as read when the page is viewed
    for n in notifs:
        n.is_read = True
    db.session.commit()
    return render_template('notifications.html', notifications=notifs)


@app.route('/notifications/mark-read/<int:nid>', methods=['POST'])
def mark_notification_read(nid):
    if not session.get('user_id'):
        return jsonify({'error': 'unauthorized'}), 401
    notif = Notification.query.get_or_404(nid)
    if notif.user_id != session['user_id']:
        return jsonify({'error': 'forbidden'}), 403
    notif.is_read = True
    db.session.commit()
    return jsonify({'success': True})

@app.route('/toggle_product/<int:pid>')
def toggle_product(pid):
    product = Product.query.get_or_404(pid)

    product.is_active = not product.is_active

    db.session.commit()

    return redirect(url_for('farmer_dashboard'))


@app.route('/notifications/unread-count')
def unread_count_api():
    """JSON endpoint for polling unread count (used by the bell icon)."""
    if not session.get('user_id'):
        return jsonify({'count': 0})
    count = Notification.query.filter_by(user_id=session['user_id'], is_read=False).count()
    return jsonify({'count': count})


# ─────────────────────────── REVIEW ROUTES ───────────────────────────
 
@app.route('/product/<int:pid>/review', methods=['POST'])
def add_review(pid):
    if not session.get('user_id'):
        flash('Please login to review.', 'warning')
        return redirect(url_for('login'))
    if session.get('user_role') == 'farmer':
        flash('Farmers cannot review products.', 'warning')
        return redirect(url_for('product_detail', pid=pid))
    existing = Review.query.filter_by(product_id=pid, user_id=session['user_id']).first()
    if existing:
        flash('You have already reviewed this product.', 'warning')
        return redirect(url_for('product_detail', pid=pid))
    review = Review(
        product_id=pid,
        user_id=session['user_id'],
        rating=int(request.form['rating']),
        comment=request.form.get('comment', '')
    )
    db.session.add(review)
    db.session.commit()
    flash('Review submitted!', 'success')
    return redirect(url_for('product_detail', pid=pid))
 
 
# ─────────────────────────── INIT DB ───────────────────────────
 
def seed_data():
    if User.query.first():
        return
    if os.environ.get('ENABLE_SEED_DATA', 'false').lower() != 'true':
        return

    def required_env(name):
        value = os.environ.get(name)
        if not value:
            raise RuntimeError(f"Environment variable {name} is required when ENABLE_SEED_DATA=true")
        return value

    farmer = User(
        name=required_env('SEED_FARMER_NAME'),
        email=required_env('SEED_FARMER_EMAIL'),
        password=generate_password_hash(required_env('SEED_FARMER_PASSWORD')),
        role='farmer',
        phone=os.environ.get('SEED_FARMER_PHONE', ''),
        location=os.environ.get('SEED_FARMER_LOCATION', '')
    )
    customer = User(
        name=required_env('SEED_CUSTOMER_NAME'),
        email=required_env('SEED_CUSTOMER_EMAIL'),
        password=generate_password_hash(required_env('SEED_CUSTOMER_PASSWORD')),
        role='customer',
        phone=os.environ.get('SEED_CUSTOMER_PHONE', ''),
        location=os.environ.get('SEED_CUSTOMER_LOCATION', '')
    )
    db.session.add_all([farmer, customer])
    db.session.flush()

    products = []
    for idx in range(1, 3):
        products.append(Product(
            name=required_env(f'SEED_PRODUCT_{idx}_NAME'),
            description=required_env(f'SEED_PRODUCT_{idx}_DESCRIPTION'),
            price=float(required_env(f'SEED_PRODUCT_{idx}_PRICE')),
            unit=required_env(f'SEED_PRODUCT_{idx}_UNIT'),
            quantity_available=float(required_env(f'SEED_PRODUCT_{idx}_QUANTITY')),
            category=required_env(f'SEED_PRODUCT_{idx}_CATEGORY'),
            image_url=os.environ.get(f'SEED_PRODUCT_{idx}_IMAGE_URL', ''),
            farmer_id=farmer.id
        ))

    db.session.add_all(products)
    db.session.commit()
    print("✅ Seed data created")

with app.app_context():
    db.create_all()
print("\n===== REGISTERED ROUTES =====")
print(app.url_map)
print("=============================\n")

if __name__ == '__main__':
    app.run(debug=True, use_reloader=False)