from flask import Flask, request, jsonify
from datetime import datetime
import os

app = Flask(__name__)

# 🔐 Dummy License Database (এইখানে key list থাকবে)
licenses = {
    "ABC123": {
        "device_id": "your_device_id_will_bind_here",
        "expires": "2025-12-31",  # মেয়াদ শেষ হবে
        "version": "1.0.0"         # ইউজারের কাছে কোন version আছে
    }
}

# 🔄 Latest version info
LATEST_VERSION = "1.0.0"
UPDATE_LINK = "https://yourwebsite.com/download/tool.exe"  # এটা তোমার Tool এর নতুন download লিংক হবে

@app.route("/check", methods=["POST"])
def check_license():
    data = request.json
    key = data.get("key")
    device = data.get("device_id")
    version = data.get("version")

    if key not in licenses:
        return jsonify({"valid": False, "reason": "Invalid key"})

    license_info = licenses[key]

    # ✅ Device bind check
    if license_info["device_id"] != device:
        return jsonify({"valid": False, "reason": "Device mismatch"})

    # ⏱ Expiry check
    expired = datetime.strptime(license_info["expires"], "%Y-%m-%d") < datetime.now()

    # 🆕 Version outdated check
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

# ✅ Render-compatible server runner
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
