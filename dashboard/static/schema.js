// หน้า 🗂 ตั้งค่าผลลัพธ์ (ใช้ $, $$, h, api, postJSON, S, loadUserSchemaCount จาก app.js)
// parcel: ฟิลด์หลักจาก LandsMaps (ติ๊กออก/เปลี่ยนชื่อได้) + add-on กรอกเอง + ฟิลด์เสริม + พรีวิว 1 แปลง
// cityplanning: ฟิลด์หลัก 12 (ติ๊กออก/เปลี่ยนชื่อได้) + ปุ่ม preset คืนค่าเริ่มต้น + ฟิลด์เสริม
const SHP_NAME_MAX = 10;
const ADDON_TYPES = ['str', 'int', 'float'];
const SCH = { sample: null, base: new Map(), addons: [], cityBase: new Map() };

async function loadSchema(){
  if(!S.catalogs.parcel){
    const [p, c, u, s] = await Promise.all([
      api('/catalog/parcel'), api('/catalog/cityplanning'), api('/user-schema'),
      api('/schema/sample').catch(()=>({ sample: null })),
    ]);
    S.catalogs.parcel = p; S.catalogs.cityplanning = c; SCH.sample = s.sample;
    applyUserSchema(u);
  }
  renderSchema();
}
function applyUserSchema(u){
  buildExtras('parcel', u.parcel?.extra_fields);
  buildExtras('cityplanning', u.cityplanning?.extra_fields);
  buildCore(u.parcel);
  buildCityCore(u.cityplanning);
}
/** ฟิลด์หลัก 12 ของผังเมือง: ไม่มี base_fields (รูปแบบเดิม/ยังไม่เคยบันทึก) = preset ติ๊กครบ ชื่อเดิม */
function buildCityCore(c){
  const cat = S.catalogs.cityplanning, hasLayout = Array.isArray(c?.base_fields);
  const savedBase = new Map((c?.base_fields||[]).map(b=>[b.field, b.name]));
  SCH.cityBase = new Map((cat.base_fields||[]).map(d=>[d.field, {
    checked: !hasLayout || savedBase.has(d.field), name: savedBase.get(d.field) ?? d.field,
  }]));
}
function applyCityPreset(){
  const cat = S.catalogs.cityplanning;
  SCH.cityBase = new Map((cat.base_fields||[]).map(d=>[d.field, { checked: true, name: d.field }]));
  renderSchema();
}
function buildExtras(key, saved){
  const cat = S.catalogs[key];
  const fixed = new Set(key==='parcel' ? [] : cat.fixed_fields||[]);
  const savedMap = new Map((saved||[]).map(x=>[x.source, x.name]));
  S.schemaState[key] = new Map((cat.groups||[]).flatMap(g=>g.fields||[]).map(f=>{
    const isFixed = fixed.has(f.label), name = savedMap.get(f.source);
    return [f.source, { checked: isFixed || name != null, name: name ?? f.label, fixed: isFixed }];
  }));
}
/** ไฟล์ที่ไม่มี base_fields (รูปแบบเดิม/ยังไม่เคยบันทึก) = preset ANIS POWER: ติ๊กครบ 14 ฟิลด์ */
function buildCore(p){
  const cat = S.catalogs.parcel, hasLayout = Array.isArray(p?.base_fields);
  const savedBase = new Map((p?.base_fields||[]).map(b=>[b.field, b.name]));
  SCH.base = new Map((cat.base_fields||[]).map(d=>[d.field, {
    checked: !hasLayout || !!d.locked || savedBase.has(d.field), name: savedBase.get(d.field) ?? d.field,
  }]));
  const saved = hasLayout ? (p.addon_fields||[]) : [];
  const presets = (cat.addon_presets||[]).map(pr=>{
    const hit = saved.find(a=>a.name===pr.name);
    return { name: pr.name, type: hit?.type || pr.type || 'str', desc: pr.desc, preset: true, checked: !hasLayout || !!hit };
  });
  const presetNames = new Set(presets.map(a=>a.name));
  const custom = saved.filter(a=>!presetNames.has(a.name)).map(a=>({ name: a.name, type: a.type||'str', preset: false, checked: true }));
  SCH.addons = [...presets, ...custom];
}
function applyPreset(kind){
  const cat = S.catalogs.parcel;
  SCH.base = new Map((cat.base_fields||[]).map(d=>[d.field, { checked: true, name: d.field }]));
  SCH.addons = (cat.addon_presets||[]).map(pr=>({ ...pr, type: pr.type||'str', preset: true, checked: kind==='anispower' }));
  renderSchema();
}

// ─────────────── ค่าในแปลงตัวอย่าง (เลียนแบบ landsmaps/export.py) ───────────────
const pick = (obj, path)=>path.split('.').reduce((o,k)=>o==null ? undefined : o[k], obj);
const waTotal = info=>(Number(info?.wa)||0) + (Number(info?.subwa)||0)/10;
function ringArea(ring){ let a=0; for(let i=0;i<ring.length-1;i++) a += ring[i][0]*ring[i+1][1] - ring[i+1][0]*ring[i][1]; return Math.abs(a)/2; }
function areaM2(geom){
  const polys = geom?.type==='Polygon' ? [geom.coordinates] : geom?.type==='MultiPolygon' ? geom.coordinates : [];
  const first = polys[0]?.[0]?.[0];
  if(!first || Math.abs(first[0]) < 1000) return undefined;          // พิกัดเป็นองศา -> ไม่คำนวณ (ต้องเป็นเมตร UTM)
  return Math.round(polys.reduce((s,p)=>s + ringArea(p[0]) - p.slice(1).reduce((t,r)=>t+ringArea(r),0), 0)*100)/100;
}
function exampleOf(source){
  const f = (S.catalogs.parcel.groups||[]).flatMap(g=>g.fields||[]).find(x=>x.source===source);
  return f?.example;
}
function sampleValue(source){
  const s = SCH.sample, info = s?.info;
  if(!s) return exampleOf(source);
  switch(source){
    case 'seq': return s.seq;
    case 'wfs.land_no': return s.land_no;
    case 'system': return '';
    case 'info.parcel_type': return info.parcel_type || 'โฉนดที่ดิน';
    case 'virtual.wa_total': return waTotal(info);
    case 'virtual.rawang_short': return (info.utm||'').split(' (')[0];
    case 'virtual.area_m2': return areaM2(s.geometry);
  }
  return source.startsWith('info.') ? pick(info, source.slice(5)) : undefined;
}
function castValue(v, type){
  if(v==null || v==='') return v;
  if(type==='int') return parseInt(v, 10) || 0;
  if(type==='float') return Number(v) || 0;
  return typeof v==='object' ? JSON.stringify(v) : String(v);
}
function fmtVal(v){
  if(v===undefined) return '<span class="muted">—</span>';
  if(v===null || v==='') return '<span class="muted">(ว่าง)</span>';
  return h(v);
}
const hasVal = v=>v!==undefined && v!==null && v!=='';

// ─────────────── รายการฟิลด์ที่จะออกใน output (ลำดับคอลัมน์) ───────────────
/** @returns {{id:string,name:string,source:string,type:string,kind:'base'|'addon'|'extra'}[]} */
function outputFields(key){
  const out = [];
  if(key==='parcel'){
    for(const d of S.catalogs.parcel.base_fields||[]){
      const st = SCH.base.get(d.field);
      if(st?.checked) out.push({ id:`b:${d.field}`, name:st.name, source:d.source, type:d.type, kind:'base' });
    }
    SCH.addons.forEach((a,i)=>{ if(a.checked) out.push({ id:`a:${i}`, name:a.name, source:'', type:a.type, kind:'addon' }); });
  }else if(key==='cityplanning'){
    for(const d of S.catalogs.cityplanning.base_fields||[]){
      const st = SCH.cityBase.get(d.field);
      if(st?.checked) out.push({ id:`cb:${d.field}`, name:st.name, source:d.source, type:d.type, kind:'base' });
    }
  }
  for(const g of S.catalogs[key].groups||[]) for(const f of g.fields||[]){
    const st = S.schemaState[key].get(f.source);
    if(st?.checked && !st.fixed) out.push({ id:`x:${f.source}`, name:st.name, source:f.source, type:f.type, kind:'extra' });
  }
  return out;
}
/** ปัญหาชื่อ -> Map(id -> ข้อความ) · DBF ไม่แยกตัวพิมพ์ จึงเทียบตัวเล็ก (กฎเดียวกับ server) */
function schemaProblems(key){
  // parcel + cityplanning: ฟิลด์หลักแก้ชื่อได้แล้ว อยู่ใน outputFields -> ชนกันตรวจด้วย seen ไม่ต้อง reserve
  const reserved = new Map();
  const seen = new Map(), out = new Map();
  for(const f of outputFields(key)){
    const low = f.name.toLowerCase();
    if(!f.name) out.set(f.id, 'ยังไม่ได้ตั้งชื่อ');
    else if(f.name.length > SHP_NAME_MAX) out.set(f.id, `เกิน ${SHP_NAME_MAX} ตัวอักษร`);
    else if(reserved.has(low)) out.set(f.id, `ซ้ำกับฟิลด์มาตรฐาน ${reserved.get(low)}`);
    else if(seen.has(low)){
      out.set(f.id, `ชื่อ "${f.name}" ซ้ำกับฟิลด์อื่น`);
      if(!out.has(seen.get(low))) out.set(seen.get(low), `ชื่อ "${f.name}" ซ้ำกับฟิลด์อื่น`);
    }
    else seen.set(low, f.id);
  }
  return out;
}

// ─────────────── render ───────────────
function fieldRow({ id, checked, locked, code, desc, sample, name, nameEditable=true, typeCell }){
  const ex = hasVal(sample) ? ` <span class="ex">→ ${h(sample)}</span>` : '';
  return `<div class="field${locked?' locked':''}">
    <input type="checkbox" ${checked?'checked':''} ${locked?'disabled':''} data-id="${h(id)}" aria-label="เลือก ${h(name)}">
    <code>${h(code)}</code>
    <span class="desc" title="${h((desc||'') + (hasVal(sample) ? ` · ตัวอย่าง: ${sample}` : ''))}">${h(desc||'—')}${ex}</span>
    <input type="text" value="${h(name)}" ${nameEditable?'':'disabled'} data-id="${h(id)}" maxlength="${SHP_NAME_MAX}" aria-label="ชื่อฟิลด์ใน output">
    ${typeCell}
  </div>`;
}
function renderParcelCore(){
  const cat = S.catalogs.parcel, parts = [];
  const nBase = [...SCH.base.values()].filter(s=>s.checked).length;
  parts.push(`<div class="group"><h4><span>ฟิลด์หลักจาก LandsMaps</span><span class="g-count">${nBase}/${SCH.base.size}</span></h4>`);
  for(const d of cat.base_fields||[]){
    const st = SCH.base.get(d.field);
    parts.push(fieldRow({ id:`b:${d.field}`, checked:st.checked, locked:d.locked, code:d.source, desc:d.desc,
      sample: castValue(sampleValue(d.source), d.type), name:st.name, typeCell:`<span class="type">${h(d.type)}</span>` }));
  }
  parts.push('</div>');
  const nAdd = SCH.addons.filter(a=>a.checked).length;
  parts.push(`<div class="group addon"><h4><span>ฟิลด์ add-on — กรอกเองทีหลัง (LandsMaps ไม่มีข้อมูลนี้ ออกมาเป็นคอลัมน์ว่าง)</span><span class="g-count">${nAdd}/${SCH.addons.length}</span></h4>`);
  SCH.addons.forEach((a,i)=>{
    const sel = `<select data-id="a:${i}" aria-label="ชนิดข้อมูล">${ADDON_TYPES.map(t=>`<option ${t===a.type?'selected':''}>${t}</option>`).join('')}</select>`;
    const del = a.preset ? '' : `<button class="btn ghost sm" data-del="${i}" title="ลบ add-on นี้" aria-label="ลบ ${h(a.name)}">🗑</button>`;
    parts.push(fieldRow({ id:`a:${i}`, checked:a.checked, code:a.preset?'LandParcels':'กำหนดเอง', desc:a.desc||'คอลัมน์ว่างไว้กรอกเอง',
      name:a.name, typeCell:`<span class="row" style="gap:4px">${sel}${del}</span>` }));
  });
  parts.push(`<div class="field add-row"><span></span><button class="btn ghost sm" id="addAddon" type="button">+ เพิ่มฟิลด์ add-on</button></div></div>`);
  return parts.join('');
}
function renderCityCore(){
  const cat = S.catalogs.cityplanning, parts = [];
  const nBase = [...SCH.cityBase.values()].filter(s=>s.checked).length;
  parts.push(`<div class="group"><h4><span>ฟิลด์หลักผังเมือง</span><span class="g-count">${nBase}/${SCH.cityBase.size}</span></h4>`);
  for(const d of cat.base_fields||[]){
    const st = SCH.cityBase.get(d.field);
    parts.push(fieldRow({ id:`cb:${d.field}`, checked:st.checked, code:d.source, desc:d.desc,
      sample: d.example, name:st.name, typeCell:`<span class="type">${h(d.type)}</span>` }));
  }
  parts.push('</div>');
  return parts.join('');
}
function renderExtras(key){
  const cat = S.catalogs[key], parts = [];
  for(const g of cat.groups||[]){
    const chosen = g.fields.filter(f=>S.schemaState[key].get(f.source).checked).length;
    parts.push(`<div class="group"><h4><span>${h(g.name)}</span><span class="g-count">${chosen}/${g.fields.length}</span></h4>`);
    for(const f of g.fields){
      const st = S.schemaState[key].get(f.source);
      parts.push(fieldRow({ id:`x:${f.source}`, checked:st.checked, locked:st.fixed, code:f.source, desc:f.desc,
        sample: key==='parcel' ? castValue(sampleValue(f.source), f.type) : f.example, name:st.name, nameEditable:!st.fixed,
        typeCell:`<span class="type">${h(f.type||'')}</span>` }));
    }
    parts.push('</div>');
  }
  return parts.join('');
}
function renderPreview(){
  const s = SCH.sample, fields = outputFields('parcel');
  const head = s ? `แปลงจริงจาก cache ของพื้นที่ <code>${h(s.site)}</code> · เลขที่ดิน ${h(s.land_no)}`
                 : 'ยังไม่เคยดึงรายละเอียด — ใช้ค่าตัวอย่างจาก catalog แทน';
  const rows = fields.map(f=>{
    const val = f.kind==='addon' ? '<span class="muted">(ว่าง — กรอกเอง)</span>' : fmtVal(castValue(sampleValue(f.source), f.type));
    return `<tr class="k-${f.kind}"><td><code>${h(f.name||'?')}</code></td><td>${val}</td><td class="muted">${h(f.kind==='addon' ? 'กรอกเอง' : f.source)}</td></tr>`;
  }).join('');
  return `<div class="card sch-preview"><h3>พรีวิวผลลัพธ์ 1 แปลง <span class="muted">${fields.length} ฟิลด์</span></h3><div class="body">
    <div class="pv-top">${polygonSvg(s?.geometry)}<div class="muted pv-cap">${head}<br>ติ๊ก / เปลี่ยนชื่อด้านซ้าย → ตารางนี้เปลี่ยนตามทันที</div></div>
    <table class="pv-table"><thead><tr><th>ฟิลด์ใน output</th><th>ค่า</th><th>มาจาก</th></tr></thead>
    <tbody>${rows || '<tr><td colspan="3" class="muted">ยังไม่ได้เลือกฟิลด์</td></tr>'}</tbody></table>
  </div></div>`;
}
function polygonSvg(geom){
  const rings = geom?.type==='Polygon' ? [geom.coordinates[0]] : geom?.type==='MultiPolygon' ? geom.coordinates.map(p=>p[0]) : [];
  const pts = rings.flat();
  if(!pts.length) return '<svg class="pv-poly" viewBox="0 0 100 100" aria-hidden="true"><rect x="15" y="20" width="70" height="55" rx="2"/></svg>';
  const xs = pts.map(p=>p[0]), ys = pts.map(p=>p[1]);
  const x0 = Math.min(...xs), y0 = Math.min(...ys);
  const k = 90 / Math.max(Math.max(...xs)-x0, Math.max(...ys)-y0, 1e-9);
  const path = rings.map(r=>'M'+r.map(([x,y])=>`${(5+(x-x0)*k).toFixed(1)},${(95-(y-y0)*k).toFixed(1)}`).join('L')+'Z').join('');
  return `<svg class="pv-poly" viewBox="0 0 100 100" role="img" aria-label="รูปแปลงตัวอย่าง"><path d="${path}"/></svg>`;
}
function renderSchema(){
  $$('.tabs-sub button').forEach(b=>b.classList.toggle('active', b.dataset.stab===S.schemaTab));
  const host = $('#schHost'), key = S.schemaTab;
  if(!S.catalogs[key]){ host.innerHTML = '<div class="muted">กำลังโหลด…</div>'; return; }
  if(key==='parcel'){
    host.innerHTML = `<div class="toolbar">
        <button class="btn ghost sm" type="button" data-preset="anispower" title="ฟิลด์หลัก 8 + add-on 6 = 14 ฟิลด์เดิม (merge กับ CBD/BNN ได้)">LandParcels · 14 ฟิลด์เดิม</button>
        <button class="btn ghost sm" type="button" data-preset="landsmaps" title="เฉพาะฟิลด์ที่ LandsMaps ให้ ไม่มีคอลัมน์กรอกเอง">เฉพาะที่ LandsMaps ให้</button>
        <span class="muted">ติ๊กออก = ไม่เอาฟิลด์นั้น · แก้ชื่อในช่องขวาได้ (≤${SHP_NAME_MAX} ตัวอักษร)</span></div>
      <div class="sch-layout"><div>${renderParcelCore()}<h4 class="sch-sub">ฟิลด์เสริมจาก LandsMaps</h4>${renderExtras('parcel')}</div>
      <div id="schPreview">${renderPreview()}</div></div>`;
  }else{
    host.innerHTML = `<div class="toolbar">
        <button class="btn ghost sm" type="button" data-citypreset="default" title="ติ๊กครบ 12 ฟิลด์ ชื่อเดิม — ใช้ merge ได้">คืนค่าเริ่มต้น · 12 ฟิลด์ (merge ได้)</button>
        <span class="muted">ติ๊กออก = ไม่เอาฟิลด์นั้น · แก้ชื่อในช่องขวาได้ (≤${SHP_NAME_MAX} ตัวอักษร)</span></div>
      ${renderCityCore()}<h4 class="sch-sub">ฟิลด์เสริม</h4>${renderExtras(key)}`;
  }
  bindSchemaInputs(host, key);
  markSchemaProblems();
}
function bindSchemaInputs(host, key){
  const stateOf = id=>{
    const [kind, ...rest] = id.split(':'), k = rest.join(':');
    return kind==='b' ? SCH.base.get(k) : kind==='a' ? SCH.addons[Number(k)]
         : kind==='cb' ? SCH.cityBase.get(k) : S.schemaState[key].get(k);
  };
  host.querySelectorAll('input[type=checkbox]').forEach(cb=>cb.addEventListener('change',()=>{ stateOf(cb.dataset.id).checked = cb.checked; renderSchema(); }));
  host.querySelectorAll('input[type=text]').forEach(inp=>inp.addEventListener('input',()=>{
    stateOf(inp.dataset.id).name = inp.value.trim();
    if(key==='parcel') $('#schPreview').innerHTML = renderPreview();
    markSchemaProblems();
  }));
  host.querySelectorAll('select[data-id]').forEach(sel=>sel.addEventListener('change',()=>{ stateOf(sel.dataset.id).type = sel.value; renderSchema(); }));
  host.querySelectorAll('[data-del]').forEach(b=>b.addEventListener('click',()=>{ SCH.addons = SCH.addons.filter((_,i)=>i!==Number(b.dataset.del)); renderSchema(); }));
  host.querySelectorAll('[data-preset]').forEach(b=>b.addEventListener('click',()=>applyPreset(b.dataset.preset)));
  host.querySelectorAll('[data-citypreset]').forEach(b=>b.addEventListener('click',()=>applyCityPreset()));
  $('#addAddon')?.addEventListener('click',()=>{
    SCH.addons = [...SCH.addons, { name:'', type:'str', preset:false, checked:true }];
    renderSchema();
    $$('#schHost .group.addon input[type=text]').at(-1)?.focus();
  });
}
function markSchemaProblems(){
  const probs = schemaProblems(S.schemaTab);
  $$('#schHost input[type=text]').forEach(inp=>{
    const msg = probs.get(inp.dataset.id);
    inp.classList.toggle('bad', !!msg);
    inp.title = msg || '';
    if(msg) inp.setAttribute('aria-invalid','true'); else inp.removeAttribute('aria-invalid');
  });
  const label = new Map(outputFields(S.schemaTab).map(f=>[f.id, f.name || f.id]));
  showSchemaProblems([...probs].map(([id,msg])=>`${S.schemaTab} · ${label.get(id) || id}: ${msg}`));
}
function showSchemaProblems(lines){
  $('#schProblems').innerHTML = lines.map(t=>`<li class="bad"><b>⚠</b><span>${h(t)}</span></li>`).join('');
}

// ─────────────── save / reload ───────────────
$$('.tabs-sub button').forEach(b=>b.addEventListener('click',()=>{ S.schemaTab = b.dataset.stab; renderSchema(); }));
$('#schSave').addEventListener('click', async()=>{
  const bad = ['parcel','cityplanning'].find(k=>schemaProblems(k).size);
  if(bad){
    if(bad!==S.schemaTab){ S.schemaTab = bad; renderSchema(); }
    $('#schStatus').textContent = `✗ ยังไม่บันทึก — แก้ชื่อที่ขึ้นกรอบแดงใน ${bad} ก่อน`;
    $('#schHost input.bad')?.focus();
    return;
  }
  const extras = key=>outputFields(key).filter(f=>f.kind==='extra').map(f=>({ source:f.source, name:f.name }));
  const body = {
    parcel: {
      base_fields: outputFields('parcel').filter(f=>f.kind==='base').map(f=>({ field:f.id.slice(2), name:f.name })),
      addon_fields: SCH.addons.filter(a=>a.checked).map(a=>({ name:a.name, type:a.type })),
      extra_fields: extras('parcel'),
    },
    cityplanning: {
      base_fields: outputFields('cityplanning').filter(f=>f.kind==='base').map(f=>({ field:f.id.slice(3), name:f.name })),
      extra_fields: extras('cityplanning'),
    },
  };
  try{
    const r = await postJSON('/user-schema', body);
    $('#schStatus').textContent = '✓ บันทึก ' + r.path;
    loadUserSchemaCount();
  }catch(e){
    $('#schStatus').textContent = '✗ ' + e.message;
    showSchemaProblems(e.detail?.problems || []);
  }
});
$('#schReload').addEventListener('click', async()=>{
  applyUserSchema(await api('/user-schema'));
  renderSchema();
  $('#schStatus').textContent = '↻ โหลดจาก disk';
});
