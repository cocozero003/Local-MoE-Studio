"use strict";
const $ = id => document.getElementById(id);
const state = { csrf: null, user: null, currentChat: null, sending: false, setup: false, fdaReady: false };
const fmt = value => new Date(value * 1000).toLocaleString();
function notify(message) { const node = $('toast'); node.textContent = message; node.classList.remove('hidden'); setTimeout(() => node.classList.add('hidden'), 5000); }
async function request(path, { method = 'GET', data = null } = {}) {
  const headers = {};
  if (data !== null) headers['Content-Type'] = 'application/json';
  if (method !== 'GET' && state.csrf) headers['X-CSRF-Token'] = state.csrf;
  const response = await fetch(path, { method, headers, credentials: 'same-origin', body: data === null ? undefined : JSON.stringify(data) });
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || ('HTTP ' + response.status));
  return result;
}
function escapeNode(tag, text, cls) { const node = document.createElement(tag); if (cls) node.className = cls; node.textContent = text; return node; }
function renderAuth(setup) {
  state.setup = setup;
  $('application').classList.add('hidden'); $('auth-view').classList.remove('hidden');
  $('auth-title').textContent = setup ? 'Create administrator' : 'Sign in';
  $('auth-desc').textContent = setup ? 'First-run setup is available only on the server PC.' : 'Sign in with your team account.';
  $('auth-action').textContent = setup ? 'Create administrator' : 'Sign in';
  $('auth-error').textContent = '';
}
async function refreshIdentity() {
  try {
    const me = await request('/api/me');
    state.user = me; state.csrf = me.csrf;
    $('auth-view').classList.add('hidden'); $('application').classList.remove('hidden');
    $('account-name').textContent = me.username;
    $('admin-nav').classList.toggle('hidden', me.role !== 'admin');
    $('fda-update-nav').classList.toggle('hidden', me.role !== 'admin');
    $('endpoint').textContent = location.origin + '/v1';
    await refreshChats(); await refreshDocuments(); await refreshKeys();
    if (me.role === 'admin') { await refreshUsers(); await refreshManageStatus(); }
    await checkModel(); await checkFDA(); setInterval(checkModel, 12000);
    navigate('chat');
  } catch (_) {
    const setup = await request('/api/setup-required');
    renderAuth(setup.required && setup.local);
    if (setup.required && !setup.local) $('auth-error').textContent = 'Ask the computer administrator to finish local setup first.';
  }
}
async function checkModel() {
  try {
    const s = await request('/api/status');
    $('model-state').textContent = s.backend_ready ? 'Model ready' : 'Start model on host PC';
    $('model-dot').classList.toggle('online', s.backend_ready);
  } catch (_) { $('model-state').textContent = 'Connection lost'; $('model-dot').classList.remove('online'); }
}
async function checkFDA() {
  const option = $('chat-mode').querySelector('option[value="thai_fda"]');
  try {
    const s = await request('/api/fda/status');
    state.fdaReady = Boolean(s.available);
    option.disabled = !state.fdaReady;
    $('fda-mode-state').textContent = state.fdaReady ? 'V3.17 ready' : 'Thai FDA data/setup required';
    $('fda-mode-state').title = state.fdaReady ? s.engine : ((s.missing_files || []).join(', ') || s.dependency_error || 'Unavailable');
    if (!state.fdaReady && $('chat-mode').value === 'thai_fda') $('chat-mode').value = 'general';
  } catch (_) {
    state.fdaReady = false; option.disabled = true; $('fda-mode-state').textContent = 'Thai FDA mode unavailable';
  }
}
function navigate(page) {
  ['chat','documents','settings','updates','users'].forEach(p => $('page-' + p).classList.toggle('hidden', p !== page));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('current', b.dataset.page === page));
  $('page-title').textContent = ({chat:'Chat',documents:'My documents',settings:'API access',updates:'Data & updates',users:'Team members'})[page];
  if (page==='updates' && state.user?.role==='admin') refreshManageStatus();
}
function renderMessage(role, content) {
  const div = escapeNode('div', '', 'message ' + (role === 'user' ? 'user' : 'assistant'));
  div.append(escapeNode('div', role === 'user' ? 'You' : 'Assistant', 'speaker'));
  const text = escapeNode('div', content, 'body'); div.append(text); $('chat-history').append(div);
  $('chat-history').scrollTop = $('chat-history').scrollHeight;
  return text;
}
function renderFDAMeta(bodyNode, fda) {
  if (!fda || bodyNode.parentNode.querySelector('.fda-meta')) return;
  const box = escapeNode('div', '', 'fda-meta');
  const head = escapeNode('div', 'Thai FDA V3.17 precedent portfolio', 'fda-meta-title');
  box.append(head);
  const candidate = fda.candidate_class || 'not established';
  box.append(escapeNode('div', 'Candidate hypothesis: ' + candidate + ' | Human authorization required', 'fda-meta-note'));
  (fda.precedents || []).slice(0,5).forEach((p, i) => {
    const line = (i + 1) + '. ' + (p.portfolio_role || 'PRECEDENT') + ' — ' +
      (p.precedent_product || p.precedent_case_id || 'case') + ' (' + (p.precedent_year || '-') + ')' +
      (p.historical_class ? ' | historical: ' + p.historical_class : '');
    box.append(escapeNode('div', line, 'fda-meta-row'));
  });
  bodyNode.parentNode.append(box);
}
function welcome() {
  $('chat-history').replaceChildren();
  const w = escapeNode('div', '', 'welcome');
  w.append(escapeNode('h1', 'Your private AI workspace'));
  w.append(escapeNode('p', 'Choose General chat or Thai FDA precedent mode. The model and precedent retrieval run locally on your server computer.'));
  $('chat-history').append(w);
}
async function refreshChats() {
  const {items} = await request('/api/conversations');
  const list = $('chat-list'); list.replaceChildren();
  items.forEach(item => {
    const row = escapeNode('button', item.title, 'chat-row' + (state.currentChat === item.id ? ' active' : ''));
    row.addEventListener('click', () => selectChat(item.id)); list.append(row);
  });
}
async function newChat(title = 'New chat') {
  const result = await request('/api/conversations', {method:'POST',data:{title}});
  await selectChat(result.id); await refreshChats();
}
async function selectChat(id) {
  state.currentChat = id;
  const {items} = await request('/api/conversations/' + id);
  $('chat-history').replaceChildren(); items.forEach(item => renderMessage(item.role,item.content));
  if (!items.length) welcome();
  await refreshChats(); navigate('chat');
}
async function sendMessage() {
  if (state.sending) return;
  const text = $('message').value.trim();
  if (!text) return;
  if (text.length > 12000) return notify('Maximum message length is 12000 characters.');
  state.sending = true; $('send-message').disabled = true;
  try {
    if (!state.currentChat) await newChat(text.slice(0,65));
    const welcomeNode = document.querySelector('.welcome'); if (welcomeNode) welcomeNode.remove();
    renderMessage('user',text); $('message').value = '';
    const assistant = renderMessage('assistant','');
    $('send-status').textContent = 'Waiting for local GPU...';
    const response = await fetch('/api/chat/send', {
      method:'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':state.csrf},
      body:JSON.stringify({
        message:text,
        conversation_id:state.currentChat,
        use_documents:$('use-documents').checked,
        mode:$('chat-mode').value,
        fda_cutoff_year:2026,
        fda_retrieval_mode:'classification'
      })
    });
    if (!response.ok) { const error=await response.json(); throw new Error(error.error || 'Chat failed'); }
    const reader = response.body.getReader(); const decoder=new TextDecoder(); let buffer = '';
    while(true) {
      const {done,value} = await reader.read(); if(done)break;
      buffer += decoder.decode(value,{stream:true});
      const blocks=buffer.split('\n\n'); buffer=blocks.pop();
      for(const block of blocks) {
        const evt = /^event: ([^\n]+)/m.exec(block)?.[1];
        const data = /^data: (.*)$/m.exec(block)?.[1];
        if (!data) continue;
        let payload; try {payload=JSON.parse(data);}catch(_){continue;}
        if(evt==='delta') { assistant.textContent += payload.text; $('chat-history').scrollTop=$('chat-history').scrollHeight; }
        if(evt==='meta') {
          if (payload.fda) {
            renderFDAMeta(assistant,payload.fda);
            $('send-status').textContent='Thai FDA: using ' + (payload.fda.precedents || []).length + ' precedents' +
              (payload.sources?.length ? ' + ' + payload.sources.length + ' document excerpt(s)' : '');
          } else if (payload.sources?.length) {
            $('send-status').textContent='Using ' + payload.sources.length + ' document excerpt(s)';
          }
        }
        if(evt==='error') throw new Error(payload.error);
      }
    }
    $('send-status').textContent='Ready'; await refreshChats();
  } catch(e) { $('send-status').textContent='Error'; notify(e.message); }
  finally {state.sending=false;$('send-message').disabled=false;}
}
function rowList(id,items,render) { const box=$(id);box.replaceChildren(); if(!items.length) box.append(escapeNode('div','Nothing here yet.','item-row')); else items.forEach(i=>box.append(render(i))); }
function itemWithAction(title,sub,buttonText,onClick) {
  const row=escapeNode('div','','item-row'); const name=escapeNode('div',title);
  name.append(escapeNode('small',sub)); row.append(name);
  if(buttonText) {const b=escapeNode('button',buttonText); b.addEventListener('click',onClick);row.append(b);} return row;
}
async function refreshDocuments() {
  const {items}=await request('/api/documents');
  rowList('doc-list',items,x=>itemWithAction(x.name,'  Uploaded '+fmt(x.created),'Delete',async()=>{
    if (!confirm('Delete document '+x.name+'?'))return;
    try {await request('/api/documents/'+x.id,{method:'DELETE'});await refreshDocuments();}catch(e){notify(e.message);}
  }));
}
async function uploadDocument() {
  const file=$('document-file').files[0];if(!file)return notify('Choose a file first');
  if(file.size>6*1024*1024)return notify('Maximum document size is 6 MiB');
  $('upload-doc').disabled=true;$('upload-state').textContent='Reading and indexing...';
  try {
    const base64=await new Promise((resolve,reject)=>{const reader=new FileReader();
      reader.onload=()=>resolve(String(reader.result).split(',')[1]); reader.onerror=reject;reader.readAsDataURL(file);});
    const result=await request('/api/documents',{method:'POST',data:{name:file.name,content_base64:base64}});
    $('upload-state').textContent='Indexed '+result.characters+' characters'; $('document-file').value='';await refreshDocuments();
  } catch(e) {$('upload-state').textContent=e.message;}
  finally{$('upload-doc').disabled=false;}
}
async function searchDocuments() {
  const q=$('doc-query').value.trim();if(!q)return;
  try {
    const {items}=await request('/api/search?q='+encodeURIComponent(q));
    rowList('doc-results',items,x=>itemWithAction(x.name+' / section '+(x.seq+1),'  '+x.content.slice(0,260),'',null));
  } catch(e){notify(e.message);}
}
async function refreshKeys() {
  const {items}=await request('/api/keys');
  rowList('keys-list',items,x=>itemWithAction(x.prefix+'...','  Created '+fmt(x.created),'Revoke',async()=>{
    if(!confirm('Revoke this API key?'))return;
    await request('/api/keys/'+x.id,{method:'DELETE'});await refreshKeys();
  }));
}
async function refreshUsers() {
  const {items}=await request('/api/users');
  rowList('users-list',items,x=>itemWithAction(x.username,'  Role: '+x.role+' | Joined '+fmt(x.created),'',null));
}
async function fileBase64(file,maxBytes) {
  if(!file) throw new Error('Choose a file first');
  if(file.size>maxBytes) throw new Error('File is too large');
  return await new Promise((resolve,reject)=>{
    const reader=new FileReader();
    reader.onload=()=>resolve(String(reader.result).split(',')[1]);
    reader.onerror=reject; reader.readAsDataURL(file);
  });
}
async function refreshManageStatus() {
  if(state.user?.role!=='admin') return;
  try {
    const s=await request('/api/fda/manage/status');
    const d=s.data||{}, sw=s.software||{}, rt=s.runtime||{};
    $('fda-data-status').textContent =
      'Runtime: '+(rt.available?'ready':'not ready')+
      ' | Data version: '+(d.data_version||'unversioned')+
      ' | Backup: '+(d.backup_available?'available':'none')+
      ' | '+(d.data_dir||'');
    $('software-update-status').textContent =
      'Software '+(sw.version||'unknown')+
      (sw.commit?' | commit '+sw.commit.slice(0,10):'')+
      ' | '+(sw.source_root||'');
  } catch(e) {
    $('fda-data-status').textContent=e.message;
    $('software-update-status').textContent=e.message;
  }
}
async function uploadFDADataPack() {
  const file=$('fda-data-pack-file').files[0];
  $('upload-fda-data-pack').disabled=true;
  try {
    $('fda-data-action-state').textContent='Reading and validating data pack...';
    const b64=await fileBase64(file,32*1024*1024);
    const result=await request('/api/fda/data/import',{method:'POST',data:{name:file.name,content_base64:b64}});
    $('fda-data-action-state').textContent='Activated data version '+(result.data_version||'unversioned')+'. Previous version kept for rollback.';
    $('fda-data-pack-file').value=''; await checkFDA(); await refreshManageStatus();
  } catch(e) {$('fda-data-action-state').textContent=e.message;}
  finally {$('upload-fda-data-pack').disabled=false;}
}
async function rollbackFDAData() {
  if(!confirm('Rollback to the previous Thai FDA data pack?')) return;
  try {
    const r=await request('/api/fda/data/rollback',{method:'POST',data:{}});
    $('fda-data-action-state').textContent='Rolled back. Active data version: '+(r.data_version||'unversioned');
    await checkFDA(); await refreshManageStatus();
  } catch(e) {$('fda-data-action-state').textContent=e.message;}
}
async function stageFDASource() {
  const file=$('fda-source-file').files[0];
  try {
    $('fda-source-state').textContent='Staging source file...';
    const b64=await fileBase64(file,32*1024*1024);
    const r=await request('/api/fda/source/stage',{method:'POST',data:{name:file.name,content_base64:b64}});
    $('fda-source-state').textContent=r.note+' Saved to '+r.path;
    $('fda-source-file').value='';
  } catch(e) {$('fda-source-state').textContent=e.message;}
}
async function checkSoftwareUpdate() {
  try {
    $('software-update-state').textContent='Checking GitHub...';
    const r=await request('/api/software/update/check');
    $('software-update-state').textContent =
      r.update_available ? 'Update available: '+r.remote_commit.slice(0,10)+' — '+r.remote_message :
      'Software is current. Remote commit '+(r.remote_commit||'unknown').slice(0,10);
  } catch(e) {$('software-update-state').textContent=e.message;}
}
async function applyOnlineUpdate() {
  if(!confirm('Apply the latest Local MoE Studio source update? Thai FDA data will not be replaced. Restart Team Hub afterwards.')) return;
  try {
    $('software-update-state').textContent='Downloading and applying update...';
    const r=await request('/api/software/update/apply-online',{method:'POST',data:{}});
    $('software-update-state').textContent='Update applied. Backup: '+r.backup+'. Restart Team Hub now.';
    await refreshManageStatus();
  } catch(e) {$('software-update-state').textContent=e.message;}
}
async function uploadSoftwarePatch() {
  const file=$('software-patch-file').files[0];
  if(!confirm('Apply this software patch? Thai FDA data will not be replaced.')) return;
  try {
    $('software-update-state').textContent='Validating and applying patch...';
    const b64=await fileBase64(file,20*1024*1024);
    const r=await request('/api/software/patch/import',{method:'POST',data:{name:file.name,content_base64:b64}});
    $('software-update-state').textContent='Patch applied. Backup: '+r.backup+'. Restart Team Hub.';
    $('software-patch-file').value=''; await refreshManageStatus();
  } catch(e) {$('software-update-state').textContent=e.message;}
}
window.addEventListener('DOMContentLoaded',()=>{
  $('auth-form').addEventListener('submit',async e=>{ e.preventDefault();$('auth-error').textContent='';
    try {await request(state.setup?'/api/setup':'/api/login',{method:'POST',data:{username:$('login-name').value,password:$('login-pass').value}});await refreshIdentity();}
    catch(err){$('auth-error').textContent=err.message;}
  });
  document.querySelectorAll('.nav-btn').forEach(b=>b.addEventListener('click',()=>navigate(b.dataset.page)));
  $('logout').addEventListener('click',async()=>{await request('/api/logout',{method:'POST',data:{}});state.csrf=null;state.user=null;renderAuth(false);});
  $('new-chat').addEventListener('click',()=>newChat());
  $('send-message').addEventListener('click',sendMessage);
  $('message').addEventListener('keydown',e=>{if(e.key==='Enter'&&e.ctrlKey){e.preventDefault();sendMessage();}});
  $('upload-doc').addEventListener('click',uploadDocument);
  $('search-doc').addEventListener('click',searchDocuments);
  $('generate-key').addEventListener('click',async()=>{try {const result=await request('/api/keys',{method:'POST',data:{}});
    $('new-key').textContent=result.api_key; $('new-key').classList.remove('hidden');await refreshKeys();}catch(e){notify(e.message);}});
  $('upload-fda-data-pack').addEventListener('click',uploadFDADataPack);
  $('rollback-fda-data').addEventListener('click',rollbackFDAData);
  $('stage-fda-source').addEventListener('click',stageFDASource);
  $('check-software-update').addEventListener('click',checkSoftwareUpdate);
  $('apply-online-update').addEventListener('click',applyOnlineUpdate);
  $('upload-software-patch').addEventListener('click',uploadSoftwarePatch);
  $('add-user-form').addEventListener('submit',async e=>{e.preventDefault();try{
    await request('/api/users',{method:'POST',data:{username:$('new-username').value,password:$('new-password').value}});
    $('add-user-form').reset();await refreshUsers();notify('Team member created');}catch(err){notify(err.message);}});
  welcome();refreshIdentity();
});
