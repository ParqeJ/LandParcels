// 📖 คู่มือ — แสดง README.md + docs/*.md ในหน้า dashboard (ใช้ $, $$, api, h, readError, TAB_INIT จาก app.js)
// marked + DOMPurify โหลดจาก CDN ตอนเปิดหน้านี้ครั้งแรก · ไม่มี internet = แสดงเป็นข้อความดิบแทน

const DOC_LIBS = [
  ['https://cdn.jsdelivr.net/npm/marked@12.0.2/marked.min.js',
   'sha384-/TQbtLCAerC3jgaim+N78RZSDYV7ryeoBCVqTuzRrFec2akfBkHS7ACQ3PQhvMVi'],
  ['https://cdn.jsdelivr.net/npm/dompurify@3.1.6/dist/purify.min.js',
   'sha384-+VfUPEb0PdtChMwmBcBmykRMDd+v6D/oFmB3rZM/puCMDYcIvF968OimRh4KQY9a'],
];
const DOCS = { list: null, current: null, libs: null };

function loadScript([src, integrity]){
  return new Promise((ok, fail)=>{
    const s = document.createElement('script');
    Object.assign(s, { src, integrity, crossOrigin: 'anonymous', onload: ok });
    s.onerror = ()=>fail(new Error('โหลดตัวแสดงผล markdown ไม่ได้ (ต้องมี internet)'));
    document.head.appendChild(s);
  });
}
function docLibs(){
  DOCS.libs ??= Promise.all(DOC_LIBS.map(loadScript)).catch(e=>{ DOCS.libs = null; throw e; });
  return DOCS.libs;
}

/** slug แบบเดียวกับ GitHub — ลิงก์ #หัวข้อ ในไฟล์ .md จึงใช้ได้ทั้งบน GitHub และใน dashboard */
function docSlug(text){
  return text.trim().toLowerCase().replace(/[^\p{L}\p{N}\p{M}\s_-]/gu, '').replace(/\s/g, '-');
}

/** href ในไฟล์ .md -> {external} | {doc, anchor} (คู่มืออีกหน้า/หัวข้อ) | {} (ไฟล์ในเครื่อง เปิดจากเว็บไม่ได้) */
function docLink(raw, current){
  let href = raw;
  try{ href = decodeURIComponent(raw); }catch{}
  if(/^[a-z][a-z0-9+.-]*:/i.test(href)) return { external: true };
  if(href.startsWith('#')) return { doc: current, anchor: href.slice(1) };
  const m = href.match(/(?:^|\/)([\w-]+)\.md(?:#(.*))?$/i);
  if(m){
    const name = m[1].toLowerCase()==='readme' ? 'index' : m[1];
    if(DOCS.list.some(d=>d.name===name)) return { doc: name, anchor: m[2] };
  }
  return {};
}

function decorateDoc(root, name){
  const used = new Map();
  root.querySelectorAll('h1,h2,h3,h4').forEach(hd=>{
    const base = docSlug(hd.textContent), n = used.get(base) || 0;
    used.set(base, n+1);
    hd.id = 'doc-' + (n ? `${base}-${n}` : base);
  });
  root.querySelectorAll('a[href]').forEach(a=>{
    const t = docLink(a.getAttribute('href'), name);
    if(t.external){ a.target = '_blank'; a.rel = 'noopener noreferrer'; return; }
    if(t.doc){ a.setAttribute('href', `#docs/${t.doc}` + (t.anchor ? `/${t.anchor}` : '')); return; }
    const span = document.createElement('span');
    span.className = 'doc-local';
    span.title = 'ไฟล์ในเครื่อง: ' + a.getAttribute('href');
    span.append(...a.childNodes);
    a.replaceWith(span);
  });
}

function renderDocToc(){
  $('#docToc').innerHTML = DOCS.list.map(d=>
    `<a href="#docs/${h(d.name)}" class="${d.name===DOCS.current?'active':''}"${d.name===DOCS.current?' aria-current="page"':''}>`
    + `<span class="t">${h(d.title)}</span><span class="f">${d.name==='index'?'README.md':'docs/'+h(d.name)+'.md'}</span></a>`
  ).join('');
}

async function renderDoc(name){
  const body = $('#docBody');
  body.innerHTML = '<p class="muted">กำลังโหลด…</p>';
  const r = await fetch(`${API}/docs/${encodeURIComponent(name)}`);
  if(!r.ok) throw await readError(r);
  const md = await r.text();
  try{
    await docLibs();
    body.innerHTML = DOMPurify.sanitize(marked.parse(md));
  }catch(e){
    body.innerHTML = `<div class="warn">${h(e.message)} — แสดงเป็นข้อความดิบแทน</div><pre class="raw">${h(md)}</pre>`;
  }
  decorateDoc(body, name);
  DOCS.current = name;
}

/** @param {string} [arg] 'parcel' หรือ 'parcel/หัวข้อ' จาก #docs/parcel/หัวข้อ */
async function openDocs(arg){
  const [name, anchor] = (arg || DOCS.current || 'index').split('/');
  try{
    DOCS.list ??= (await api('/docs')).items;
    if(name !== DOCS.current) await renderDoc(name);
    renderDocToc();
    history.replaceState(null, '', `#docs/${name}` + (anchor ? `/${anchor}` : ''));
    const target = anchor && document.getElementById('doc-' + anchor);
    (target || $('#sec-docs')).scrollIntoView({ block: 'start' });
  }catch(e){
    $('#docBody').innerHTML = `<div class="warn">เปิดคู่มือไม่ได้: ${h(e.message)}</div>`;
  }
}
TAB_INIT.docs = openDocs;
