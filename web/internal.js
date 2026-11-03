"use strict";
let internalData=null,internalTopic="",internalEdit=null,internalCategories=null;
const splitInternal=value=>value.split(/[,;\n]/).map(x=>x.trim()).filter(Boolean);
function internalOptions(rows,selected=[]){return rows.map(r=>`<option value="${esc(r.id)}" ${selected.includes(r.id)?"selected":""}>${esc(r.name)}</option>`).join("");}
function internalCategoryNames(ids){return ids.map(id=>internalData.categories.items.find(c=>c.id===id)?.name||id).join(", ");}
async function openInternal(){
  internalData=await api("/api/internal",{});renderInternal();
  $("internal-chat-role").innerHTML='<option value="">Alle</option>'+options(meta.roles,"");
  $("internal-chat-language").innerHTML='<option value="">Alle</option>'+options(meta.languages,"");
  if(!$("internal-dialog").open)$("internal-dialog").showModal();
}
function internalDescendants(id){const ids=new Set([id]);let size;do{size=ids.size;internalData.categories.items.forEach(c=>{if(ids.has(c.parent_id))ids.add(c.id);});}while(size!==ids.size);return ids;}
function renderInternal(){
  const categories=internalData.categories.items;
  function branch(parent){return categories.filter(c=>c.parent_id===parent).map(c=>{const sub=branch(c.id),ids=internalDescendants(c.id),count=internalData.entries.filter(e=>e.categories.some(id=>ids.has(id))).length;const button=`<button data-internal-topic="${esc(c.id)}" class="${internalTopic===c.id?"primary":""}">${esc(c.name)} · ${count}</button>`;return sub?`<details open><summary>${button}</summary><div class="internal-subtree">${sub}</div></details>`:button;}).join("");}
  $("internal-tree").innerHTML=`<button data-internal-topic="" class="${!internalTopic?"primary":""}">Alle internen Themen · ${internalData.entries.length}</button>`+branch("");
  $("internal-tree").querySelectorAll("[data-internal-topic]").forEach(el=>el.onclick=e=>{e.preventDefault();internalTopic=el.dataset.internalTopic;renderInternal();});
  renderInternalList();
}
function renderInternalList(){
  const query=$("internal-search").value.trim().toLocaleLowerCase(),status=$("internal-status").value,ids=internalTopic?internalDescendants(internalTopic):null;
  const rows=internalData.entries.filter(e=>(!ids||e.categories.some(id=>ids.has(id)))&&(!status||e.status===status)&&(!query||[e.title,e.body,e.question,e.answer,...e.labels,...e.keywords,...e.roles,...e.markets,internalCategoryNames(e.categories)].join(" ").toLocaleLowerCase().includes(query)));
  $("internal-list").innerHTML=rows.map(e=>`<article class="internal-card"><h3>${esc(e.title)}</h3><p>${esc(internalCategoryNames(e.categories))} · ${esc(e.status)} · R${e.revision} · ${esc(e.language)}</p><p>${esc(e.body.slice(0,240))}</p><p class="muted">${esc([...e.labels,...e.roles,...e.markets].join(" · "))}</p>${e.question?`<p><b>FAQ:</b> ${esc(e.question)}</p>`:""}<p>${e.chatbot_enabled?"Für internen Chatbot vorgemerkt":"Keine Chatbot-Vormerkung"}</p><button data-internal-edit="${esc(e.id)}">Bearbeiten</button> <button data-internal-history="${esc(e.id)}">Revisionen</button></article>`).join("")||'<p class="muted">Keine passenden internen Einträge.</p>';
  $("internal-list").querySelectorAll("[data-internal-edit]").forEach(el=>el.onclick=()=>editInternal(internalData.entries.find(e=>e.id===el.dataset.internalEdit)));
  $("internal-list").querySelectorAll("[data-internal-history]").forEach(el=>el.onclick=run(async()=>{const rows=await api("/api/internal/history",{id:el.dataset.internalHistory});$("internal-history").innerHTML=rows.map(e=>`<details><summary>R${e.revision} · ${esc(e.title)} · ${esc(e.status)} · ${esc(formatDate(e.updated))}</summary><p class="internal-text">${esc(e.body)}</p><h4>${esc(e.question)}</h4><p class="internal-text">${esc(e.answer)}</p><p>${esc(e.source)}</p><p>${esc(e.note)}</p></details>`).join("");$("internal-history-dialog").showModal();}));
}
function editInternal(entry){
  internalEdit=structuredClone(entry||{id:uuid(),revision:0,title:"",body:"",question:"",answer:"",source:"",note:"",categories:[internalTopic||"internal-testing"],domains:[],roles:[],markets:[],labels:[],keywords:[],status:"Entwurf",language:"de",chatbot_enabled:false});
  for(const key of ["title","body","question","answer","source","note"])$("internal-"+key).value=internalEdit[key];
  $("internal-entry-categories").innerHTML=internalOptions(internalData.categories.items,internalEdit.categories);
  $("internal-entry-domains").innerHTML=internalOptions(allTargets(),internalEdit.domains);
  $("internal-entry-roles").innerHTML=meta.roles.map(r=>`<option ${internalEdit.roles.includes(r)?"selected":""}>${esc(r)}</option>`).join("");
  for(const key of ["markets","labels","keywords"])$("internal-entry-"+key).value=internalEdit[key].join(", ");
  $("internal-entry-status").value=internalEdit.status;$("internal-entry-language").innerHTML=options(meta.languages,internalEdit.language);$("internal-enabled").checked=internalEdit.chatbot_enabled;
  $("internal-edit-dialog").showModal();
}
$("internal-edit-form").onsubmit=run(async event=>{
  event.preventDefault();const entry=structuredClone(internalEdit);
  for(const key of ["title","body","question","answer","source","note"])entry[key]=$("internal-"+key).value;
  for(const key of ["categories","domains","roles"])entry[key]=[...$("internal-entry-"+key).selectedOptions].map(o=>o.value);
  for(const key of ["markets","labels","keywords"])entry[key]=splitInternal($("internal-entry-"+key).value);
  entry.status=$("internal-entry-status").value;entry.language=$("internal-entry-language").value;entry.chatbot_enabled=$("internal-enabled").checked;
  await api("/api/internal/save",entry);$("internal-edit-dialog").close();await openInternal();message("Interne Wissensrevision gespeichert. Dokumentausgaben enthalten diesen Eintrag nicht.");
});
function renderInternalCategories(){
  $("internal-category-rows").innerHTML=internalCategories.items.map((c,i)=>`<div class="config-grid"><label>Themenname<input data-category-name="${i}" value="${esc(c.name)}" maxlength="150"></label><label>Oberthema<select data-category-parent="${i}"><option value="">Hauptthema</option>${internalOptions(internalCategories.items.filter(x=>x.id!==c.id),[c.parent_id])}</select></label></div>`).join("");
  $("internal-category-rows").querySelectorAll("[data-category-name]").forEach(el=>el.oninput=()=>internalCategories.items[Number(el.dataset.categoryName)].name=el.value);
  $("internal-category-rows").querySelectorAll("[data-category-parent]").forEach(el=>el.onchange=()=>internalCategories.items[Number(el.dataset.categoryParent)].parent_id=el.value);
  $("internal-category-parent").innerHTML='<option value="">Hauptthema</option>'+internalOptions(internalCategories.items);
}
$("internal-categories-button").onclick=()=>{internalCategories=structuredClone(internalData.categories);renderInternalCategories();$("internal-categories-dialog").showModal();};
$("internal-category-add").onclick=run(async()=>{const name=$("internal-category-name").value.trim();if(!name)throw new Error("Themenname ergänzen.");internalCategories.items.push({id:uuid(),name,parent_id:$("internal-category-parent").value});$("internal-category-name").value="";renderInternalCategories();});
$("internal-category-save").onclick=run(async()=>{await api("/api/internal/categories",internalCategories);$("internal-categories-dialog").close();await openInternal();});
$("internal-chat-search").onclick=run(async()=>{const rows=await api("/api/internal/chatbot-preview",{query:$("internal-chat-query").value,role:$("internal-chat-role").value,market:$("internal-chat-market").value,language:$("internal-chat-language").value});$("internal-chat-results").innerHTML=rows.map(r=>`<article class="internal-card"><h4>${esc(r.question)}</h4><p class="internal-text">${esc(r.answer)}</p><p>Quelle: ${esc(r.source||"noch nicht ergänzt")} · R${r.revision} · nur intern</p></article>`).join("")||"Keine freigegebenen FAQ-Kandidaten für diese Auswahl.";});
$("internal-button").onclick=run(openInternal);$("internal-new").onclick=()=>editInternal();
$("internal-search").oninput=renderInternalList;$("internal-status").onchange=renderInternalList;
for(const [button,dialog] of [["internal-close","internal-dialog"],["internal-edit-close","internal-edit-dialog"],["internal-category-close","internal-categories-dialog"],["internal-history-close","internal-history-dialog"]])$(button).onclick=()=>$(dialog).close();
