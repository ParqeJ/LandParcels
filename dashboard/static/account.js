// theme (สว่าง/มืด/ตามระบบ) + บัญชี LandsMaps — โหลดหลัง app.js (ใช้ $, api, postJSON, h)

// ─────────────── theme ───────────────
const THEME_KEY = 'lp-theme';
const darkQuery = matchMedia('(prefers-color-scheme: dark)');
function themePref(){ try{ return localStorage.getItem(THEME_KEY) || 'auto'; }catch{ return 'auto'; } }
function applyTheme(pref){
  const dark = pref==='dark' || (pref==='auto' && darkQuery.matches);
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';
  $$('.theme-switch button').forEach(b=>b.setAttribute('aria-pressed', String(b.dataset.theme===pref)));
}
$$('.theme-switch button').forEach(b=>b.addEventListener('click',()=>{
  try{ localStorage.setItem(THEME_KEY, b.dataset.theme); }catch{}
  applyTheme(b.dataset.theme);
}));
darkQuery.addEventListener('change',()=>{ if(themePref()==='auto') applyTheme('auto'); });
applyTheme(themePref());

// ─────────────── บัญชี LandsMaps ───────────────
let AUTH = null;

function fmtRemain(sec){
  if(sec==null) return '';
  if(sec<=0) return 'หมดอายุแล้ว';
  const hr = Math.floor(sec/3600), mn = Math.floor(sec%3600/60);
  return hr>0 ? `เหลือ ${hr} ชม. ${mn} นาที` : `เหลือ ${mn} นาที`;
}
function fmtDate(iso){
  if(!iso) return '—';
  return new Date(iso).toLocaleString('th-TH',{dateStyle:'medium',timeStyle:'short'});
}
function authState(a){ return a.logged_in ? 'ok' : (a.expired ? 'expired' : 'none'); }

function renderAuthPill(a){
  const pill = $('#authPill');
  pill.dataset.state = authState(a);
  $('#authPillText').textContent = a.logged_in
    ? `${a.user || 'เข้าสู่ระบบแล้ว'} · ${fmtRemain(a.remaining_sec)}`
    : (a.expired ? 'token หมดอายุ' : 'ยังไม่เข้าสู่ระบบ');
  pill.title = `${a.provider}\nโควตาค้นรายละเอียด ${a.quota} แปลง/วัน`;
}

function renderAccount(a){
  const box = $('#acctState');
  box.dataset.state = authState(a);
  $('#acctHeadline').textContent = a.logged_in ? 'เข้าสู่ระบบแล้ว'
    : a.expired ? 'token หมดอายุแล้ว' : 'ยังไม่ได้เข้าสู่ระบบ';
  $('#acctSub').textContent = a.logged_in
    ? 'fetch_parcels.py จะใช้ token ของบัญชีนี้ (โควตาสูงกว่าแบบไม่ล็อกอิน)'
    : 'ตอนนี้ใช้แบบสาธารณะ — ดึงรูปแปลงได้ แต่ค้นรายละเอียดได้น้อย';
  $('#acctUser').textContent = a.user || '—';
  $('#acctExpire').textContent = a.expires_at ? `${fmtDate(a.expires_at)} (${fmtRemain(a.remaining_sec)})` : '—';
  $('#acctQuota').textContent = `${a.quota} แปลง/วัน`;
  $('#acctRemember').textContent = a.remembered ? 'จำไว้ในเครื่อง (ต่ออายุอัตโนมัติตอนรัน)' : 'ไม่ได้จำ';
  $('#acctSource').textContent = a.source==='env' ? 'ตัวแปร LANDSMAPS_TOKEN' : a.source==='file' ? 'Access_Key.txt' : '—';
  $('#renewBtn').disabled = !a.remembered;
  $('#logoutBtn').disabled = !a.logged_in && !a.expired;
  $('#forgetBtn').disabled = !a.remembered && !a.user;
  $('#acctEnvNote').hidden = a.source!=='env';
  if(a.error) setAuthMsg(a.error, 'err');
}

function renderParcelHint(a){
  const el = $('#parcelAuthHint');
  if(!el) return;
  el.hidden = a.logged_in;
  el.querySelector('span').textContent = a.expired
    ? 'token LandsMaps หมดอายุ — ค้นรายละเอียดแปลงจะได้โควตาแบบสาธารณะ'
    : `ยังไม่เข้าสู่ระบบ LandsMaps — ค้นรายละเอียดได้ ${a.quota} แปลง/วัน`;
}

async function refreshAuth(){
  try{
    AUTH = await api('/auth/status');
  }catch(e){
    $('#authPillText').textContent = 'เช็คบัญชีไม่ได้';
    return;
  }
  renderAuthPill(AUTH); renderAccount(AUTH); renderParcelHint(AUTH);
}

function setAuthMsg(text, kind=''){
  const el = $('#authMsg');
  el.textContent = text; el.className = 'form-msg' + (kind ? ' '+kind : '');
}
function setAuthBusy(busy){
  ['loginBtn','renewBtn','logoutBtn','forgetBtn'].forEach(id=>{ $('#'+id).disabled = busy; });
  $('#loginBtn').textContent = busy ? 'กำลังเข้าสู่ระบบกับ LandsMaps…' : 'เข้าสู่ระบบด้วย LandsMaps (DGA)';
}
async function authCall(path, body, okMsg){
  setAuthBusy(true); setAuthMsg('');
  try{
    AUTH = await postJSON(path, body);
    setAuthMsg(okMsg(AUTH), 'ok');
  }catch(e){
    setAuthMsg(e.message, 'err');
  }finally{
    setAuthBusy(false);
    if(AUTH){ renderAuthPill(AUTH); renderAccount(AUTH); renderParcelHint(AUTH); }
  }
}

$('#loginForm').addEventListener('submit', e=>{
  e.preventDefault();
  const user = $('#dgaUser').value.trim(), password = $('#dgaPass').value;
  if(!user || !password){ setAuthMsg('กรอกบัญชีผู้ใช้และรหัสผ่าน', 'err'); return; }
  authCall('/auth/login', {user, password, remember: $('#dgaRemember').checked},
    a=>`✓ เข้าสู่ระบบแล้ว · ${fmtRemain(a.remaining_sec)}`)
    .then(()=>{ $('#dgaPass').value=''; });
});
$('#renewBtn').addEventListener('click',()=>authCall('/auth/login', {}, a=>`✓ ต่ออายุแล้ว · ${fmtRemain(a.remaining_sec)}`));
$('#logoutBtn').addEventListener('click',()=>authCall('/auth/logout', {forget:false},
  a=>a.remembered ? 'ออกจากระบบแล้ว — บัญชียังจำไว้ รอบหน้าที่รัน fetch_parcels.py จะล็อกอินให้อีก' : 'ออกจากระบบแล้ว'));
$('#forgetBtn').addEventListener('click',()=>{
  if(!confirm('ออกจากระบบและลบบัญชี/รหัสผ่านที่จำไว้ใน Access_Key.txt และ .env ?')) return;
  authCall('/auth/logout', {forget:true}, ()=>'ออกจากระบบและลืมบัญชีแล้ว');
});
$('#togglePw').addEventListener('click',()=>{
  const inp = $('#dgaPass'), show = inp.type==='password';
  inp.type = show ? 'text' : 'password';
  $('#togglePw').textContent = show ? 'ซ่อน' : 'แสดง';
  $('#togglePw').setAttribute('aria-pressed', String(show));
});
$('#authPill').addEventListener('click',()=>switchTo('account'));

refreshAuth();
setInterval(refreshAuth, 60_000);
