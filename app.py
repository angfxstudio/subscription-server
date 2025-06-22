import os
import json
import uuid
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, session, redirect, url_for, flash, jsonify, render_template_string
from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, SubmitField, DateField, BooleanField
from wtforms.validators import DataRequired
from werkzeug.security import check_password_hash, generate_password_hash
import bcrypt

# ====== Config ======
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-this-secret')
ADMIN_USERNAME = os.environ.get('ADMIN_USERNAME', 'admin')
ADMIN_PASSWORD_HASH = os.environ.get('ADMIN_PASSWORD_HASH', generate_password_hash('admin'))
LICENSES_FILE = 'licenses.json'
TOOLS_FILE = 'tools.json'

app = Flask(__name__)
app.config['SECRET_KEY'] = SECRET_KEY
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = True

# ====== Forms ======
class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class LicenseForm(FlaskForm):
    device_id = StringField('Device ID', validators=[DataRequired()])
    version = StringField('Tool Version', validators=[DataRequired()])
    expiry_date = DateField('Expiry Date', validators=[DataRequired()])
    submit = SubmitField('Generate')

class ToolForm(FlaskForm):
    name = StringField('Tool Name', validators=[DataRequired()])
    version = StringField('Version', validators=[DataRequired()])
    download_url = StringField('Download URL', validators=[DataRequired()])
    update_required = BooleanField('Update Required')
    submit = SubmitField('Add Tool')

# ====== Helpers ======
def load_json(file):
    if not os.path.exists(file):
        return []
    with open(file, 'r') as f:
        return json.load(f)

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def check_password(plain, hashed):
    # Support both werkzeug and bcrypt hashes
    if hashed.startswith("$2b$") or hashed.startswith("$2a$"):
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    else:
        return check_password_hash(hashed, plain)

# ====== Templates ======
layout = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>{{ title or "Admin Dashboard" }}</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; background: #f7f7f7; margin: 0; }
        nav { background: #222; padding: 1em; }
        nav a { color: #fff; margin-right: 1em; text-decoration: none; }
        .container { padding: 2em; background: #fff; max-width: 900px; margin: 2em auto; border-radius: 6px; }
        table { width: 100%; border-collapse: collapse; margin-top: 1em; }
        th, td { border: 1px solid #ccc; padding: 0.5em; }
        th { background: #eee; }
        .alert { padding: 1em; background: #fffae6; border-left: 5px solid orange; margin: 1em 0; }
        .flashes { list-style: none; padding: 0; }
        .flashes li { padding: 0.5em; margin-bottom: 0.5em; border-radius: 3px; }
        .flashes li.danger { background: #ffeaea; color: #a33; }
        .flashes li.info { background: #eaf4ff; color: #235; }
        .flashes li.success { background: #eaffea; color: #295; }
        button { border: none; background: #1976d2; color: #fff; padding: 0.4em 1em; border-radius: 4px; cursor: pointer; }
        button:hover { background: #125a9c; }
        input[type="text"], input[type="date"] { padding: 0.3em; width: 90%; border: 1px solid #bbb; border-radius: 3px; }
    </style>
</head>
<body>
    <nav>
        {% if session.get('admin_logged_in') %}
            <a href="{{ url_for('dashboard') }}">Dashboard</a>
            <a href="{{ url_for('licenses') }}">Licenses</a>
            <a href="{{ url_for('tools') }}">Tools</a>
            <a href="{{ url_for('logout') }}">Logout</a>
        {% else %}
            <a href="{{ url_for('login') }}">Login</a>
        {% endif %}
    </nav>
    <div class="container">
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                <ul class="flashes">
                {% for category, message in messages %}
                    <li class="{{ category }}">{{ message }}</li>
                {% endfor %}
                </ul>
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

login_tpl = """
<h2>Admin Login</h2>
<form method="POST">
    {{ form.hidden_tag() }}
    <div>
        {{ form.username.label }}<br>
        {{ form.username(size=32) }}
    </div>
    <div>
        {{ form.password.label }}<br>
        {{ form.password(size=32) }}
    </div>
    <div>
        {{ form.submit() }}
    </div>
</form>
"""

dashboard_tpl = """
<h2>Dashboard</h2>
<ul>
    <li><a href="{{ url_for('licenses') }}">Manage Licenses</a></li>
    <li><a href="{{ url_for('tools') }}">Manage Tools</a></li>
</ul>
<h3>License Stats</h3>
<ul>
    <li>Total Licenses: {{ license_count }}</li>
    <li>Active: {{ active_count }}, Expired: {{ expired_count }}</li>
    <li>Tools: {{ tool_count }}</li>
</ul>
"""

licenses_tpl = """
<h2>Licenses</h2>
<a href="{{ url_for('generate_license') }}"><button>Generate New License</button></a>
{% if soon_expiry %}
    <div class="alert">
        <strong>Expiring Soon:</strong>
        <ul>
        {% for lic in soon_expiry %}
            <li>{{ lic.key }} (expires: {{ lic.expiry_date }})</li>
        {% endfor %}
        </ul>
    </div>
{% endif %}
<table>
    <tr>
        <th>Key</th><th>Device ID</th><th>Version</th><th>Expiry</th><th>Active</th><th>Actions</th>
    </tr>
    {% for lic in licenses %}
    <tr>
        <td>{{ lic.key }}</td>
        <td>{{ lic.device_id }}</td>
        <td>{{ lic.version }}</td>
        <td>{{ lic.expiry_date }}</td>
        <td>{{ 'Yes' if lic.active else 'No' }}</td>
        <td>
            {% if lic.active %}
            <form method="POST" action="{{ url_for('revoke_license', license_key=lic.key) }}" style="display:inline">
                <button type="submit">Revoke</button>
            </form>
            {% endif %}
        </td>
    </tr>
    {% endfor %}
</table>
"""

license_generate_tpl = """
<h2>Generate New License</h2>
<form method="POST">
    {{ form.hidden_tag() }}
    <div>
        {{ form.device_id.label }}<br>
        {{ form.device_id(size=40) }}
    </div>
    <div>
        {{ form.version.label }}<br>
        {{ form.version(size=20) }}
    </div>
    <div>
        {{ form.expiry_date.label }}<br>
        {{ form.expiry_date() }}
    </div>
    <div>
        {{ form.submit() }}
    </div>
</form>
"""

tools_tpl = """
<h2>Tools</h2>
<form method="POST">
    {{ form.hidden_tag() }}
    <div>
        {{ form.name.label }}<br>
        {{ form.name(size=30) }}
    </div>
    <div>
        {{ form.version.label }}<br>
        {{ form.version(size=15) }}
    </div>
    <div>
        {{ form.download_url.label }}<br>
        {{ form.download_url(size=60) }}
    </div>
    <div>
        {{ form.update_required.label }} {{ form.update_required() }}
    </div>
    <div>
        {{ form.submit() }}
    </div>
</form>
<h3>Existing Tools</h3>
<table>
    <tr>
        <th>Name</th><th>Version</th><th>URL</th><th>Update Required</th><th>Actions</th>
    </tr>
    {% for tool in tools %}
    <tr>
        <td>{{ tool.name }}</td>
        <td>{{ tool.version }}</td>
        <td><a href="{{ tool.download_url }}" target="_blank">Download</a></td>
        <td>{{ 'Yes' if tool.update_required else 'No' }}</td>
        <td>
            <form method="POST" action="{{ url_for('update_tool', tool_name=tool.name) }}" style="display:inline">
                <input type="text" name="version" value="{{ tool.version }}">
                <input type="text" name="download_url" value="{{ tool.download_url }}">
                <input type="checkbox" name="update_required" {% if tool.update_required %}checked{% endif %}>
                <button type="submit">Update</button>
            </form>
            <form method="POST" action="{{ url_for('delete_tool', tool_name=tool.name) }}" style="display:inline">
                <button type="submit">Delete</button>
            </form>
        </td>
    </tr>
    {% endfor %}
</table>
"""

# ====== Template rendering helper ======
def render_with_layout(content_tpl, **context):
    full_template = layout.replace('{% block content %}{% endblock %}', content_tpl)
    return render_template_string(full_template, **context)

# ====== Routes ======
@app.route('/')
def index():
    if session.get('admin_logged_in'):
        return redirect(url_for('dashboard'))
    else:
        return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        if (form.username.data == ADMIN_USERNAME and check_password(form.password.data, ADMIN_PASSWORD_HASH)):
            session['admin_logged_in'] = True
            flash('Logged in!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid username or password', 'danger')
    return render_with_layout(login_tpl, form=form)

@app.route('/logout')
def logout():
    session.clear()
    flash('Logged out', 'info')
    return redirect(url_for('login'))

@app.route('/dashboard')
@admin_required
def dashboard():
    licenses = load_json(LICENSES_FILE)
    tools = load_json(TOOLS_FILE)
    now = datetime.now()
    expired_count = sum(1 for l in licenses if datetime.strptime(l['expiry_date'], '%Y-%m-%d') < now)
    active_count = sum(1 for l in licenses if l['active'] and datetime.strptime(l['expiry_date'], '%Y-%m-%d') >= now)
    return render_with_layout(dashboard_tpl,
        license_count=len(licenses),
        active_count=active_count,
        expired_count=expired_count,
        tool_count=len(tools)
    )

@app.route('/licenses')
@admin_required
def licenses():
    licenses = load_json(LICENSES_FILE)
    soon_expiry = [l for l in licenses if l['active'] and datetime.strptime(l['expiry_date'], '%Y-%m-%d') <= datetime.now() + timedelta(days=7)]
    return render_with_layout(licenses_tpl, licenses=licenses, soon_expiry=soon_expiry)

@app.route('/licenses/generate', methods=['GET', 'POST'])
@admin_required
def generate_license():
    form = LicenseForm()
    if form.validate_on_submit():
        licenses = load_json(LICENSES_FILE)
        new_license = {
            "key": str(uuid.uuid4()),
            "device_id": form.device_id.data,
            "version": form.version.data,
            "expiry_date": form.expiry_date.data.strftime('%Y-%m-%d'),
            "active": True,
        }
        licenses.append(new_license)
        save_json(LICENSES_FILE, licenses)
        flash('License generated!', 'success')
        return redirect(url_for('licenses'))
    return render_with_layout(license_generate_tpl, form=form)

@app.route('/licenses/revoke/<license_key>', methods=['POST'])
@admin_required
def revoke_license(license_key):
    licenses = load_json(LICENSES_FILE)
    for lic in licenses:
        if lic['key'] == license_key:
            lic['active'] = False
            break
    save_json(LICENSES_FILE, licenses)
    flash('License revoked', 'info')
    return redirect(url_for('licenses'))

@app.route('/tools', methods=['GET', 'POST'])
@admin_required
def tools():
    form = ToolForm()
    tools = load_json(TOOLS_FILE)
    if form.validate_on_submit():
        new_tool = {
            "name": form.name.data,
            "version": form.version.data,
            "download_url": form.download_url.data,
            "update_required": bool(form.update_required.data),
        }
        tools.append(new_tool)
        save_json(TOOLS_FILE, tools)
        flash('Tool added!', 'success')
        return redirect(url_for('tools'))
    return render_with_layout(tools_tpl, form=form, tools=tools)

@app.route('/tools/update/<tool_name>', methods=['POST'])
@admin_required
def update_tool(tool_name):
    tools = load_json(TOOLS_FILE)
    updated = False
    for tool in tools:
        if tool['name'] == tool_name:
            tool['version'] = request.form.get('version', tool['version'])
            tool['download_url'] = request.form.get('download_url', tool['download_url'])
            tool['update_required'] = True if request.form.get('update_required') == 'on' else False
            updated = True
            break
    if updated:
        save_json(TOOLS_FILE, tools)
        flash('Tool updated!', 'success')
    else:
        flash('Tool not found.', 'danger')
    return redirect(url_for('tools'))

@app.route('/tools/delete/<tool_name>', methods=['POST'])
@admin_required
def delete_tool(tool_name):
    tools = load_json(TOOLS_FILE)
    tools = [tool for tool in tools if tool['name'] != tool_name]
    save_json(TOOLS_FILE, tools)
    flash('Tool deleted!', 'info')
    return redirect(url_for('tools'))

# ====== API Endpoints ======
@app.route('/api/license/check', methods=['POST'])
def api_license_check():
    data = request.json
    if not data or 'key' not in data or 'device_id' not in data or 'version' not in data:
        return jsonify({"status": "error", "message": "Invalid request"}), 400
    licenses = load_json(LICENSES_FILE)
    lic = next((l for l in licenses if l['key'] == data['key']), None)
    if not lic:
        return jsonify({"status": "invalid", "message": "License key not found"}), 404
    if not lic['active']:
        return jsonify({"status": "revoked", "message": "License revoked"}), 403
    if lic['device_id'] != data['device_id']:
        return jsonify({"status": "invalid", "message": "Device mismatch"}), 403
    if lic['version'] != data['version']:
        return jsonify({"status": "upgrade_required", "message": "Version mismatch"}), 426
    if datetime.strptime(lic['expiry_date'], '%Y-%m-%d') < datetime.now():
        return jsonify({"status": "expired", "message": "License expired"}), 403
    days_left = (datetime.strptime(lic['expiry_date'], '%Y-%m-%d') - datetime.now()).days
    return jsonify({
        "status": "valid",
        "days_left": days_left,
        "expiry_date": lic['expiry_date']
    })

@app.route('/api/tools', methods=['GET'])
def api_tools():
    tools = load_json(TOOLS_FILE)
    return jsonify({"tools": tools})

# ====== For docs/static/demo ======
@app.route('/docs')
def docs():
    return '''<h2>API Endpoints</h2>
    <ul>
    <li>POST /api/license/check: {key, device_id, version}</li>
    <li>GET /api/tools</li>
    </ul>'''

# ====== Main ======
if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
