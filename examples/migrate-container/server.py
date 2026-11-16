#!/usr/bin/env python3
"""Small stateless catalogue used for a hosting-only packaging rehearsal.

No database, credentials, dependency install, writes or background jobs. Binding
all interfaces is explicit and intended for the container behind a reviewed LB.
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import time
from urllib.parse import parse_qs, urlsplit

ITEMS = [{"id": "notebook", "category": "work", "name": "Field notebook"},
         {"id": "mug", "category": "home", "name": "Studio mug"}]
PAGE = b"<!doctype html><html lang=en><meta charset=utf-8><title>Small catalogue</title><h1>Small catalogue</h1><p>Two useful things. One portable web service.</p><a href=/api/items?category=work>Browse work items</a></html>"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def reply(self, status, body=b"", content_type="application/json", *, location=None):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(body)))
        if location:
            self.send_header("Location", location)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        try:
            selected = urlsplit(self.path)
            if selected.path == "/healthz":
                self.reply(200, b'{"status":"ok"}')
            elif selected.path in {"/", "/catalogue"}:
                self.reply(200, PAGE, "text/html; charset=utf-8")
            elif selected.path == "/start":
                self.reply(307, location="/catalogue")
            elif selected.path == "/private":
                self.reply(401, b'{"error":"sign-in-required"}')
            elif selected.path == "/api/items":
                args = parse_qs(selected.query, keep_blank_values=True, max_num_fields=8)
                if set(args) - {"category"} or "category" in args and args["category"] not in (["home"], ["work"]):
                    self.reply(400, b'{"error":"invalid-category"}')
                else:
                    category = args.get("category", [None])[0]
                    data = {"items": [item for item in ITEMS if category is None or item["category"] == category]}
                    self.reply(200, json.dumps(data, separators=(",", ":")).encode())
            elif selected.path == "/stream":
                chunks = [b"event: ready\ndata: catalogue\n\n", b"event: complete\ndata: two-items\n\n"]
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(sum(map(len, chunks))))
                self.end_headers()
                if self.command != "HEAD":
                    self.wfile.write(chunks[0])
                    self.wfile.flush()
                    time.sleep(.15)
                    self.wfile.write(chunks[1])
            else:
                self.reply(404, b'{"error":"not-found"}')
        except (ValueError, BrokenPipeError, ConnectionResetError):
            self.close_connection = True

    do_HEAD = do_GET

    def do_POST(self):
        self.close_connection = True
        self.reply(405, b'{"error":"read-only-example"}')

    do_PUT = do_POST
    do_PATCH = do_POST
    do_DELETE = do_POST


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", choices=("127.0.0.1", "0.0.0.0"), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    with ThreadingHTTPServer((args.host, args.port), Handler) as server:
        server.serve_forever()


if __name__ == "__main__":
    main()
