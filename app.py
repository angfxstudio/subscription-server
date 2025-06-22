import os
import json
import uuid
from datetime import datetime, timedelta
from flask import Flask, request, render_template_string, redirect, url_for, flash, send_file
from werkzeug.utils import secure_filename
import csv
import io

LICENSES_FILE = 'licenses.json'
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'admin123')

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'your-secret-key')

# ======= HTML Layout =======
layout = """
<!DOCTYPE html>
<html lang="en">
<head>
    <title>License Manager Dashboard</title>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; background: #f7f7f7; margin: 0; }
        .container { padding: 2em; background: #fff; max-width: 1100px; margin: 2em auto; border-radius: 8px; }
        h1 { margin-bottom: 0.5em; }
        form { margin-bottom: 2em; }
        label { font-weight: bold; }
        input, select { margin-bottom: 1em; padding: 0.4em; font-size: 1em; border-radius: 3px; border: 1px solid #bbb; }
        input[type="date"] { padding: 0.3em; }
        input[type="text"], input[type="date"] { width: 240px; }
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
        .big { font-size: 1.2em; }
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
    <div class="container">
        <h1>🔑 License Manager</h1>
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
def load_licenses():
    if not os.path.exists(LICENSES_FILE):
        return []
    with open(LICENSES_FILE, 'r') as f:
        return json.load(f)

def save_licenses(data):
    with open(LICENSES_FILE, 'w') as f:
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

# ======= CSV Export =======
@app.route("/export")
def export_csv():
    licenses = load_licenses()
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

# ======= CSV Import =======
@app.route("/import", methods=["POST"])
def import_csv():
    file = request.files.get('csvfile')
    if not file:
        flash("No file uploaded.", "danger")
        return redirect(url_for("dashboard"))
    try:
        stream = io.StringIO(file.stream.read().decode("utf-8"))
        reader = csv.DictReader(stream)
        licenses = load_licenses()
        for row in reader:
            key = row.get("License Key") or row.get('key')
            if not key:
                continue
            # Check for duplicates
            if any(l['key'] == key for l in licenses):
                continue
            licenses.append({
                'key': key,
                'device_id': row.get("Device ID") or "",
                'created': row.get("Created") or datetime.now().strftime("%Y-%m-%d"),
                'expiry': row.get("Expiry") or (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d"),
                'enabled': row.get("Enabled", "True") == "True"
            })
        save_licenses(licenses)
        flash("Licenses imported successfully!", "success")
    except Exception as e:
        flash(f"Import failed: {e}", "danger")
    return redirect(url_for("dashboard"))

# ======= License Renew/Extend =======
@app.route("/license/renew/<key>", methods=["POST"])
def renew_license(key):
    licenses = load_licenses()
    new_expiry = request.form.get("new_expiry")
    if not new_expiry:
        flash("New expiry date is required!", "danger")
        return redirect(url_for("dashboard"))
    for lic in licenses:
        if lic['key'] == key:
            lic['expiry'] = new_expiry
            save_licenses(licenses)
            flash(f"License <b>{lic['key']}</b> renewed!", "success")
            break
    return redirect(url_for("dashboard"))

# ======= Cloud Backup (Download licenses.json) =======
@app.route("/backup")
def backup():
    if not os.path.exists(LICENSES_FILE):
        flash("No data to backup.", "danger")
        return redirect(url_for("dashboard"))
    return send_file(LICENSES_FILE, as_attachment=True)

# ======= Cloud Restore (Upload and replace licenses.json) =======
@app.route("/restore", methods=["POST"])
def restore():
    file = request.files.get('backupfile')
    if not file:
        flash("No backup file uploaded.", "danger")
        return redirect(url_for("dashboard"))
    try:
        data = json.load(file)
        if isinstance(data, list):
            save_licenses(data)
            flash("Backup restored successfully!", "success")
        else:
            flash("Invalid backup file format.", "danger")
    except Exception as e:
        flash(f"Restore failed: {e}", "danger")
    return redirect(url_for("dashboard"))

# ======= Main Dashboard =======
@app.route("/", methods=["GET", "POST"])
def dashboard():
    licenses = load_licenses()
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
                "enabled": True
            }
            licenses.append(new_license)
            save_licenses(licenses)
            flash(f"License <b>{new_license['key']}</b> created!", "success")
            return redirect(url_for("dashboard"))

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

    # Table search/filter (by device ID/partial code)
    filter_val = request.args.get("filter", "").strip().lower()
    filtered_licenses = licenses
    if filter_val:
        filtered_licenses = [l for l in licenses if filter_val in l['device_id'].lower() or filter_val in l['key'].lower()]

    # Pagination
    page = int(request.args.get("page", 1))
    per_page = 15
    total_pages = max(1, (len(filtered_licenses) + per_page - 1) // per_page)
    paginated_licenses = filtered_licenses[(page-1)*per_page: page*per_page]

    # Stats for chart
    total = len(licenses)
    active = sum(1 for l in licenses if status_of(l) == "Active")
    expired = sum(1 for l in licenses if status_of(l) == "Expired")
    disabled = sum(1 for l in licenses if status_of(l) == "Disabled")

    # Sort: active first, then expired, then disabled
    def sort_key(l):
        st = status_of(l)
        return (0 if st=="Active" else 1 if st=="Expired" else 2, -days_left(l))
    paginated_licenses.sort(key=sort_key)

    # Show page
    dashboard_html = """
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

    <div style="margin-bottom:1.5em;">
    <form method="POST" class="search-box" style="display:inline-block;">
        <label>Search License Code:</label>
        <input name="search_code" type="text" placeholder="Enter License Key" style="width: 350px;">
        <input type="submit" name="search" value="Check Status">
    </form>
    <form method="GET" style="display:inline-block; margin-left:2em;">
        <label>🔍 Filter:</label>
        <input type="text" name="filter" value="{{request.args.get('filter','')}}" placeholder="Device ID or Key">
        <input type="submit" value="Apply">
        <a href="{{ url_for('dashboard') }}"><button type="button">Reset</button></a>
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
    <div class="chart-container">
        <canvas id="licenseChart"></canvas>
    </div>
    <script>
    window.addEventListener('DOMContentLoaded', function() {
        var ctx = document.getElementById('licenseChart').getContext('2d');
        var chart = new Chart(ctx, {
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
    });
    </script>
    <table>
        <tr>
            <th>License Key</th>
            <th>Device ID</th>
            <th>Subscribed</th>
            <th>Expiry</th>
            <th>Status</th>
            <th>Days Left</th>
            <th>Action</th>
        </tr>
        {% for lic in paginated_licenses %}
        <tr class="{% if status_of(lic)=='Active' %}active{% elif status_of(lic)=='Expired' %}expired{% else %}disabled{% endif %}">
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
            </td>
        </tr>
        {% endfor %}
    </table>
    <div class="pagination">
        {% for p in range(1, total_pages+1) %}
            {% if p == page %}
                <span class="current">{{ p }}</span>
            {% else %}
                <a href="{{ url_for('dashboard', filter=request.args.get('filter',''), page=p) }}">{{ p }}</a>
            {% endif %}
        {% endfor %}
    </div>
    """
    return render_template_string(layout.replace('{% block content %}{% endblock %}', dashboard_html),
        request=request,
        searched_license=searched_license,
        search_status=search_status,
        paginated_licenses=paginated_licenses,
        status_of=status_of,
        days_left=days_left,
        created_days_ago=created_days_ago,
        active=active,
        expired=expired,
        disabled=disabled,
        page=page,
        total_pages=total_pages
    )

# ======= Enable/Disable License =======
@app.route("/license/toggle/<key>", methods=["POST"])
def toggle_license(key):
    licenses = load_licenses()
    for lic in licenses:
        if lic['key'] == key:
            lic['enabled'] = not lic.get('enabled', True)
            save_licenses(licenses)
            flash(f"License <b>{lic['key']}</b> {'Enabled' if lic['enabled'] else 'Disabled'}.", "success")
            break
    return redirect(url_for("dashboard"))

# ======= Delete License =======
@app.route("/license/delete/<key>", methods=["POST"])
def delete_license(key):
    licenses = load_licenses()
    new_licenses = [lic for lic in licenses if lic['key'] != key]
    save_licenses(new_licenses)
    flash("License deleted.", "danger")
    return redirect(url_for("dashboard"))

# ======= Run =======
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
