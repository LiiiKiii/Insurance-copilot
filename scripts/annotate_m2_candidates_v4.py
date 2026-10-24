"""Independent evidence-only v4 annotation UI; no ranking or labels are generated."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from scripts.build_m2_candidate_dataset_v4 import ANNOTATORS, DATASET_ID, ROOT


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def state(blind, annotations, annotator):
    if (
        annotator not in ANNOTATORS
        or blind.get("dataset_id") != DATASET_ID
        or annotations.get("dataset_id") != DATASET_ID
    ):
        raise ValueError("Expected matching v4 files and a v4 annotator")
    if blind.get("data_fingerprint") != annotations.get("data_fingerprint"):
        raise ValueError("Evidence fingerprint mismatch")
    saved = {}
    saved_notes = {}
    completed = {}
    orders = {}
    for scenario in annotations["scenarios"]:
        slot = next(
            a for a in scenario["annotations"] if a["annotator_id"] == annotator
        )
        saved[scenario["scenario_id"]] = slot["ranking"]
        saved_notes[scenario["scenario_id"]] = slot.get("notes", "")
        completed[scenario["scenario_id"]] = bool(slot.get("completed", False))
    for scenario in blind["scenarios"]:
        ids = list(scenario["formal_ranking_candidate_ids"])
        seed = int.from_bytes(
            hashlib.sha256(
                f"{annotator}|{scenario['scenario_id']}|v4".encode()
            ).digest()[:8],
            "big",
        )
        random.Random(seed).shuffle(ids)
        orders[scenario["scenario_id"]] = ids
    return {
        "dataset_id": DATASET_ID,
        "annotator": annotator,
        "scenarios": blind["scenarios"],
        "saved": saved,
        "notes": saved_notes,
        "completed": completed,
        "presentation_orders": orders,
    }


def save(annotations, annotator, scenario_id, ranking, notes):
    if annotator not in ANNOTATORS:
        raise ValueError("Unknown annotator")
    scenario = next(
        (s for s in annotations["scenarios"] if s["scenario_id"] == scenario_id), None
    )
    if scenario is None:
        raise ValueError("Unknown scenario")
    if not isinstance(ranking, list) or any(not isinstance(x, str) for x in ranking):
        raise ValueError("Ranking must be a list of candidate IDs")
    expected = scenario["ranking_candidate_ids"]
    if (
        len(ranking) != len(expected)
        or len(set(ranking)) != len(ranking)
        or set(ranking) != set(expected)
    ):
        raise ValueError(
            "Rank every formal in-horizon candidate exactly once; do not add future or unsupported credits"
        )
    if not isinstance(notes, str) or len(notes) > 5000:
        raise ValueError("Notes must be text up to 5000 characters")
    slot = next(a for a in scenario["annotations"] if a["annotator_id"] == annotator)
    slot.update(ranking=ranking, notes=notes, completed=True)


HTML = r"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>M2 v4 independent annotation</title>
<style>body{margin:0;background:#f3f6fa;color:#18314c;font:15px/1.5 system-ui}header{background:#17345c;color:white;padding:20px}main{max-width:1050px;margin:20px auto;padding:0 18px}.panel,.card{background:white;border:1px solid #d5deea;border-radius:10px;padding:15px;margin:12px 0}.card{display:flex;gap:15px}.facts{flex:1}.muted{color:#65758a}button,select,textarea{font:inherit;padding:8px;border:1px solid #bdcad9;border-radius:7px}button{cursor:pointer;background:#e9f1fa}h2{font-size:19px}pre{white-space:pre-wrap;word-break:break-word;font-size:12px}.controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}#message{font-weight:600}textarea{box-sizing:border-box;width:100%;min-height:70px}</style></head><body>
<header><h1>M2 v4 independent annotation</h1><div>Fresh 30-day USD written-premium judgement. Do not consult other annotators, M4 scores or v3 rankings.</div></header>
<main><div class="controls"><label>Scenario <select id="scenarios"></select></label><span id="progress"></span></div><section id="objective" class="panel"></section>
<div class="panel">Rank who should be followed up first to reduce the exact horizon gap. Consider a clear action, timing, premium impact and product fit. An action deadline is not a crediting date. Estimates and target assumptions are synthetic and uncertain. Rank only the in-window cards; review excluded evidence separately.</div>
<h2>Formal in-horizon ranking</h2><div id="cards"></div><h2>Outside formal horizon ranking</h2><div id="outside"></div>
<label>Independent reasoning / disagreement with assumptions<textarea id="notes"></textarea></label><div class="controls"><button id="save">Save scenario</button><button id="next">Save and next</button><span id="message"></span></div></main>
<script>
let data,index=0,orders={},notes={};
const el=(tag,text,cls)=>{const x=document.createElement(tag);if(text!==undefined)x.textContent=text;if(cls)x.className=cls;return x};
const money=n=>'USD '+Number(n).toLocaleString('en-US');
function card(c,rank,move){const box=el('div',undefined,'card');if(rank)box.append(el('strong',String(rank)));const f=el('div',undefined,'facts');f.append(el('strong',c.candidate_id+' · '+c.product_type));f.append(el('div','Premium '+money(c.premium)+' · Action by '+(c.action_deadline||'unknown')));f.append(el('div','Expected credit '+(c.expected_realization_date||'unsupported')+' · '+c.realization_group));f.append(el('div',c.action_signal));f.append(el('div',(c.client_tags||[]).join(' · '),'muted'));if(c.out_of_horizon_reason)f.append(el('div',c.out_of_horizon_reason,'muted'));const d=el('details');d.append(el('summary','Evidence / timeline assumption'));d.append(el('pre',JSON.stringify(c.expected_realization_source,null,2)));f.append(d);box.append(f);if(move){const controls=el('div');for(const [symbol,delta] of [['↑',-1],['↓',1]]){const b=el('button',symbol);b.type='button';b.onclick=()=>move(delta);controls.append(b)}box.append(controls)}return box}
function render(){const s=data.scenarios[index],o=s.objective;document.getElementById('scenarios').value=String(index);const target=document.getElementById('objective');target.replaceChildren(el('h2',s.scenario_id+' · '+data.annotator));target.append(el('div',o.planning_horizon_start+' through '+o.planning_horizon_end+' inclusive · '+o.business_timezone));target.append(el('div','Target '+money(o.horizon_target)+' · Confirmed current '+money(o.horizon_current)+' · Horizon gap '+money(o.horizon_open_gap)));target.append(el('div','Snapshot/cutoff '+o.data_cutoff));target.append(el('div','Agent specialties: '+s.agent_specialties.join(' · ')));target.append(el('div','Annual gap '+money(o.annual_open_gap)+' (annual monitoring only; not this ranking denominator)','muted'));const source=el('details');source.append(el('summary','Target and current provenance'));source.append(el('pre',JSON.stringify({target:o.horizon_target_source,current:o.horizon_current_source},null,2)));target.append(source);const byId=Object.fromEntries(s.candidates.map(c=>[c.candidate_id,c]));const cards=document.getElementById('cards');cards.replaceChildren();orders[s.scenario_id].forEach((id,i)=>cards.append(card(byId[id],i+1,delta=>{const a=orders[s.scenario_id],j=i+delta;if(j<0||j>=a.length)return;[a[i],a[j]]=[a[j],a[i]];render()})));if(!orders[s.scenario_id].length)cards.append(el('div','No supported in-window candidates; no ranking can be supplied.'));const outside=document.getElementById('outside');outside.replaceChildren();s.candidates.filter(c=>!s.formal_ranking_candidate_ids.includes(c.candidate_id)).forEach(c=>outside.append(card(c)));document.getElementById('notes').value=notes[s.scenario_id]||'';document.getElementById('progress').textContent=Object.values(data.completed).filter(Boolean).length+'/10 saved';document.getElementById('message').textContent=''}
async function submit(next){const s=data.scenarios[index];notes[s.scenario_id]=document.getElementById('notes').value;const r=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario_id:s.scenario_id,ranking:orders[s.scenario_id],notes:notes[s.scenario_id]})});const b=await r.json();if(!r.ok){document.getElementById('message').textContent=b.error;return}data.completed[s.scenario_id]=true;if(next&&index<data.scenarios.length-1)index++;render();document.getElementById('message').textContent='Saved your independent ranking; no consensus labels were generated.'}
document.getElementById('notes').oninput=e=>notes[data.scenarios[index].scenario_id]=e.target.value;document.getElementById('scenarios').onchange=e=>{index=Number(e.target.value);render()};document.getElementById('save').onclick=()=>submit(false);document.getElementById('next').onclick=()=>submit(true);
(async()=>{data=await(await fetch('/api/state')).json();notes=data.notes;data.scenarios.forEach((s,i)=>{orders[s.scenario_id]=data.saved[s.scenario_id].length?[...data.saved[s.scenario_id]]:[...data.presentation_orders[s.scenario_id]];document.getElementById('scenarios').append(new Option(s.scenario_id,String(i)))});render()})();
</script></body></html>"""


def handler(blind_path, annotation_path, annotator):
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def send_json(self, payload, code=200):
            raw = json.dumps(payload, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def do_GET(self):
            if self.path == "/":
                raw = HTML.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
            elif self.path == "/api/state":
                self.send_json(
                    state(read(blind_path), read(annotation_path), annotator)
                )
            else:
                self.send_error(404)

        def do_POST(self):
            if self.path != "/api/save":
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 100000:
                    raise ValueError("Invalid request size")
                payload = json.loads(self.rfile.read(length))
                with lock:
                    doc = read(annotation_path)
                    state(read(blind_path), doc, annotator)
                    save(
                        doc,
                        annotator,
                        payload["scenario_id"],
                        payload["ranking"],
                        payload.get("notes", ""),
                    )
                    temporary = annotation_path.with_suffix(".json.tmp")
                    temporary.write_text(
                        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8",
                    )
                    temporary.replace(annotation_path)
                self.send_json({"ok": True})
            except (ValueError, TypeError, KeyError, StopIteration) as exc:
                self.send_json({"error": str(exc)}, 400)

        def log_message(self, *args):
            pass

    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annotator", choices=ANNOTATORS, required=True)
    parser.add_argument("--port", type=int)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    blind = ROOT / "data/evaluation/m2_candidate_blind_v4.json"
    annotations = (
        ROOT / f"data/evaluation/m2_candidate_annotations_v4_{args.annotator}.json"
    )
    state(read(blind), read(annotations), args.annotator)
    port = args.port or 8771 + ANNOTATORS.index(args.annotator)
    server = ThreadingHTTPServer(
        ("127.0.0.1", port), handler(blind, annotations, args.annotator)
    )
    url = f"http://127.0.0.1:{port}/"
    print(f"Independent v4 annotation: {url}; saves only {annotations.name}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
