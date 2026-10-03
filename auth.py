import hmac
import hashlib
import os

SHARED_SECRET = os.environ.get("SHARED_SECRET", "change-this-secret-in-production")
API_KEY       = os.environ.get("API_KEY", "change-this-api-key")


def make_device_token(device_id: str) -> str:
    return hmac.new(
        SHARED_SECRET.encode(),
        device_id.encode(),
        hashlib.sha256
    ).hexdigest()


def verify_device_token(token: str) -> bool:
    from db import get_conn
    conn = get_conn()
    row = conn.execute("SELECT id FROM devices WHERE token=? AND active=1", (token,)).fetchone()
    conn.close()
    return row is not None


def verify_api_key(key: str) -> bool:
    from db import get_conn
    conn = get_conn()
    row = conn.execute("SELECT key FROM api_keys WHERE key=?", (key,)).fetchone()
    conn.close()
    return row is not None or hmac.compare_digest(key, API_KEY)
