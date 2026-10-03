import json
import os
import uuid
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from db import init_db, get_conn, rows_to_list
from auth import verify_device_token, verify_api_key

PORT = int(os.environ.get("PORT", 8080))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def _send(self, code, data):
        body = json.dumps(data, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _auth_device(self):
        return verify_device_token(self.headers.get("X-Device-Token", ""))

    def _auth_api(self):
        return verify_api_key(self.headers.get("X-Api-Key", ""))

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, X-Api-Key, X-Device-Token")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        path = parsed.path.rstrip("/")

        if path in ("", "/"):
            self._serve_ui(); return

        if path == "/device/queue":
            if not self._auth_device():
                self._send(401, {"error": "Unauthorized"}); return
            conn = get_conn()
            rows = conn.execute("""
                SELECT * FROM messages
                WHERE status = 'queued'
                  AND (scheduled_at IS NULL OR scheduled_at <= datetime('now'))
                ORDER BY created_at ASC LIMIT 10
            """).fetchall()
            conn.close()
            self._send(200, {"messages": rows_to_list(rows)}); return

        if not self._auth_api():
            self._send(401, {"error": "Unauthorized"}); return

        if path == "/api/messages":
            status = qs.get("status", [None])[0]
            conn = get_conn()
            if status:
                rows = conn.execute("SELECT * FROM messages WHERE status=? ORDER BY created_at DESC LIMIT 100", (status,)).fetchall()
            else:
                rows = conn.execute("SELECT * FROM messages ORDER BY created_at DESC LIMIT 100").fetchall()
            conn.close()
            self._send(200, {"messages": rows_to_list(rows)})

        elif path == "/api/devices":
            conn = get_conn()
            rows = conn.execute("SELECT id,name,last_seen,last_port,last_signal,last_network,active FROM devices").fetchall()
            conn.close()
            self._send(200, {"devices": rows_to_list(rows)})

        elif path == "/api/stats":
            conn = get_conn()
            stats = {}
            for s in ("queued", "sending", "sent", "failed"):
                row = conn.execute("SELECT COUNT(*) as c FROM messages WHERE status=?", (s,)).fetchone()
                stats[s] = row["c"]
            conn.close()
            self._send(200, stats)

        else:
            self._send(404, {"error": "Not found"})

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/")

        if path == "/device/heartbeat":
            if not self._auth_device():
                self._send(401, {"error": "Unauthorized"}); return
            data = self._body()
            token = self.headers.get("X-Device-Token", "")
            conn = get_conn()
            conn.execute("""
                UPDATE devices SET last_seen=datetime('now'),
                last_port=?, last_signal=?, last_network=? WHERE token=?
            """, (data.get("port"), json.dumps(data.get("signal")), data.get("network"), token))
            conn.commit(); conn.close()
            self._send(200, {"ok": True}); return

        if path == "/device/report":
            if not self._auth_device():
                self._send(401, {"error": "Unauthorized"}); return
            data = self._body()
            msg_id = data.get("id")
            status = data.get("status")
            error  = data.get("error", "")
            conn = get_conn()
            conn.execute("""
                UPDATE messages SET status=?, error=?,
                sent_at=CASE WHEN ? = 'sent' THEN datetime('now') ELSE NULL END,
                updated_at=datetime('now') WHERE id=?
            """, (status, error, status, msg_id))
            conn.commit(); conn.close()
            self._send(200, {"ok": True}); return

        if not self._auth_api():
            self._send(401, {"error": "Unauthorized"}); return

        if path == "/api/messages":
            data = self._body()
            to   = data.get("to", "").strip()
            body = data.get("body", "").strip()
            sched= data.get("scheduled_at")
            if not to or not body:
                self._send(400, {"error": "to y body son requeridos"}); return
            msg_id = str(uuid.uuid4())
            conn = get_conn()
            conn.execute("INSERT INTO messages (id,to_number,body,status,scheduled_at) VALUES (?,?,?,'queued',?)",
                         (msg_id, to, body, sched))
            conn.commit(); conn.close()
            self._send(201, {"ok": True, "id": msg_id})

        elif path == "/api/messages/bulk":
            data = self._body()
            items = data.get("messages", [])
            if not items:
                self._send(400, {"error": "messages[] requerido"}); return
            conn = get_conn()
            ids = []
            for item in items:
                mid = str(uuid.uuid4())
                conn.execute("INSERT INTO messages (id,to_number,body,status,scheduled_at) VALUES (?,?,?,'queued',?)",
                             (mid, item.get("to",""), item.get("body",""), item.get("scheduled_at")))
                ids.append(mid)
            conn.commit(); conn.close()
            self._send(201, {"ok": True, "ids": ids, "count": len(ids)})

        elif path == "/api/devices":
            data = self._body()
            name = data.get("name", "Device").strip()
            dev_id = str(uuid.uuid4())
            from auth import make_device_token
            token = make_device_token(dev_id)
            conn = get_conn()
            conn.execute("INSERT INTO devices (id,name,token) VALUES (?,?,?)", (dev_id, name, token))
            conn.commit(); conn.close()
            self._send(201, {"ok": True, "id": dev_id, "token": token})

        else:
            self._send(404, {"error": "Not found"})

    def do_DELETE(self):
        if not self._auth_api():
            self._send(401, {"error": "Unauthorized"}); return
        parts = self.path.strip("/").split("/")
        if len(parts) == 3 and parts[0] == "api" and parts[1] == "messages":
            conn = get_conn()
            conn.execute("DELETE FROM messages WHERE id=? AND status='queued'", (parts[2],))
            conn.commit(); conn.close()
            self._send(200, {"ok": True})
        else:
            self._send(404, {"error": "Not found"})

    def _serve_ui(self):
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")
        with open(path, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    init_db()
    print(f"🌐 Platform B corriendo en http://0.0.0.0:{PORT}")
    HTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
