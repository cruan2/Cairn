"""Daily 'Guess the Win Condition' web game that collects rank-weighted labels.

Run:   python -m game.server        (http://127.0.0.1:5000)
Deploy: any host that runs Flask (Render/Fly/Replit free tier). Set RIOT_API_KEY to enable
        account verification; without it, players use self-report or stay anonymous.

Trust is decided SERVER-SIDE from the session, never from what the client claims:
  - anonymous by default,
  - self_reported after POST /api/selfreport (capped),
  - verified only after the Riot ownership check passes.
"""
from __future__ import annotations
import datetime as _dt
import secrets

from flask import Flask, jsonify, request, session

from .daily import daily_puzzle
from .puzzle import LABELS, score
from .envfile import load_env
from . import store, trust, riot

import os
load_env()  # pull .env into os.environ before anything reads a key

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET") or secrets.token_hex(16)

# session-scoped verification state and per-day pending nonces (in-memory: fine for MVP)
_PENDING: dict[str, dict] = {}


def _sid() -> str:
    if "sid" not in session:
        session["sid"] = secrets.token_hex(8)
        session["tier"] = "anonymous"
        session["rank"] = None
        session["voted"] = []
    return session["sid"]


PAGE = """<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Guess the Win Condition</title>
<style>
 :root{color-scheme:dark}
 *{box-sizing:border-box} body{margin:0;background:#0d1117;color:#e6edf3;
   font:16px/1.5 ui-sans-serif,system-ui,Segoe UI,Roboto,sans-serif}
 .wrap{max-width:720px;margin:0 auto;padding:24px 18px}
 h1{font-size:20px;margin:0 0 2px} .sub{color:#7d8590;font-size:13px;margin-bottom:18px}
 .card{background:#161b22;border:1px solid #30363d;border-radius:12px;padding:16px;margin:14px 0}
 .teams{display:grid;grid-template-columns:1fr 1fr;gap:12px}
 .team h3{margin:0 0 6px;font-size:13px;letter-spacing:.4px}
 .blue h3{color:#58a6ff} .red h3{color:#ff7b72}
 .champ{background:#0d1117;border:1px solid #30363d;border-radius:6px;padding:4px 8px;margin:3px 0;font-size:14px}
 button.opt{display:block;width:100%;text-align:left;margin:8px 0;padding:12px 14px;border-radius:10px;
   border:1px solid #30363d;background:#21262d;color:#e6edf3;font-size:15px;cursor:pointer}
 button.opt:hover{border-color:#58a6ff}
 .pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;border:1px solid #30363d}
 .tier-anonymous{color:#7d8590} .tier-self_reported{color:#d29922} .tier-verified{color:#3fb950;border-color:#238636}
 .result{font-size:15px} .stars{font-size:22px;color:#f0b429}
 select,input{background:#0d1117;color:#e6edf3;border:1px solid #30363d;border-radius:8px;padding:8px}
 button.act{padding:8px 12px;border-radius:8px;border:1px solid #30363d;background:#238636;color:#fff;cursor:pointer}
 .bar{height:8px;background:#30363d;border-radius:6px;overflow:hidden;margin-top:4px}
 .bar>i{display:block;height:100%;background:#58a6ff}
 a{color:#58a6ff} small{color:#7d8590}
</style></head><body><div class=wrap>
 <h1>Guess the Win Condition</h1>
 <div class=sub>Daily puzzle · your read helps train the coach · <span id=tier class=pill>…</span></div>

 <div class=card id=puzzle>loading…</div>

 <div class=card id=login>
   <b>Make your vote count more</b>
   <div class=sub>Anonymous votes are counted but weighted low. Self-report for a bit more; verify your Riot account for full weight.</div>
   <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-top:8px">
     <select id=srank>
       <option value="">— your rank —</option>
       <option>IRON</option><option>BRONZE</option><option>SILVER</option><option>GOLD</option>
       <option>PLATINUM</option><option>EMERALD</option><option>DIAMOND</option>
       <option>MASTER</option><option>GRANDMASTER</option><option>CHALLENGER</option>
     </select>
     <button class=act onclick=selfreport()>Self-report</button>
     <span id=verifybox></span>
   </div>
 </div>
 <div class=sub><small>Result &amp; live consensus appear after you vote. Rank-weighted, Rankdle-style.</small></div>
</div>
<script>
let PZ=null;
async function load(){
  const r=await fetch('/api/daily'); PZ=await r.json();
  document.getElementById('tier').textContent=PZ.you.tier.replace('_',' ')+(PZ.you.rank?(' · '+PZ.you.rank):'');
  document.getElementById('tier').className='pill tier-'+PZ.you.tier;
  renderPuzzle();
  renderVerify(PZ.verify_available);
}
function champs(list){return list.map(c=>`<div class=champ>${c}</div>`).join('')}
function renderPuzzle(){
  const p=document.getElementById('puzzle');
  if(PZ.you.already_voted){return renderResult(PZ.result);}
  p.innerHTML=`<div class=teams>
      <div class="team blue"><h3>BLUE</h3>${champs(PZ.blue)}</div>
      <div class="team red"><h3>RED</h3>${champs(PZ.red)}</div></div>
    <div style=margin-top:14px><b>${PZ.question}</b></div>
    ${PZ.options.map(o=>`<button class=opt onclick="vote('${o.key}')">${o.label}</button>`).join('')}`;
}
async function vote(ans){
  const r=await fetch('/api/vote',{method:'POST',headers:{'Content-Type':'application/json'},
     body:JSON.stringify({answer:ans})});
  const d=await r.json(); renderResult(d);
}
function renderResult(d){
  const p=document.getElementById('puzzle');
  const stars='★'.repeat(d.stars)+'☆'.repeat(2-d.stars);
  const c=d.consensus, tot=Object.values(c.breakdown).reduce((a,b)=>a+b.weight,0)||1;
  const rows=PZ.options.map(o=>{const b=c.breakdown[o.key];const pct=Math.round(100*b.weight/tot);
     return `<div style=margin:6px0><small>${o.label} — ${b.raw} votes</small>
       <div class=bar><i style=width:${pct}%></i></div></div>`}).join('');
  p.innerHTML=`<div class=result>You said <b>${LABEL(d.your_answer)}</b>
     &nbsp; <span class=stars>${stars}</span></div>
     <div class=sub style=margin:8px0>Crowd consensus (rank-weighted): <b>${LABEL(c.answer)}</b>
       · ${Math.round(c.agreement*100)}% agreement · n=${c.n}</div>
     ${rows}
     <div class=sub style=margin-top:10px>${c.flag_engine_bug?'⚠ crowd disagrees with the engine — logged as a rule to review.':'✓ your answer is now part of the dataset.'}</div>`;
}
function LABEL(k){const o=(PZ.options||[]).find(x=>x.key===k);return o?o.label:k}
async function selfreport(){
  const rank=document.getElementById('srank').value; if(!rank)return;
  await fetch('/api/selfreport',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rank})});
  load();
}
function renderVerify(avail){
  const b=document.getElementById('verifybox');
  if(!avail){b.innerHTML='<small>Riot verification off (no API key configured).</small>';return;}
  b.innerHTML=`<input id=rid placeholder="Name#TAG" style=width:120px>
     <input id=plat placeholder="na1" style=width:60px value=na1>
     <button class=act onclick=vstart()>Verify</button>`;
}
async function vstart(){
  const riot_id=document.getElementById('rid').value, platform=document.getElementById('plat').value;
  const r=await fetch('/api/verify/start',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({riot_id,platform})}); const d=await r.json();
  if(d.error){alert(d.error);return;}
  document.getElementById('verifybox').innerHTML=
    `<small>Paste this into League → Settings → Verification, then click Check:</small><br>
     <code style="background:#0d1117;padding:4px 8px;border-radius:6px">${d.nonce}</code>
     <button class=act onclick=vcheck()>Check</button>`;
}
async function vcheck(){
  const r=await fetch('/api/verify/check',{method:'POST'}); const d=await r.json();
  if(d.verified){alert('Verified'+(d.rank?(' as '+d.rank):' (unranked)'));load();}
  else alert(d.error||'Code not found yet — set it in the client and try again.');
}
load();
</script></body></html>"""


@app.get("/")
def index():
    _sid()
    return PAGE


@app.get("/api/daily")
def api_daily():
    _sid()
    pz = daily_puzzle()
    session["engine_answer"] = pz.engine_answer
    session["puzzle_id"] = pz.puzzle_id
    already = pz.puzzle_id in session.get("voted", [])
    payload = {
        "puzzle_id": pz.puzzle_id, "question": pz.question,
        "blue": pz.blue, "red": pz.red,
        "options": [{"key": k, "label": LABELS[k]} for k in pz.options],
        "you": {"tier": session.get("tier", "anonymous"), "rank": session.get("rank"),
                "already_voted": already},
        "verify_available": riot.has_key(),
    }
    if already:
        payload["result"] = _result_payload(pz.puzzle_id, pz.engine_answer,
                                             session.get("last_answer", ""))
    return jsonify(payload)


def _result_payload(puzzle_id, engine_answer, your_answer):
    c = store.consensus(puzzle_id, engine_answer)
    return {"your_answer": your_answer, "stars": score(your_answer, engine_answer),
            "consensus": c.__dict__}


@app.post("/api/vote")
def api_vote():
    _sid()
    pid = session.get("puzzle_id")
    engine_answer = session.get("engine_answer", "")
    if not pid:
        return jsonify({"error": "load a puzzle first"}), 400
    if pid in session.get("voted", []):
        return jsonify(_result_payload(pid, engine_answer, session.get("last_answer", "")))
    ans = (request.get_json(silent=True) or {}).get("answer", "")
    if ans not in LABELS:
        return jsonify({"error": "bad answer"}), 400
    store.record_vote(pid, ans, session.get("tier", "anonymous"), session.get("rank"),
                      session["sid"], ts=_dt.datetime.utcnow().isoformat() + "Z")
    session["voted"] = session.get("voted", []) + [pid]
    session["last_answer"] = ans
    return jsonify(_result_payload(pid, engine_answer, ans))


@app.post("/api/selfreport")
def api_selfreport():
    _sid()
    rank = (request.get_json(silent=True) or {}).get("rank", "").upper()
    if rank not in trust.RANK_MULT:
        return jsonify({"error": "unknown rank"}), 400
    # never upgrade a verified session down to self-report
    if session.get("tier") != "verified":
        session["tier"] = "self_reported"
        session["rank"] = rank
    return jsonify({"ok": True, "tier": session["tier"], "rank": session["rank"]})


@app.post("/api/verify/start")
def api_verify_start():
    _sid()
    if not riot.has_key():
        return jsonify({"error": "verification disabled (no RIOT_API_KEY)"}), 503
    body = request.get_json(silent=True) or {}
    try:
        info = riot.resolve_summoner(body.get("riot_id", ""), body.get("platform", "na1"))
    except Exception as e:
        return jsonify({"error": f"could not find that Riot ID ({e})"}), 400
    nonce = "COACH-" + secrets.token_hex(3).upper()
    _PENDING[session["sid"]] = {**info, "platform": body.get("platform", "na1"), "nonce": nonce}
    return jsonify({"nonce": nonce})


@app.post("/api/verify/check")
def api_verify_check():
    _sid()
    p = _PENDING.get(session["sid"])
    if not p:
        return jsonify({"error": "start verification first"}), 400
    try:
        ok, rank = riot.verify_ownership(p["summoner_id"], p["platform"], p["nonce"])
    except Exception as e:
        return jsonify({"error": f"verification failed ({e})"}), 400
    if not ok:
        return jsonify({"verified": False, "error": "code not set yet"})
    session["tier"] = "verified"
    session["rank"] = rank or "UNRANKED"
    _PENDING.pop(session["sid"], None)
    return jsonify({"verified": True, "rank": rank})


def main():
    print("Daily game at http://127.0.0.1:5000")
    print("Riot verification:", "ON" if riot.has_key() else "OFF (set RIOT_API_KEY to enable)")
    app.run(host="127.0.0.1", port=5000, debug=False)


if __name__ == "__main__":
    main()
