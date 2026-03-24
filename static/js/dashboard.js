const S = { modelReady: false, csvLoaded: false, fwActive: false, sse: null, pollTimer: null, analyticsTimer: null, rows: [], charts: {} };

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    btn.classList.add('active');
    document.getElementById('page-' + btn.dataset.page).classList.add('active');
    if (btn.dataset.page === 'analytics')    loadAnalytics();
    if (btn.dataset.page === 'protection')   loadProtection();
    if (btn.dataset.page === 'intelligence') loadIntelligence();
    if (btn.dataset.page === 'admin')        loadAdmin();
  });
});

function fmtN(n) { if (n >= 1000000) return (n/1000000).toFixed(1)+'M'; if (n >= 1000) return (n/1000).toFixed(1)+'K'; return String(n); }

function showAlert(msg, type='inf') {
  const box = document.getElementById('alert-box');
  const icon = {ok:'✓', err:'✗', inf:'ℹ'}[type] || 'ℹ';
  box.innerHTML = `<div class="alert alert-${type}">${icon} ${msg}</div>`;
  setTimeout(() => box.innerHTML = '', 6000);
}

function sysLog(msg, type='in') {
  const log = document.getElementById('sys-log');
  const now  = new Date().toTimeString().slice(0,8);
  const cls  = {ok:'tl-ok', er:'tl-er', wn:'tl-wn', in:'tl-in'}[type] || 'tl-in';
  const div  = document.createElement('div');
  div.className = 'tl';
  div.innerHTML = `<span class="tl-t">[${now}]</span> <span class="${cls}">${msg}</span>`;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}

function setStep(n) {
  [1,2,3].forEach(i => {
    const s = document.getElementById('step'+i);
    s.classList.remove('act','done');
    if (i < n) s.classList.add('done');
    else if (i === n) s.classList.add('act');
    const line = document.getElementById('sl'+i);
    if (line) line.classList.toggle('done', i < n);
  });
}

const zone = document.getElementById('upload-zone');
const finp = document.getElementById('file-input');
zone.addEventListener('dragover', e => { e.preventDefault(); zone.classList.add('drag'); });
zone.addEventListener('dragleave', () => zone.classList.remove('drag'));
zone.addEventListener('drop', e => { e.preventDefault(); zone.classList.remove('drag'); if (e.dataTransfer.files[0]) doUpload(e.dataTransfer.files[0]); });
finp.addEventListener('change', () => { if (finp.files[0]) doUpload(finp.files[0]); });

function doUpload(file) {
  if (!file.name.toLowerCase().endsWith('.csv')) { showAlert('Only .csv files are supported', 'err'); return; }
  const progWrap = document.getElementById('upload-prog-wrap');
  const bar = document.getElementById('upload-bar');
  const pct = document.getElementById('upload-pct');
  progWrap.classList.remove('hidden');
  sysLog(`Uploading ${file.name} (${(file.size/1024/1024).toFixed(1)} MB)…`);
  const fd = new FormData(); fd.append('file', file);
  const xhr = new XMLHttpRequest(); xhr.open('POST', '/api/upload');
  xhr.upload.onprogress = e => { if (e.lengthComputable) { const p = Math.round(e.loaded/e.total*100); bar.style.width = p+'%'; pct.textContent = p+'%'; } };
  xhr.onload = () => {
    progWrap.classList.add('hidden');
    const d = JSON.parse(xhr.responseText);
    if (d.success) {
      S.csvLoaded = true;
      showAlert(`Dataset loaded: ${d.info.loaded_rows.toLocaleString()} rows, ${d.info.feature_count} features`, 'ok');
      sysLog(`CSV loaded: ${d.info.filename}`, 'ok');
      sysLog(`Rows: ${d.info.loaded_rows.toLocaleString()} | Features: ${d.info.feature_count} | Attack ratio: ${d.info.attack_ratio ?? 'unknown'}%`, 'in');
      renderCsvInfo(d.info);
      if (S.modelReady) { document.getElementById('btn-start').disabled = false; document.getElementById('admin-start').disabled = false; setStep(2); }
    } else { showAlert('Upload failed: ' + d.error, 'err'); sysLog('Upload error: ' + d.error, 'er'); }
  };
  xhr.onerror = () => { progWrap.classList.add('hidden'); showAlert('Network error during upload', 'err'); };
  xhr.send(fd);
}

function renderCsvInfo(info) {
  document.getElementById('csv-empty').classList.add('hidden');
  document.getElementById('csv-content').classList.remove('hidden');
  const atkPct = info.attack_ratio;
  const atkColor = atkPct > 40 ? 'var(--red)' : atkPct > 15 ? 'var(--amber)' : 'var(--text)';
  document.getElementById('csv-stats-grid').innerHTML = `<div class="icard"><div class="icard-val">${fmtN(info.loaded_rows)}</div><div class="icard-lbl">Rows</div></div><div class="icard"><div class="icard-val">${info.feature_count}</div><div class="icard-lbl">Features</div></div><div class="icard"><div class="icard-val" style="color:${atkColor}">${atkPct ?? '?'}%</div><div class="icard-lbl">Attacks</div></div>`;
  const featHtml = (info.features_found || []).map(f => `<span class="feat-pill">${f}</span>`).join('');
  document.getElementById('csv-features-wrap').innerHTML = `<div style="font-size:1.1rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--muted);margin-bottom:0.6rem">Features Mapped</div>${featHtml}`;
  const atkCounts = Object.entries(info.attack_counts || {}).filter(([k]) => k.trim().toUpperCase() !== 'BENIGN').sort((a,b) => b[1]-a[1]).slice(0,6);
  if (atkCounts.length > 0) {
    const maxV = atkCounts[0][1];
    document.getElementById('csv-attacks-wrap').innerHTML = `<div style="font-size:1.1rem;letter-spacing:0.1em;text-transform:uppercase;color:var(--muted);margin-bottom:0.8rem">Attack Types in CSV</div>` + atkCounts.map(([name, count]) => `<div class="atk-row"><div class="atk-name">${name}</div><div class="atk-bar-wrap"><div class="atk-bar-fill" style="width:${Math.round(count/maxV*100)}%"></div></div><div class="atk-count">${count.toLocaleString()}</div></div>`).join('');
  }
  document.getElementById('admin-csv-empty').classList.add('hidden');
  document.getElementById('admin-csv-info').classList.remove('hidden');
  document.getElementById('adm-file').textContent  = info.filename;
  document.getElementById('adm-rows').textContent  = info.loaded_rows.toLocaleString();
  document.getElementById('adm-feats').textContent = info.feature_count;
  document.getElementById('adm-atk').textContent   = (atkPct ?? '?') + '%';
}

async function fwStart() {
  const r = await fetch('/api/firewall/start', { method: 'POST' });
  const d = await r.json();
  if (!d.success) { showAlert(d.error, 'err'); return; }
  S.fwActive = true; setFwPill(true);
  document.getElementById('btn-stop').disabled = false; document.getElementById('admin-stop').disabled = false;
  setStep(3); sysLog('Firewall active — streaming PPO predictions', 'ok');
  showAlert('Firewall started — analysing CSV with PPO model', 'ok');
  startSSE(); startCounterPoll();
}

async function fwStop() {
  await fetch('/api/firewall/stop', { method: 'POST' });
  S.fwActive = false; setFwPill(false);
  if (S.sse) { S.sse.close(); S.sse = null; }
  if (S.pollTimer) { clearInterval(S.pollTimer); S.pollTimer = null; }
  sysLog('Firewall stopped', 'wn');
}

function setFwPill(on) {
  document.getElementById('fw-pill').className = 'fw-pill ' + (on ? 'on' : 'off');
  document.getElementById('fw-pill-txt').textContent = on ? 'ACTIVE' : 'OFFLINE';
}

function startSSE() {
  if (S.sse) S.sse.close();
  S.sse = new EventSource('/api/stream/packets');
  S.sse.onmessage = e => {
    const pkt = JSON.parse(e.data);
    if (pkt._hb) return;
    if (pkt._done) { sysLog(`Analysis complete — ${S.rows.length}+ packets processed`, 'ok'); setFwPill(false); S.fwActive = false; return; }
    addPacketRow(pkt); bumpCounters(pkt);
  };
  S.sse.onerror = () => { if (!S.fwActive) return; sysLog('SSE dropped — reconnecting…', 'wn'); };
}

const MAX_ROWS = 150;
function addPacketRow(pkt) {
  const tbody = document.getElementById('pkt-tbody');
  const decMap = { ALLOW: 'allow', BLOCK: 'block', 'RATE-LIMIT': 'ratelimit' };
  const decCls = decMap[pkt.decision] || 'allow';
  const lblCls = pkt.true_label === 'ATTACK' ? 'attack' : 'benign';
  const confColor = pkt.confidence > 85 ? 'var(--text)' : pkt.confidence > 65 ? 'var(--amber)' : 'var(--red)';
  const tr = document.createElement('tr'); tr.className = 'new-row';
  tr.innerHTML = `<td>${pkt.id}</td><td>${pkt.ts}</td><td style="color:var(--text)">${pkt.dst_port}</td><td>${pkt.flow_dur}</td><td>${pkt.fwd_pkts}</td><td>${pkt.bwd_pkts}</td><td><span class="badge badge-${lblCls}">${pkt.true_label}</span></td><td style="color:${confColor}">${pkt.confidence}%</td><td><span class="badge badge-${decCls}">${pkt.decision}</span></td>`;
  S.rows.unshift(tr); if (S.rows.length > MAX_ROWS) S.rows.pop();
  tbody.innerHTML = ''; S.rows.forEach(r => tbody.appendChild(r));
}

function bumpCounters(pkt) { const totEl = document.getElementById('s-total'); totEl.textContent = fmtN((parseInt(totEl.textContent.replace(/[^0-9]/g,'')) || 0) + 1); }

function startCounterPoll() {
  if (S.pollTimer) clearInterval(S.pollTimer);
  S.pollTimer = setInterval(async () => {
    const r = await fetch('/api/model/status'); const d = await r.json();
    document.getElementById('s-total').textContent = fmtN(d.total);
    document.getElementById('s-allow').textContent = fmtN(d.counts.allow);
    document.getElementById('s-block').textContent = fmtN(d.counts.block);
    document.getElementById('s-rl').textContent    = fmtN(d.counts.rate_limit);
  }, 2500);
}

function pushSettings() {
  fetch('/api/settings', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ strict_mode: document.getElementById('tgl-strict').checked, auto_block: document.getElementById('tgl-autoblock').checked, rl_threshold: parseFloat(document.getElementById('rl-range').value) }) });
}

Chart.defaults.color = 'rgba(246,246,246,0.4)'; Chart.defaults.borderColor = 'rgba(246,246,246,0.06)';
function mkChart(id, type, data, opts = {}) { const el = document.getElementById(id); if (!el) return; if (S.charts[id]) S.charts[id].destroy(); S.charts[id] = new Chart(el, { type, data, options: { responsive: true, maintainAspectRatio: true, animation: { duration: 400 }, plugins: { legend: { labels: { color: 'rgba(246,246,246,0.4)', font: { family: "'PP Neue Montreal','Neue Montreal','Inter',sans-serif", size: 11 } } } }, ...opts } }); }
function axOpts(ylabel='') { const base = { ticks: { color: 'rgba(246,246,246,0.3)', font: { family: "'PP Neue Montreal','Neue Montreal','Inter',sans-serif", size: 10 } }, grid: { color: 'rgba(246,246,246,0.04)' } }; if (ylabel) base.title = { display: true, text: ylabel, color: 'rgba(246,246,246,0.3)', font: { family: "'PP Neue Montreal','Neue Montreal','Inter',sans-serif", size: 10 } }; return base; }

async function loadAnalytics() {
  const r = await fetch('/api/analytics'); const d = await r.json();
  mkChart('pie-chart', 'doughnut', { labels: ['Benign', 'Attack'], datasets: [{ data: [d.benign_pct || 0, d.attack_pct || 0], backgroundColor: ['rgba(91,196,1,0.2)', 'rgba(255,77,77,0.2)'], borderColor: ['#5bc401', '#ff4d4d'], borderWidth: 1.5 }] }, { cutout: '68%', plugins: { legend: { position: 'bottom' } } });
  const atkEntries = Object.entries(d.attack_counts || {}).sort((a,b) => b[1]-a[1]).slice(0,8);
  if (atkEntries.length > 0) mkChart('atk-bar-chart', 'bar', { labels: atkEntries.map(([k]) => k), datasets: [{ label: 'Count', data: atkEntries.map(([,v]) => v), backgroundColor: 'rgba(255,77,77,0.2)', borderColor: '#ff4d4d', borderWidth: 1.5, borderRadius: 4 }] }, { indexAxis: atkEntries.length > 4 ? 'y' : 'x', scales: { x: axOpts(), y: axOpts() }, plugins: { legend: { display: false } } });
  const ar = d.attack_pct || 0; document.getElementById('atk-rate-num').textContent = ar.toFixed(1) + '%'; document.getElementById('atk-rate-bar').style.width = Math.min(100, ar) + '%';
  const tl = d.timeline || [];
  if (tl.length > 0) mkChart('timeline-chart', 'line', { labels: tl.map(x => x.time), datasets: [ { label: 'Attacks', data: tl.map(x => x.attacks), borderColor: '#ff4d4d', backgroundColor: 'rgba(255,77,77,0.06)', fill: true, tension: 0.4, borderWidth: 1.5, pointRadius: 2 }, { label: 'Benign', data: tl.map(x => x.benign), borderColor: '#5bc401', backgroundColor: 'rgba(91,196,1,0.05)', fill: true, tension: 0.4, borderWidth: 1.5, pointRadius: 2 } ] }, { scales: { x: axOpts(), y: axOpts('Packets') } });
  if (S.analyticsTimer) clearInterval(S.analyticsTimer);
  if (S.fwActive) S.analyticsTimer = setInterval(loadAnalytics, 5000);
}

async function loadProtection() {
  const r = await fetch('/api/performance'); const d = await r.json();
  mkChart('cpu-chart', 'line', { labels: d.t, datasets: [ { label: 'No Firewall', data: d.cpu_no_fw, borderColor: '#ff4d4d', backgroundColor: 'rgba(255,77,77,0.05)', fill: true, tension: 0.3, borderWidth: 1.5, pointRadius: 0 }, { label: 'With Firewall', data: d.cpu_fw, borderColor: '#5bc401', backgroundColor: 'rgba(91,196,1,0.04)', fill: true, tension: 0.3, borderWidth: 1.5, pointRadius: 0 } ] }, { scales: { x: axOpts('Time (s)'), y: { ...axOpts('CPU %'), min:0, max:100 } } });
  mkChart('mem-chart', 'line', { labels: d.t, datasets: [ { label: 'No Firewall', data: d.mem_no_fw, borderColor: '#ff4d4d', backgroundColor: 'rgba(255,77,77,0.05)', fill: true, tension: 0.3, borderWidth: 1.5, pointRadius: 0 }, { label: 'With Firewall', data: d.mem_fw, borderColor: '#3ec9ff', backgroundColor: 'rgba(62,201,255,0.04)', fill: true, tension: 0.3, borderWidth: 1.5, pointRadius: 0 } ] }, { scales: { x: axOpts('Time (s)'), y: { ...axOpts('Memory %'), min:0, max:100 } } });
  mkChart('lat-chart', 'line', { labels: d.t, datasets: [ { label: 'Attack Load', data: d.attack_load, borderColor: '#ffb020', backgroundColor: 'rgba(255,176,32,0.05)', fill: true, tension: 0.3, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y' }, { label: 'Latency (no FW)', data: d.lat_no_fw, borderColor: '#ff4d4d', backgroundColor: 'transparent', fill: false, tension: 0.3, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y1' }, { label: 'Latency (FW)', data: d.lat_fw, borderColor: '#5bc401', backgroundColor: 'transparent', fill: false, tension: 0.3, borderWidth: 1.5, pointRadius: 0, yAxisID: 'y1' } ] }, { scales: { x: axOpts('Time (s)'), y: { ...axOpts('Attack Load'), position: 'left' }, y1: { ...axOpts('Latency (ms)'), position: 'right', grid: { drawOnChartArea: false } } } });
}

async function loadIntelligence() {
  const [intelRes, anaRes, qlRes, dqnRes] = await Promise.all([ fetch('/api/model/intel'), fetch('/api/analytics'), fetch('/api/algo/qlearning'), fetch('/api/algo/dqn') ]);
  const intel = await intelRes.json(); const ana = await anaRes.json(); const ql = await qlRes.json(); const dqn = await dqnRes.json();
  if (!intel.ready) return;
  if (ql.rewards?.length > 0) document.getElementById('ql-best-reward').textContent = Math.max(...ql.rewards).toLocaleString(undefined, {maximumFractionDigits:0});
  if (dqn.rewards?.length > 0) document.getElementById('dqn-best-reward').textContent = Math.max(...dqn.rewards).toLocaleString(undefined, {maximumFractionDigits:0});
  if (intel.reward_log?.length > 0) document.getElementById('ppo-best-reward').textContent = Math.max(...intel.reward_log).toLocaleString(undefined, {maximumFractionDigits:0});
  const qlR = ql.rewards || [], dqnR = dqn.rewards || [], ppoR = intel.reward_log || [];
  const maxLen = Math.max(qlR.length, dqnR.length, ppoR.length, 1);
  const padded = arr => { const o = [...arr]; while (o.length < maxLen) o.push(null); return o; };
  const labels = Array.from({length: maxLen}, (_,i) => `Ep ${i+1}`);
  const datasets = [];
  if (qlR.length > 0)  datasets.push({ label:'Q-Learning',    data: padded(qlR),  borderColor:'#ffb020', backgroundColor:'rgba(255,176,32,0.06)', fill:true, tension:0.4, borderWidth:2, pointRadius: qlR.length<=20?3:1, spanGaps:true });
  if (dqnR.length > 0) datasets.push({ label:'DQN',           data: padded(dqnR), borderColor:'#3ec9ff', backgroundColor:'rgba(62,201,255,0.06)', fill:true, tension:0.4, borderWidth:2, pointRadius: dqnR.length<=20?3:1, spanGaps:true });
  if (ppoR.length > 0) datasets.push({ label:'PPO (deployed)', data: padded(ppoR), borderColor:'#5bc401', backgroundColor:'rgba(91,196,1,0.07)', fill:true, tension:0.4, borderWidth:2.5, pointRadius: ppoR.length<=20?4:2, spanGaps:true });
  if (datasets.length > 0) mkChart('reward-chart', 'line', {labels, datasets}, { scales: { x: axOpts('Episode / Phase'), y: axOpts('Cumulative Reward') } });
  if (ppoR.length > 0) mkChart('ppo-phase-chart', 'bar', { labels: ppoR.map((_,i) => `Ph ${i+1}`), datasets: [{ label: 'PPO Phase Reward', data: ppoR, backgroundColor: ppoR.map(v => v >= 0 ? 'rgba(91,196,1,0.25)' : 'rgba(255,77,77,0.25)'), borderColor: ppoR.map(v => v >= 0 ? '#5bc401' : '#ff4d4d'), borderWidth: 1.5, borderRadius: 4 }] }, { scales: { x: axOpts(), y: axOpts('Reward') }, plugins: { legend: { display: false } } });
  const ad = intel.action_dist;
  mkChart('action-hist', 'bar', { labels: ['Allow', 'Block', 'Rate-Limit'], datasets: [{ label: 'PPO Action %', data: [ad.allow, ad.block, ad.rate_limit], backgroundColor: ['rgba(91,196,1,0.22)', 'rgba(255,77,77,0.22)', 'rgba(255,176,32,0.22)'], borderColor: ['#5bc401', '#ff4d4d', '#ffb020'], borderWidth: 1.5, borderRadius: 6 }] }, { scales: { x: axOpts(), y: axOpts('%') }, plugins: { legend: { display: false } } });
  if (ana.accuracy !== null && ana.accuracy !== undefined) {
    document.getElementById('metrics-empty').classList.add('hidden'); document.getElementById('metrics-content').classList.remove('hidden');
    document.getElementById('m-acc').textContent = ana.accuracy + '%'; document.getElementById('m-auc').textContent = ana.auc ?? '—';
    document.getElementById('m-allow').textContent = ad.allow + '%'; document.getElementById('m-block').textContent = ad.block + '%'; document.getElementById('m-rl').textContent = ad.rate_limit + '%';
  }
  if (ana.confusion) {
    const cm = ana.confusion;
    document.getElementById('cm-empty').classList.add('hidden'); document.getElementById('cm-content').classList.remove('hidden');
    document.getElementById('cm-tp').textContent = (cm[1]?.[1] ?? 0).toLocaleString(); document.getElementById('cm-fp').textContent = (cm[0]?.[1] ?? 0).toLocaleString();
    document.getElementById('cm-fn').textContent = (cm[1]?.[0] ?? 0).toLocaleString(); document.getElementById('cm-tn').textContent = (cm[0]?.[0] ?? 0).toLocaleString();
    document.getElementById('cm-note').textContent = `Computed on ${intel.total_processed.toLocaleString()} rows processed so far.`;
  }
}

function loadAdmin() {
  fetch('/api/model/status').then(r => r.json()).then(d => {
    if (d.csv_loaded && d.csv_info?.filename) {
      document.getElementById('admin-csv-empty').classList.add('hidden'); document.getElementById('admin-csv-info').classList.remove('hidden');
      document.getElementById('adm-file').textContent = d.csv_info.filename; document.getElementById('adm-rows').textContent = (d.csv_info.loaded_rows||0).toLocaleString();
      document.getElementById('adm-feats').textContent = d.csv_info.feature_count||'—'; document.getElementById('adm-atk').textContent = (d.csv_info.attack_ratio??'?') + '%';
    }
    document.getElementById('tgl-strict').checked = d.strict_mode; document.getElementById('tgl-autoblock').checked = d.auto_block;
    document.getElementById('rl-range').value = d.rl_threshold; document.getElementById('rl-lbl').textContent = 'Current: ' + parseFloat(d.rl_threshold).toFixed(2);
  });
}

window.addEventListener('load', async () => {
  const r = await fetch('/api/model/status'); const d = await r.json();
  S.modelReady = d.model_ready; S.csvLoaded = d.csv_loaded;
  if (!d.model_ready) { document.getElementById('model-warn').classList.remove('hidden'); sysLog('No trained model found. Run train_ppo.py first.', 'er'); }
  else { sysLog('PPO model loaded and ready', 'ok'); if (d.reward_log?.length > 0) sysLog(`Reward log: ${d.reward_log.length} training phases`, 'in'); }
  if (d.csv_loaded && d.csv_info?.filename) { S.csvLoaded = true; renderCsvInfo(d.csv_info); if (d.model_ready) { document.getElementById('btn-start').disabled = false; document.getElementById('admin-start').disabled = false; setStep(2); } }
  if (d.fw_active) { S.fwActive = true; setFwPill(true); startSSE(); startCounterPoll(); setStep(3); }
  loadProtection();
});

(function(){
  const canvas = document.getElementById('bg-canvas');
  const ctx = canvas.getContext('2d');
  function resize(){ canvas.width = innerWidth; canvas.height = innerHeight; }
  resize(); window.addEventListener('resize', resize);
  const COUNT = 90;
  const particles = Array.from({ length: COUNT }, () => ({ x: Math.random()*innerWidth, y: Math.random()*innerHeight, vx: (Math.random()-0.5)*0.35, vy: (Math.random()-0.5)*0.35, r: Math.random()*1.5+0.8, pulse: Math.random()*Math.PI*2, speed: Math.random()*0.3+0.15 }));
  let t = 0; const CONNECT_DIST = 130;
  function draw(){
    requestAnimationFrame(draw); t += 0.008;
    const W = canvas.width, H = canvas.height;
    ctx.clearRect(0, 0, W, H);
    particles.forEach(p => { p.x += p.vx; p.y += p.vy; if (p.x<0||p.x>W) p.vx*=-1; if (p.y<0||p.y>H) p.vy*=-1; });
    for (let i = 0; i < COUNT; i++) {
      for (let j = i+1; j < COUNT; j++) {
        const a = particles[i], b = particles[j];
        const dx = a.x-b.x, dy = a.y-b.y, dist = Math.sqrt(dx*dx+dy*dy);
        if (dist < CONNECT_DIST) { const alpha = (1-dist/CONNECT_DIST)*0.18; ctx.beginPath(); ctx.moveTo(a.x,a.y); ctx.lineTo(b.x,b.y); ctx.strokeStyle=`rgba(91,196,1,${alpha})`; ctx.lineWidth=0.6; ctx.stroke(); }
      }
    }
    particles.forEach(p => { const pulse=0.5+Math.sin(t*p.speed+p.pulse)*0.5; const alpha=0.25+pulse*0.25; const radius=p.r+pulse*0.4; ctx.beginPath(); ctx.arc(p.x,p.y,radius,0,Math.PI*2); ctx.fillStyle=`rgba(91,196,1,${alpha})`; ctx.fill(); });
  }
  draw();
})();