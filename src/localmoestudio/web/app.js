"use strict";
const $ = id => document.getElementById(id);
const state = { csrf: null, user: null, currentChat: null, sending: false, setup: false };
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
    $('endpoint').textContent = location.origin + '/v1';
    await refreshChats(); await refreshDocuments(); await refreshKeys();
    if (me.role === 'admin') await refreshUsers();
    await checkModel(); setInterval(checkModel, 12000);
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
function navigate(page) {
  ['chat','documents','settings','users'].forEach(p => $('page-' + p).classList.toggle('hidden', p !== page));
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('current', b.dataset.page === page));
  $('page-title').textContent = ({chat:'Chat',documents:'My documents',settings:'API access',users:'Team members'})[page];
}
function renderMessage(role, content) {
  const div = escapeNode('div', '', 'message ' + (role === 'user' ? 'user' : 'assistant'));
  div.append(escapeNode('div', role === 'user' ? 'You' : 'Assistant', 'speaker'));
  const text = escapeNode('div', content, 'body'); div.append(text); $('chat-history').append(div);
  $('chat-history').scrollTop = $('chat-history').scrollHeight;
  return text;
}
function welcome() {
  $('chat-history').replaceChildren();
  const w = escapeNode('div', '', 'welcome');
  w.append(escapeNode('h1', 'Your private AI workspace'));
  w.append(escapeNode('p', 'Choose a conversation or ask something new. The model runs locally on your server computer.'));
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
      body:JSON.stringify({message:text,conversation_id:state.currentChat,use_documents:$('use-documents').checked})
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
        if(evt==='meta' && payload.sources?.length) { $('send-status').textContent='Using ' + payload.sources.length + ' document excerpt(s)'; }
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
  $('add-user-form').addEventListener('submit',async e=>{e.preventDefault();try{
    await request('/api/users',{method:'POST',data:{username:$('new-username').value,password:$('new-password').value}});
    $('add-user-form').reset();await refreshUsers();notify('Team member created');}catch(err){notify(err.message);}});
  welcome();refreshIdentity();
});
