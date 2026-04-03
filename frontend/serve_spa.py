"""Minimal SPA-aware HTTP server: serves static files from dist/, falls back to index.html for unknown paths."""

import http.server
import os
import sys

DIST = os.path.join(os.path.dirname(__file__), "dist")


class SPAHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=DIST, **kwargs)

    def do_GET(self):
        # If the requested file exists on disk, serve it normally
        path = self.translate_path(self.path)
        if os.path.isfile(path):
            return super().do_GET()
        # Otherwise serve index.html (SPA client-side routing)
        self.path = "/index.html"
        return super().do_GET()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5173
    with http.server.HTTPServer(("0.0.0.0", port), SPAHandler) as httpd:
        print(f"SPA server running at http://localhost:{port}")
        httpd.serve_forever()
