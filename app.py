import os
import time
import base64
import threading
from typing import Dict, Any

from flask import Flask, request, jsonify, Response, render_template, abort

app = Flask(__name__)

UPLOAD_TOKEN = os.environ.get("UPLOAD_TOKEN", "change-me")
PORT = int(os.environ.get("PORT", 5000))

# Lưu frame mới nhất trong RAM
streams: Dict[str, Dict[str, Any]] = {}
streams_lock = threading.Lock()

# streams = {
#   "demo1": {
#       "jpeg_bytes": b"...",
#       "updated_at": 1710000000.0,
#       "sender_ip": "1.2.3.4"
#   }
# }


def get_stream(stream_id: str):
    with streams_lock:
        return streams.get(stream_id)


def set_stream(stream_id: str, jpeg_bytes: bytes, sender_ip: str):
    with streams_lock:
        streams[stream_id] = {
            "jpeg_bytes": jpeg_bytes,
            "updated_at": time.time(),
            "sender_ip": sender_ip,
        }


def cleanup_stale_streams(max_age_seconds: int = 60):
    while True:
        now = time.time()
        with streams_lock:
            stale_ids = [
                sid for sid, data in streams.items()
                if now - data["updated_at"] > max_age_seconds
            ]
            for sid in stale_ids:
                del streams[sid]
        time.sleep(10)


@app.route("/")
def index():
    with streams_lock:
        items = [
            {
                "stream_id": sid,
                "updated_at": data["updated_at"],
                "sender_ip": data["sender_ip"],
                "age_sec": round(time.time() - data["updated_at"], 1),
            }
            for sid, data in streams.items()
        ]
    items.sort(key=lambda x: x["updated_at"], reverse=True)
    return render_template("index.html", streams=items)


@app.route("/health")
def health():
    return jsonify({"ok": True, "streams": len(streams)})


@app.route("/api/upload/<stream_id>", methods=["POST"])
def upload_frame(stream_id: str):
    token = request.headers.get("X-Upload-Token", "")
    if token != UPLOAD_TOKEN:
        return jsonify({"error": "unauthorized"}), 401

    if not stream_id or len(stream_id) > 100:
        return jsonify({"error": "invalid_stream_id"}), 400

    content_type = request.content_type or ""

    try:
        if content_type.startswith("application/json"):
            data = request.get_json(silent=True) or {}
            frame_b64 = data.get("frame_b64")
            if not frame_b64:
                return jsonify({"error": "missing_frame_b64"}), 400
            jpeg_bytes = base64.b64decode(frame_b64)
        else:
            jpeg_bytes = request.data

        if not jpeg_bytes:
            return jsonify({"error": "empty_frame"}), 400

        sender_ip = request.headers.get("X-Forwarded-For", request.remote_addr or "unknown")
        set_stream(stream_id, jpeg_bytes, sender_ip)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"error": str(e)}), 400


def mjpeg_generator(stream_id: str):
    last_sent_ts = 0.0

    while True:
        stream = get_stream(stream_id)

        if not stream:
            # Chưa có stream thì chờ
            time.sleep(0.2)
            continue

        updated_at = stream["updated_at"]
        jpeg_bytes = stream["jpeg_bytes"]

        if updated_at <= last_sent_ts:
            time.sleep(0.03)
            continue

        last_sent_ts = updated_at

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            jpeg_bytes +
            b"\r\n"
        )


@app.route("/mjpeg/<stream_id>")
def mjpeg_feed(stream_id: str):
    return Response(
        mjpeg_generator(stream_id),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )


@app.route("/watch/<stream_id>")
def watch(stream_id: str):
    stream = get_stream(stream_id)
    status = None
    if stream:
        age = round(time.time() - stream["updated_at"], 1)
        status = {
            "age_sec": age,
            "sender_ip": stream["sender_ip"]
        }
    return render_template("watch.html", stream_id=stream_id, status=status)


if __name__ == "__main__":
    cleaner = threading.Thread(target=cleanup_stale_streams, daemon=True)
    cleaner.start()
    app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)