import os
import json
import uuid
import bcrypt
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Flask, render_template_string, request, redirect, url_for, session,
    flash, jsonify, send_file
)

# ========= CONFIG ==============
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
# Generate hash: bcrypt.hashpw(b'admin123', bcrypt.gensalt()).decode()
ADMIN_PASSWORD_HASH = os.environ.get(
    'ADMIN_PASSWORD_HASH',
    b'$2b$12$8Ff6dn7m9BkYa0dXx7Hi4uZqOeLQ3wYwppW4k1iM9JkYv3vTezj4q'  # hash for 'admin123'
).encode()
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret')
LICENSES_FILE = 'data/licenses.json'
TOOLS_FILE = 'data/tools.json'
os.makedirs('data', exist_ok=True)

# ===== Flask Setup =====
app = Flask(__name__)
app.secret_key = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS

# ===== HTML TEMPLATES =====
BASE_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>{{ title or "Admin Dashboard" }}</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; background: #f7f7f7; margin: 0; }
        nav { background: #222; padding: 1em; border-radius: 0 0 6px 6px;}
        nav a { color: #fff; margin-right: 1em; text-decoration: none; }
        .container { padding: 2em; background: #fff; max-width: 1200px; margin: 2em auto; border-radius: 6px; }
        .flashes { list-style: none; padding: 0; }
        .flashes li { padding: 0.5em; margin-bottom: 0.5em; border-radius: 3px; }
        .flashes li.danger { background: #ffeaea; color: #a33; }
        .flashes li.info { background: #eaf4ff; color: #235; }
        .flashes li.success { background: #eaffea; color: #295; }
        h1, h2 { margin-top:0; }
        table { width:100%; border-collapse:collapse; margin-top:1em;}
        th, td { border:1px solid #ccc; padding:0.5em; }
        th { background:#eee; }
        .active { background:#eaffea; }
        .expired { background:#ffeaea; color:#a33;}
        .disabled { background:#f5f5f5; color:#b1b1b1;}
        .msg { padding: 1em; margin-bottom: 1.2em; background: #eaf4ff; border-left: 5px solid #1976d2; border-radius: 4px;}
        .danger { background: #ffeaea; border-left: 5px solid #d80000;}
        .success { background: #eaffea; border-left: 5px solid #008800;}
        .form-row { margin-bottom: 0.7em; }
        .pagination { margin: 1.5em 0; text-align: center; }
        .pagination a, .pagination span { display: inline-block; padding: 0.3em 0.8em; margin: 0 0.2em; border-radius: 2px; background: #eee; color: #333; text-decoration: none; }
        .pagination .current { background: #1976d2; color: #fff; font-weight: bold; }
        .chart-container { max-width: 600px; margin: 2em auto 0 auto; }
        input[type="text"], input[type="password"], input[type="date"] {
            padding: 0.2em 0.4em;
            border-radius: 2px;
            border: 1px solid #ccc;
        }
        input[type="checkbox"] {
            transform: scale(1.1);
        }
        button, input[type="submit"] {
            background: #1976d2;
            color: #fff;
            border: none;
            border-radius: 2px;
            padding: 0.4em 1em;
            margin-right: 0.3em;
            cursor: pointer;
        }
        button:hover, input[type="submit"]:hover {
            background: #145cab;
        }
        @media (max-width: 700px) {
            .container { padding: 0.5em; }
            table, th, td { font-size: 0.96em; }
        }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <nav>
        {% if session.get('admin_logged_in') %}
            <a href="{{ url_for('dashboard') }}">Dashboard</a>
            <a href="{{ url_for('license_admin') }}">Licenses</a>
            <a href="{{ url_for('tools_admin') }}">Tools</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
            <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
        <a href="{{ url_for('docs') }}">API Docs</a>
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <ul class="flashes">
                {% for category, message in messages %}
                    <li class="{{ category }}">{{ message|safe }}</li>
                {% endfor %}
                </ul>
            {% endif %}
        {% endwith %}
        {% block content %}{{ content|safe }}{% endblock %}
    </div>
</body>
</html>
"""

# ====== Utility Functions ======
def load_json(path):
    if not os.path.exists(path):
        return []
    with open(path, 'r') as f:
        return json.load(f)

def save_json(path, data):
    with open(path, 'w') as f:
        json.dump(data, f, indent=2)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def password_check(pw_plain, pw_hash):
    return bcrypt.checkpw(pw_plain.encode(), pw_hash)

def status_of(lic):
    today = datetime.now().date()
    expiry = datetime.strptime(lic['expiry'], "%Y-%m-%d").date()
    if not lic.get('active', True):
        return "Disabled"
    elif expiry < today:
        return "Expired"
    else:
        return "Active"

def days_left(lic):
    expiry = datetime.strptime(lic['expiry'], "%Y-%m-%d").date()
    today = datetime.now().date()
    return (expiry - today).days

# ====== AUTH ======
@app.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard'))
    error = ""
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if (
            username == ADMIN_USERNAME
            and password_check(password, ADMIN_PASSWORD_HASH)
        ):
            session['admin_logged_in'] = True
            flash('Logged in!', 'success')
            return redirect(url_for('dashboard'))
        flash('Invalid credentials', 'danger')
    login_form = """
    <h2>Admin Login</h2>
    <form method="POST">
        <label>Username:</label><br>
        <input name="username" required><br>
        <label>Password:</label><br>
        <input name="password" type="password" required><br>
        <button type="submit">Login</button>
    </form>
    """
    return render_template_string(BASE_TEMPLATE, content=login_form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

# ========== DASHBOARD ==========
@app.route('/')
@admin_required
def dashboard():
    licenses = load_json(LICENSES_FILE)
    tools = load_json(TOOLS_FILE)
    total = len(licenses)
    active = sum(1 for l in licenses if status_of(l) == "Active")
    expired = sum(1 for l in licenses if status_of(l) == "Expired")
    disabled = sum(1 for l in licenses if status_of(l) == "Disabled")
    tool_total = len(tools)
    soon_expiry = [
        lic for lic in licenses
        if lic.get('active', True) and status_of(lic) == "Active" and datetime.strptime(lic['expiry'], "%Y-%m-%d") < datetime.now() + timedelta(days=7)
    ]
    dashboard_html = f"""
    <h2>Dashboard</h2>
    <div style="display:flex; gap:2em; flex-wrap:wrap; align-items:flex-end;">
    <div>
        <h3>License Stats</h3>
        <ul>
            <li>Total Licenses: <b>{total}</b></li>
            <li>Active: <b>{active}</b></li>
            <li>Expired: <b>{expired}</b></li>
            <li>Disabled: <b>{disabled}</b></li>
        </ul>
        <div class="chart-container">
            <canvas id="licenseChart"></canvas>
        </div>
    </div>
    <div>
        <h3>Tool Stats</h3>
        <ul>
            <li>Total Tools: <b>{tool_total}</b></li>
        </ul>
        <div class="chart-container">
            <canvas id="toolChart"></canvas>
        </div>
    </div>
    </div>
    <script>
    window.addEventListener('DOMContentLoaded', function() {{
        var ctx = document.getElementById('licenseChart').getContext('2d');
        new Chart(ctx, {{
            type: 'doughnut',
            data: {{
                labels: ['Active', 'Expired', 'Disabled'],
                datasets: [{{
                    data: [{active}, {expired}, {disabled}],
                    backgroundColor: ['#3ec96b', '#f35a5a', '#cccccc']
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ position: 'bottom' }} }}
            }}
        }});
        var toolCtx = document.getElementById('toolChart').getContext('2d');
        new Chart(toolCtx, {{
            type: 'bar',
            data: {{
                labels: [{','.join([f"'{t['name']} v{t['version']}'" for t in tools])}],
                datasets: [{{
                    label: 'Tools',
                    data: [{','.join(['1' for _ in tools])}],
                    backgroundColor: '#1976d2'
                }}]
            }},
            options: {{
                responsive: true,
                plugins: {{ legend: {{ display: false }} }}
            }}
        }});
    }});
    </script>
    """
    if soon_expiry:
        dashboard_html += f"""
        <div class="msg danger">
            <b>Expiring soon:</b>
            <ul>
            {''.join([f"<li>{lic['key']} (expires: {lic['expiry']})</li>" for lic in soon_expiry])}
            </ul>
        </div>
        """
    return render_template_string(BASE_TEMPLATE, content=dashboard_html)

# ========== LICENSE MANAGEMENT ==========
@app.route('/licenses', methods=['GET', 'POST'])
@admin_required
def license_admin():
    licenses = load_json(LICENSES_FILE)
    # Generate License
    if request.method == "POST" and "generate" in request.form:
        device_id = request.form['device_id']
        version = request.form['version']
        expiry = request.form['expiry']
        key = str(uuid.uuid4()).replace('-', '').upper()[:20]
        licenses.append({
            "key": key,
            "device_id": device_id,
            "version": version,
            "expiry": expiry,
            "active": True,
            "created": datetime.now().strftime("%Y-%m-%d"),
            "history": [{"event": "Created", "date": datetime.now().strftime("%Y-%m-%d")}]
        })
        save_json(LICENSES_FILE, licenses)
        flash(f'License {key} created', 'success')
        return redirect(url_for('license_admin'))
    # Search/filter
    q = request.args.get('q', '').lower()
    status_filter = request.args.get('status', '')
    filtered = licenses
    if q:
        filtered = [lic for lic in filtered if q in lic['device_id'].lower() or q in lic['key'].lower()]
    if status_filter:
        filtered = [lic for lic in filtered if status_of(lic).lower() == status_filter.lower()]
    # Pagination
    page = int(request.args.get('page', 1))
    per_page = 15
    total_pages = max(1, (len(filtered) + per_page - 1) // per_page)
    paginated = filtered[(page-1)*per_page: page*per_page]
    # HTML
    html = """
    <h2>License Management</h2>
    <form method="POST" style="margin-bottom:1.5em; background:#f3f9ff; border-radius:6px; padding:1em 1.5em;">
        <div class="form-row">
            <label>Device ID:</label><br>
            <input name="device_id" type="text" required>
        </div>
        <div class="form-row">
            <label>Version:</label><br>
            <input name="version" type="text" required>
        </div>
        <div class="form-row">
            <label>Expiry Date:</label><br>
            <input name="expiry" type="date" required>
        </div>
        <input type="submit" name="generate" value="Generate License">
    </form>
    <form method="GET" style="margin-bottom:1em;">
        <input name="q" placeholder="Search device or key" value="{q}">
        <select name="status">
            <option value="" {"selected" if not status_filter else ""}>All</option>
            <option value="Active" {"selected" if status_filter=='Active' else ""}>Active</option>
            <option value="Expired" {"selected" if status_filter=='Expired' else ""}>Expired</option>
            <option value="Disabled" {"selected" if status_filter=='Disabled' else ""}>Disabled</option>
        </select>
        <input type="submit" value="Search">
    </form>
    <table>
        <tr>
            <th>Key</th><th>Device ID</th><th>Version</th><th>Expiry</th><th>Status</th><th>Days</th><th>Action</th>
        </tr>
    """
    for lic in paginated:
        st = status_of(lic)
        html += f"""
        <tr class="{st.lower()}">
            <td>{lic['key']}</td>
            <td>{lic['device_id']}</td>
            <td>{lic['version']}</td>
            <td>{lic['expiry']}</td>
            <td>{st}</td>
            <td>{days_left(lic) if st=='Active' else 'Expired' if st=='Expired' else 'N/A'}</td>
            <td>
                {'<form method="POST" action="'+url_for('license_revoke', key=lic['key'])+'" style="display:inline"><button type="submit">Revoke</button></form>' if lic.get('active', True) else ''}
                <form method="POST" action="{url_for('license_extend', key=lic['key'])}" style="display:inline">
                    <input type="date" name="expiry" required>
                    <button type="submit">Extend</button>
                </form>
            </td>
        </tr>
        """
    html += "</table>"
    html += f"""
    <div class="pagination">
    {''.join([
        f'<span class="current">{p}</span>' if p == page else f'<a href="{url_for("license_admin")}?q={q}&status={status_filter}&page={p}">{p}</a>'
        for p in range(1, total_pages+1)
    ])}
    </div>
    """
    return render_template_string(BASE_TEMPLATE, content=html)

@app.route('/licenses/revoke/<key>', methods=['POST'])
@admin_required
def license_revoke(key):
    licenses = load_json(LICENSES_FILE)
    for lic in licenses:
        if lic['key'] == key:
            lic['active'] = False
            lic.setdefault('history',[]).append({"event":"Revoked","date":datetime.now().strftime("%Y-%m-%d")})
    save_json(LICENSES_FILE, licenses)
    flash('License revoked', 'info')
    return redirect(url_for('license_admin'))

@app.route('/licenses/extend/<key>', methods=['POST'])
@admin_required
def license_extend(key):
    new_expiry = request.form['expiry']
    licenses = load_json(LICENSES_FILE)
    for lic in licenses:
        if lic['key'] == key:
            lic['expiry'] = new_expiry
            lic.setdefault('history',[]).append({"event":f"Extended to {new_expiry}","date":datetime.now().strftime("%Y-%m-%d")})
    save_json(LICENSES_FILE, licenses)
    flash('License extended', 'success')
    return redirect(url_for('license_admin'))

# ========== LICENSE API ==========
@app.route('/api/license/generate', methods=['POST'])
def api_generate_license():
    data = request.get_json(force=True)
    device_id = data.get('device_id')
    version = data.get('version')
    expiry = data.get('expiry')
    if not (device_id and version and expiry):
        return jsonify({'error': 'Missing fields'}), 400
    licenses = load_json(LICENSES_FILE)
    key = str(uuid.uuid4()).replace('-', '').upper()[:20]
    licenses.append({
        "key": key,
        "device_id": device_id,
        "version": version,
        "expiry": expiry,
        "active": True,
        "created": datetime.now().strftime("%Y-%m-%d"),
        "history": [{"event": "Created", "date": datetime.now().strftime("%Y-%m-%d")}]
    })
    save_json(LICENSES_FILE, licenses)
    return jsonify({'key': key})

@app.route('/api/license/check', methods=['POST'])
def api_check_license():
    data = request.get_json(force=True)
    key = data.get('key')
    device_id = data.get('device_id')
    version = data.get('version')
    licenses = load_json(LICENSES_FILE)
    lic = next((l for l in licenses if l['key'] == key), None)
    if not lic:
        return jsonify({'status': 'not_found'}), 404
    if not lic.get('active', True):
        return jsonify({'status': 'revoked'}), 403
    if lic['device_id'] != device_id:
        return jsonify({'status': 'device_mismatch'}), 403
    if lic['version'] != version:
        return jsonify({'status': 'version_mismatch'}), 426
    expiry = datetime.strptime(lic['expiry'], "%Y-%m-%d")
    if expiry < datetime.now():
        return jsonify({'status': 'expired'}), 403
    days_left_val = (expiry - datetime.now()).days
    return jsonify({'status': 'valid', 'days_left': days_left_val, 'expiry': lic['expiry']})

@app.route('/api/license/revoke', methods=['POST'])
def api_revoke_license():
    data = request.get_json(force=True)
    key = data.get('key')
    licenses = load_json(LICENSES_FILE)
    for lic in licenses:
        if lic['key'] == key:
            lic['active'] = False
            lic.setdefault('history',[]).append({"event":"Revoked by API","date":datetime.now().strftime("%Y-%m-%d")})
    save_json(LICENSES_FILE, licenses)
    return jsonify({'status': 'revoked'})

@app.route('/api/license/extend', methods=['POST'])
def api_extend_license():
    data = request.get_json(force=True)
    key = data.get('key')
    new_expiry = data.get('expiry')
    licenses = load_json(LICENSES_FILE)
    for lic in licenses:
        if lic['key'] == key:
            lic['expiry'] = new_expiry
            lic.setdefault('history',[]).append({"event":f"Extended by API to {new_expiry}","date":datetime.now().strftime("%Y-%m-%d")})
    save_json(LICENSES_FILE, licenses)
    return jsonify({'status': 'extended'})

# ========== TOOL MANAGEMENT ==========
@app.route('/tools', methods=['GET', 'POST'])
@admin_required
def tools_admin():
    tools = load_json(TOOLS_FILE)
    msg = ""

    # Add tool
    if request.method == "POST":
        if "add_tool" in request.form:
            name = request.form["name"].strip()
            version = request.form["version"].strip()
            url = request.form["download_url"].strip()
            update_required = bool(request.form.get("update_required"))
            if any(t["name"].lower() == name.lower() for t in tools):
                flash("Tool already exists", "danger")
            else:
                tools.append({
                    "name": name,
                    "version": version,
                    "download_url": url,
                    "update_required": update_required
                })
                save_json(TOOLS_FILE, tools)
                flash("Tool added", "success")
            return redirect(url_for('tools_admin'))

        elif "edit_tool" in request.form:
            # Edit tool
            old_name = request.form["original_name"]
            for tool in tools:
                if tool["name"] == old_name:
                    tool["name"] = request.form["name"].strip()
                    tool["version"] = request.form["version"].strip()
                    tool["download_url"] = request.form["download_url"].strip()
                    tool["update_required"] = bool(request.form.get("update_required"))
                    flash("Tool updated", "success")
                    break
            save_json(TOOLS_FILE, tools)
            return redirect(url_for('tools_admin'))

        elif "delete_tool" in request.form:
            del_name = request.form["delete_tool"]
            tools = [t for t in tools if t["name"] != del_name]
            save_json(TOOLS_FILE, tools)
            flash("Tool deleted", "info")
            return redirect(url_for('tools_admin'))

    # Filter/search
    filter_val = request.args.get("filter", "").strip().lower()
    filtered_tools = tools
    if filter_val:
        filtered_tools = [t for t in tools if filter_val in t['name'].lower() or filter_val in t['version'].lower()]

    # Pagination
    page = int(request.args.get("page", 1))
    per_page = 10
    total_pages = max(1, (len(filtered_tools) + per_page - 1) // per_page)
    paginated_tools = filtered_tools[(page-1)*per_page : page*per_page]

    # HTML
    html = """
    <h2>Tool Management</h2>
    <form method="POST" style="margin-bottom:2em; background:#f3f9ff; border-radius:6px; padding:1em 1.5em;">
        <div class="form-row">
            <label>Tool Name:</label><br>
            <input name="name" type="text" required>
        </div>
        <div class="form-row">
            <label>Version:</label><br>
            <input name="version" type="text" required>
        </div>
        <div class="form-row">
            <label>Download URL:</label><br>
            <input name="download_url" type="text" required>
        </div>
        <label><input type="checkbox" name="update_required"> Update Required?</label>
        <br>
        <input type="submit" name="add_tool" value="Add Tool">
    </form>
    <form method="GET" style="margin-bottom:1em;">
        <input type="text" name="filter" value="{filter_val}" placeholder="Tool Name or Version">
        <input type="submit" value="Search">
    </form>
    <table>
        <tr>
            <th>Name</th><th>Version</th><th>Download URL</th><th>Update Required</th><th>Action</th>
        </tr>
    """
    for tool in paginated_tools:
        html += f"""
        <tr>
            <form method="POST" style="display:inline;">
                <input type="hidden" name="original_name" value="{tool['name']}">
                <td><input name="name" value="{tool['name']}" style="width:120px" required></td>
                <td><input name="version" value="{tool['version']}" style="width:90px" required></td>
                <td><input name="download_url" value="{tool['download_url']}" style="width:210px" required></td>
                <td style="text-align:center;">
                    <input type="checkbox" name="update_required" {"checked" if tool.get("update_required") else ""}>
                </td>
                <td>
                    <button type="submit" name="edit_tool" value="1">Save</button>
                    <button type="submit" name="delete_tool" value="{tool['name']}" onclick="return confirm('Delete this tool?')">Delete</button>
                </td>
            </form>
        </tr>
        """
    html += "</table>"
    html += f"""
    <div class="pagination">
    {''.join([
        f'<span class="current">{p}</span>' if p == page else f'<a href="{url_for("tools_admin")}?filter={filter_val}&page={p}">{p}</a>'
        for p in range(1, total_pages+1)
    ])}
    </div>
    """
    return render_template_string(BASE_TEMPLATE, content=html)

# ========== TOOL API ==========
@app.route('/api/tools', methods=['GET'])
def api_get_tools():
    tools = load_json(TOOLS_FILE)
    return jsonify({'tools': tools})

@app.route('/api/tool/<name>', methods=['GET'])
def api_get_tool_by_name(name):
    tools = load_json(TOOLS_FILE)
    for tool in tools:
        if tool['name'].lower() == name.lower():
            return jsonify(tool)
    return jsonify({'error': 'Tool not found'}), 404

# ========== API DOCS ==========
@app.route('/docs')
def docs():
    # Example data for API documentation
    docs_html = """
    <h2>API Documentation</h2>
    <ul>
        <li><b>POST /api/license/generate</b><br>
            <b>Request:</b>
            <pre>{
    "device_id": "device-123",
    "version": "1.0.0",
    "expiry": "2025-12-31"
}</pre>
            <b>Response:</b>
            <pre>{
    "key": "LICENSEKEY1234567890"
}</pre>
        </li>
        <li><b>POST /api/license/check</b><br>
            <b>Request:</b>
            <pre>{
    "key": "LICENSEKEY1234567890",
    "device_id": "device-123",
    "version": "1.0.0"
}</pre>
            <b>Response (valid):</b>
            <pre>{
    "status": "valid",
    "days_left": 90,
    "expiry": "2025-12-31"
}</pre>
            <b>Response (expired):</b>
            <pre>{
    "status": "expired"
}</pre>
            <b>Response (device mismatch):</b>
            <pre>{
    "status": "device_mismatch"
}</pre>
        </li>
        <li><b>POST /api/license/revoke</b><br>
            <b>Request:</b>
            <pre>{
    "key": "LICENSEKEY1234567890"
}</pre>
            <b>Response:</b>
            <pre>{
    "status": "revoked"
}</pre>
        </li>
        <li><b>POST /api/license/extend</b><br>
            <b>Request:</b>
            <pre>{
    "key": "LICENSEKEY1234567890",
    "expiry": "2026-12-31"
}</pre>
            <b>Response:</b>
            <pre>{
    "status": "extended"
}</pre>
        </li>
        <li><b>GET /api/tools</b><br>
            <b>Response:</b>
            <pre>{
    "tools": [
        {
            "name": "ToolA",
            "version": "1.0.0",
            "download_url": "https://example.com/ToolA.zip",
            "update_required": false
        }
    ]
}</pre>
        </li>
        <li><b>GET /api/tool/&lt;name&gt;</b><br>
            <i>Returns a single tool by name (case-insensitive)</i><br>
            <b>Example:</b> <code>/api/tool/ToolA</code><br>
            <b>Response:</b>
            <pre>{
    "name": "ToolA",
    "version": "1.0.0",
    "download_url": "https://example.com/ToolA.zip",
    "update_required": false
}</pre>
            <b>Not found:</b>
            <pre>{
    "error": "Tool not found"
}</pre>
        </li>
    </ul>
    <p>All APIs use JSON. Always set <code>Content-Type: application/json</code> in your requests.</p>
    """
    return render_template_string(BASE_TEMPLATE, content=docs_html)

# ========== MAIN ==========
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
