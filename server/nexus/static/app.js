'use strict';
const el=id=>document.getElementById(id);
let admin='';
async function api(path,method='GET',body){
  const response=await fetch(path,{method,headers:{Authorization:`Bearer ${admin}`,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined,cache:'no-store'});
  const data=await response.json(); if(!response.ok)throw Error(data.error||'Request failed'); return data;
}
async function load(){
  const [data,health]=await Promise.all([api('/v1/admin/devices'),fetch('/health',{cache:'no-store'}).then(r=>r.json())]);
  el('health').textContent=health.node_synced_recently?'Node synchronized recently.':'Node has not synchronized recently; check the server agent.';
  el('devices').replaceChildren();
  for(const device of data.devices){
    const item=document.createElement('div');item.className='device';
    const label=document.createElement('p');label.textContent=`${device.name} · desired: ${device.desired} · applied: ${device.applied}`;item.append(label);
    if(device.desired==='active'){
      const button=document.createElement('button');button.textContent='Revoke device';
      button.onclick=()=>action(async()=>{if(!confirm(`Revoke ${device.name}?`))return;await api(`/v1/admin/devices/${device.id}/revoke`,'POST');await load();});item.append(button);
    }
    el('devices').append(item);
  }
}
async function action(fn){el('message').textContent='';try{await fn();}catch(error){el('message').textContent=error.message;}}
el('login').onclick=()=>action(async()=>{admin=el('token').value;el('token').value='';await load();});
el('logout').onclick=()=>{admin='';el('token').value='';el('devices').replaceChildren();el('invitation').textContent='';el('health').textContent='';};
el('invite').onclick=()=>action(async()=>{const data=await api('/v1/admin/invitations','POST',{ttl:600});el('invitation').textContent=`Server: ${location.origin}\nToken: ${data.token}\nExpires: ${new Date(data.expires_at*1000).toLocaleString()}`;});
