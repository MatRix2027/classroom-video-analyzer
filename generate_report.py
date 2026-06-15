"""Generate QC-v4 HTML analysis report."""
import json

cards = {}
for i in [1, 2, 3]:
    with open(f"output/slice_{i}_qc_v4/score_card.json", "r", encoding="utf-8") as f:
        cards[f"slice_{i}"] = json.load(f)

dim_names = [d["name"] for d in cards["slice_1"]["dimensions"]]

# CSS
css = """
:root{--bg:#f5f7fa;--card:#fff;--text:#2d3748;--muted:#718096;--border:#e2e8f0;
  --green:#38a169;--blue:#3182ce;--orange:#dd6b20;--red:#e53e3e;--teal:#319795}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
  background:var(--bg);color:var(--text);line-height:1.6}
.container{max-width:1200px;margin:0 auto;padding:20px}
header{background:linear-gradient(135deg,#1a365d,#2a4365);color:#fff;padding:40px 20px;text-align:center}
header h1{font-size:2rem;margin-bottom:8px}
header p{opacity:.85;font-size:1rem}
.grid-3{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:20px 0}
.stat-card{background:var(--card);border-radius:12px;padding:20px;text-align:center;
  box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--border)}
.stat-card .label{color:var(--muted);font-size:.85rem;margin-bottom:4px}
.stat-card .value{font-size:2rem;font-weight:700}
.stat-card .sub{color:var(--muted);font-size:.8rem;margin-top:4px}
.chart-row{display:grid;grid-template-columns:1fr 1fr;gap:20px;margin:20px 0}
.chart-card{background:var(--card);border-radius:12px;padding:20px;
  box-shadow:0 1px 3px rgba(0,0,0,.08);border:1px solid var(--border)}
.chart-card h3{font-size:1.1rem;margin-bottom:16px}
canvas{max-height:400px}
.grade-badge{display:inline-block;padding:4px 12px;border-radius:20px;font-weight:600;font-size:.85rem}
.grade-good{background:#bee3f8;color:#2a4365}
.grade-mid{background:#fefcbf;color:#975a16}
.grade-poor{background:#fed7d7;color:#822727}
.tabs{display:flex;gap:4px;margin:20px 0;background:var(--card);border-radius:12px;
  padding:4px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.tab-btn{flex:1;padding:12px;border:none;background:transparent;border-radius:8px;
  cursor:pointer;font-size:.9rem;font-weight:600;color:var(--muted);transition:all .2s}
.tab-btn.active{background:#ebf8ff;color:var(--blue)}
.tab-content{display:none}
.tab-content.active{display:block}
.dim-table{width:100%;border-collapse:collapse;background:var(--card);
  border-radius:12px;overflow:hidden;box-shadow:0 1px 3px rgba(0,0,0,.08);margin-bottom:20px}
.dim-table th{background:#f7fafc;padding:12px 16px;text-align:left;font-size:.85rem;
  color:var(--muted);font-weight:600;border-bottom:2px solid var(--border)}
.dim-table td{padding:10px 16px;border-bottom:1px solid var(--border);font-size:.9rem}
.dim-table tr:hover{background:#f7fafc}
.score-bar-bg{width:100%;height:8px;background:#edf2f7;border-radius:4px;overflow:hidden}
.score-bar-fill{height:100%;border-radius:4px}
.sp-card{background:var(--card);border-radius:8px;padding:16px;margin:12px 0;border:1px solid var(--border)}
.sp-card h4{font-size:.95rem;margin-bottom:8px;display:flex;align-items:center;gap:8px}
.sp-tag{display:inline-block;padding:2px 6px;border-radius:4px;font-size:.75rem;font-weight:700}
.sp-tag.plus{background:#c6f6d5;color:#22543d}
.sp-tag.minus{background:#fed7d7;color:#822727}
.sp-item{font-size:.85rem;padding:6px 0;border-bottom:1px dashed var(--border);
  display:flex;gap:8px;align-items:flex-start}
.sp-item:last-child{border-bottom:none}
.quote{color:var(--teal);font-style:italic;font-size:.8rem}
footer{text-align:center;padding:30px;color:var(--muted);font-size:.85rem}
@media(max-width:768px){.grid-3,.chart-row{grid-template-columns:1fr}}
"""

parts = []
parts.append("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>课堂视频质量分析报告 - QC-v4</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>""")
parts.append(css)
parts.append("</style></head><body>")

# Header
parts.append("""<header>
<h1>课堂视频质量分析报告</h1>
<p>QC-v4 新版课中质检标准 | 3轮评估取均值 | 合格线75分</p>
<p style="font-size:.85rem;margin-top:8px;opacity:.7">L8-C71《探索物不知数(上)》| 2026-06-04</p>
</header><div class="container">""")

# Summary cards
parts.append('<div class="grid-3">')
labels = {"slice_1": "切片 1 (0-70s)", "slice_2": "切片 2 (70-140s)", "slice_3": "切片 3 (140-210s)"}
for key, label in labels.items():
    c = cards[key]
    parts.append(f"""<div class="stat-card"><div class="label">{label}</div>
<div class="value">{c["total_score"]:.0f}<span style="font-size:1rem;color:var(--muted)">/{c["total_max"]:.0f}</span></div>
<div class="sub"><span class="grade-badge grade-good">{c["grade"]}</span> · {c["num_rounds"]}轮</div></div>""")
parts.append('</div>')

# Charts
parts.append("""<div class="chart-row">
<div class="chart-card"><h3>雷达图：10维度对比</h3><canvas id="radarChart"></canvas></div>
<div class="chart-card"><h3>总分对比</h3><canvas id="barChart"></canvas></div>
</div>""")

# Tabs
parts.append("""<div class="tabs">
<button class="tab-btn active" onclick="switchTab('slice1')">切片 1 (0-70s)</button>
<button class="tab-btn" onclick="switchTab('slice2')">切片 2 (70-140s)</button>
<button class="tab-btn" onclick="switchTab('slice3')">切片 3 (140-210s)</button>
</div>""")

# Tab content for each slice
for key, tab_id in [("slice_1", "slice1"), ("slice_2", "slice2"), ("slice_3", "slice3")]:
    c = cards[key]
    active = ' active' if tab_id == 'slice1' else ''
    parts.append(f'<div class="tab-content{active}" id="{tab_id}">')
    
    # Dimension table
    parts.append('<table class="dim-table"><thead><tr><th>维度</th><th>评分</th><th>等级</th><th>满分</th><th>标准差</th><th>3轮原始分</th></tr></thead><tbody>')
    for d in c["dimensions"]:
        pct = d["score"] / d["max_score"] * 100
        if pct >= 85: color = "var(--green)"
        elif pct >= 75: color = "var(--blue)"
        elif pct >= 50: color = "var(--orange)"
        else: color = "var(--red)"
        
        grd = d["grade"]
        if grd == "优": gcls = "grade-good"
        elif grd in ("良", "中"): gcls = "grade-mid"
        else: gcls = "grade-poor"
        
        rounds_str = " · ".join(f"{r:.1f}" for r in d["round_scores"])
        parts.append(f"""<tr>
<td><strong>{d["name"]}</strong></td>
<td><div style="display:flex;align-items:center;gap:8px">
<span style="font-weight:700;min-width:40px">{d["score"]:.1f}</span>
<div class="score-bar-bg"><div class="score-bar-fill" style="width:{pct}%;background:{color}"></div></div></div></td>
<td><span class="grade-badge {gcls}">{grd}</span></td>
<td>{d["max_score"]:.0f}</td>
<td>{d["score_std"]:.2f}</td>
<td><span style="font-size:.8rem;color:var(--muted)">{rounds_str}</span></td></tr>""")
    parts.append('</tbody></table>')
    
    # Scoring points per dimension
    skip_quotes = {
        "（文本结束）", "（无相关文本）", "（转录文本为纯音频）", "（无视频信息）",
        "（转录文本仅5秒）", "（无相关证据）", "（转录文本中无相关描述）",
        "（转录文本仅包含5秒内容）", "（转录文本仅包含约5秒内容）",
        "（转录文本中仅有一位学生应答）", "（转录文本为纯文本，无相关证据）",
        "（转录文本仅5秒，仅有一位学生互动）", "（转录文本仅5秒，无例题或练习题内容）",
        "（整体语言流畅度尚可）", "（转录文本中无相关描述）",
        "（转录文本中仅有一位学生应答）",
    }
    for d in c["dimensions"]:
        sps = d.get("scoring_points", [])
        if not sps: continue
        pos_count = sum(1 for sp in sps if sp["type"] == "+")
        neg_count = sum(1 for sp in sps if sp["type"] == "-")
        evidence = d.get("evidence", "")
        
        parts.append(f'<div class="sp-card"><h4>{d["name"]} <span class="sp-tag plus">+{pos_count}</span> <span class="sp-tag minus">-{neg_count}</span></h4>')
        if evidence:
            parts.append(f'<div style="font-size:.85rem;color:var(--muted);margin-bottom:8px">{evidence}</div>')
        
        for sp in sps:
            tag_class = "plus" if sp["type"] == "+" else "minus"
            time_str = f' [{sp["at"]}s]' if sp.get("at") is not None else ''
            q = sp.get("quote", "")
            if q and q not in skip_quotes and not q.startswith("（"):
                quote_html = f'<div class="quote">\u300c{q}\u300d{time_str}</div>'
            else:
                quote_html = ''
            parts.append(f'<div class="sp-item"><span class="sp-tag {tag_class}">{sp["type"]}</span><div><div>{sp["reason"]}</div>{quote_html}</div></div>')
        parts.append('</div>')
    parts.append('</div>')

# Chart.js
s1 = ','.join(f'{d["score"]/d["max_score"]*10:.1f}' for d in cards["slice_1"]["dimensions"])
s2 = ','.join(f'{d["score"]/d["max_score"]*10:.1f}' for d in cards["slice_2"]["dimensions"])
s3 = ','.join(f'{d["score"]/d["max_score"]*10:.1f}' for d in cards["slice_3"]["dimensions"])
dn = json.dumps(dim_names, ensure_ascii=False)
t1 = cards['slice_1']['total_score']
t2 = cards['slice_2']['total_score']
t3 = cards['slice_3']['total_score']

parts.append(f"""</div>
<footer><p>课堂视频智能分析工具 v1.0.0 · QC-v4 新版课中质检标准 · 合格线75分</p>
<p>基于火花思维教学评价体系 · 3轮LLM独立评估取均值+标准差</p></footer>
<script>
var dimNames={dn};
new Chart(document.getElementById("radarChart"),{{type:"radar",data:{{labels:dimNames,datasets:[
{{label:"切片1(0-70s)",data:[{s1}],borderColor:"#3182ce",backgroundColor:"rgba(49,130,206,.15)",borderWidth:2}},
{{label:"切片2(70-140s)",data:[{s2}],borderColor:"#38a169",backgroundColor:"rgba(56,161,105,.15)",borderWidth:2}},
{{label:"切片3(140-210s)",data:[{s3}],borderColor:"#dd6b20",backgroundColor:"rgba(221,107,32,.15)",borderWidth:2}}]}},
options:{{responsive:true,scales:{{r:{{min:0,max:10,ticks:{{stepSize:2,backdropColor:"transparent"}}}}}},plugins:{{legend:{{position:"bottom"}}}}}}}});
new Chart(document.getElementById("barChart"),{{type:"bar",data:{{labels:["切片1","切片2","切片3"],
datasets:[{{label:"总分",data:[{t1:.1f},{t2:.1f},{t3:.1f}],
backgroundColor:["#3182ce","#38a169","#dd6b20"],borderRadius:8,barThickness:60}}]}},
options:{{responsive:true,scales:{{y:{{min:0,max:100,ticks:{{callback:function(v){{return v+"分"}}}}}}}},plugins:{{legend:{{display:false}}}}}},
plugins:[{{id:"passLine",afterDraw:function(chart){{var ctx=chart.ctx,y=chart.scales.y.getPixelForValue(75);
ctx.save();ctx.setLineDash([8,4]);ctx.strokeStyle="#e53e3e";ctx.lineWidth=2;ctx.beginPath();
ctx.moveTo(chart.scales.x.left,y);ctx.lineTo(chart.scales.x.right,y);ctx.stroke();
ctx.fillStyle="#e53e3e";ctx.font="bold 12px sans-serif";ctx.fillText("合格线 75分",chart.scales.x.right-80,y-6);ctx.restore()}}}}}}]);
function switchTab(id){{document.querySelectorAll(".tab-content").forEach(function(e){{e.classList.remove("active")}});
document.querySelectorAll(".tab-btn").forEach(function(e){{e.classList.remove("active")}});
document.getElementById(id).classList.add("active");event.target.classList.add("active")}}
</script></body></html>""")

html = "\n".join(parts)
with open("output/analysis_report.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"Report generated: {len(html)} chars, {html.count(chr(10))} lines")
