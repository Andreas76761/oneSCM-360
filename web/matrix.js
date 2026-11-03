"use strict";
let remarkContext = null;
function countChunks(ids, role = $("tree-chunk-role")?.value || "*") {
  return (meta.chunk_index || []).filter(chunk => (role === "*" || (chunk.labels.roles || []).includes(role)) && chunk.assignments.some(a => a.outline_id === current.id && ids.has(a.chapter_id))).length;
}
function chunkCount(id, recursive = false, role) {
  const index = current.chapters.findIndex(c => c.id === id);
  const chapters = recursive ? current.chapters.slice(index,subtreeEnd(current.chapters,index)) : [current.chapters[index]];
  return countChunks(new Set(chapters.filter(Boolean).map(c=>c.id)),role);
}
async function refreshSourceIndex() {
  const data = await api("/api/sources",{}); meta.chunk_index=data.chunk_index;
  return data;
}
function renderClassification(c) {
  c.roles ||= []; c.remarks ||= [];
  $("chapter-classification").innerHTML = `<h3>Thema & Suchbegriffe</h3><div class="classification-fields">${inputField("Stichwörter","keywords",c.keywords || "")}${inputField("Labels","labels",c.labels || "")}${inputField("Thema","topic",c.topic || "")}</div><p class="muted">Kapitelrollen zur Einordnung; keine Auswahl bedeutet alle Rollen. Die Exportregeln der Textbausteine bleiben separat.</p><div class="role-choices">${meta.roles.map(r=>`<label class="check"><input type="checkbox" data-chapter-role="${esc(r)}" ${c.roles.includes(r)?"checked":""}>${esc(r)}</label>`).join("")}</div><h3>Interne Bemerkungen</h3>${c.remarks.map(n=>`<div class="note note-${esc(n.color)}"><div>${esc(n.text)}</div><small>${esc(n.role === "*" ? "Alle Rollen" : n.role)} · ${esc(n.domain_id === "*" ? "Alle Domänen" : targetLabel(n.domain_id))}</small><div class="note-actions"><button data-edit-note="${esc(n.id)}">Bearbeiten</button><button data-delete-note="${esc(n.id)}">Entfernen</button></div></div>`).join("")}<button id="add-chapter-note">+ Interne Bemerkung</button><p class="muted">${chunkCount(c.id,false,"*")} bestätigte Chunks direkt zugeordnet. Chunks sind Quellmaterial und werden erst als redigierte Textbausteine ausgegeben.</p>`;
  $("chapter-classification").querySelectorAll("[data-key]").forEach(el=>el.oninput=()=>{c[el.dataset.key]=el.value;markDirty();});
  $("chapter-classification").querySelectorAll("[data-chapter-role]").forEach(el=>el.onchange=()=>{c.roles=[...$("chapter-classification").querySelectorAll("[data-chapter-role]:checked")].map(x=>x.dataset.chapterRole);markDirty();});
  $("add-chapter-note").onclick=()=>openRemark(c.id);
  $("chapter-classification").querySelectorAll("[data-edit-note]").forEach(b=>b.onclick=()=>openRemark(c.id,b.dataset.editNote));
  $("chapter-classification").querySelectorAll("[data-delete-note]").forEach(b=>b.onclick=()=>{c.remarks=c.remarks.filter(n=>n.id!==b.dataset.deleteNote);markDirty();renderClassification(c);});
}
function openRemark(chapterId, noteId=null, role="*", domain="*") {
  remarkContext={chapterId,noteId}; const c=current.chapters.find(x=>x.id===chapterId), n=c.remarks?.find(x=>x.id===noteId);
  $("remark-text").value=n?.text || ""; $("remark-color").value=n?.color || "gelb";
  $("remark-role").innerHTML=options(meta.roles,n?.role || role,true);
  $("remark-domain").innerHTML='<option value="*">Alle Domänen</option>'+allTargets().map(d=>`<option value="${esc(d.id)}">${esc(targetLabel(d.id))}</option>`).join("");
  $("remark-domain").value=n?.domain_id || domain; $("remark-dialog").showModal();
}
$("cancel-remark").onclick=()=>$("remark-dialog").close();
$("remark-form").onsubmit=e=>{
  e.preventDefault(); const c=current.chapters.find(x=>x.id===remarkContext.chapterId); c.remarks ||= [];
  const note={id:remarkContext.noteId || uuid(),text:$("remark-text").value,color:$("remark-color").value,role:$("remark-role").value,domain_id:$("remark-domain").value};
  const index=c.remarks.findIndex(n=>n.id===note.id); if(index<0)c.remarks.push(note);else c.remarks[index]=note;
  markDirty(); $("remark-dialog").close(); if(!$("matrix-view").hidden)renderMatrix();else editor();
};
function renderMatrix() {
  const q=$("matrix-keyword").value.toLowerCase(), label=$("matrix-label").value.toLowerCase(), topic=$("matrix-topic").value.toLowerCase(), role=$("matrix-role").value, domain=$("matrix-domain").value;
  const numbers=new Map(); function visit(nodes){for(const n of nodes){numbers.set(n.chapter.id,n.number);visit(n.children);}}visit(nestedChapters(current.chapters));
  const rows=[];
  for(const c of current.chapters){
    if(![c.title,c.goal,c.keywords,...(c.remarks||[]).map(n=>n.text)].join(" ").toLowerCase().includes(q) || !(c.labels||"").toLowerCase().includes(label) || !(c.topic||"").toLowerCase().includes(topic))continue;
    const roles=c.roles?.length ? c.roles : meta.roles, mappings=c.mappings?.length ? c.mappings : [{target_id:"*",active:false}];
    for(const r of roles)for(const m of mappings){
      if(role && r!==role || domain && m.target_id!==domain)continue;
      const notes=(c.remarks||[]).filter(n=>(n.role==="*"||n.role===r)&&(n.domain_id==="*"||n.domain_id===m.target_id));
      rows.push(`<tr><td><button data-matrix-chapter="${esc(c.id)}">${esc(numbers.get(c.id))} ${esc(c.title)}</button><small>${esc(c.topic||"")}</small><small>${esc(c.labels||"")}</small></td><td>${esc(r)}</td><td>${m.target_id==="*" ? "Ohne Zuordnung" : esc(targetLabel(m.target_id))}<small>${m.target_id!=="*" ? (current.mapping_enabled && m.active ? "Aktiv" : "Inaktiv") : ""}</small></td><td>${chunkCount(c.id,false,r)}</td><td>${notes.map(n=>`<div class="note note-${esc(n.color)}">${esc(n.text)}<br><button data-note="${esc(n.id)}" data-chapter="${esc(c.id)}">Bearbeiten</button></div>`).join("")}<button data-new-note="${esc(c.id)}" data-role="${esc(r)}" data-domain="${esc(m.target_id)}">+ Bemerkung</button></td></tr>`);
    }
  }
  $("matrix-table").innerHTML=`<p class="muted">${rows.length} Kombinationen · Chunk-Zahlen je Kapitel und Rolle; derselbe Chunk kann in mehreren Domänenzeilen erscheinen.</p><table class="matrix-table"><thead><tr><th>Kapitel / Unterkapitel</th><th>Rolle</th><th>Domäne / Unterdomäne</th><th>Chunks</th><th>Interne Bemerkungen</th></tr></thead><tbody>${rows.join("")||'<tr><td colspan="5">Keine passenden Einträge.</td></tr>'}</tbody></table>`;
  $("matrix-table").querySelectorAll("[data-matrix-chapter]").forEach(b=>b.onclick=()=>{selected=b.dataset.matrixChapter;showTab(false);tree();editor();});
  $("matrix-table").querySelectorAll("[data-new-note]").forEach(b=>b.onclick=()=>openRemark(b.dataset.newNote,null,b.dataset.role,b.dataset.domain));
  $("matrix-table").querySelectorAll("[data-note]").forEach(b=>b.onclick=()=>openRemark(b.dataset.chapter,b.dataset.note));
}
$("matrix-tab").onclick=()=>{
  previewRequest++;showTab(false);$("editing").hidden=true;$("matrix-view").hidden=false;$("edit-tab").classList.remove("active");$("matrix-tab").classList.add("active");
  const value=$("matrix-domain").value;$("matrix-domain").innerHTML='<option value="">Alle Domänen</option>'+allTargets().map(d=>`<option value="${esc(d.id)}">${esc(targetLabel(d.id))}</option>`).join("");$("matrix-domain").value=value;renderMatrix();
};
for(const id of ["matrix-keyword","matrix-label","matrix-role","matrix-topic","matrix-domain"])$(id).oninput=renderMatrix;
