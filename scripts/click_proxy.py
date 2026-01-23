import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlencode
from urllib.request import Request, urlopen

TARGET_URL = os.getenv(
    "CLICK_TARGET_URL",
    "https://fudly-bot-production.up.railway.app/api/v1/payment/click/callback",
)

KEY_ORDER = [
    "click_trans_id",
    "merchant_trans_id",
    "merchant_prepare_id",
    "merchant_confirm_id",
    "error",
    "error_note",
]


def _normalize_response(raw_bytes: bytes, content_type: str) -> bytes:
    text = raw_bytes.decode("utf-8", errors="replace").strip()
    data = None

    if "application/json" in content_type:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None
    elif "application/x-www-form-urlencoded" in content_type:
        data = {k: v[0] if v else "" for k, v in parse_qs(text).items()}

    if data is None:
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = None

    if isinstance(data, dict):
        ordered = {}
        for key in KEY_ORDER:
            ordered[key] = data.get(key, "")
        for key, value in data.items():
            if key not in ordered:
                ordered[key] = value
        lines = [f"{k}={ordered[k]}" for k in KEY_ORDER]
        payload = "\n".join(lines)
        return payload.encode("cp1251", errors="replace")

    # Fallback: return plain text as-is with CRLF line endings
    return text.encode("cp1251", errors="replace")


class ClickProxyHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            length = int(self.headers.get("Content-Length", "0") or "0")
            body = self.rfile.read(length)

            req = Request(TARGET_URL, data=body, method="POST")
            req.add_header(
                "Content-Type",
                self.headers.get("Content-Type", "application/x-www-form-urlencoded"),
            )
            req.add_header("Accept", "*/*")

            with urlopen(req, timeout=15) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type", "")

            payload = _normalize_response(raw, content_type.lower())

            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            body = f"error=-1\r\nerror_note={exc}\r\n".encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)


def main():
    port = int(os.getenv("CLICK_PROXY_PORT", "8080"))
    server = HTTPServer(("127.0.0.1", port), ClickProxyHandler)
    print(f"Click proxy listening on http://127.0.0.1:{port}")
    print(f"Forwarding to {TARGET_URL}")
    server.serve_forever()


if __name__ == "__main__":
    main()
