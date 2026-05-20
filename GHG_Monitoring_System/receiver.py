from flask import Flask, request, jsonify
from datetime import datetime
import sqlite3

from database import DB_FILE, get_connection, save_alert, setup_database

app = Flask(__name__)


@app.route("/sensor", methods=["POST"])
def receive_data():
    """Accept a JSON reading from an ESP32 node and persist it."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No JSON body received"}), 400

    # Validate required fields
    required = ["emitter_id", "co2", "ch4"]
    missing  = [f for f in required if f not in data]
    if missing:
        return jsonify({"status": "error", "message": f"Missing fields: {missing}"}), 400

    try:
        emitter_id = int(data["emitter_id"])   # FIX 3: from payload, not hardcoded
        co2        = float(data["co2"])
        ch4        = float(data["ch4"])
    except (ValueError, TypeError) as e:
        return jsonify({"status": "error", "message": f"Invalid data types: {e}"}), 400

    # Classify status using same thresholds as dashboard
    CO2_LIMIT, CH4_LIMIT = 450.0, 25.0
    if co2 < 0.8 * CO2_LIMIT and ch4 < 0.8 * CH4_LIMIT:
        status = "Compliant"
    elif co2 > CO2_LIMIT or ch4 > CH4_LIMIT:
        status = "Critical"
    else:
        status = "Warning"

    setup_database(verbose=False)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT 1 FROM emitters WHERE id=?", (emitter_id,))
    if not cursor.fetchone():
        conn.close()
        return jsonify({"status": "error", "message": "Unknown emitter_id"}), 404

    # FIX 1: correct table name → readings (was 'emissions')
    # FIX 2: correct column name → ch4 (was 'methane')
    try:
        cursor.execute("""
        INSERT INTO readings (emitter_id, co2, ch4, timestamp)
        VALUES (?, ?, ?, ?)
        """, (emitter_id, co2, ch4, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

        conn.commit()
    except sqlite3.Error as exc:
        conn.rollback()
        return jsonify({"status": "error", "message": str(exc)}), 500
    finally:
        conn.close()

    # Auto-log alert if threshold exceeded. Uses the shared helper so an
    # ongoing condition updates one open alert instead of creating duplicates.
    if status in ("Warning", "Critical"):
        save_alert(
            emitter_id,
            status,
            f"{status}: CO2={co2:.1f} ppm, CH4={ch4:.1f} ppm",
        )

    return jsonify({
        "status":     "received",
        "emitter_id": emitter_id,
        "co2":        co2,
        "ch4":        ch4,
        "classified": status,
        "timestamp":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


@app.route("/readings", methods=["GET"])
def list_readings():
    """Return the latest saved readings from the database."""
    setup_database(verbose=False)
    limit = request.args.get("limit", default=50, type=int)
    limit = min(max(limit or 50, 1), 500)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT r.id, r.emitter_id, e.name, r.co2, r.ch4, r.timestamp
        FROM readings r
        JOIN emitters e ON r.emitter_id = e.id
        ORDER BY r.timestamp DESC, r.id DESC
        LIMIT ?
    """, (limit,))
    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        "status": "ok",
        "count": len(rows),
        "readings": [
            {
                "id": row[0],
                "emitter_id": row[1],
                "emitter_name": row[2],
                "co2": row[3],
                "ch4": row[4],
                "timestamp": row[5],
            }
            for row in rows
        ],
    })


@app.route("/emitters", methods=["GET"])
def list_emitters():
    """Return registered emitters so sensors can use a valid emitter_id."""
    setup_database(verbose=False)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id, name, type, location
        FROM emitters
        ORDER BY id
    """)
    rows = cursor.fetchall()
    conn.close()

    return jsonify({
        "status": "ok",
        "count": len(rows),
        "emitters": [
            {
                "id": row[0],
                "name": row[1],
                "type": row[2],
                "location": row[3],
            }
            for row in rows
        ],
    })


@app.route("/health", methods=["GET"])
def health():
    """Simple health-check endpoint."""
    return jsonify({"status": "ok", "service": "GHG Receiver", "db": DB_FILE})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
