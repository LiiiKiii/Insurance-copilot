"""Run a local, blinded annotation UI for the M2 candidate dataset.

The tool shows only the evidence fields in ``m2_candidate_blind.json``. It
never calculates a relevance label. The annotator ranks the six eligible
candidates in each scenario, and the ranking is saved to the separate human
annotation file.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BLIND_DATASET = ROOT / "data" / "evaluation" / "m2_candidate_blind.json"
DEFAULT_ANNOTATIONS = ROOT / "data" / "evaluation" / "m2_candidate_annotations.json"
ANNOTATOR_IDS = ("non_m4_annotator_1", "non_m4_annotator_2")


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_ranking(ranking: Any, expected_ids: list[str]) -> list[str]:
    """Return a valid full ranking or raise a user-facing ValueError."""
    if not isinstance(ranking, list) or not all(isinstance(item, str) for item in ranking):
        raise ValueError("ranking 必须是候选编号数组")
    if len(ranking) != len(expected_ids):
        raise ValueError(f"必须完整排列 {len(expected_ids)} 个候选对象")
    if len(set(ranking)) != len(ranking):
        raise ValueError("同一候选对象不能重复出现")
    if set(ranking) != set(expected_ids):
        raise ValueError("排序中包含缺失或不属于该场景的候选编号")
    return ranking


def apply_ranking(
    annotations: dict[str, Any],
    scenario_id: str,
    annotator_id: str,
    ranking: Any,
) -> None:
    """Validate and apply one annotator's ranking without creating labels."""
    if annotator_id not in ANNOTATOR_IDS:
        raise ValueError("未知标注者")
    scenario = next(
        (row for row in annotations["scenarios"] if row["scenario_id"] == scenario_id),
        None,
    )
    if scenario is None:
        raise ValueError("未知场景")
    checked = validate_ranking(ranking, scenario["eligible_candidate_ids"])
    annotation = next(
        (row for row in scenario["annotations"] if row["annotator_id"] == annotator_id),
        None,
    )
    if annotation is None:
        raise ValueError("标注文件中没有该标注者槽位")
    annotation["ranking"] = checked


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def build_state(
    blind: dict[str, Any], annotations: dict[str, Any], annotator_id: str
) -> dict[str, Any]:
    saved = {
        scenario["scenario_id"]: next(
            row["ranking"]
            for row in scenario["annotations"]
            if row["annotator_id"] == annotator_id
        )
        for scenario in annotations["scenarios"]
    }
    presentation_orders = {}
    for scenario in blind["scenarios"]:
        candidate_ids = [row["candidate_id"] for row in scenario["candidates"]]
        seed_material = f"{annotator_id}|{scenario['scenario_id']}".encode("utf-8")
        seed = int.from_bytes(hashlib.sha256(seed_material).digest()[:8], "big")
        random.Random(seed).shuffle(candidate_ids)
        presentation_orders[scenario["scenario_id"]] = candidate_ids
    return {
        "dataset_id": blind["dataset_id"],
        "annotator_id": annotator_id,
        "as_of_date": "2026-05-31",
        "scenarios": blind["scenarios"],
        "saved_rankings": saved,
        "presentation_orders": presentation_orders,
    }


HTML_PAGE = r"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>M2 候选对象人工排序</title>
  <style>
    :root { --navy:#17345c; --blue:#2b68a9; --gold:#e6ad3c; --ink:#172235;
      --muted:#66758b; --line:#dbe3ee; --bg:#f3f6fa; --good:#19714b; }
    * { box-sizing:border-box; }
    body { margin:0; color:var(--ink); background:var(--bg); font:15px/1.5 system-ui,"Microsoft YaHei",sans-serif; }
    header { background:linear-gradient(120deg,var(--navy),#26598d); color:white; padding:24px 28px; }
    header h1 { margin:0 0 5px; font-size:25px; } header p { margin:0; opacity:.86; }
    .layout { display:grid; grid-template-columns:260px minmax(0,1fr); min-height:calc(100vh - 105px); }
    aside { padding:20px; background:white; border-right:1px solid var(--line); }
    .rule { padding:13px; margin-bottom:12px; border-radius:10px; background:#f5f8fc; }
    .rule strong { display:block; color:var(--navy); margin-bottom:3px; }
    .scenario-nav { display:grid; gap:7px; margin-top:18px; }
    .scenario-nav button { text-align:left; padding:9px 11px; border:1px solid var(--line); background:white; border-radius:8px; cursor:pointer; }
    .scenario-nav button.active { color:white; background:var(--blue); border-color:var(--blue); }
    .scenario-nav button.done::after { content:" ✓"; color:var(--good); font-weight:bold; }
    .scenario-nav button.active.done::after { color:#bdf2d6; }
    main { max-width:1050px; width:100%; padding:24px 30px 50px; margin:auto; }
    .question { padding:16px 18px; background:#fff6df; border-left:5px solid var(--gold); border-radius:8px; margin-bottom:17px; font-size:17px; }
    .meta { display:flex; gap:12px; flex-wrap:wrap; color:var(--muted); margin-bottom:14px; }
    .meta span { background:white; border:1px solid var(--line); border-radius:999px; padding:5px 10px; }
    .candidate { display:grid; grid-template-columns:54px minmax(0,1fr) 48px; gap:14px; align-items:center;
      background:white; border:1px solid var(--line); border-radius:12px; padding:14px; margin:9px 0; box-shadow:0 2px 8px #1c355008; }
    .candidate[draggable="true"] { cursor:grab; }
    .candidate.dragging { opacity:.45; }
    .rank { display:grid; place-items:center; width:43px; height:43px; border-radius:50%; background:var(--navy); color:white; font-size:20px; font-weight:700; }
    .candidate h3 { display:flex; gap:8px; align-items:center; margin:0 0 7px; font-size:16px; }
    .badge { color:var(--blue); background:#e9f2fb; padding:2px 8px; border-radius:999px; font-size:12px; }
    .facts { display:flex; gap:7px 18px; flex-wrap:wrap; color:#34445c; }
    .facts b { color:var(--ink); }
    .tags { color:var(--muted); margin-top:6px; }
    .moves { display:grid; gap:5px; }
    .moves button { border:1px solid var(--line); border-radius:7px; background:white; cursor:pointer; height:31px; }
    .actions { position:sticky; bottom:0; display:flex; align-items:center; justify-content:space-between; gap:12px;
      padding:13px 0; background:linear-gradient(#f3f6fa00,#f3f6fa 25%); }
    .actions button { padding:11px 17px; border:0; border-radius:8px; background:var(--blue); color:white; font-weight:600; cursor:pointer; }
    .actions button.secondary { background:white; color:var(--navy); border:1px solid var(--line); }
    #message { min-height:24px; color:var(--good); font-weight:600; }
    @media (max-width:780px) { .layout{grid-template-columns:1fr} aside{border-right:0;border-bottom:1px solid var(--line)} main{padding:18px}.scenario-nav{grid-template-columns:repeat(5,1fr)} }
  </style>
</head>
<body>
<header><h1>M2 候选对象人工排序</h1><p>只看业务证据；不展示 M4 结果，也不自动生成答案。</p></header>
<div class="layout">
  <aside>
    <div class="rule"><strong>评判谁？</strong>当前代理人名下 6 个合格的候选客户或待处理保单。</div>
    <div class="rule"><strong>评判什么？</strong>谁最值得代理人现在优先跟进，以便在截止日前缩小 open gap。</div>
    <div class="rule"><strong>怎么看？</strong>先看是否有明确行动，再看时间紧迫性与保费影响；金额不能单独决定排名。</div>
    <div class="rule"><strong>怎么填？</strong>拖动卡片或点箭头。第 1 名最优先，第 6 名最不优先；不允许并列。</div>
    <div class="rule"><strong>仍然相同时</strong>依次比较保费较高、提交较早、候选编号较小。初始显示顺序没有推荐含义。</div>
    <div id="nav" class="scenario-nav"></div>
  </aside>
  <main>
    <div class="question"><b>唯一问题：</b>如果代理人现在只能依次联系这些对象，你建议先联系谁？</div>
    <div id="meta" class="meta"></div>
    <div id="candidates"></div>
    <div class="actions">
      <span id="message"></span>
      <div><button class="secondary" id="save">保存本场景</button> <button id="next">保存并进入下一场景</button></div>
    </div>
  </main>
</div>
<script>
let state, current = 0, orders = {};
const statusText = {"Awaiting Documents":"等待补充材料（有明确行动）", "Underwriting":"核保中（直接行动较少）"};

async function start() {
  state = await (await fetch('/api/state')).json();
  state.scenarios.forEach(s => orders[s.scenario_id] =
    state.saved_rankings[s.scenario_id].length ? [...state.saved_rankings[s.scenario_id]] : [...state.presentation_orders[s.scenario_id]]);
  renderNav(); render();
}
function renderNav() {
  const nav = document.getElementById('nav'); nav.innerHTML='';
  state.scenarios.forEach((s,i) => { const b=document.createElement('button');
    b.textContent=`场景 ${i+1} · ${s.agent_id}`; b.className=(i===current?'active ':'')+(state.saved_rankings[s.scenario_id].length?'done':'');
    b.onclick=()=>{current=i;renderNav();render()}; nav.appendChild(b); });
}
function facts(c) {
  if (c.candidate_type === 'policy') return `<span><b>状态：</b>${statusText[c.policy_status]||c.policy_status}</span>
    <span><b>提交：</b>${c.submit_date}</span><span><b>审批周期：</b>${c.estimated_approval_days.min}–${c.estimated_approval_days.max} 天</span>`;
  return `<span><b>状态：</b>客户跟进线索</span><span><b>行动信号：</b>${c.client_tags.includes('Renewal Due')?'续保到期':c.client_tags.includes('Follow-up')?'需跟进':'一般'}</span>`;
}
function render() {
  const s=state.scenarios[current], byId=Object.fromEntries(s.candidates.map(c=>[c.candidate_id,c]));
  document.getElementById('meta').innerHTML=`<span>代理人：${s.agent_id}</span><span>Open gap：${money(s.open_gap)}</span><span>截止日：${s.deadline}</span><span>证据截至：${state.as_of_date}</span><span>产品专长：${s.agent_specialties.join(' · ')}</span>`;
  const box=document.getElementById('candidates'); box.innerHTML='';
  orders[s.scenario_id].forEach((id,index)=>{const c=byId[id], card=document.createElement('div'); card.className='candidate'; card.draggable=true; card.dataset.id=id;
    card.innerHTML=`<div class="rank">${index+1}</div><div><h3>${id}<span class="badge">${c.candidate_type==='policy'?'待处理保单':'候选客户'}</span></h3>
      <div class="facts"><span><b>保费：</b>${money(c.premium)}</span><span><b>产品：</b>${c.product_type}</span>${facts(c)}</div>
      <div class="tags"><b>客户标签：</b>${c.client_tags.join(' · ')}</div></div>
      <div class="moves"><button title="上移">▲</button><button title="下移">▼</button></div>`;
    card.querySelectorAll('button')[0].onclick=()=>move(index,-1); card.querySelectorAll('button')[1].onclick=()=>move(index,1);
    card.ondragstart=()=>card.classList.add('dragging'); card.ondragend=()=>card.classList.remove('dragging');
    card.ondragover=e=>{e.preventDefault(); const from=box.querySelector('.dragging'); if(!from||from===card)return; const a=orders[s.scenario_id]; const fi=a.indexOf(from.dataset.id), ti=a.indexOf(card.dataset.id); a.splice(ti,0,a.splice(fi,1)[0]); render();};
    box.appendChild(card); });
  document.getElementById('message').textContent='';
}
function move(index, delta) { const a=orders[state.scenarios[current].scenario_id], j=index+delta; if(j<0||j>=a.length)return; [a[index],a[j]]=[a[j],a[index]]; render(); }
function money(n){return new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:0}).format(n)}
async function save(goNext) { const s=state.scenarios[current]; const res=await fetch('/api/save',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({scenario_id:s.scenario_id,ranking:orders[s.scenario_id]})}); const body=await res.json();
  if(!res.ok){document.getElementById('message').textContent=body.error;return} state.saved_rankings[s.scenario_id]=[...orders[s.scenario_id]]; renderNav();
  if(goNext&&current<state.scenarios.length-1){current++;renderNav();render();document.getElementById('message').textContent='上一场景已保存';} else document.getElementById('message').textContent=body.completed===body.total?'你的 10 个场景已全部保存':'本场景已保存'; }
document.getElementById('save').onclick=()=>save(false); document.getElementById('next').onclick=()=>save(true); start();
</script></body></html>"""


def make_handler(
    blind_path: Path, annotations_path: Path, annotator_id: str
) -> type[BaseHTTPRequestHandler]:
    class AnnotationHandler(BaseHTTPRequestHandler):
        def send_json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/":
                body = HTML_PAGE.encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/api/state":
                self.send_json(build_state(read_json(blind_path), read_json(annotations_path), annotator_id))
                return
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/api/save":
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("请求内容大小无效")
                body = json.loads(self.rfile.read(length).decode("utf-8"))
                annotations = read_json(annotations_path)
                apply_ranking(annotations, body.get("scenario_id", ""), annotator_id, body.get("ranking"))
                write_json_atomic(annotations_path, annotations)
                completed = sum(
                    bool(next(row["ranking"] for row in scenario["annotations"] if row["annotator_id"] == annotator_id))
                    for scenario in annotations["scenarios"]
                )
                self.send_json({"ok": True, "completed": completed, "total": len(annotations["scenarios"])})
            except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
                self.send_json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

        def log_message(self, format: str, *args: Any) -> None:
            return

    return AnnotationHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="打开 M2 候选对象的盲评排序界面")
    parser.add_argument("--annotator", choices=ANNOTATOR_IDS, default=ANNOTATOR_IDS[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="不自动打开浏览器")
    parser.add_argument("--blind-dataset", type=Path, default=DEFAULT_BLIND_DATASET)
    parser.add_argument("--annotations", type=Path, default=DEFAULT_ANNOTATIONS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    blind = read_json(args.blind_dataset)
    annotations = read_json(args.annotations)
    build_state(blind, annotations, args.annotator)
    server = ThreadingHTTPServer(
        ("127.0.0.1", args.port),
        make_handler(args.blind_dataset, args.annotations, args.annotator),
    )
    url = f"http://127.0.0.1:{args.port}/"
    print(f"M2 标注界面：{url}")
    print("完成后在此窗口按 Ctrl+C 关闭。")
    if not args.no_browser:
        threading.Timer(0.3, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n标注服务已关闭。")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
