"use strict";
const documentUses=["Handbuch","Releaseletter","Quickreference"];
let layoutEntries=[], markdownFiles=[];
function renderValidity(container,rows,onChange) {
  const labels={from:"Gültig ab",until:"Gültig bis",year:"Jahr",market:"Land",role:"Rolle",division:"Sparte",state:"Status",version:"Version",environment:"Umgebung"};
  container.innerHTML=`<div class="table-scroll"><table class="rules-table"><thead><tr>${Object.values(labels).map(v=>`<th>${v}</th>`).join("")}<th></th></tr></thead><tbody>${rows.map((r,i)=>`<tr data-validity-row="${i}">${Object.keys(labels).map(k=>`<td>${["role","division","state","environment"].includes(k)?`<select data-rule="${k}">${options(k==="role"?["*",...meta.roles]:k==="division"?["*","Van","PC"]:k==="environment"?["*","prod","preprod"]:["Entwurf","In Prüfung","Freigegeben","Zurückgezogen"],r[k])}</select>`:`<input data-rule="${k}" value="${esc(r[k]||"")}" ${["from","until"].includes(k)?'type="date"':k==="year"?'type="number" min="1900" max="2200"':''}>`}</td>`).join("")}<td><button type="button" data-remove-rule="${i}">×</button></td></tr>`).join("")}</tbody></table></div><button type="button" class="add-validity">+ Gültigkeitsregel</button><p class="muted">Ohne Regeln zeitlich unbeschränkt. Land/Rolle/Sparte „Alle“ bzw. * = alle; leeres Jahr = alle Jahre. Spezifischere Regeln gehen vor. Gleich spezifische Widersprüche blockieren die Veröffentlichung.</p>`;
  container.querySelectorAll("[data-validity-row]").forEach(el=>{const r=rows[Number(el.dataset.validityRow)];el.querySelectorAll("[data-rule]").forEach(field=>field.oninput=()=>{r[field.dataset.rule]=field.value;onChange();});});
  container.querySelectorAll("[data-remove-rule]").forEach(el=>el.onclick=()=>{rows.splice(Number(el.dataset.removeRule),1);onChange();renderValidity(container,rows,onChange);});
  container.querySelector(".add-validity").onclick=()=>{rows.push({from:"",until:"",year:"",market:"*",role:"*",division:"*",state:"Entwurf",version:"",environment:"*"});onChange();renderValidity(container,rows,onChange);};
}
function renderPublication(container,b,onChange) {
  b.uses ||= Object.fromEntries(documentUses.map(k=>[k,true]));b.evidence ||= [];b.validity ||= [];
  const panel=document.createElement("details");panel.className="chapter-settings publication-panel";panel.blockData=b;
  panel.innerHTML=`<summary>Dokumenteignung · Jira-Nachweise · Zeit</summary><div class="actions">${documentUses.map(k=>`<label class="check"><input type="checkbox" data-use="${k}" ${b.uses[k]?"checked":""}>${k==="Handbuch"?"Manual / Handbuch":k==="Quickreference"?"Quick Reference":k}</label>`).join("")}</div>${selectField("Textformat","text_format",["plain","markdown"],b.text_format||"plain")}<h4>Interne Jira-Verifikation</h4><p class="muted">Ticketnummer, Status, Typ, Datum und Prüfvermerk bleiben intern. Verknüpfte Ticketnummern und deren /browse/-Links werden auch aus dem Lesertext entfernt. Ein Jira-Status allein ist keine fachliche Verifikation.</p><div class="evidence-rows"></div><button type="button" class="add-evidence">+ Jira-Nachweis</button><h4>Zeitliche Gültigkeit des Textes</h4><div class="block-validity"></div>`;
  panel.querySelectorAll("[data-use]").forEach(el=>el.onchange=()=>{b.uses[el.dataset.use]=el.checked;invalidateEvidence(b);onChange();});
  panel.querySelector("[data-key=text_format]").onchange=e=>{b.text_format=e.target.value;invalidateEvidence(b);onChange();};
  function evidenceRows(){
    panel.querySelector(".evidence-rows").innerHTML=b.evidence.map((r,i)=>`<fieldset data-evidence-row="${i}"><legend>Nachweis ${i+1}</legend><div class="config-grid">${[["key","Jira-Ticket"],["status","Jira-Status"],["type","Jira-Typ"],["date","Ticketdatum"]].map(([k,label])=>`<label>${label}<input data-evidence="${k}" value="${esc(r[k]||"")}" ${k==="date"?'type="date"':''}></label>`).join("")}</div><label class="check"><input type="checkbox" data-evidence="verified" ${r.verified?"checked":""}>Text anhand dieses Nachweises geprüft</label><label>Interner Prüfvermerk<textarea data-evidence="note" rows="2">${esc(r.note||"")}</textarea></label><button type="button" data-remove-evidence="${i}">Nachweis entfernen</button></fieldset>`).join("");
    panel.querySelectorAll("[data-evidence-row]").forEach(row=>row.querySelectorAll("[data-evidence]").forEach(el=>el.oninput=()=>{const r=b.evidence[Number(row.dataset.evidenceRow)];r[el.dataset.evidence]=el.type==="checkbox"?el.checked:el.value;if(el.dataset.evidence==="verified")r.content_hash="";else if(el.dataset.evidence!=="note"){r.verified=false;r.content_hash="";row.querySelector("[data-evidence=verified]").checked=false;}onChange();}));
    panel.querySelectorAll("[data-remove-evidence]").forEach(el=>el.onclick=()=>{b.evidence.splice(Number(el.dataset.removeEvidence),1);onChange();evidenceRows();});
  }
  panel.querySelector(".add-evidence").onclick=()=>{b.evidence.push({key:"",status:"",type:"",date:"",verified:false,note:""});onChange();evidenceRows();};
  evidenceRows();renderValidity(panel.querySelector(".block-validity"),b.validity,()=>{invalidateEvidence(b);onChange();});container.append(panel);
}
function refValue(ref){return ref?`${ref.id}|${ref.revision}`:"";}
function readRef(value){if(!value)return null;const [id,revision]=value.split("|");return {id,revision:Number(revision)};}
function templateOptions(fmt,ref) {
  const entries=layoutEntries.filter(e=>e.format===fmt),value=refValue(ref);
  let result='<option value="">Standardlayout</option>'+entries.map(e=>`<option value="${esc(refValue(e))}" ${refValue(e)===value?"selected":""}>${esc(e.name)} · V${esc(e.version)} · R${e.revision}</option>`).join("");
  if(value&&!entries.some(e=>refValue(e)===value)) result+=`<option value="${esc(value)}" selected>Gebundene Templaterevision R${ref.revision}</option>`;
  return result;
}
async function openLayouts(){
  layoutEntries=await api("/api/layouts",{});
  $("layout-existing").innerHTML='<option value="">Neue Templatereihe</option>'+layoutEntries.map(e=>`<option value="${esc(e.id)}">${esc(e.name)} · ${esc(e.format)} · R${e.revision}</option>`).join("");
  for(const fmt of ["docx","pptx"])$("layout-"+fmt).innerHTML=templateOptions(fmt,current.layout?.[fmt]);
  const t={primary:"#123443",accent:"#00858b",text:"#203640",font:"Arial",size:11,...current.layout?.theme};
  $("layout-theme").innerHTML=[["primary","Hauptfarbe"],["accent","Akzentfarbe"],["text","Textfarbe"],["font","Schrift"],["size","Schriftgröße"]].map(([k,label])=>inputField(label,k,t[k],["primary","accent","text"].includes(k)?'type="color"':k==="size"?'type="number" min="8" max="18"':'')).join("");
  if(!$("layout-dialog").open)$("layout-dialog").showModal();
}
$("layout-existing").onchange=()=>{const e=layoutEntries.find(e=>e.id===$("layout-existing").value);if(e){$("layout-name").value=e.name;$("layout-version").value=e.version;}};
async function base64File(file){const bytes=new Uint8Array(await file.arrayBuffer());let binary="";for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));return btoa(binary);}
$("layout-upload").onsubmit=run(async e=>{
  e.preventDefault();const file=$("layout-file").files[0];if(!file||file.size>10*1024*1024)throw new Error("DOCX/PPTX bis 10 MB wählen.");
  const existing=layoutEntries.find(x=>x.id===$("layout-existing").value),format=file.name.split(".").at(-1).toLowerCase();
  await api("/api/layout/upload",{id:existing?.id,revision:existing?.revision||0,name:$("layout-name").value,version:$("layout-version").value,format,base64:await base64File(file)});
  await openLayouts();message("Templaterevision gespeichert. Gewünschte Revision für die Gliederung auswählen.");
});
$("layout-apply").onclick=()=>{current.layout={theme:{}};for(const fmt of ["docx","pptx"]){const ref=readRef($("layout-"+fmt).value);if(ref)current.layout[fmt]=ref;}$("layout-theme").querySelectorAll("[data-key]").forEach(el=>current.layout.theme[el.dataset.key]=el.dataset.key==="size"?Number(el.value):el.value);markDirty();$("layout-dialog").close();message("Layoutauswahl übernommen. Gliederung speichern.");};
$("layout-tool").onclick=run(openLayouts);$("layout-close").onclick=()=>$("layout-dialog").close();
$("markdown-tool").onclick=run(async()=>{layoutEntries=await api("/api/layouts",{});$("md-template").innerHTML=templateOptions("docx",current?.layout?.docx);$("markdown-dialog").showModal();});
$("md-files").onchange=run(async()=>{markdownFiles=[...$("md-files").files];renderMarkdownFiles();});
function renderMarkdownFiles(){
  $("md-file-list").innerHTML=markdownFiles.map((f,i)=>`<p>${i+1}. ${esc(f.name)} <button data-md-up="${i}" ${!i?"disabled":""}>↑</button><button data-md-down="${i}" ${i===markdownFiles.length-1?"disabled":""}>↓</button><button data-md-remove="${i}">Entfernen</button></p>`).join("");
  $("md-file-list").querySelectorAll("button").forEach(el=>el.onclick=()=>{if(el.dataset.mdRemove!==undefined)markdownFiles.splice(Number(el.dataset.mdRemove),1);else{const i=Number(el.dataset.mdUp??el.dataset.mdDown),j=i+(el.dataset.mdUp!==undefined?-1:1);[markdownFiles[i],markdownFiles[j]]=[markdownFiles[j],markdownFiles[i]];}renderMarkdownFiles();});
}
async function downloadResponse(response,name){const url=URL.createObjectURL(await response.blob()),a=document.createElement("a");a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}
$("md-convert").onclick=run(async()=>{
  if(!markdownFiles.length||markdownFiles.length>100)throw new Error("1–100 Markdown-Dateien wählen.");
  if(markdownFiles.reduce((n,f)=>n+f.size,0)>10*1024*1024)throw new Error("Stapel auf höchstens 10 MB aufteilen.");
  const files=[];for(const f of markdownFiles)files.push({name:f.name,text:await f.text()});
  const combined=$("md-mode").value==="combined";$("md-convert").disabled=true;
  try{const response=await api("/api/markdown/convert",{files,combined,title:$("md-title").value,template:readRef($("md-template").value)});await downloadResponse(response,`Markdown-Konvertierung.${combined?"docx":"zip"}`);message("Markdown in bearbeitbare Word-Dokumente umgewandelt.");}finally{$("md-convert").disabled=false;}
});
$("md-close").onclick=()=>$("markdown-dialog").close();
$("paste-source-text").onpaste=e=>{const html=e.clipboardData?.getData("text/html");if(html&&$("paste-source-format").value==="html"){e.preventDefault();$("paste-source-text").value=html;}};
$("paste-source-save").onclick=run(async()=>{await api("/api/source/paste",{name:$("paste-source-name").value,text:$("paste-source-text").value,format:$("paste-source-format").value,kind:$("source-kind").value,origin:$("source-origin").value,release:$("source-release").value});await loadSources();$("paste-source-text").value="";message("Zwischenablage als Quelle mit Chunks gespeichert.");});
async function applicability(){
  const result=await api("/api/applicability",{outline:current});
  $("applicability-table").innerHTML=`<div class="table-scroll"><table class="outline-table"><thead><tr><th>Kapitel / Text</th>${documentUses.map(k=>`<th>${esc(k)}</th>`).join("")}<th>Jira-Nachweise (intern)</th><th>Textstatus</th></tr></thead><tbody>${result.rows.map(r=>`<tr><td><b>${esc(r.chapter)}</b><p>${esc(r.text)}</p></td>${documentUses.map(k=>`<td>${r.uses[k].included?"✓ Verwendet":"— Nicht verwendet"}<small>${esc(r.uses[k].reason)}</small></td>`).join("")}<td>${r.evidence.map(e=>`${esc(e.key)} · ${esc(e.status)} · ${esc(e.type)} · ${esc(e.date)} · ${e.verified?"geprüft":"ungeprüft"}`).join("<br>")||"Keine"}</td><td>${esc(r.status)}</td></tr>`).join("")}</tbody></table></div>${Object.entries(result.warnings).map(([k,rows])=>`<details><summary>${esc(k)}: ${rows.length} Prüfpunkte</summary><ul>${rows.map(w=>`<li>${esc(w)}</li>`).join("")}</ul></details>`).join("")}`;
}
$("applicability-tool").onclick=run(async()=>{current.validity ||= [];renderValidity($("outline-validity"),current.validity,markDirty);$("applicability-dialog").showModal();await applicability();await openTimeline();});
$("refresh-applicability").onclick=run(applicability);$("applicability-close").onclick=()=>$("applicability-dialog").close();

let timelineRows=[];
async function openTimeline(){timelineRows=await api("/api/timeline",{});$("timeline-filters").innerHTML='<label>Land<input data-time="market"></label><label>Jahr<input data-time="year" type="number" min="1900" max="2200"></label>'+[["role","Rolle",meta.roles],["division","Sparte",["Van","PC","Beide"]],["status","Status",["Entwurf","In Prüfung","Freigegeben","Archiviert"]]].map(([k,label,values])=>`<label>${label}<select data-time="${k}"><option value="">Alle</option>${options(values,"")}</select></label>`).join("");$("timeline-filters").querySelectorAll("input,select").forEach(el=>el.oninput=renderTimeline);renderTimeline();}
function renderTimeline(){const f={};$("timeline-filters").querySelectorAll("[data-time]").forEach(el=>f[el.dataset.time]=el.value.trim());const rows=timelineRows.filter(r=>(!f.market||r.profile.market.toLowerCase()===f.market.toLowerCase()||r.validity.some(v=>["*",f.market].includes(v.market)))&&(!f.role||r.profile.role===f.role||r.validity.some(v=>["*",f.role].includes(v.role)))&&(!f.division||r.profile.division===f.division||r.validity.some(v=>["*",f.division].includes(v.division)))&&(!f.status||r.metadata.status===f.status)&&(!f.year||(r.profile.as_of||r.created).slice(0,4)===f.year||r.validity.some(v=>v.year===f.year||(!v.year&&(v.from||"0000").slice(0,4)<=f.year&&(v.until||"9999").slice(0,4)>=f.year))));$("timeline-table").innerHTML=`<div class="table-scroll"><table class="outline-table"><thead><tr><th>Gliederung / Version</th><th>Gespeichert</th><th>Status</th><th>Land / Rolle / Sparte</th><th>Stichtag / Umgebung</th><th>Zeitregeln</th></tr></thead><tbody>${rows.map(r=>`<tr><td>${esc(r.title)}<small>V${esc(r.metadata.version)} · R${r.revision}</small></td><td>${esc(formatDate(r.created))}</td><td>${esc(r.metadata.status)}</td><td>${esc(r.profile.market||"offen")} / ${esc(r.profile.role)} / ${esc(r.profile.division)}</td><td>${esc(r.profile.as_of||"offen")} / ${esc(r.profile.environment)}</td><td>${r.validity.map(v=>`${esc(v.year||"alle Jahre")}: ${esc(v.from||"offen")} – ${esc(v.until||"offen")} · ${esc(v.state)} · V${esc(v.version)}`).join("<br>")||"Keine zusätzlichen Regeln"}</td></tr>`).join("")}</tbody></table></div>`;}

function invalidateEvidence(b){
  (b.evidence||[]).forEach(r=>{r.verified=false;r.content_hash="";});
  document.querySelectorAll(".publication-panel").forEach(p=>{if(p.blockData===b)p.querySelectorAll("[data-evidence=verified]").forEach(el=>el.checked=false);});
}
document.addEventListener("input",event=>{
  const el=event.target;
  const meaningful=["text","language","role","scope","market","division","release"].includes(el.dataset.key)||!!el.closest("[data-variant]")&&el.tagName==="TEXTAREA";
  if(el.closest("#library-edit-dialog")&&(meaningful||el.id==="library-text")){if(libraryEdit)invalidateEvidence(libraryEdit.block);}
  else if(meaningful){const b=el.closest(".block")?.querySelector(".publication-panel")?.blockData;if(b)invalidateEvidence(b);}
});
