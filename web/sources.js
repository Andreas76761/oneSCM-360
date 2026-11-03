"use strict";
let sourceRows=[], sourceId=null, sourceChunks=[], chunkPage=0, triageRunning=false, triageCancelled=false;
let reviewChunk=null, reviewLinks=[], reviewOutline="";
const splitLabels=value=>value.split(",").map(x=>x.trim()).filter(Boolean);
async function openSources() {
  previewRequest++;domainTreeRequest++;
  for(const id of ["studio","empty","overview","comparison"])$(id).hidden=true;
  $("sources-view").hidden=false;$("message").hidden=true;
  $("triage-outline").innerHTML=meta.outlines.map(o=>`<option value="${esc(o.id)}">${esc(o.title)} · V${esc(o.metadata.version)}</option>`).join("");
  if(current)$("triage-outline").value=current.id;
  await loadSources();
}
async function loadSources() {
  const result=await refreshSourceIndex();sourceRows=result.sources;renderSources();
}
function renderSources() {
  const query=$("source-search").value.toLowerCase();
  $("source-list").innerHTML=sourceRows.filter(s=>[s.name,s.kind,s.origin,s.release].join(" ").toLowerCase().includes(query)).map(s=>`<article class="source-card" data-source="${esc(s.id)}"><div class="panel-heading"><div><strong>${esc(s.name)}</strong><p class="muted">${esc(s.kind)} · ${s.chunks} Chunks · ${Math.ceil(s.size/1024)} KB · ${esc(formatDate(s.uploaded))}<br>${esc(s.origin)} ${s.release ? " · Release " + esc(s.release) : ""}</p></div><div class="actions"><button data-open-source="${esc(s.id)}">Chunks ansehen</button><button data-triage="${esc(s.id)}" ${triageRunning||!meta.outlines.length||!s.chunks?"disabled":""}>KI Triage</button>${/\.(docx|pptx|pdf)$/i.test(s.name)?`<button data-extract-images="${esc(s.id)}">Bilder extrahieren</button>`:""}<button data-delete-source="${esc(s.id)}" class="danger" ${triageRunning?"disabled":""}>Datei löschen</button></div></div>${s.warnings.map(w=>`<div class="warning">${esc(w)}</div>`).join("")}</article>`).join("") || '<p class="muted">Keine passenden Quellen vorhanden.</p>';
  $("source-list").querySelectorAll("[data-open-source]").forEach(b=>b.onclick=run(()=>openSource(b.dataset.openSource)));
  $("source-list").querySelectorAll("[data-triage]").forEach(b=>b.onclick=run(()=>triageSource(b.dataset.triage)));
  $("source-list").querySelectorAll("[data-extract-images]").forEach(b=>b.onclick=run(async()=>{
    if(!["HQ","intern"].includes(mediaRole())) throw new Error("Unter Bilder & Klickstrecken zuerst Redaktionsrolle HQ / intern wählen.");
    b.disabled=true;
    try { const result=await api("/api/media/extract",{id:b.dataset.extractImages,working_role:mediaRole(),language:current?.profile.language || "de"});message(`${result.images.length} Bildfundstellen verarbeitet. ${result.notice} ${result.warnings.join(" ")}`); }
    finally { b.disabled=false; }
  }));
  $("source-list").querySelectorAll("[data-delete-source]").forEach(b=>b.onclick=run(async()=>{
    const s=sourceRows.find(x=>x.id===b.dataset.deleteSource);
    if(!confirm(`„${s.name}“ mit Originaldatei, ${s.chunks} Chunks und deren Zuordnungen endgültig löschen? Extrahierte Medienkopien und erzeugte Dokumente bleiben erhalten.`))return;
    await api("/api/source/delete",{id:s.id});if(sourceId===s.id){sourceId=null;sourceChunks=[];$("source-chunks").hidden=true;}await loadSources();message("Quelle, Chunks und Zuordnungen gelöscht. Bereits erzeugte Dokumente bleiben erhalten.");
  }));
}
async function openSource(id) {
  sourceId=id;sourceChunks=await api("/api/source/chunks",{id});chunkPage=0;
  $("source-chunks").hidden=false;$("source-chunks-title").textContent=sourceRows.find(s=>s.id===id)?.name || "Chunks";renderChunks();
}
function effectiveLabels(c) {return Object.keys(c.labels).length ? c.labels : c.suggestion;}
function renderChunks() {
  const query=$("chunk-search").value.toLowerCase(),label=$("chunk-label-search").value.toLowerCase(),role=$("chunk-role-search").value,topic=$("chunk-topic-search").value.toLowerCase();
  const filtered=sourceChunks.filter(c=>{const v=effectiveLabels(c);return [c.text,...(v.keywords||[])].join(" ").toLowerCase().includes(query) && (v.labels||[]).join(" ").toLowerCase().includes(label) && (!role||(v.roles||[]).includes(role)) && (v.topic||"").toLowerCase().includes(topic);});
  const pages=Math.max(1,Math.ceil(filtered.length/20));chunkPage=Math.min(chunkPage,pages-1);
  $("chunk-list").innerHTML=filtered.slice(chunkPage*20,chunkPage*20+20).map(c=>{
    const v=effectiveLabels(c), reviewed=Object.keys(c.labels).length>0;
    return `<article class="source-card"><strong>Chunk ${c.ordinal} · ${esc(c.location)}</strong><p class="chunk-text">${esc(c.text)}</p><p class="muted">${reviewed?"Labels geprüft":"Labels noch nicht bestätigt"}${c.suggestion.method?" · Vorschlag: "+esc(c.suggestion.method):""}</p><div>${[...(v.roles||[]),...(v.domain_ids||[]).map(targetLabel),...(v.keywords||[]),...(v.labels||[])].map(label=>`<span class="label-chip">${esc(label)}</span>`).join("")}</div><p class="muted">Thema: ${esc(v.topic||"Noch offen")}<br>${c.assignments.length} bestätigte Kapitelzuordnungen</p><div class="chunk-actions"><button data-review-chunk="${esc(c.id)}">Prüfen & zuordnen</button>${c.suggestion.method?`<button data-proposed-chunk="${esc(c.id)}">Triage-Vorschlag prüfen</button>`:""}</div></article>`;
  }).join("")||'<p class="muted">Keine passenden Chunks.</p>';
  $("chunks-page").textContent=`Seite ${chunkPage+1} / ${pages} · ${filtered.length} Chunks`;
  $("chunks-prev").disabled=chunkPage===0;$("chunks-next").disabled=chunkPage>=pages-1;
  $("chunk-list").querySelectorAll("[data-review-chunk]").forEach(b=>b.onclick=()=>openChunkReview(b.dataset.reviewChunk,false));
  $("chunk-list").querySelectorAll("[data-proposed-chunk]").forEach(b=>b.onclick=()=>openChunkReview(b.dataset.proposedChunk,true));
}
function syncReviewLinks() {
  if(!reviewOutline)return;
  reviewLinks=reviewLinks.filter(a=>a.outline_id!==reviewOutline).concat([...$("review-chapters").selectedOptions].map(o=>({outline_id:reviewOutline,chapter_id:o.value})));
}
function showReviewChapters() {
  reviewOutline=$("review-outline").value;
  const outline=meta.outlines.find(o=>o.id===reviewOutline);
  $("review-chapters").innerHTML=(outline?.chapters||[]).map(c=>`<option value="${esc(c.id)}" ${reviewLinks.some(a=>a.outline_id===reviewOutline&&a.chapter_id===c.id)?"selected":""}>${esc("— ".repeat(c.level-1)+c.title)}</option>`).join("");
}
function openChunkReview(id, proposed) {
  reviewChunk=sourceChunks.find(c=>c.id===id);
  const value=proposed||!Object.keys(reviewChunk.labels).length?reviewChunk.suggestion:reviewChunk.labels;
  reviewLinks=structuredClone(reviewChunk.assignments);
  if(proposed||!Object.keys(reviewChunk.labels).length){
    for(const chapter_id of value.chapter_ids||[])if(!reviewLinks.some(a=>a.outline_id===value.outline_id&&a.chapter_id===chapter_id))reviewLinks.push({outline_id:value.outline_id,chapter_id});
  }
  $("chunk-review-text").textContent=reviewChunk.text;$("chunk-review-origin").textContent=`${reviewChunk.location} · ${value.method||"Manuelle Prüfung"}`;
  $("review-roles").innerHTML=meta.roles.map(r=>`<option ${(value.roles||[]).includes(r)?"selected":""}>${esc(r)}</option>`).join("");
  $("review-domains").innerHTML=allTargets().map(d=>`<option value="${esc(d.id)}" ${(value.domain_ids||[]).includes(d.id)?"selected":""}>${esc(targetLabel(d.id))}</option>`).join("");
  $("review-keywords").value=(value.keywords||[]).join(", ");$("review-labels").value=(value.labels||[]).join(", ");$("review-topic").value=value.topic||"";
  $("review-outline").innerHTML='<option value="">Keine Gliederung wählen</option>'+meta.outlines.map(o=>`<option value="${esc(o.id)}">${esc(o.title)}</option>`).join("");
  $("review-outline").value=value.outline_id||current?.id||meta.outlines[0]?.id||"";
  showReviewChapters();$("chunk-review-error").hidden=true;$("chunk-review-dialog").showModal();
}
$("review-outline").onchange=()=>{syncReviewLinks();showReviewChapters();};
$("cancel-review").onclick=()=>$("chunk-review-dialog").close();
$("chunk-review-form").onsubmit=async e=>{
  e.preventDefault();syncReviewLinks();
  try {
    await api("/api/source/review",{id:reviewChunk.id,revision:reviewChunk.revision,labels:{roles:[...$("review-roles").selectedOptions].map(o=>o.value),domain_ids:[...$("review-domains").selectedOptions].map(o=>o.value),keywords:splitLabels($("review-keywords").value),labels:splitLabels($("review-labels").value),topic:$("review-topic").value},assignments:reviewLinks});
    $("chunk-review-dialog").close();await refreshSourceIndex();const page=chunkPage;sourceChunks=await api("/api/source/chunks",{id:sourceId});chunkPage=page;renderChunks();message("Chunk-Labels und Kapitelzuordnungen gespeichert.");
  }catch(error){$("chunk-review-error").textContent=error.message;$("chunk-review-error").hidden=false;}
};
async function triageSource(id) {
  const outline_id=$("triage-outline").value,mode=$("triage-mode").value,model=$("triage-model").value;
  if(!outline_id)throw new Error("Bitte zuerst eine Gliederung anlegen und speichern.");
  triageRunning=true;triageCancelled=false;$("stop-triage").hidden=false;renderSources();
  let offset=0;
  try {
    do {
      $("triage-progress").textContent=`${mode==="rules"?"Lokale Regel-Triage (keine KI)":"KI Triage über Ollama"}: ${offset} Chunks verarbeitet …`;
      const result=await api("/api/source/triage",{id,outline_id,mode,model,offset});offset=result.processed;
      if(result.done){$("triage-progress").textContent=`${offset}/${result.total} Chunks mit Vorschlägen versehen. Bitte Labels und Zuordnungen prüfen.`;break;}
    }while(!triageCancelled);
    if(triageCancelled)$("triage-progress").textContent=`Triage nach ${offset} Chunks angehalten. Vorhandene Vorschläge bleiben gespeichert.`;
    await openSource(id);
  }catch(error){$("triage-progress").textContent=error.message;throw error;}
  finally{triageRunning=false;$("stop-triage").hidden=true;renderSources();}
}
$("stop-triage").onclick=()=>{triageCancelled=true;$("triage-progress").textContent="Hält nach dem laufenden Chunk beziehungsweise Regel-Batch an …";};
$("sources-button").onclick=run(openSources);$("source-search").oninput=renderSources;
for(const id of ["chunk-search","chunk-label-search","chunk-role-search","chunk-topic-search"])$(id).oninput=()=>{chunkPage=0;renderChunks();};
$("chunks-prev").onclick=()=>{chunkPage--;renderChunks();};$("chunks-next").onclick=()=>{chunkPage++;renderChunks();};
$("source-upload").onsubmit=run(async e=>{
  e.preventDefault();const files=[...$("source-files").files];if(!files.length)return;
  const button=$("source-upload").querySelector('button[type="submit"]');button.disabled=true;
  const results=[];
  try {
    for(const file of files){
      try{
        if(file.size>10*1024*1024)throw new Error("größer als 10 MB");
        const bytes=new Uint8Array(await file.arrayBuffer());let binary="";
        for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
        const result=await api("/api/source/upload",{name:file.name,base64:btoa(binary),kind:$("source-kind").value,origin:$("source-origin").value,release:$("source-release").value});
        results.push(`${file.name}: ${result.duplicate?"bereits vorhanden":`${result.chunks} Chunks importiert`}`);
      }catch(error){results.push(`${file.name}: ${error.message}`);}
    }
    await loadSources();$("source-files").value="";message(results.join(" · "));
  }finally{button.disabled=false;}
});
