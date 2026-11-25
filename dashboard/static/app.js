// LandParcels Dashboard — input/schema/run/monitor/output (บัญชี + theme อยู่ใน account.js)
const API = '/api';
const S = {
  catalogs: { parcel: null, cityplanning: null },
  schemaState: { parcel: new Map(), cityplanning: new Map() },
  schemaTab: 'parcel',
  areas: [], selectedArea: null,
  provinces: [], pickedProvs: [],
  jobs: [],
  currentJob: null,
  monEvents: null,
  maps: { area: null, mon: null },
  layers: { area: null, mon: null },
};

const $ = sel => document.querySelector(sel);
const $$ = sel => Array.from(document.querySelectorAll(sel));
function h(s){return (s==null?'':String(s)).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function hum(bytes){ if(!bytes) return '—'; const u=['B','KB','MB','GB']; let i=0,v=bytes; while(v>1024&&i<u.length-1){v/=1024;i++} return v.toFixed(v<10?1:0)+u[i]; }
function timeAgo(ts){ if(!ts) return '—'; const s=Math.floor(Date.now()/1000-ts); if(s<60) return s+'s ago'; if(s<3600) return Math.floor(s/60)+'m ago'; if(s<86400) return Math.floor(s/3600)+'h ago'; return Math.floor(s/86400)+'d ago'; }
function dur(a,b){ if(!a) return '—'; const s=Math.floor((b||Date.now()/1000)-a); return s<60?`${s}s`:`${Math.floor(s/60)}m ${s%60}s`; }

class ApiError extends Error {
  constructor(status, detail){ super(typeof detail==='string' ? detail : (detail?.message || JSON.stringify(detail))); this.status=status; this.detail=detail; }
}
async function readError(r){
  const text = await r.text();
  try{ return new ApiError(r.status, JSON.parse(text).detail ?? text); }catch{ return new ApiError(r.status, text || r.statusText); }
}
async function api(path, opts){ const r = await fetch(API+path, opts); if(!r.ok) throw await readError(r); return r.json(); }
const postJSON = (path, body) => api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)});

// ─────────────── nav ───────────────
const TAB_INIT = {
  input: ()=>{ initAreaMap(); loadAreas(); },
  schema: ()=>loadSchema(),
  city: ()=>{ loadProvinces(); loadAreas().then(fillCityArea); },
  parcel: ()=>{ loadAreas().then(fillParcelPicker); refreshAuth(); },
  monitor: ()=>initMonMap(),
  output: ()=>loadOutput(),
  overview: ()=>refreshOverview(),
  account: ()=>refreshAuth(),
};
$$('.sidebar button').forEach(b=>b.addEventListener('click',()=>{
  const t=b.dataset.tab, arg=S.tabArg; S.tabArg=null;
  $$('.sidebar button').forEach(x=>x.classList.toggle('active',x===b));
  $$('.section').forEach(s=>s.classList.toggle('active',s.id==='sec-'+t));
  history.replaceState(null, '', '#'+t);
  TAB_INIT[t]?.(arg);
  setTimeout(()=>{ S.maps.area?.invalidateSize(); S.maps.mon?.invalidateSize(); }, 50);
}));
/** @param {string} tab @param {string} [arg] ส่วนหลัง / ใน hash เช่น 'parcel' ของ #docs/parcel */
function switchTo(tab, arg){ S.tabArg = arg || null; document.querySelector(`.sidebar button[data-tab="${tab}"]`)?.click(); }
function routeFromHash(){
  let raw = location.hash.slice(1);
  try{ raw = decodeURIComponent(raw); }catch{}
  const [tab, ...rest] = raw.split('/');
  if(TAB_INIT[tab]) switchTo(tab, rest.join('/'));
}
window.addEventListener('hashchange', routeFromHash);
$$('[data-goto]').forEach(el=>el.addEventListener('click',e=>{ e.preventDefault(); switchTo(el.dataset.goto); }));

setInterval(()=>{ $('#clockPill').textContent=new Date().toLocaleTimeString('th-TH',{hour12:false}); },1000);

// ─────────────── overview ───────────────
async function refreshOverview(){
  await Promise.allSettled([loadAreas(), loadOutput(), loadJobs(), loadUserSchemaCount()]);
}
async function loadUserSchemaCount(){
  try{
    const u = await api('/user-schema');
    $('#kpiExtra').textContent = `${(u.parcel?.extra_fields||[]).length}+${(u.cityplanning?.extra_fields||[]).length}`;
  }catch{ $('#kpiExtra').textContent='—'; }
}
async function loadJobs(){
  const { items } = await api('/jobs');
  S.jobs = items;
  $('#kpiRunning').textContent = items.filter(j=>j.status==='running').length;
  $('#jobCount').textContent = `${items.length} jobs`;
  const tb = $('#jobsTable tbody'); tb.innerHTML='';
  if(items.length===0){ tb.innerHTML='<tr><td colspan="6" class="muted">ยังไม่มี job</td></tr>'; return; }
  for(const j of items){
    const pct = j.progress?.percent;
    const tr = document.createElement('tr');
    tr.innerHTML = `
      <td><code>${h(j.id)}</code></td>
      <td>${h(j.kind)}</td>
      <td><span class="badge b-${h(j.status)}">${h(j.status)}</span></td>
      <td>${pct!=null?pct.toFixed(1)+'%':'—'}${j.progress?.n!=null?' <span class="muted">('+j.progress.n+'/'+j.progress.total+')</span>':''}</td>
      <td class="muted">${timeAgo(j.started_at)}</td>
      <td class="actions"><button class="btn ghost sm" data-job="${h(j.id)}">เปิด</button></td>`;
    tb.appendChild(tr);
  }
  tb.querySelectorAll('button[data-job]').forEach(b=>b.addEventListener('click',()=>{ openJob(b.dataset.job); switchTo('monitor'); }));
}
$('#refreshJobs').addEventListener('click',loadJobs);

// ─────────────── input: areas ───────────────
async function loadAreas(){
  const { items } = await api('/areas');
  S.areas = items;
  $('#kpiAreas').textContent = items.length;
  const tb = $('#areaTable tbody');
  tb.innerHTML='';
  if(items.length===0){ tb.innerHTML='<tr><td colspan="5" class="muted">ยังไม่มีไฟล์ — ลากไฟล์มาวางด้านบนได้เลย</td></tr>'; }
  for(const a of items){
    const tr = document.createElement('tr');
    tr.classList.toggle('selected', a.name===S.selectedArea);
    tr.dataset.area = a.name;
    tr.innerHTML = `<td class="chk"><input type="checkbox" data-name="${h(a.name)}" aria-label="เลือก ${h(a.name)}"></td>`
      + `<td><code>${h(a.name)}</code><span class="area-meta">${h(a.kind)} · ${hum(a.size)}</span></td>`
      + `<td class="fetch-st"><span class="muted">…</span></td><td class="fetch-when muted">—</td>`
      + `<td class="actions"><button class="btn ghost sm del" title="ลบ ${h(a.name)}" aria-label="ลบ ${h(a.name)}">🗑</button></td>`;
    tr.addEventListener('click',()=>selectArea(a.name, tr));
    tr.querySelector('.chk').addEventListener('click',e=>e.stopPropagation());
    tr.querySelector('input').addEventListener('change',syncAreaChecks);
    tr.querySelector('.del').addEventListener('click',e=>{ e.stopPropagation(); deleteAreas([a.name]); });
    tb.appendChild(tr);
  }
  syncAreaChecks();
  renderAreaStatus();
  loadAreaStatus();
}

// ─────────────── input: สถานะการดึงรายพื้นที่ (cache/status/) ───────────────
const FETCH_POLL_MS = 15000;
const fmtN = n => n==null ? '—' : Number(n).toLocaleString('th-TH');
/** @type {Record<string, {label:string, cls:string}>} */
const FETCH_STATES = {
  new:       {label:'ยังไม่เคยดึง',        cls:'b-pending'},
  running:   {label:'🔄 กำลังดึง',         cls:'b-running'},
  done:      {label:'✅ ครบ',              cls:'b-done'},
  partial:   {label:'⏸ ยังค้าง',          cls:'b-warn'},
  quota:     {label:'⛔ โควตาเต็ม',        cls:'b-warn'},
  stale:     {label:'⚠ หยุดกลางทาง',      cls:'b-warn'},
  cancelled: {label:'⏹ ถูกยกเลิก',        cls:'b-cancelled'},
  error:     {label:'✗ ผิดพลาด',          cls:'b-failed'},
};
S.areaStatus = new Map();

async function loadAreaStatus(){
  try{
    const { items } = await api('/status/areas');
    S.areaStatus = new Map(items.map(it=>[it.area, it]));
  }catch(e){
    S.areaStatus = new Map();
    $('#areaStatus').textContent = 'อ่านสถานะการดึงไม่สำเร็จ: ' + e.message;
  }
  renderAreaStatus();
}

/** แปลงสถานะ 1 พื้นที่ -> {badge, bar(0-100|null), text, tip} */
function describeFetch(st){
  const def = FETCH_STATES[st.state] || {label:st.state, cls:'b-pending'};
  const total = st.total, pending = st.pending;
  const done = total!=null && pending!=null ? total - pending : null;
  let bar = total ? Math.round((done ?? 0) * 100 / total) : null, text = '', tip = '';
  if(st.state==='running'){
    const p = st.progress;
    bar = p?.todo ? Math.round(p.n * 100 / p.todo) : null;
    text = p ? `รอบนี้ ${fmtN(p.n)}/${fmtN(p.todo)} แปลง` : (total!=null ? `พบ ${fmtN(total)} แปลง · กำลังเตรียม…` : 'กำลังหาระวาง/รูปแปลง…');
  }else if(st.state==='new'){
    text = ''; bar = null;
  }else if(done!=null){
    text = pending ? `${fmtN(done)}/${fmtN(total)} · ค้าง ${fmtN(pending)}` : `${fmtN(total)} แปลง`;
  }
  if(st.state==='quota') tip = 'โควตาวันนี้หมดแล้ว — รันใหม่หลังโควตารีเซ็ตจะทำต่อจาก cache';
  if(st.state==='partial') tip = 'ยังมีแปลงที่ไม่มีรายละเอียด — รันใหม่จะทำต่อจาก cache';
  if(st.state==='stale') tip = 'process หยุดไปก่อนจบ (ปิดหน้าต่าง/ไฟดับ/ถูก kill) — รันใหม่จะทำต่อจาก cache';
  if(st.state==='error') tip = st.error || '';
  if(st.from==='output') tip = (tip ? tip+' · ' : '') + 'นับจาก shapefile ใน output/ (ดึงไว้ก่อนมีระบบสถานะ)';
  return { badge:def, bar, text, tip };
}

function renderAreaStatus(){
  for(const tr of $$('#areaTable tbody tr[data-area]')){
    const st = S.areaStatus.get(tr.dataset.area);
    const cell = tr.querySelector('.fetch-st'), when = tr.querySelector('.fetch-when');
    if(!st){ cell.innerHTML = '<span class="muted">…</span>'; when.textContent = '—'; continue; }
    const d = describeFetch(st);
    cell.title = d.tip;
    cell.innerHTML = `<span class="badge ${h(d.badge.cls)}">${h(d.badge.label)}</span>`
      + (d.bar!=null ? `<div class="pbar${st.state==='running'&&d.bar===0?' indet':''}"><div class="fill" style="width:${d.bar}%"></div></div>` : '')
      + (d.text ? `<div class="nums">${h(d.text)}</div>` : '');
    const ts = st.state==='running' ? st.updated_at : (st.ended_at || st.updated_at);
    when.textContent = ts ? timeAgo(ts) : '—';
    when.title = ts ? new Date(ts*1000).toLocaleString('th-TH') : '';
  }
}

// refresh เองเฉพาะตอนเปิดหน้านี้อยู่และแท็บ browser มองเห็น (ไม่ยิง server ทิ้งไว้เปล่า ๆ)
setInterval(()=>{
  if(!document.hidden && $('#sec-input').classList.contains('active')) loadAreaStatus();
}, FETCH_POLL_MS);
const checkedAreas = ()=>$$('#areaTable tbody input[type=checkbox]:checked').map(c=>c.dataset.name);
function syncAreaChecks(){
  const n = checkedAreas().length, total = S.areas.length;
  const btn = $('#deleteAreas');
  btn.disabled = n===0;
  btn.textContent = n ? `🗑 ลบที่เลือก (${n})` : '🗑 ลบที่เลือก';
  const all = $('#areaAll');
  all.checked = total>0 && n===total;
  all.indeterminate = n>0 && n<total;
}
$('#areaAll').addEventListener('change',e=>{
  $$('#areaTable tbody input[type=checkbox]').forEach(c=>{ c.checked = e.target.checked; });
  syncAreaChecks();
});
$('#deleteAreas').addEventListener('click',()=>deleteAreas(checkedAreas()));

async function deleteAreas(names){
  if(!names.length) return;
  const list = names.length>8 ? [...names.slice(0,8), `… อีก ${names.length-8} ไฟล์`] : names;
  if(!confirm(`ลบ ${names.length} ไฟล์ออกจาก areas/ ?\n\n${list.join('\n')}\n\n(ย้ายไป areas/.deleted/ — กู้คืนได้จาก 📂 ไม่ได้ลบทิ้งถาวร)`)) return;
  const status = $('#areaStatus');
  status.textContent = 'กำลังลบ…';
  try{
    const res = await postJSON('/areas/delete', {names});
    status.textContent = `✓ ลบแล้ว ${res.deleted.length} ไฟล์ · เก็บสำรองไว้ที่ areas/${res.trash}/`;
    if(res.deleted.includes(S.selectedArea)) clearAreaPreview();
  }catch(e){
    const busy = e.detail?.busy;
    status.textContent = '✗ ' + e.message + (busy?.length ? `: ${busy.join(', ')}` : '');
  }
  await loadAreas();
}
function clearAreaPreview(){
  S.selectedArea = null;
  $('#areaSelLabel').textContent = '—';
  if(S.layers.area){ S.maps.area?.removeLayer(S.layers.area); S.layers.area = null; }
}
async function selectArea(name, row){
  S.selectedArea = name;
  $$('#areaTable tbody tr').forEach(r=>r.classList.toggle('selected',r===row));
  $('#areaSelLabel').textContent = name;
  try{
    const gj = await api(`/areas/${encodeURIComponent(name)}/geojson`);
    showAreaOnMap(S.maps.area, 'area', gj);
  }catch(e){ $('#areaSelLabel').textContent = `${name} — อ่านไม่ได้: ${e.message}`; }
}
function makeMap(id){
  const m = L.map(id).setView([13.75, 100.5], 6);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap'}).addTo(m);
  return m;
}
function initAreaMap(){ if(!S.maps.area) S.maps.area = makeMap('areaMap'); }
function initMonMap(){ if(!S.maps.mon) S.maps.mon = makeMap('map'); }
function showAreaOnMap(map, key, geojson){
  if(!map) return;
  if(S.layers[key]) map.removeLayer(S.layers[key]);
  const color = getComputedStyle(document.documentElement).getPropertyValue('--accent').trim() || '#1a7a3e';
  S.layers[key] = L.geoJSON(geojson,{style:{color,weight:2,fillOpacity:.12}}).addTo(map);
  try{ map.fitBounds(S.layers[key].getBounds(),{padding:[20,20]}); }catch{}
}
$('#refreshAreas').addEventListener('click',loadAreas);
$('#revealAreas').addEventListener('click',()=>reveal('areas',''));

// ─────────────── input: upload (drag & drop) ───────────────
const dz = $('#dropzone'), fileInput = $('#fileInput');
dz.addEventListener('click',()=>fileInput.click());
dz.addEventListener('keydown',e=>{ if(e.key==='Enter'||e.key===' '){ e.preventDefault(); fileInput.click(); } });
fileInput.addEventListener('change',()=>{ if(fileInput.files.length) uploadFiles(Array.from(fileInput.files)); fileInput.value=''; });
['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{ e.preventDefault(); dz.classList.add('over'); }));
['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{ e.preventDefault(); dz.classList.remove('over'); }));
dz.addEventListener('drop',e=>{
  const items = Array.from(e.dataTransfer.items||[]);
  if(items.some(it=>it.webkitGetAsEntry?.()?.isDirectory)){
    showUploadMsg([{ok:false,name:'โฟลเดอร์',message:'ลากโฟลเดอร์ (.gdb) มาตรง ๆ ไม่ได้ — คลิกขวา > Send to > Compressed (zip) แล้วลาก .zip มาแทน'}]);
    return;
  }
  const files = Array.from(e.dataTransfer.files||[]);
  if(files.length) uploadFiles(files);
});
// ลากไฟล์พลาดไปนอกกรอบ -> ไม่ให้ browser เปิดไฟล์นั้นแทนหน้า dashboard
['dragover','drop'].forEach(ev=>window.addEventListener(ev,e=>e.preventDefault()));

function uploadFiles(files, overwrite=false){
  const fd = new FormData();
  files.forEach(f=>fd.append('files', f, f.name));
  fd.append('overwrite', overwrite ? 'true' : 'false');
  const bar = $('#uploadBar');
  bar.hidden = false; bar.classList.remove('indet');
  bar.querySelector('.fill').style.width='0%';
  $('#uploadStatus').textContent = `กำลังอัปโหลด ${files.length} ไฟล์…`;
  const xhr = new XMLHttpRequest();
  xhr.open('POST', API+'/areas/upload');
  xhr.upload.onprogress = e=>{
    if(!e.lengthComputable) return;
    bar.querySelector('.fill').style.width = (e.loaded*100/e.total).toFixed(0)+'%';
    if(e.loaded===e.total){ bar.classList.add('indet'); $('#uploadStatus').textContent='กำลังตรวจไฟล์…'; }
  };
  xhr.onerror = ()=>{ bar.hidden=true; $('#uploadStatus').textContent='✗ ติดต่อ server ไม่ได้'; };
  xhr.onload = async ()=>{
    bar.hidden = true;
    let data; try{ data = JSON.parse(xhr.responseText); }catch{ data = {detail: xhr.responseText}; }
    if(xhr.status===409 && !overwrite){
      const names = data.detail?.conflicts || [];
      $('#uploadStatus').textContent = '';
      const ok = confirm(`มีไฟล์ชื่อนี้อยู่แล้วใน areas/:\n\n${names.join('\n')}\n\nแทนที่ไหม? (ไฟล์เดิมจะถูกย้ายไป areas/.replaced/ ไม่ได้ลบทิ้ง)`);
      if(ok) uploadFiles(files, true);
      return;
    }
    if(xhr.status>=400){
      const msg = typeof data.detail==='string' ? data.detail : (data.detail?.message || xhr.statusText);
      $('#uploadStatus').textContent = '✗ '+msg;
      return;
    }
    $('#uploadStatus').textContent = `✓ บันทึกลง areas/ แล้ว ${data.saved.length} รายการ` + (data.replaced.length?` · ย้ายของเดิม ${data.replaced.length} ไฟล์ไป .replaced/`:'');
    showUploadMsg(data.saved);
    await loadAreas();
    const first = data.saved.find(s=>s.ok);
    if(first){
      const row = $$('#areaTable tbody tr').find(r=>r.querySelector('code')?.textContent===first.name);
      selectArea(first.name, row);
    }
  };
  xhr.send(fd);
}
function showUploadMsg(list){
  $('#uploadResult').innerHTML = list.map(s=>`<li class="${s.ok?'ok':'bad'}"><b>${s.ok?'✓':'⚠'}</b><code>${h(s.name)}</code><span class="muted">${h(s.message)}</span></li>`).join('');
}

// ─────────────── output ───────────────
async function loadOutput(){
  const { items } = await api('/output');
  $('#kpiOutput').textContent = items.length;
  const tb = $('#outTable tbody');
  tb.innerHTML='';
  if(items.length===0){ tb.innerHTML='<tr><td colspan="4" class="muted">ยังไม่มี output</td></tr>'; return; }
  const groups = new Map();
  for(const o of items){ if(!groups.has(o.dir)) groups.set(o.dir, []); groups.get(o.dir).push(o); }
  for(const [dir, files] of groups){
    const gr = document.createElement('tr'); gr.className='group-row';
    gr.innerHTML = `<td colspan="3">📁 output/${h(dir)}</td><td class="actions">
      ${dir?`<a class="btn ghost sm" href="${dlUrl(dir)}" download>⬇ zip ทั้งโฟลเดอร์</a>`:''}
      <button class="btn ghost sm" data-reveal="${h(dir)}">📂 เปิด</button></td>`;
    tb.appendChild(gr);
    for(const o of files){
      const name = o.path.split('/').pop();
      const isShp = name.toLowerCase().endsWith('.shp');
      const tr = document.createElement('tr');
      tr.innerHTML = `<td><code>${h(name)}</code>${isShp?' <span class="muted">+ .dbf .shx .prj</span>':''}</td>
        <td class="muted">${hum(o.size)}</td><td class="muted">${timeAgo(o.mtime)}</td>
        <td class="actions"><a class="btn sm" href="${dlUrl(o.path)}" download>⬇ ${isShp?'zip':'ดาวน์โหลด'}</a>
        <button class="btn ghost sm" data-reveal="${h(o.path)}" title="เปิดใน Explorer">📂</button></td>`;
      tb.appendChild(tr);
    }
  }
  tb.querySelectorAll('[data-reveal]').forEach(b=>b.addEventListener('click',()=>reveal('output', b.dataset.reveal)));
}
const dlUrl = path => `${API}/output/download?path=${encodeURIComponent(path)}`;
async function reveal(root, path){
  try{ await postJSON('/reveal', {root, path}); }
  catch(e){ alert('เปิดโฟลเดอร์ไม่ได้: '+e.message); }
}
$('#refreshOutput').addEventListener('click',loadOutput);
$('#revealOutput').addEventListener('click',()=>reveal('output',''));

// ─────────────── schema: อยู่ใน schema.js ───────────────

// ─────────────── run: parcel ───────────────
function fillParcelPicker(){
  const host = $('#parcelAreaPicker');
  if(S.areas.length===0){ host.innerHTML='<span class="muted">ไม่มีไฟล์ใน areas/ — <a href="#" data-goto="input">อัปโหลดที่หน้า Input</a></span>'; host.querySelector('[data-goto]').addEventListener('click',e=>{e.preventDefault();switchTo('input');}); return; }
  host.innerHTML = S.areas.map(a=>`<label class="pill-item"><input type="checkbox" data-name="${h(a.name)}"> ${h(a.name)}</label>`).join('');
  host.querySelectorAll('input').forEach(c=>c.addEventListener('change',updateParcelCmdPreview));
  updateParcelCmdPreview();
}
function parcelArgs(){
  return {
    areas: $$('#parcelAreaPicker input:checked').map(c=>c.dataset.name),
    no_detail: $('#pNoDetail').checked,
    refetch: $('#pRefetch').value,
    layer: $('#pLayer').value.trim() || null,
    name: $('#pName').value.trim() || null,
  };
}
function updateParcelCmdPreview(){
  const a = parcelArgs();
  const parts = ['python fetch_parcels.py', ...a.areas.map(x=>'areas/'+x)];
  if(a.no_detail) parts.push('--no-detail');
  if(a.refetch&&a.refetch!=='none') parts.push('--refetch',a.refetch);
  if(a.layer) parts.push('--layer',a.layer);
  if(a.name) parts.push('--name',a.name);
  $('#parcelCmdPreview').textContent = parts.join(' ');
}
['pNoDetail','pRefetch','pLayer','pName'].forEach(id=>$('#'+id).addEventListener('input',updateParcelCmdPreview));
$('#runParcel').addEventListener('click',async()=>{
  try{
    const r = await postJSON('/run', {kind:'parcel', parcel:parcelArgs()});
    openJob(r.job_id); switchTo('monitor');
  }catch(e){ alert('Start fail: '+e.message); }
});

// ─────────────── run: cityplanning ───────────────
async function loadProvinces(){
  if(S.provinces.length>0) return;
  S.provinces = (await api('/provinces')).items;
  fillProvDropdown();
}
function fillProvDropdown(){
  const q = $('#provFilter').value.trim().toLowerCase();
  const matched = S.provinces.filter(p=>!q||p.code.includes(q)||p.name.toLowerCase().includes(q));
  $('#provSelect').innerHTML = matched.map(p=>`<option value="${h(p.code)}">${h(p.code)} ${h(p.name)}</option>`).join('');
}
$('#provFilter').addEventListener('input',fillProvDropdown);
$('#addProv').addEventListener('click',()=>{
  const v = $('#provSelect').value; if(!v || S.pickedProvs.includes(v)) return;
  S.pickedProvs.push(v); renderPickedProvs();
});
function renderPickedProvs(){
  const host = $('#provPicked');
  host.innerHTML = S.pickedProvs.map(code=>{
    const p = S.provinces.find(x=>x.code===code);
    return `<span class="pill-item">${h(p?`${code} ${p.name}`:code)} <button data-code="${h(code)}" aria-label="เอาออก">×</button></span>`;
  }).join('');
  host.querySelectorAll('button[data-code]').forEach(b=>b.addEventListener('click',()=>{
    S.pickedProvs = S.pickedProvs.filter(c=>c!==b.dataset.code); renderPickedProvs();
  }));
  updateCityCmdPreview();
}
function fillCityArea(){
  $('#cArea').innerHTML = '<option value="">—</option>' + S.areas.map(a=>`<option value="${h(a.name)}">${h(a.name)}</option>`).join('');
}
function cityArgs(){
  return {
    provinces: S.pickedProvs.slice(),
    area: $('#cArea').value || null,
    layer: $('#cLayer').value.trim() || null,
    token: $('#cToken').value.trim() || null,
    format: $('#cFormat').value,
    method: $('#cMethod').value,
  };
}
function updateCityCmdPreview(){
  const a = cityArgs();
  const parts = ['python fetch_cityplanning.py', ...a.provinces];
  if(a.area) parts.push('--area','areas/'+a.area);
  if(a.layer) parts.push('--layer',a.layer);
  if(a.token) parts.push('--token','***');
  if(a.format&&a.format!=='both') parts.push('--format',a.format);
  if(a.method&&a.method!=='auto') parts.push('--method',a.method);
  $('#cityCmdPreview').textContent = parts.join(' ');
}
['cArea','cFormat','cMethod','cLayer','cToken'].forEach(id=>$('#'+id).addEventListener('input',updateCityCmdPreview));
$('#runCity').addEventListener('click',async()=>{
  const args = cityArgs(); if(args.provinces.length===0) return alert('ยังไม่เลือกจังหวัด');
  try{
    const r = await postJSON('/run', {kind:'cityplanning', cityplanning:args});
    openJob(r.job_id); switchTo('monitor');
  }catch(e){ alert('Start fail: '+e.message); }
});

// ─────────────── monitor ───────────────
async function openJob(id){
  if(S.monEvents){ S.monEvents.close(); S.monEvents=null; }
  const j = await api(`/jobs/${id}`);
  S.currentJob = j;
  $('#monTitle').textContent = `Job ${j.id} · ${j.kind}`;
  $('#monCmd').textContent = (j.cmd||[]).join(' ');
  setMonStatus(j.status);
  $('#monLog').textContent = '';
  updateProgress(j.progress);
  initMonMap();
  const areaName = j.kind==='parcel' ? (j.args?.areas||[])[0] : j.args?.area;
  if(areaName){
    try{ showAreaOnMap(S.maps.mon,'mon', await api(`/areas/${encodeURIComponent(areaName)}/geojson`)); }catch{}
  }
  // stream ส่ง log ย้อนหลัง 100 บรรทัดมาก่อน แล้วค่อย live -> ใช้ stream อย่างเดียวพอ ไม่ซ้ำ
  const es = new EventSource(`${API}/jobs/${id}/stream`);
  S.monEvents = es;
  es.onmessage = ev => {
    const d = JSON.parse(ev.data);
    if(d.type==='line'){
      appendLog(d.line);
      if(d.progress) updateProgress(d.progress);
    }else if(d.type==='status'){
      S.currentJob.status = d.status;
      setMonStatus(d.status);
      if(d.status!=='running' && d.status!=='pending'){ es.close(); S.monEvents=null; S.currentJob.ended_at ||= Date.now()/1000; loadJobs(); loadOutput(); }
    }
  };
  startDurationTicker();
}
function setMonStatus(st){
  $('#monBadge').className = 'badge b-'+st;
  $('#monBadge').textContent = st;
  $('#cancelBtn').disabled = st !== 'running';
  $('#monToOutput').hidden = st !== 'done';
}
function appendLog(line){
  const log = $('#monLog');
  const div = document.createElement('div');
  const cls = /error|ผิดพลาด|fail/i.test(line) ? 'l-err' : /warn|เตือน/i.test(line) ? 'l-warn' : /\bok\b|สำเร็จ|เสร็จ|done/i.test(line) ? 'l-ok' : '';
  if(cls) div.className=cls;
  div.textContent = line;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
}
function updateProgress(p){
  if(!p || p.percent==null){ $('#monPbar').classList.add('indet'); $('#monPct').textContent='—'; return; }
  $('#monPbar').classList.remove('indet');
  $('#monPbar').querySelector('.fill').style.width = Math.min(100,p.percent)+'%';
  $('#monPct').textContent = `${p.percent.toFixed(1)}%${p.n!=null?' ('+p.n+'/'+p.total+')':''}`;
}
let durTimer=null;
function startDurationTicker(){
  if(durTimer) clearInterval(durTimer);
  durTimer = setInterval(()=>{
    const j=S.currentJob; if(!j||!j.started_at){ $('#monDuration').textContent='—'; return; }
    $('#monDuration').textContent = dur(j.started_at, j.status==='running' ? null : j.ended_at);
  },1000);
}
$('#cancelBtn').addEventListener('click',async()=>{
  if(!S.currentJob || !confirm('ยกเลิก job นี้?')) return;
  await api(`/jobs/${S.currentJob.id}/cancel`,{method:'POST'});
});

// ─────────────── boot ───────────────
async function healthCheck(){
  try{ await api('/jobs'); $('#svDot').style.background='var(--green)'; }
  catch{ $('#svDot').style.background='var(--red)'; $('#svPill').textContent='server unreachable'; }
}
$('#svPill').textContent = location.host;
healthCheck();
refreshOverview();
setInterval(loadJobs, 5000);
// รอ script อื่น (docs.js) ลงทะเบียน TAB_INIT ก่อน แล้วค่อยเปิดหน้าตาม hash
window.addEventListener('DOMContentLoaded', routeFromHash);
