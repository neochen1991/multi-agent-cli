"""本地故障页面服务：用于监控链路端到端验证。"""

from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer


HTML = """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <title>Buggy Monitor Target</title>
</head>
<body>
  <h1>Buggy Monitor Target</h1>
  <p>这个页面会抛出前端异常，并触发一个 500 接口请求。</p>
  <script>
    // 前端异常：让 Playwright 的 pageerror/console 捕获到问题。
    setTimeout(() => { throw new Error("Synthetic frontend crash for monitor e2e"); }, 50);
    // 接口异常：让 Playwright response 监听到 500。
    fetch("/api/fail", { credentials: "include" }).catch(() => {});
  </script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/":
            data = HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        if self.path.startswith("/api/fail"):
            data = b'{"error":"synthetic_500"}'
            self.send_response(500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, fmt: str, *args):  # noqa: A003
        # 保持测试输出简洁。
        _ = fmt, args


def main() -> None:
    server = HTTPServer(("127.0.0.1", 18081), Handler)
    print("buggy web service listening on http://127.0.0.1:18081")
    server.serve_forever()


if __name__ == "__main__":
    main()
