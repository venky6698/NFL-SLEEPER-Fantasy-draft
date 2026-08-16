from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .agent import DraftAnalyst
from .live_sync import LiveDraftSync


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Live Draft Analyst</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; background: #f5f6f7; color: #17202a; }
    header { background: #113b33; color: white; padding: 14px 20px; display: flex; justify-content: space-between; align-items: center; gap: 16px; }
    h1 { margin: 0; font-size: 20px; }
    main { max-width: 1280px; margin: 0 auto; padding: 18px; }
    button { background: #176b5b; color: white; border: 0; border-radius: 6px; padding: 9px 12px; font-weight: 650; cursor: pointer; }
    button:disabled { opacity: .65; cursor: wait; }
    .layout { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(360px, .85fr); gap: 16px; align-items: start; }
    .toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
    .status { color: #d9f5ec; font-size: 13px; }
    .panel { background: white; border: 1px solid #d9dee5; border-radius: 8px; padding: 14px; }
    .panel h2 { margin: 0 0 10px; font-size: 16px; }
    .metrics { display: grid; grid-template-columns: repeat(4, minmax(110px, 1fr)); gap: 10px; margin-bottom: 16px; }
    .metric { background: white; border: 1px solid #d9dee5; border-radius: 8px; padding: 10px; }
    .metric .label { color: #5c6875; font-size: 12px; }
    .metric .value { font-weight: 760; margin-top: 3px; }
    .board { display: grid; grid-template-columns: repeat(auto-fill, minmax(178px, 1fr)); gap: 8px; max-height: 68vh; overflow: auto; padding-right: 4px; }
    .pick { border: 1px solid #d9dee5; border-left: 4px solid #aab4bf; border-radius: 7px; padding: 8px; background: #fff; min-height: 70px; }
    .pick.mine { border-left-color: #176b5b; background: #f2fbf7; }
    .pick .num { color: #687584; font-size: 12px; }
    .pick .player { font-weight: 740; margin-top: 4px; }
    .pick .meta { color: #53616f; font-size: 13px; margin-top: 2px; }
    .grid { display: grid; grid-template-columns: 1fr; gap: 10px; margin-top: 10px; }
    .card { background: white; border: 1px solid #d9dee5; border-radius: 8px; padding: 14px; }
    .name { font-size: 18px; font-weight: 750; }
    .meta { color: #53616f; margin-top: 4px; }
    .factor { margin-top: 8px; font-size: 14px; }
    pre { white-space: pre-wrap; background: #101820; color: #f1f5f9; padding: 12px; border-radius: 8px; overflow: auto; max-height: 240px; font-size: 12px; }
    @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .metrics { grid-template-columns: repeat(2, minmax(110px, 1fr)); } }
  </style>
</head>
<body>
  <header>
    <h1>Live Draft Analyst</h1>
    <div class="toolbar">
      <span id="syncStatus" class="status">Connecting...</span>
      <button id="sync">Sync now</button>
      <button id="recommend">Recommend</button>
    </div>
  </header>
  <main>
    <section class="metrics">
      <div class="metric"><div class="label">Current Pick</div><div id="pickNo" class="value">-</div></div>
      <div class="metric"><div class="label">Drafted</div><div id="pickedCount" class="value">-</div></div>
      <div class="metric"><div class="label">Last Pick</div><div id="lastPick" class="value">-</div></div>
      <div class="metric"><div class="label">Next Auto Sync</div><div id="countdown" class="value">60s</div></div>
    </section>
    <section class="layout">
      <div class="panel">
        <h2>Draft Board</h2>
        <div id="board" class="board"></div>
      </div>
      <div class="panel">
        <h2>Recommendation</h2>
        <div id="summary"></div>
        <div id="cards" class="grid"></div>
        <pre id="raw"></pre>
      </div>
    </section>
  </main>
  <script>
    const syncInterval = 60000;
    let nextSyncAt = Date.now() + syncInterval;
    const raw = document.querySelector('#raw');
    const cards = document.querySelector('#cards');
    const summary = document.querySelector('#summary');
    const board = document.querySelector('#board');
    const syncStatus = document.querySelector('#syncStatus');
    const pickNo = document.querySelector('#pickNo');
    const pickedCount = document.querySelector('#pickedCount');
    const lastPick = document.querySelector('#lastPick');
    const countdown = document.querySelector('#countdown');

    function esc(value) {
      return String(value == null ? '' : value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    }

    function renderState(data) {
      pickNo.textContent = data.current_pick_no || '-';
      pickedCount.textContent = data.picked_count || 0;
      lastPick.textContent = data.last_pick ? `${data.last_pick.name} (${data.last_pick.position || ''})` : '-';
      syncStatus.textContent = data.error ? `Sync issue: ${data.error}` : `Synced ${new Date(data.synced_at).toLocaleTimeString()}`;
      board.innerHTML = (data.board || []).map(p => `
        <div class="pick">
          <div class="num">Pick ${esc(p.pick_no)} · Round ${esc(p.round)} · Slot ${esc(p.draft_slot)}</div>
          <div class="player">${esc(p.name)}</div>
          <div class="meta">${esc(p.position || '')} ${esc(p.team || '')}</div>
        </div>
      `).join('');
    }

    async function syncNow() {
      syncStatus.textContent = 'Syncing...';
      const res = await fetch('/api/state?force=1');
      const data = await res.json();
      renderState(data);
      nextSyncAt = Date.now() + syncInterval;
      return data;
    }

    async function loadRecommendation() {
      raw.textContent = 'Working...';
      const data = await fetch('/api/recommend?use_sync=1').then(r => r.json());
      raw.textContent = JSON.stringify(data, null, 2);
      if (data.top_3) {
        summary.innerHTML = `<p><strong>Provider:</strong> ${esc(data.provider)}</p><p><strong>Final:</strong> ${esc((data.llm_recommendation || {}).final_recommendation || data.top_3[0].name)}</p>`;
        cards.innerHTML = data.top_3.map((p, i) => `<section class="card"><div class="name">${i + 1}. ${esc(p.name)}</div><div class="meta">${esc(p.position)} ${esc(p.team || '')} · ${esc(p.projected_season_points)} season · ${esc(p.projected_fp_per_game)} fp/g</div><div class="factor">${p.major_factors.map(esc).join('<br>')}</div></section>`).join('');
      }
    }

    document.querySelector('#sync').onclick = syncNow;
    document.querySelector('#recommend').onclick = loadRecommendation;
    setInterval(() => {
      const remaining = Math.max(0, Math.ceil((nextSyncAt - Date.now()) / 1000));
      countdown.textContent = `${remaining}s`;
      if (remaining === 0) syncNow();
    }, 1000);
    syncNow().then(loadRecommendation);
  </script>
</body>
</html>
"""


def run_server(analyst: DraftAnalyst, host: str, port: int) -> None:
    live_sync = LiveDraftSync(analyst.settings, sleeper=analyst.sleeper)
    live_sync.start()

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
                if parsed.path == "/api/state":
                    params = parse_qs(parsed.query)
                    force = params.get("force", ["0"])[0] in {"1", "true", "yes"}
                    self.send_json(live_sync.snapshot(force=force).as_dict())
                    return
                if parsed.path == "/api/recommend":
                    params = parse_qs(parsed.query)
                    manual_state = params.get("manual_state", [None])[0]
                    use_sync = params.get("use_sync", ["1"])[0] not in {"0", "false", "no"}
                    snapshot = live_sync.snapshot(force=True) if use_sync and not manual_state else None
                    self.send_json(analyst.recommend(manual_state, snapshot))
                    return
                self.send_json({"error": "not found"}, 404)
            except Exception as exc:
                self.send_json({"error": str(exc)}, 500)

    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"Draft analyst running at http://{host}:{port}")
    try:
        httpd.serve_forever()
    finally:
        live_sync.stop()
