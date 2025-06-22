import os
import json
import uuid
import csv
import io
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, url_for, flash, send_file, jsonify

LICENSES_FILE = 'licenses.json'
TOOLS_FILE = 'tools.json'
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')

# ======= HTML Layout =======
layout = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>License & Tool Dashboard</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; background: #f7f7f7; margin: 0; }
        .container { padding: 2em; background: #fff; max-width: 1200px; margin: 2em auto; border-radius: 8px; }
        h1 { margin-bottom: 0.5em; }
        nav { background: #222; padding: 1em; border-radius: 6px; margin-bottom:2em;}
        nav a { color: #fff; margin-right: 1em; text-decoration: none; }
        form { margin-bottom: 2em; }
        label { font-weight: bold; }
        input, select { margin-bottom: 1em; padding: 0.4em; font-size: 1em; border-radius: 3px; border: 1px solid #bbb; }
        input[type="date"] { padding: 0.3em; }
        input[type="text"], input[type="date"] { width: 200px; }
        input[type="submit"], button { margin-top: 0.3em; margin-right: 0.5em; padding: 0.5em 1.4em; background: #1976d2; color: #fff; border: none; border-radius: 4px; font-size:1em; cursor: pointer; }
        input[type="submit"]:hover, button:hover { background: #155a99; }
        table { width: 100%; border-collapse: collapse; margin-top: 1.5em; }
        th, td { border: 1px solid #ccc; padding: 0.6em; text-align: center; }
        th { background: #eee; }
        .expired { background: #ffeaea; color: #a33; }
        .active { background: #eaffea; color: #295; }
        .disabled { background: #f5f5f5; color: #b1b1b1; }
        .search-box { margin-bottom: 1.5em; }
        .status-running { color: #008800; font-weight: bold; }
        .status-expired { color: #d80000; font-weight: bold; }
        .status-disabled { color: #888; font-weight: bold; }
        .big { font-size: 1.1em; }
        .msg { padding: 1em; margin-bottom: 1.2em; background: #eaf4ff; border-left: 5px solid #1976d2; border-radius: 4px;}
        .danger { background: #ffeaea; border-left: 5px solid #d80000;}
        .success { background: #eaffea; border-left: 5px solid #008800;}
        .form-row { margin-bottom: 0.7em; }
        .pagination { margin: 1.5em 0; text-align: center; }
        .pagination a, .pagination span { display: inline-block; padding: 0.3em 0.8em; margin: 0 0.2em; border-radius: 2px; background: #eee; color: #333; text-decoration: none; }
        .pagination .current { background: #1976d2; color: #fff; font-weight: bold; }
        .chart-container { max-width: 600px; margin: 2em auto 0 auto; }
    </style>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
</head>
<body>
    <nav>
        <a href="{{ url_for('dashboard') }}">Dashboard</a>
        <a href="{{ url_for('license_manager') }}">License Manager</a>
        <a href="{{ url_for('tool_manager') }}">Tool Manager</a>
    </nav>
    <div class="container">
        <h1>🛠 License & Tool Dashboard</h1>
        {% with messages = get_flashed_messages(with_categories=true) %}
            {% if messages %}
                {% for cat, msg in messages %}
                    <div class="msg {{cat}}">{{ msg|safe }}</div>
                {% endfor %}
            {% endif %}
        {% endwith %}
        {% block content %}{% endblock %}
    </div>
</body>
</html>
"""

# ======= Helper Functions =======
def load_json(file):
    if not os.path.exists(file):
        return []
    with open(file, 'r') as f:
        return json.load(f)

def save_json(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

def status_of(lic):
    today = datetime.now().date()
    expiry = datetime.strptime(lic['expiry'], "%Y-%m-%d").date()
    if not lic.get('enabled', True):
        return "Disabled"
    elif expiry < today:
        return "Expired"
    else:
        return "Active"

def days_left(lic):
    expiry = datetime.strptime(lic['expiry'], "%Y-%m-%d").date()
    today = datetime.now().date()
    return (expiry - today).days

def created_days_ago(lic):
    created = datetime.strptime(lic['created'], "%Y-%m-%d").date()
    today = datetime.now().date()
    return (today - created).days

def tool_download_count(tool):
    return tool.get("download_count", 0)

# ======= Dashboard =======
@app.route("/")
def dashboard():
    licenses = load_json(LICENSES_FILE)
    tools = load_json(TOOLS_FILE)
    # License stats
    total = len(licenses)
    active = sum(1 for l in licenses if status_of(l) == "Active")
    expired = sum(1 for l in licenses if status_of(l) == "Expired")
    disabled = sum(1 for l in licenses if status_of(l) == "Disabled")
    # Tool stats
    tool_total = len(tools)
    tool_downloads = sum(tool_download_count(t) for t in tools)
    dashboard_html = """
    <h2>Dashboard</h2>
    <div style="display:flex; gap:2em; flex-wrap:wrap; align-items:flex-end;">
    <div>
        <h3>License Stats</h3>
        <ul>
            <li>Total Licenses: <b>{{total}}</b></li>
            <li>Active: <b>{{active}}</b></li>
            <li>Expired: <b>{{expired}}</b></li>
            <li>Disabled: <b>{{disabled}}</b></li>
        </ul>
        <div class="chart-container">
            <canvas id="licenseChart"></canvas>
        </div>
    </div>
    <div>
        <h3>Tool Stats</h3>
        <ul>
            <li>Total Tools: <b>{{tool_total}}</b></li>
            <li>Total Downloads: <b>{{tool_downloads}}</b></li>
        </ul>
        <div class="chart-container">
            <canvas id="toolChart"></canvas>
        </div>
    </div>
    </div>
    <script>
    window.addEventListener('DOMContentLoaded', function() {
        var ctx = document.getElementById('licenseChart').getContext('2d');
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: ['Active', 'Expired', 'Disabled'],
                datasets: [{
                    data: [{{active}}, {{expired}}, {{disabled}}],
                    backgroundColor: ['#3ec96b', '#f35a5a', '#cccccc']
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { position: 'bottom' } }
            }
        });
        var toolCtx = document.getElementById('toolChart').getContext('2d');
        new Chart(toolCtx, {
            type: 'bar',
            data: {
                labels: [{% for t in tools %}'{{t.name}} v{{t.version}}',{% endfor %}],
                datasets: [{
                    label: 'Download Count',
                    data: [{% for t in tools %}{{t.download_count|default(0)}},{% endfor %}],
                    backgroundColor: '#1976d2'
                }]
            },
            options: {
                responsive: true,
                plugins: { legend: { display: false } }
            }
        });
    });
    </script>
    """
    return render_template_string(layout.replace('{% block content %}{% endblock %}', dashboard_html),
        total=total, active=active, expired=expired, disabled=disabled,
        tool_total=tool_total, tool_downloads=tool_downloads, tools=tools
    )

# ======= License Manager =======
@app.route("/licenses", methods=["GET", "POST"])
def license_manager():
    licenses = load_json(LICENSES_FILE)
    # License creation
    if request.method == "POST" and "generate" in request.form:
        device = request.form.get("device_id", "").strip()
        expiry = request.form.get("expiry", "").strip()
        if not device or not expiry:
            flash("Device ID and Expiry Date required.", "danger")
        else:
            new_license = {
                "key": str(uuid.uuid4()).replace("-", "").upper()[:20],
                "device_id": device,
                "created": datetime.now().strftime("%Y-%m-%d"),
                "expiry": expiry,
                "enabled": True,
                "history": [
                    {"event": "Created", "date": datetime.now().strftime("%Y-%m-%d")}
                ]
            }
            licenses.append(new_license)
            save_json(LICENSES_FILE, licenses)
            flash(f"License <b>{new_license['key']}</b> created!", "success")
            return redirect(url_for("license_manager"))

    # License search (by code)
    search_status = None
    searched_license = None
    if request.method == "POST" and "search" in request.form:
        code = request.form.get("search_code", "").strip()
        for lic in licenses:
            if lic['key'] == code:
                searched_license = lic
                search_status = status_of(lic)
                break
        if not searched_license:
            flash("License code not found.", "danger")

    # Table search/filter (by device ID/partial code/status)
    filter_val = request.args.get("filter", "").strip().lower()
    status_filter = request.args.get("status", "")
    filtered_licenses = licenses
    if filter_val:
        filtered_licenses = [l for l in filtered_licenses if filter_val in l['device_id'].lower() or filter_val in l['key'].lower()]
    if status_filter:
        filtered_licenses = [l for l in filtered_licenses if status_of(l).lower() == status_filter.lower()]

    # Pagination
    page = int(request.args.get("page", 1))
    per_page = 15
    total_pages = max(1, (len(filtered_licenses) + per_page - 1) // per_page)
    paginated_licenses = filtered_licenses[(page-1)*per_page: page*per_page]

    # Sort: active first, then expired, then disabled
    def sort_key(l):
        st = status_of(l)
        return (0 if st=="Active" else 1 if st=="Expired" else 2, -days_left(l))
    paginated_licenses.sort(key=sort_key)

    license_html = """
    <h2>License Manager</h2>
    <form method="POST" enctype="multipart/form-data" style="margin-bottom:2em; background:#f3f9ff; border-radius:6px; padding:1em 1.5em;">
        <div class="form-row">
            <label>Device ID:</label><br>
            <input name="device_id" type="text" required>
        </div>
        <div class="form-row">
            <label>Expiry Date:</label><br>
            <input name="expiry" type="date" required>
        </div>
        <input type="submit" name="generate" value="Create License">
    </form>
    <div style="margin-bottom:1em;">
    <form method="POST" class="search-box" style="display:inline-block;">
        <label>Search License Code:</label>
        <input name="search_code" type="text" placeholder="Enter License Key" style="width: 250px;">
        <input type="submit" name="search" value="Check Status">
    </form>
    <form method="GET" style="display:inline-block; margin-left:2em;">
        <label>🔍 Filter:</label>
        <input type="text" name="filter" value="{{request.args.get('filter','')}}" placeholder="Device ID or Key">
        <select name="status">
            <option value="" {% if not request.args.get('status') %}selected{% endif %}>All</option>
            <option value="Active" {% if request.args.get('status')=='Active' %}selected{% endif %}>Active</option>
            <option value="Expired" {% if request.args.get('status')=='Expired' %}selected{% endif %}>Expired</option>
            <option value="Disabled" {% if request.args.get('status')=='Disabled' %}selected{% endif %}>Disabled</option>
        </select>
        <input type="submit" value="Apply">
        <a href="{{ url_for('license_manager') }}"><button type="button">Reset</button></a>
    </form>
    </div>
    <div style="margin-bottom:1.5em;">
        <form method="POST" action="{{ url_for('import_csv') }}" enctype="multipart/form-data" style="display:inline-block;">
            <label>Import CSV: </label>
            <input type="file" name="csvfile" accept=".csv" required>
            <input type="submit" value="Import">
        </form>
        <a href="{{ url_for('export_csv') }}"><button>Export CSV</button></a>
        <a href="{{ url_for('backup') }}"><button>Backup (JSON)</button></a>
        <form method="POST" action="{{ url_for('restore') }}" enctype="multipart/form-data" style="display:inline-block;">
            <label>Restore: </label>
            <input type="file" name="backupfile" accept=".json" required>
            <input type="submit" value="Restore">
        </form>
    </div>
    {% if searched_license %}
        <div class="msg big {% if search_status == 'Active' %}success{% elif search_status == 'Expired' %}danger{% else %}disabled{% endif %}">
        License: <b>{{searched_license.key}}</b> | Device: <b>{{searched_license.device_id}}</b> <br>
        Status: 
        {% if search_status == "Active" %}
            <span class="status-running">Running ({{ days_left(searched_license) }} days left)</span>
        {% elif search_status == "Expired" %}
            <span class="status-expired">Expired ({{ -days_left(searched_license) }} days ago)</span>
        {% else %}
            <span class="status-disabled">Disabled</span>
        {% endif %}
        <br>
        Subscription: <b>{{ searched_license.created }}</b> | Expires: <b>{{ searched_license.expiry }}</b>
        </div>
    {% endif %}
    <table>
        <tr>
            <th><input type="checkbox" id="selectall" onclick="toggleAll(this)"></th>
            <th>License Key</th>
            <th>Device ID</th>
            <th>Subscribed</th>
            <th>Expiry</th>
            <th>Status</th>
            <th>Days Left</th>
            <th>Action</th>
        </tr>
        <form method="POST" action="{{ url_for('bulk_action') }}">
        {% for lic in paginated_licenses %}
        <tr class="{% if status_of(lic)=='Active' %}active{% elif status_of(lic)=='Expired' %}expired{% else %}disabled{% endif %}">
            <td><input type="checkbox" name="selected" value="{{lic.key}}"></td>
            <td class="big">{{ lic.key }}</td>
            <td>{{ lic.device_id }}</td>
            <td>{{ lic.created }}<br>({{ created_days_ago(lic) }} days ago)</td>
            <td>
                {{ lic.expiry }}
                <form method="POST" action="{{ url_for('renew_license', key=lic.key) }}" style="margin-top: 0.2em;">
                    <input type="date" name="new_expiry" required>
                    <input type="submit" value="Renew">
                </form>
            </td>
            <td>
                {% if status_of(lic) == "Active" %}
                    <span class="status-running">Running</span>
                {% elif status_of(lic) == "Expired" %}
                    <span class="status-expired">Expired</span>
                {% else %}
                    <span class="status-disabled">Disabled</span>
                {% endif %}
            </td>
            <td>
                {% if status_of(lic) == "Active" %}
                    {{ days_left(lic) }} days
                {% elif status_of(lic) == "Expired" %}
                    Expired {{ -days_left(lic) }} days ago
                {% else %}
                    N/A
                {% endif %}
            </td>
            <td>
                <form method="POST" action="{{ url_for('toggle_license', key=lic.key) }}" style="display:inline">
                    {% if lic.get('enabled', True) %}
                        <button name="disable" value="1" onclick="return confirm('Disable this license?')">Disable</button>
                    {% else %}
                        <button name="enable" value="1" onclick="return confirm('Enable this license?')">Enable</button>
                    {% endif %}
                </form>
                <form method="POST" action="{{ url_for('delete_license', key=lic.key) }}" style="display:inline">
                    <button name="delete" value="1" onclick="return confirm('Delete this license?')">Delete</button>
                </form>
                <button onclick="showHistory('{{lic.key}}')" type="button">History</button>
            </td>
        </tr>
        {% endfor %}
        <tr>
            <td colspan="8" align="right">
                <select name="bulk_action" required>
                    <option value="">Bulk Action</option>
                    <option value="disable">Disable Selected</option>
                    <option value="enable">Enable Selected</option>
                    <option value="delete">Delete Selected</option>
                </select>
                <input type="submit" value="Apply">
            </td>
        </tr>
        </form>
    </table>
    <div class="pagination">
        {% for p in range(1, total_pages+1) %}
            {% if p == page %}
                <span class="current">{{ p }}</span>
            {% else %}
                <a href="{{ url_for('license_manager', filter=request.args.get('filter',''), status=request.args.get('status',''), page=p) }}">{{ p }}</a>
            {% endif %}
        {% endfor %}
    </div>
    <div id="historyModal" style="display:none; position:fixed; left:0; top:0; width:100vw; height:100vh; background:rgba(0,0,0,.5); z-index:1000;">
        <div style="background:#fff; margin:10vh auto; padding:2em; max-width:500px; border-radius:10px; position:relative;">
            <button onclick="document.getElementById('historyModal').style.display='none'" style="position:absolute; right:1em; top:1em;">Close</button>
            <h3>License History</h3>
            <div id="historyContent"></div>
        </div>
    </div>
    <script>
    function toggleAll(box) {
        let boxes = document.querySelectorAll('input[name="selected"]');
        boxes.forEach(b => b.checked = box.checked);
    }
    function showHistory(key) {
        fetch('/license/history/' + key)
        .then(r=>r.json()).then(data=>{
            let c = document.getElementById('historyContent');
            c.innerHTML = '';
            if(data.length > 0) {
                c.innerHTML = '<ul>' + data.map(e=>`<li>${e.date}: ${e.event}</li>`).join('') + '</ul>';
            } else {
                c.innerHTML = 'No history found.';
            }
            document.getElementById('historyModal').style.display='block';
        });
    }
    </script>
    """
    return render_template_string(layout.replace('{% block content %}{% endblock %}', license_html),
        request=request,
        searched_license=searched_license,
        search_status=search_status,
        paginated_licenses=paginated_licenses,
        status_of=status_of,
        days_left=days_left,
        created_days_ago=created_days_ago,
        page=page,
        total_pages=total_pages
    )

# ======= License API: History =======
@app.route("/license/history/<key>")
def license_history(key):
    licenses = load_json(LICENSES_FILE)
    lic = next((l for l in licenses if l['key'] == key), None)
    if not lic:
        return jsonify([])
    return jsonify(lic.get("history", []))

# ======= License Enable/Disable =======
@app.route("/license/toggle/<key>", methods=["POST"])
def toggle_license(key):
    licenses = load_json(LICENSES_FILE)
    for lic in licenses:
        if lic['key'] == key:
            lic['enabled'] = not lic.get('enabled', True)
            lic.setdefault("history", []).append({
                "event": "Enabled" if lic['enabled'] else "Disabled",
                "date": datetime.now().strftime("%Y-%m-%d")
            })
            save_json(LICENSES_FILE, licenses)
            flash(f"License <b>{lic['key']}</b> {'Enabled' if lic['enabled'] else 'Disabled'}.", "success")
            break
    return redirect(url_for("license_manager"))

# ======= License Delete =======
@app.route("/license/delete/<key>", methods=["POST"])
def delete_license(key):
    licenses = load_json(LICENSES_FILE)
    licenses = [lic for lic in licenses if lic['key'] != key]
    save_json(LICENSES_FILE, licenses)
    flash("License deleted.", "danger")
    return redirect(url_for("license_manager"))

# ======= License Renew =======
@app.route("/license/renew/<key>", methods=["POST"])
def renew_license(key):
    licenses = load_json(LICENSES_FILE)
    new_expiry = request.form.get("new_expiry")
    for lic in licenses:
        if lic['key'] == key:
            lic['expiry'] = new_expiry
            lic.setdefault("history", []).append({
                "event": f"Renewed to {new_expiry}",
                "date": datetime.now().strftime("%Y-%m-%d")
            })
            save_json(LICENSES_FILE, licenses)
            flash(f"License <b>{lic['key']}</b> renewed!", "success")
            break
    return redirect(url_for("license_manager"))

# ======= Bulk Action =======
@app.route("/licenses/bulk", methods=["POST"])
def bulk_action():
    action = request.form.get("bulk_action")
    selected = request.form.getlist("selected")
    licenses = load_json(LICENSES_FILE)
    changed = 0
    for lic in licenses:
        if lic['key'] in selected:
            if action == "disable" and lic.get("enabled", True):
                lic['enabled'] = False
                lic.setdefault("history", []).append({"event": "Bulk Disabled", "date": datetime.now().strftime("%Y-%m-%d")})
                changed += 1
            elif action == "enable" and not lic.get("enabled", True):
                lic['enabled'] = True
                lic.setdefault("history", []).append({"event": "Bulk Enabled", "date": datetime.now().strftime("%Y-%m-%d")})
                changed += 1
            elif action == "delete":
                lic['__delete__'] = True
                changed += 1
    if action == "delete":
        licenses = [l for l in licenses if not l.get("__delete__")]
    save_json(LICENSES_FILE, licenses)
    flash(f"Bulk action '{action}' applied to {changed} licenses.", "success")
    return redirect(url_for("license_manager"))

# ======= Export/Import/Backup/Restore =======
@app.route("/export")
def export_csv():
    licenses = load_json(LICENSES_FILE)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["License Key", "Device ID", "Created", "Expiry", "Enabled"])
    for lic in licenses:
        writer.writerow([
            lic['key'],
            lic['device_id'],
            lic['created'],
            lic['expiry'],
            str(lic.get('enabled', True))
        ])
    output.seek(0)
    return send_file(
        io.BytesIO(output.read().encode()),
        mimetype='text/csv',
        as_attachment=True,
        download_name='licenses_export.csv'
    )

@app.route("/import", methods=["POST"])
def import_csv():
    file = request.files.get('csvfile')
    if not file:
        flash("No file uploaded.", "danger")
        return redirect(url_for("license_manager"))
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        reader = csv.DictReader(stream)
        licenses = load_json(LICENSES_FILE)
        for row in reader:
            key = row.get("License Key") or row.get('key')
            if not key:
                continue
            if any(l['key'] == key for l in licenses):
                continue
            licenses.append({
                'key': key,
                'device_id': row.get("Device ID") or "",
                'created': row.get("Created") or datetime.now().strftime("%Y-%m-%d"),
                'expiry': row.get("Expiry") or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                'enabled': row.get("Enabled", "True") == "True",
                'history': [{"event":"Imported","date":datetime.now().strftime("%Y-%m-%d")}]
            })
        save_json(LICENSES_FILE, licenses)
        flash("Licenses imported successfully!", "success")
    except Exception as e:
        flash(f"Import failed: {e}", "danger")
    return redirect(url_for("license_manager"))

@app.route("/backup")
def backup():
    if not os.path.exists(LICENSES_FILE):
        flash("No data to backup.", "danger")
        return redirect(url_for("license_manager"))
    return send_file(LICENSES_FILE, as_attachment=True)

@app.route("/restore", methods=["POST"])
def restore():
    file = request.files.get('backupfile')
    if not file:
        flash("No backup file uploaded.", "danger")
        return redirect(url_for("license_manager"))
    try:
        data = json.load(file)
        if isinstance(data, list):
            save_json(LICENSES_FILE, data)
            flash("Backup restored successfully!", "success")
        else:
            flash("Invalid backup file format.", "danger")
    except Exception as e:
        flash(f"Restore failed: {e}", "danger")
    return redirect(url_for("license_manager"))

# ======= Tool Manager =======
@app.route("/tools", methods=["GET", "POST"])
def tool_manager():
    tools = load_json(TOOLS_FILE)
    # Tool creation
    if request.method == "POST" and "add_tool" in request.form:
        tool_name = request.form.get("tool_name", "").strip()
        version = request.form.get("version", "").strip()
        download_url = request.form.get("download_url", "").strip()
        if not tool_name or not version or not download_url:
            flash("All fields are required.", "danger")
        else:
            tools.append({
                "name": tool_name,
                "version": version,
                "download_url": download_url,
                "download_count": 0
            })
            save_json(TOOLS_FILE, tools)
            flash(f"Tool <b>{tool_name} v{version}</b> added!", "success")
            return redirect(url_for("tool_manager"))

    # Search/filter/pagination
    filter_val = request.args.get("filter", "").strip().lower()
    filtered_tools = tools
    if filter_val:
        filtered_tools = [t for t in filtered_tools if filter_val in t['name'].lower() or filter_val in t['version'].lower()]
    page = int(request.args.get("page", 1))
    per_page = 10
    total_pages = max(1, (len(filtered_tools) + per_page - 1) // per_page)
    paginated_tools = filtered_tools[(page-1)*per_page : page*per_page]

    tool_html = """
    <h2>Tool Manager</h2>
    <form method="POST" style="margin-bottom:2em; background:#f3f9ff; border-radius:6px; padding:1em 1.5em;">
        <div class="form-row">
            <label>Tool Name:</label><br>
            <input name="tool_name" type="text" required>
        </div>
        <div class="form-row">
            <label>Version:</label><br>
            <input name="version" type="text" required>
        </div>
        <div class="form-row">
            <label>Download URL:</label><br>
            <input name="download_url" type="text" required>
        </div>
        <input type="submit" name="add_tool" value="Add Tool">
    </form>
    <form method="GET" style="margin-bottom:1em;">
        <label>🔍 Filter:</label>
        <input type="text" name="filter" value="{{request.args.get('filter','')}}" placeholder="Tool Name or Version">
        <input type="submit" value="Apply">
        <a href="{{ url_for('tool_manager') }}"><button type="button">Reset</button></a>
    </form>
    <table>
        <tr>
            <th>Name</th>
            <th>Version</th>
            <th>Download URL</th>
            <th>Download Count</th>
            <th>Action</th>
        </tr>
        {% for tool in paginated_tools %}
        <tr>
            <td>{{tool.name}}</td>
            <td>{{tool.version}}</td>
            <td><a href="{{ url_for('download_tool', name=tool.name, version=tool.version) }}" target="_blank">Download</a></td>
            <td>{{tool.download_count}}</td>
            <td>
                <form method="POST" action="{{ url_for('delete_tool', name=tool.name, version=tool.version) }}" style="display:inline">
                    <button onclick="return confirm('Delete this tool?')">Delete</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
    <div class="pagination">
        {% for p in range(1, total_pages+1) %}
            {% if p == page %}
                <span class="current">{{ p }}</span>
            {% else %}
                <a href="{{ url_for('tool_manager', filter=request.args.get('filter',''), page=p) }}">{{ p }}</a>
            {% endif %}
        {% endfor %}
    </div>
    """
    return render_template_string(layout.replace('{% block content %}{% endblock %}', tool_html),
        request=request,
        paginated_tools=paginated_tools,
        page=page,
        total_pages=total_pages
    )

@app.route('/tools/download/<name>/<version>')
def download_tool(name, version):
    tools = load_json(TOOLS_FILE)
    for tool in tools:
        if tool['name'] == name and tool['version'] == version:
            tool['download_count'] = tool.get('download_count', 0) + 1
            save_json(TOOLS_FILE, tools)
            return redirect(tool['download_url'])
    flash("Tool not found.", "danger")
    return redirect(url_for("tool_manager"))

@app.route("/tools/delete/<name>/<version>", methods=["POST"])
def delete_tool(name, version):
    tools = load_json(TOOLS_FILE)
    tools = [t for t in tools if not (t['name'] == name and t['version'] == version)]
    save_json(TOOLS_FILE, tools)
    flash("Tool deleted.", "danger")
    return redirect(url_for("tool_manager"))

# ======= Run =======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
