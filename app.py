from flask import Flask, request, jsonify, session, send_from_directory, redirect
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import json, os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
USERS_FILE = os.path.join(APP_DIR, 'users.json')
ORDERS_FILE = os.path.join(APP_DIR, 'orders.json')
MESSAGES_FILE = os.path.join(APP_DIR, 'messages.json')

app = Flask(__name__, static_folder='.', static_url_path='')
app.secret_key = 'replace_this_with_a_real_secret_12345'  # поменяй перед деплоем

# --- helpers for json storage ---
def load_json(path, default):
    if not os.path.exists(path):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(default, f, indent=2, ensure_ascii=False)
        return default
    with open(path, 'r', encoding='utf-8') as f:
        try:
            return json.load(f)
        except Exception:
            return default

def save_json(path, data):
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

# --- init files and admin user ---
users = load_json(USERS_FILE, {})
orders = load_json(ORDERS_FILE, [])
messages = load_json(MESSAGES_FILE, [])

# Admin credentials provided by user
ADMIN_LOGIN = "Bobur2012.12"
ADMIN_PASSWORD = "4348888b"

def ensure_admin():
    global users
    if ADMIN_LOGIN not in users:
        users[ADMIN_LOGIN] = {
            "password_hash": generate_password_hash(ADMIN_PASSWORD),
            "role": "admin",
            "created_at": datetime.utcnow().isoformat()
        }
        save_json(USERS_FILE, users)
        print("Admin user created:", ADMIN_LOGIN)

ensure_admin()

# --- Routes: static serving for index.html and panel.html ---
@app.route('/')
def index():
    return send_from_directory(APP_DIR, 'index.html')

@app.route('/panel.html')
def panel():
    return send_from_directory(APP_DIR, 'panel.html')

# --- API: register / login / logout / who ---
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({"success": False, "error": "username/password required"}), 400

    # do not allow to register admin username
    if username == ADMIN_LOGIN:
        return jsonify({"success": False, "error": "Недопустимый логин"}), 400

    users = load_json(USERS_FILE, {})
    if username in users:
        return jsonify({"success": False, "error": "Пользователь уже существует"}), 400

    users[username] = {
        "password_hash": generate_password_hash(password),
        "role": "client",
        "created_at": datetime.utcnow().isoformat()
    }
    save_json(USERS_FILE, users)
    session['user'] = username
    return jsonify({"success": True})

@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    if not username or not password:
        return jsonify({"success": False, "error": "username/password required"}), 400

    users = load_json(USERS_FILE, {})
    user = users.get(username)
    # allow login by email? (not implemented) — username only
    if not user:
        return jsonify({"success": False, "error": "Неверный логин или пароль"}), 401

    if not check_password_hash(user['password_hash'], password):
        return jsonify({"success": False, "error": "Неверный логин или пароль"}), 401

    session['user'] = username
    return jsonify({"success": True})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('user', None)
    return jsonify({"ok": True})

@app.route('/who', methods=['GET'])
def whoami():
    username = session.get('user')
    if not username:
        return jsonify({"logged": False})
    users = load_json(USERS_FILE, {})
    user = users.get(username, {})
    return jsonify({"logged": True, "username": username, "role": user.get('role','client')})

# --- Orders API ---
@app.route('/api/orders', methods=['GET', 'POST'])
def api_orders():
    username = session.get('user')
    users = load_json(USERS_FILE, {})

    if request.method == 'POST':
        if not username:
            return jsonify({"ok": False, "error": "Not authenticated"}), 401
        data = request.get_json() or {}
        type_ = data.get('type', 'video')
        description = (data.get('description') or '').strip()
        reference = (data.get('reference') or '').strip()
        if not description:
            return jsonify({"ok": False, "error": "description required"}), 400

        orders = load_json(ORDERS_FILE, [])
        new_id = (orders[-1]['id'] + 1) if orders else 1
        item = {
            "id": new_id,
            "user": username,
            "username": username,
            "type": type_,
            "description": description,
            "reference": reference,
            "status": "pending",
            "created_at": datetime.utcnow().isoformat()
        }
        orders.append(item)
        save_json(ORDERS_FILE, orders)
        return jsonify({"ok": True, "id": new_id})

    # GET
    orders = load_json(ORDERS_FILE, [])
    user = users.get(username) if username else None
    if user and user.get('role') == 'admin':
        # admin sees all orders
        return jsonify({"ok": True, "orders": orders})
    else:
        # client sees own orders
        own = [o for o in orders if o.get('user') == username]
        return jsonify({"ok": True, "orders": own})

@app.route('/api/orders/<int:order_id>/status', methods=['POST'])
def set_order_status(order_id):
    username = session.get('user')
    users = load_json(USERS_FILE, {})
    user = users.get(username) if username else None
    if not user or user.get('role') != 'admin':
        return jsonify({"ok": False, "error": "Forbidden"}), 403
    data = request.get_json() or {}
    status = data.get('status') or 'updated'
    orders = load_json(ORDERS_FILE, [])
    found = False
    for o in orders:
        if o['id'] == order_id:
            o['status'] = status
            found = True
            break
    if not found:
        return jsonify({"ok": False, "error": "Order not found"}), 404
    save_json(ORDERS_FILE, orders)
    return jsonify({"ok": True})

# --- Messages (simple chat) ---
@app.route('/api/messages', methods=['GET', 'POST'])
def api_messages():
    if request.method == 'POST':
        data = request.get_json() or {}
        username = data.get('username') or session.get('user') or 'guest'
        message = (data.get('message') or '').strip()
        if not message:
            return jsonify({"ok": False, "error": "message required"}), 400
        messages = load_json(MESSAGES_FILE, [])
        new_id = (messages[-1]['id'] + 1) if messages else 1
        m = {"id": new_id, "username": username, "message": message, "created_at": datetime.utcnow().isoformat()}
        messages.append(m)
        # keep last 500 messages only
        if len(messages) > 500:
            messages = messages[-500:]
        save_json(MESSAGES_FILE, messages)
        return jsonify({"ok": True, "msg": m})
    else:
        messages = load_json(MESSAGES_FILE, [])
        return jsonify({"ok": True, "messages": messages})

# run
if __name__ == '__main__':
    print("Starting server on http://127.0.0.1:5000")
    app.run(debug=True)
