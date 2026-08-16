from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .agent import DraftAnalyst


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Draft Analyst</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f6f7f9; color: #17202a; }
    header { background: #0d3b3e; color: white; padding: 18px 24px; }
    main { max-width: 980px; margin: 0 auto; padding: 24px; }
    button { background: #176b5b; color: white; border: 0; border-radius: 6px; padding: 10px 14px; font-weight: 650; cursor: pointer; }
    button:disabled { opacity: .65; cursor: wait; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; margin-top: 18px; }
    .card { background: white; border: 1px solid #d9dee5; border-radius: 8px; padding: 14px; }
    .name { font-size: 18px; font-weight: 750; }
    .meta { color: #53616f; margin-top: 4px; }
    .factor { margin-top: 8px; font-size: 14px; }
    pre { white-space: pre-wrap; background: #101820; color: #f1f5f9; padding: 14px; border-radius: 8px; overflow: auto; }
  </style>
</head>
<body>
  <header><h1>Fantasy Draft Analyst</h1></header>
  <main>
    <button id="recommend">Recommend my next pick</button>
    <button id="health">Check connections</button>
    <div id="summary"></div>
    <div id="cards" class="grid"></div>
    <pre id="raw"></pre>
  </main>
  <script>
    const raw = document.querySelector('#raw');
    const cards = document.querySelector('#cards');
    const summary = document.querySelector('#summary');
    async function load(path) {
      raw.textContent = 'Working...';
      cards.innerHTML = '';
      summary.innerHTML = '';
      const res = await fetch(path);
      const data = await res.json();
      raw.textContent = JSON.stringify(data, null, 2);
      if (data.top_3) {
        summary.innerHTML = `<p><strong>Provider:</strong> ${data.provider}</p><p><strong>Final:</strong> ${(data.llm_recommendation || {}).final_recommendation || data.top_3[0].name}</p>`;
        cards.innerHTML = data.top_3.map((p, i) => `<section class="card"><div class="name">${i + 1}. ${p.name}</div><div class="meta">${p.position} ${p.team || ''} · ${p.projected_season_points} season · ${p.projected_fp_per_game} fp/g</div><div class="factor">${p.major_factors.join('<br>')}</div></section>`).join('');
      }
    }
    document.querySelector('#recommend').onclick = () => load('/api/recommend');
    document.querySelector('#health').onclick = () => load('/api/health');
  </script>
</body>
</html>
"""


def run_server(analyst: DraftAnalyst, host: str, port: int) -> None:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def send_json(self, payload: object, status: int = 200) -> None:
            body = json.dumps(payload, indent=2).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            try:
                if parsed.path == "/":
                    body = INDEX_HTML.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if parsed.path == "/api/health":
                    self.send_json(analyst.health())
                    return
                if parsed.path == "/api/recommend":
                    params = parse_qs(parsed.query)
                    manual_state = params.get("manual_state", [None])[0]
                    self.send_json(analyst.recommend(manual_state))
                    return
                self.send_json({"error": "not found"}, 404)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Draft analyst running at http://{host}:{port}")
    httpd.serve_forever()
