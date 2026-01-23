import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.request import Request, urlopen

TARGET_URL = os.getenv(
    "CLICK_TARGET_URL",
    "https://fudly-bot-production.up.railway.app/api/v1/payment/click/callback",
)

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
            req.add_header("Accept", "application/json")

            with urlopen(req, timeout=15) as resp:
                raw = resp.read()
                content_type = resp.headers.get("Content-Type", "application/json")

            payload = raw

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as exc:
            body = f'{{"error":-1,"error_note":"{exc}"}}'.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
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
