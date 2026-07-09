"""The Porofessor-style companion: run it, it opens a page, the page shows your game's note.

Stdlib only (http.server) so it packages into a single .exe with PyInstaller and friends
need nothing installed. It polls the local League client; when a game is detected it renders
the coaching note, otherwise it shows the example so the app visibly 'works' before a game.

    python -m coach.serve            # opens http://127.0.0.1:7379 in your browser
"""
from __future__ import annotations
import html
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from . import coach as make_note
from .live import read_live_game

PORT = 7379
EXAMPLE = (["Ornn", "Sejuani", "Orianna", "Ezreal", "Karma"],
           ["Renekton", "LeeSin", "LeBlanc", "Caitlyn", "Blitzcrank"])

PAGE = """\
<meta http-equiv="refresh" content="6">
<title>Cairn</title>
<style>
  :root{{color-scheme:dark}}
  body{{margin:0;background:#0d1117;color:#e6edf3;font:15px/1.55 ui-monospace,Consolas,monospace}}
  header{{padding:14px 20px;background:#161b22;border-bottom:1px solid #30363d;display:flex;
         justify-content:space-between;align-items:center}}
  h1{{font-size:15px;margin:0;letter-spacing:.5px}}
  .status{{font-size:13px;color:{status_color}}}
  pre{{padding:20px;white-space:pre-wrap;margin:0}}
  .hint{{padding:8px 20px;color:#7d8590;font-size:12px;border-top:1px solid #30363d}}
</style>
<header><h1>CAIRN · sticky note</h1><span class="status">{status}</span></header>
<pre>{note}</pre>
<div class="hint">Auto-refreshes every 6s · reads your live League game locally · no data leaves your PC</div>
<div class="hint" style="font-size:11px">Cairn isn't endorsed by Riot Games and doesn't reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc.</div>
"""


def _render() -> str:
    game = read_live_game()
    if game:
        you, enemy, meta = game
        note = make_note(you, enemy)
        status = f"Live game detected — {meta['my_side']} side"
        color = "#3fb950"
    else:
        note = make_note(*EXAMPLE)
        status = "Waiting for a League game… (showing example)"
        color = "#d29922"
    return PAGE.format(status=html.escape(status), status_color=color,
                       note=html.escape(note))


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/index.html"):
            self.send_error(404)
            return
        body = _render().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *a):  # quiet console
        pass


def main():
    url = f"http://127.0.0.1:{PORT}"
    print(f"Coach running at {url}  (Ctrl+C to stop). Launch a League game and it auto-detects.")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
