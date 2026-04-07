import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URI;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.Executors;

/**
 * 本地 Java 故障演练服务：
 * 1) 提供一个可监控页面（包含“查询”按钮）
 * 2) 提供查询接口并稳定返回 500/502 错误
 * 3) 页面主动输出 console.error + pageerror，便于感知链路捕获
 */
public class JavaMonitorFaultDemo {
    private static final int PORT = 18082;

    private static final String HTML = """
        <!doctype html>
        <html lang="zh-CN">
        <head>
          <meta charset="utf-8" />
          <meta name="viewport" content="width=device-width,initial-scale=1" />
          <title>Java Monitor Fault Demo</title>
          <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 24px; }
            .row { display: flex; gap: 8px; margin: 12px 0; }
            input { padding: 8px; width: 280px; }
            button { padding: 8px 12px; cursor: pointer; }
            #out { margin-top: 12px; color: #444; white-space: pre-wrap; }
          </style>
        </head>
        <body>
          <h1>Java 监控故障演练页</h1>
          <p>用于验证：页面感知是否能自动触发查询接口并捕获报错。</p>
          <div class="row">
            <input id="kw" type="search" placeholder="输入关键词后查询（默认 timeout）" value="timeout" />
            <button id="queryBtn" type="button">查询订单</button>
          </div>
          <div id="out">等待请求...</div>

          <script>
            const out = document.getElementById("out");
            const logLine = (text) => { out.textContent = `${new Date().toISOString()} ${text}\\n` + out.textContent; };

            // 中文注释：页面加载时先触发一个查询类 GET 请求（正常），用于让系统识别查询接口列表。
            fetch("/api/list?page=1&size=20").then(() => logLine("GET /api/list -> 200"));

            // 中文注释：主动打出 console.error，验证前端控制台异常采集。
            console.error("Synthetic console error: order-list widget render failed");
            // 中文注释：再抛出一个异步异常，验证 pageerror 采集。
            setTimeout(() => { throw new Error("Synthetic page crash: cannot read property 'rows' of undefined"); }, 120);

            async function runQuery() {
              const kw = document.getElementById("kw").value || "timeout";
              try {
                const resp = await fetch(`/api/query?kw=${encodeURIComponent(kw)}`, { method: "GET" });
                const body = await resp.text();
                logLine(`GET /api/query status=${resp.status} body=${body.slice(0, 120)}`);
              } catch (err) {
                logLine("query fetch failed: " + String(err));
              }
            }

            document.getElementById("queryBtn").addEventListener("click", runQuery);
            // 中文注释：首屏自动触发一次查询，保证无人工交互也能稳定产生接口异常。
            setTimeout(runQuery, 250);
          </script>
        </body>
        </html>
        """;

    public static void main(String[] args) throws Exception {
        HttpServer server = HttpServer.create(new InetSocketAddress("127.0.0.1", PORT), 0);
        server.setExecutor(Executors.newCachedThreadPool());
        server.createContext("/", JavaMonitorFaultDemo::handleRoot);
        server.createContext("/api/list", JavaMonitorFaultDemo::handleList);
        server.createContext("/api/query", JavaMonitorFaultDemo::handleQuery);
        server.createContext("/api/search/orders", JavaMonitorFaultDemo::handleSearchOrders);
        server.start();
        System.out.println("java monitor fault demo listening on http://127.0.0.1:" + PORT);
    }

    private static void handleRoot(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            writeJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        writeHtml(exchange, 200, HTML);
    }

    private static void handleList(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            writeJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        writeJson(exchange, 200, "{\"items\":[{\"id\":\"o_1001\",\"status\":\"ok\"}],\"total\":1}");
    }

    private static void handleQuery(HttpExchange exchange) throws IOException {
        if (!"GET".equalsIgnoreCase(exchange.getRequestMethod())) {
            writeJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        Map<String, String> params = parseQuery(exchange.getRequestURI());
        String kw = params.getOrDefault("kw", "timeout");
        // 中文注释：这里固定返回 500，模拟查询接口故障。
        writeJson(
                exchange,
                500,
                "{\"error\":\"query_failed\",\"reason\":\"db_timeout\",\"kw\":\"" + escapeJson(kw) + "\"}"
        );
    }

    private static void handleSearchOrders(HttpExchange exchange) throws IOException {
        if (!"POST".equalsIgnoreCase(exchange.getRequestMethod())) {
            writeJson(exchange, 405, "{\"error\":\"method_not_allowed\"}");
            return;
        }
        // 中文注释：POST 查询接口也返回异常，用于验证 query/search 关键词识别规则。
        writeJson(exchange, 502, "{\"error\":\"upstream_unavailable\",\"hint\":\"search cluster overload\"}");
    }

    private static void writeHtml(HttpExchange exchange, int statusCode, String html) throws IOException {
        byte[] bytes = html.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "text/html; charset=utf-8");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static void writeJson(HttpExchange exchange, int statusCode, String json) throws IOException {
        byte[] bytes = json.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.sendResponseHeaders(statusCode, bytes.length);
        try (OutputStream os = exchange.getResponseBody()) {
            os.write(bytes);
        }
    }

    private static Map<String, String> parseQuery(URI uri) {
        Map<String, String> out = new HashMap<>();
        String raw = uri.getQuery();
        if (raw == null || raw.isBlank()) {
            return out;
        }
        String[] parts = raw.split("&");
        for (String part : parts) {
            int i = part.indexOf('=');
            if (i <= 0) {
                continue;
            }
            String k = part.substring(0, i);
            String v = part.substring(i + 1);
            out.put(k, v);
        }
        return out;
    }

    private static String escapeJson(String s) {
        return String.valueOf(s).replace("\\", "\\\\").replace("\"", "\\\"");
    }
}
