"use strict";
let mediaEntries=[],assetEdit=null,assetImage=null,assetPointer=null,mediaAssignment=null,mediaChapter=null,assetPreviewValid=false;
const mediaRole=()=>$("media-working-role").value;
async function openMedia() {
  mediaEntries=await api("/api/media",{}); renderMediaTools(); renderMediaList(); $("media-dialog").showModal();
}
function renderMediaList() {
  const q=$("media-search").value.toLocaleLowerCase();
  const filters={};$("media-filters").querySelectorAll("[data-filter]").forEach(el=>filters[el.dataset.filter]=el.value);
  const filtered=mediaEntries.filter(a=>Object.entries(filters).every(([key,value])=>!value || (key==="priority"?(a.priority||"Normal")===value : a.profile[key]==="*" || a.profile[key].toLowerCase()===value.toLowerCase())));
  const sort=$("media-sort")?.value || "title", rank={Hoch:0,Normal:1,Niedrig:2};
  filtered.sort((a,b)=>sort==="priority"?(rank[a.priority||"Normal"]-rank[b.priority||"Normal"]):String(sort==="title"?a.title:a.profile[sort]).localeCompare(String(sort==="title"?b.title:b.profile[sort]),"de"));
  const editable=["HQ","intern"].includes(mediaRole());
  $("media-upload").disabled=!editable;
  $("media-list").innerHTML=filtered.filter(a=>[a.title,a.caption,...Object.values(a.profile),...(a.classification?.keywords || []),...(a.classification?.labels || [])].join(" ").toLocaleLowerCase().includes(q)).map(a=>`<article class="source-card"><h3>${esc(a.title)} · R${a.revision}</h3><p>${esc(a.status)} · Priorität ${esc(a.priority||"Normal")} · ${a.pii_reviewed ? "PII-Prüfung bestätigt" : "PII-Prüfung offen"}${a.archived ? " · Archiviert" : ""} · ${a.width} × ${a.height}</p><p>${esc(a.caption)}</p><p>${esc(Object.values(a.profile).join(" · "))}</p><button data-edit-asset="${esc(a.id)}" ${editable ? "" : "disabled"}>Bearbeiten / OCR / PII</button><button data-delete-asset="${esc(a.id)}" ${editable ? "" : "disabled"}>Endgültig löschen</button><details><summary>${a.usage.length} Verwendungen</summary><ul>${a.usage.map(u=>`<li>${esc(u.outline)} → ${esc(u.chapter)} · R${u.revision}</li>`).join("")}</ul></details></article>`).join("") || '<p>Noch keine passenden Bilder.</p>';
  $("media-list").querySelectorAll("[data-delete-asset]").forEach(el=>el.onclick=run(async()=>{if(!confirm("Bild mit Original und allen Bildrevisionen endgültig löschen? Nur ohne Verwendung in gespeicherten Gliederungsständen möglich."))return;await api("/api/media/delete",{id:el.dataset.deleteAsset,working_role:mediaRole()});mediaEntries=await api("/api/media",{});renderMediaList();}));
  $("media-list").querySelectorAll("[data-edit-asset]").forEach(el=>el.onclick=run(()=>editAsset(mediaEntries.find(a=>a.id===el.dataset.editAsset))));
}
$("media-upload").onclick=run(async()=>{
  const files=[...$("media-files").files]; if(!files.length) throw new Error("PNG- oder JPEG-Dateien wählen.");
  $("media-upload").disabled=true;
  try {
    for(const file of files) {
      if(file.size>10*1024*1024) throw new Error("Maximal 10 MB je Bild.");
      const bytes=new Uint8Array(await file.arrayBuffer()); let binary="";
      for(let i=0;i<bytes.length;i+=8192) binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
      await api("/api/media/upload",{name:file.name,base64:btoa(binary),language:current.profile.language,working_role:mediaRole(),metadata:mediaUploadMetadata()});
    }
    $("media-files").value=""; mediaEntries=await api("/api/media",{}); renderMediaList(); message("Bilder importiert. PII-Prüfung und Freigabe sind noch offen.");
  } finally {$("media-upload").disabled=false;}
});
async function editAsset(asset) {
  assetEdit=structuredClone(asset); assetEdit.classification ||= {roles:[],domain_ids:[],keywords:[],labels:[],topic:""};
  $("asset-domains").innerHTML=allTargets().map(d=>`<option value="${esc(d.id)}" ${assetEdit.classification.domain_ids.includes(d.id)?"selected":""}>${esc(d.name)}</option>`).join("");
  $("asset-keywords").value=assetEdit.classification.keywords.join(", "); $("asset-labels").value=assetEdit.classification.labels.join(", "); assetImage=null; assetPreviewValid=false;
  $("asset-title").value=asset.title; $("asset-caption").value=asset.caption; $("asset-note").value=asset.note;
  $("asset-priority").value=asset.priority||"Normal";$("asset-status").value=asset.status; $("asset-archived").checked=asset.archived;
  $("asset-pii-reviewed").checked=false; $("asset-pii-reviewed").disabled=true;
  $("asset-progress").textContent="Original wird geladen …"; $("asset-ocr-text").textContent="";
  $("asset-profile").innerHTML=selectField("Rolle","role",meta.roles,asset.profile.role,"",true)+selectField("Umfang","scope",meta.scopes,asset.profile.scope,"",true)+selectField("Sparte","division",["Van","PC"],asset.profile.division,"",true)+inputField("Markt","market",asset.profile.market)+inputField("Release","release",asset.profile.release)+selectField("Sprache","language",meta.languages,asset.profile.language);
  $("asset-preview-image").hidden=true; $("asset-canvas").hidden=false; $("media-edit-dialog").showModal();
  const result=await api("/api/media/image",{id:asset.id,revision:asset.revision,working_role:mediaRole(),original:true});
  const img=new Image(); img.src=result.image; await img.decode();
  if(assetEdit?.id!==asset.id) return;
  const storedOCR=await api("/api/media/ocr-record",{id:asset.id,working_role:mediaRole()});
  if(assetEdit?.id!==asset.id)return;
  if(storedOCR)$("asset-ocr-text").textContent=(storedOCR.stale?"VERALTET – OCR erneut ausführen.\n":"Gespeicherte OCR · ungeprüft · ")+storedOCR.updated+"\n"+storedOCR.text;
  assetImage=img; drawAsset(); $("asset-progress").textContent="Bereiche markieren und anonymisierte Fassung prüfen.";
}
function invalidateAssetPreview() {assetPreviewValid=false;$("asset-pii-reviewed").checked=false;$("asset-pii-reviewed").disabled=true;}
function drawAsset() {
  if(!assetImage) return;
  const canvas=$("asset-canvas"); canvas.width=assetImage.width; canvas.height=assetImage.height;
  const ctx=canvas.getContext("2d");ctx.drawImage(assetImage,0,0);
  for(const r of assetEdit.redactions) {ctx.fillStyle="rgba(30,55,65,.8)";ctx.fillRect(r.x,r.y,r.w,r.h);}
  for(const r of assetEdit.markers) {ctx.strokeStyle="#e05227";ctx.lineWidth=4;ctx.strokeRect(r.x,r.y,r.w,r.h);}
  $("asset-regions").innerHTML=[...assetEdit.redactions.map((r,i)=>`<p>PII ${i+1}: ${r.mode === "blur" ? "unkenntlich" : "abgedeckt"} <button data-region="${i}">Entfernen</button></p>`),...assetEdit.markers.map((r,i)=>`<p>Markierung: ${esc(r.text)} <button data-marker="${i}">Entfernen</button></p>`)].join("");
  $("asset-regions").querySelectorAll("button").forEach(el=>el.onclick=()=>{if(el.dataset.region!==undefined)assetEdit.redactions.splice(Number(el.dataset.region),1);else assetEdit.markers.splice(Number(el.dataset.marker),1);invalidateAssetPreview();drawAsset();});
}
function assetPoint(e) {const c=$("asset-canvas"),r=c.getBoundingClientRect();return {x:Math.max(0,Math.min(c.width-1,Math.floor((e.clientX-r.left)*c.width/r.width))),y:Math.max(0,Math.min(c.height-1,Math.floor((e.clientY-r.top)*c.height/r.height)))};}
$("asset-canvas").onpointerdown=e=>{if(!assetImage)return;assetPointer=assetPoint(e);e.target.setPointerCapture(e.pointerId);};
$("asset-canvas").onpointerup=e=>{
  if(!assetPointer)return;const end=assetPoint(e),start=assetPointer;assetPointer=null;
  const region={x:Math.min(start.x,end.x),y:Math.min(start.y,end.y),w:Math.max(1,Math.abs(start.x-end.x)+1),h:Math.max(1,Math.abs(start.y-end.y)+1)};
  if($("asset-tool").value==="marker") {const text=prompt("Markierungstext",`Schritt ${assetEdit.markers.length+1}`);if(text===null)return;assetEdit.markers.push({...region,text});}
  else assetEdit.redactions.push({...region,mode:$("asset-tool").value});
  invalidateAssetPreview();drawAsset();
};
$("asset-original").onclick=()=>{$("asset-preview-image").hidden=true;$("asset-canvas").hidden=false;invalidateAssetPreview();};
$("asset-preview").onclick=run(async()=>{
  const id=assetEdit.id,signature=JSON.stringify([assetEdit.redactions,assetEdit.markers]);
  const result=await api("/api/media/preview",{id,redactions:assetEdit.redactions,markers:assetEdit.markers,working_role:mediaRole()});
  if(assetEdit?.id!==id || signature!==JSON.stringify([assetEdit.redactions,assetEdit.markers]))return;
  $("asset-preview-image").src=result.image; $("asset-preview-image").hidden=false; $("asset-canvas").hidden=true;
  assetPreviewValid=true;$("asset-pii-reviewed").disabled=false;$("asset-progress").textContent="Die vollständige Fassung, Markierungen und Untertitel prüfen. Danach PII-Prüfung bestätigen.";
});
$("asset-ocr").onclick=run(async()=>{
  const id=assetEdit.id;$("asset-progress").textContent="Lokale OCR läuft …";$("asset-ocr").disabled=true;
  try {
    const result=await api("/api/media/ocr",{id,working_role:mediaRole(),outline_id:current?.id,preprocessing:$("asset-preprocessing").value}); if(assetEdit?.id!==id)return;
    if(result.classification && confirm(`Lokale Regelvorschläge (keine KI) übernehmen?\nDomänen: ${result.classification.domain_ids.map(targetLabel).join(", ")}\nRollenhinweise: ${result.classification.roles.join(", ")}\nKapitel: ${(result.chapter_titles || []).join(", ")}\n\nDomänen/Stichwörter/Labels werden in die Bearbeitungsfelder übernommen. Kapitel und Rollen bleiben Hinweise im internen Vermerk; keine automatische Zuordnung.`)){
      assetEdit.classification=result.classification;
      [...$("asset-domains").options].forEach(o=>o.selected=result.classification.domain_ids.includes(o.value));
      $("asset-keywords").value=result.classification.keywords.join(", ");$("asset-labels").value=result.classification.labels.join(", ");
      $("asset-note").value+=`\nOCR-Vorschläge: Kapitel ${(result.chapter_titles || []).join(", ")}; Rollen ${result.classification.roles.join(", ")}. Bitte prüfen.`;
    }
    $("asset-ocr-text").textContent=(result.analysis?result.analysis.engine+" · "+result.analysis.mode+" · "+result.analysis.regions.length+" Strukturregionen (ungeprüft)\n":"")+result.text;$("asset-progress").textContent=result.warning;
    if(result.regions.length && confirm(`${result.regions.length} mögliche PII-Bereiche als Abdeckung übernehmen? Anschließend manuell prüfen.`)){assetEdit.redactions.push(...result.regions);invalidateAssetPreview();drawAsset();$("asset-original").click();}
  } finally {$("asset-ocr").disabled=false;}
});
$("asset-save").onclick=run(async()=>{
  if($("asset-pii-reviewed").checked && !assetPreviewValid)throw new Error("Anonymisierte Fassung zuerst prüfen.");
  const data={...assetEdit,priority:$("asset-priority").value,title:$("asset-title").value,caption:$("asset-caption").value,note:$("asset-note").value,status:$("asset-status").value,archived:$("asset-archived").checked,pii_reviewed:$("asset-pii-reviewed").checked,working_role:mediaRole()};
  $("asset-profile").querySelectorAll("[data-key]").forEach(el=>data.profile[el.dataset.key]=el.value);
  data.classification={...assetEdit.classification,domain_ids:[...$("asset-domains").selectedOptions].map(o=>o.value),keywords:splitLabels($("asset-keywords").value),labels:splitLabels($("asset-labels").value)};
  await api("/api/media/save",data);$("media-edit-dialog").close();assetEdit=null;mediaEntries=await api("/api/media",{});renderMediaList();message("Bildrevision gespeichert. Vorhandene Zuordnungen behalten ihre alte Revision.");
});
function renderChapterMedia(c) {
  c.media ||= [];
  $("chapter-media").innerHTML=`<h3>Bilder & Klickstrecken (${c.media.length})</h3>${c.media.map(m=>`<article class="source-card"><b>${esc(m.title || m.kind)}</b><p>${esc(m.kind)} · ${m.frames.length} Positionen</p><button data-media-edit="${esc(m.id)}">Zuordnung bearbeiten</button><button data-media-remove="${esc(m.id)}">Entfernen</button></article>`).join("")}<button id="chapter-media-add">+ Bild / Klickstrecke zuordnen</button>`;
  $("chapter-media-add").onclick=run(()=>editMediaAssignment(c));
  $("chapter-media").querySelectorAll("[data-media-edit]").forEach(el=>el.onclick=run(()=>editMediaAssignment(c,c.media.find(m=>m.id===el.dataset.mediaEdit))));
  $("chapter-media").querySelectorAll("[data-media-remove]").forEach(el=>el.onclick=()=>{if(!confirm("Diese Medienzuordnung entfernen? Zentrale Bilder bleiben erhalten."))return;c.media=c.media.filter(m=>m.id!==el.dataset.mediaRemove);markDirty();renderChapterMedia(c);});
}
async function editMediaAssignment(c, existing) {
  mediaEntries=await api("/api/media",{});mediaChapter=c.id;
  mediaAssignment=structuredClone(existing || {id:uuid(),title:"",kind:"Bild",conditions:{},note:"",frames:[{caption:"",variants:[]}]});
  $("media-target-chapter").innerHTML=current.chapters.map(ch=>`<option value="${esc(ch.id)}">${esc("— ".repeat(ch.level-1)+ch.title)}</option>`).join("");$("media-target-chapter").value=c.id;
  $("media-assignment-title").value=mediaAssignment.title;$("media-assignment-kind").value=mediaAssignment.kind;$("media-assignment-note").value=mediaAssignment.note;
  $("media-assignment-conditions").innerHTML=Object.entries(assignmentLabels).map(([k,label])=>`<label>${label} (Komma getrennt)<input data-media-condition="${k}" value="${esc((mediaAssignment.conditions[k] || []).join(", "))}"></label>`).join("");
  renderMediaFrames();$("media-assignment-dialog").showModal();
}
function renderMediaFrames() {
  const choices=new Map(mediaEntries.filter(a=>!a.archived).map(a=>[`${a.id}|${a.revision}`,`${a.title} · R${a.revision} · ${a.status} · ${Object.values(a.profile).join(" / ")}`]));
  mediaAssignment.frames.forEach(f=>f.variants.forEach(r=>{const key=`${r.asset_id}|${r.revision}`;if(!choices.has(key))choices.set(key,`${mediaEntries.find(a=>a.id===r.asset_id)?.title || r.asset_id} · gebundene R${r.revision}`);}));
  $("media-frames").innerHTML=mediaAssignment.frames.map((f,i)=>`<fieldset data-frame="${i}"><legend>Position / Schritt ${i+1}</legend><label>Bildvarianten<select multiple size="5">${[...choices].map(([key,label])=>`<option value="${esc(key)}" ${f.variants.some(r=>`${r.asset_id}|${r.revision}`===key)?"selected":""}>${esc(label)}</option>`).join("")}</select></label><label>Untertitel nur für diese Verwendung (leer = zentral)<textarea rows="2">${esc(f.caption)}</textarea></label><button type="button" data-frame-up="${i}">↑</button><button type="button" data-frame-down="${i}">↓</button><button type="button" data-frame-remove="${i}">Schritt entfernen</button></fieldset>`).join("");
  $("media-frames").querySelectorAll("[data-frame]").forEach(row=>{const f=mediaAssignment.frames[Number(row.dataset.frame)];row.querySelector("select").onchange=e=>{f.variants=[...e.target.selectedOptions].map(o=>{const [id,rev]=o.value.split("|");return {asset_id:id,revision:Number(rev)}})};row.querySelector("textarea").oninput=e=>f.caption=e.target.value;});
  $("media-frames").querySelectorAll("button").forEach(el=>el.onclick=()=>{const remove=el.dataset.frameRemove;if(remove!==undefined){if(mediaAssignment.frames.length===1)return;mediaAssignment.frames.splice(Number(remove),1);}else{const from=Number(el.dataset.frameUp ?? el.dataset.frameDown),to=from+(el.dataset.frameUp!==undefined?-1:1);if(to<0||to>=mediaAssignment.frames.length)return;const part=mediaAssignment.frames.splice(from,1);mediaAssignment.frames.splice(to,0,...part);}renderMediaFrames();});
}
$("media-assignment-form").onsubmit=run(async e=>{
  e.preventDefault();mediaAssignment.title=$("media-assignment-title").value;mediaAssignment.kind=$("media-assignment-kind").value;mediaAssignment.note=$("media-assignment-note").value;
  if(mediaAssignment.kind==="Bild"&&mediaAssignment.frames.length!==1)throw new Error("Für mehrere Schritte die Art Klickstrecke wählen.");
  if(mediaAssignment.frames.some(f=>!f.variants.length))throw new Error("Für jede Position mindestens eine Bildvariante wählen.");
  $("media-assignment-conditions").querySelectorAll("input").forEach(el=>mediaAssignment.conditions[el.dataset.mediaCondition]=el.value.split(",").map(v=>v.trim()).filter(Boolean));
  const old=current.chapters.find(c=>c.id===mediaChapter),target=current.chapters.find(c=>c.id===$("media-target-chapter").value);
  const i=(old.media || []).findIndex(m=>m.id===mediaAssignment.id);
  if(old===target&&i>=0)old.media[i]=mediaAssignment;else{if(i>=0)old.media.splice(i,1);target.media ||= [];target.media.push(mediaAssignment);}
  target.config ||= {titles:{},kind:"Fachlich",inclusion:target.mandatory?"Pflicht":"Bedingt",selected:true,conditions:{},expected:[],empty_rule:target.mandatory?"Blockieren":"Auslassen",status:"Entwurf",generator:"Keiner"};target.config.status="Entwurf";
  selected=target.id;markDirty();$("media-assignment-dialog").close();if($("media-dialog").open)$("media-dialog").close();editor();tree();message("Medienzuordnung übernommen. Gliederung speichern und Ausgabe prüfen.");
});
async function renderPreviewMedia(plan,request) {
  // Insert images next to their actual chapter heading, not at the end of the document.
  const headings=[...$("preview").querySelectorAll("h2,h3,h4,h5,h6")];
  for(const c of plan.chapters.filter(c=>c.visible)) {
    const heading=headings.find(h=>h.textContent===`${c.number} ${c.title}`);if(!heading)continue;
    let anchor=heading;
    while(anchor.nextElementSibling && !/^H[2-6]$/.test(anchor.nextElementSibling.tagName))anchor=anchor.nextElementSibling;
    for(const figure of c.figures || []) {
      const container=document.createElement("section");container.className="preview-figure";container.innerHTML=`<h4>${esc(figure.title || figure.kind)}</h4>`;anchor.after(container);anchor=container;
      for(const frame of figure.frames) {
        const result=await api("/api/media/image",{id:frame.asset_id,revision:frame.revision,working_role:plan.profile.role});
        if(request!==previewRequest)return;
        const f=document.createElement("figure"),img=document.createElement("img"),caption=document.createElement("figcaption");img.src=result.image;img.alt=frame.caption||figure.title;caption.textContent=(figure.kind==="Klickstrecke"?`Schritt ${frame.step}: `:"")+frame.caption;f.append(img,caption);container.append(f);
      }
    }
  }
}
$("media-library").onclick=run(openMedia);$("media-close").onclick=()=>$("media-dialog").close();$("media-search").oninput=renderMediaList;$("media-working-role").onchange=renderMediaList;
$("asset-cancel").onclick=()=>{$("media-edit-dialog").close();assetEdit=null;};
$("media-create-path").onclick=run(()=>{const c=selectedChapter()||current.chapters[0];if(!c)throw new Error("Zuerst ein Kapitel erstellen.");return editMediaAssignment(c);});
$("media-add-frame").onclick=()=>{if(mediaAssignment.frames.length>=50)return;mediaAssignment.frames.push({caption:"",variants:[]});$("media-assignment-kind").value="Klickstrecke";renderMediaFrames();};
$("media-assignment-cancel").onclick=()=>$("media-assignment-dialog").close();
for(const id of ["asset-title","asset-caption"])$(id).oninput=invalidateAssetPreview;

function renderMediaTools(){
  $("media-upload-meta").innerHTML='<h3>Metadaten für neue Uploads</h3>'+inputField("Land (* = alle)","market","*")+selectField("Rolle","role",meta.roles,"*","",true)+selectField("Sparte","division",["Van","PC"],"*","",true)+selectField("Umfang","scope",meta.scopes,"*","",true)+selectField("Priorität","priority",["Hoch","Normal","Niedrig"],"Normal")+inputField("Labels (Komma getrennt)","labels","");
  $("media-filters").innerHTML='<label>Land<input data-filter="market"></label>'+[["role","Rolle",meta.roles],["division","Sparte",["Van","PC"]],["scope","Umfang",meta.scopes],["priority","Priorität",["Hoch","Normal","Niedrig"]]].map(([k,title,values])=>`<label>${title}<select data-filter="${k}"><option value="">Alle</option>${options(values,"")}</select></label>`).join("")+'<label>Sortieren nach<select id="media-sort"><option value="title">Titel</option><option value="market">Land</option><option value="role">Rolle</option><option value="division">Sparte</option><option value="scope">Umfang</option><option value="priority">Priorität</option></select></label>';
  $("media-filters").querySelectorAll("input,select").forEach(el=>el.oninput=renderMediaList);
}
function mediaUploadMetadata(){const data={};$("media-upload-meta").querySelectorAll("[data-key]").forEach(el=>data[el.dataset.key]=el.value);data.classification={roles:[],domain_ids:[],keywords:[],labels:splitLabels(data.labels||""),topic:""};delete data.labels;return data;}
