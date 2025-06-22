from flask import Flask, request, jsonify
from datetime import datetime

app = Flask(_name_)

# 🔐 Dummy License Database
licenses = {
    "ABC123": {
        "device_id": "your_device_id_will_bind_here",
        "expires": "2025-12-31",
        "version": "1.0.0"
    }
}

LATEST_VERSION = "1.0.0"
UPDATE_LINK = "https://yourwebsite.com/download/tool.exe"

@app.route("/check", methods=["POST"])
def check_license():
    data = request.json
    key = data.get("key")
    device = data.get("device_id")
    version = data.get("version")

    if key not in licenses:
        return jsonify({"valid": False, "reason": "Invalid key"})

    license_info = licenses[key]

    if license_info["device_id"] != device:
        return jsonify({"valid": False, "reason": "Device mismatch"})

    expired = datetime.strptime(license_info["expires"], "%Y-%m-%d") < datetime.now()
    version_outdated = version != LATEST_VERSION

    return jsonify({
        "valid": True,
        "expired": expired,
        "version_outdated": version_outdated,
        "latest_version": LATEST_VERSION,
        "update_link": UPDATE_LINK
    })

@app.route("/", methods=["GET"])
def home():
    return "Subscription API is running."

if _name_ == "_main_":
    app.run()
