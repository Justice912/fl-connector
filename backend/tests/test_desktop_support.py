from app.desktop_support import backend_is_up, frontend_dist


def test_frontend_dist_resolves_under_app_root(tmp_path):
    assert frontend_dist(tmp_path) == tmp_path / "frontend" / "dist"


def test_backend_is_up_false_when_nothing_listening():
    # Port 9 (discard) is effectively never open for HTTP here -> refused -> False.
    assert backend_is_up("http://127.0.0.1:9", timeout=0.5) is False


def test_backend_is_up_true_against_a_live_health_endpoint():
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/health":
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b'{"ok": true}')
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert backend_is_up(f"http://127.0.0.1:{port}", timeout=2.0) is True
    finally:
        server.shutdown()
