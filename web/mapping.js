"use strict";
let domainTreeRequest = 0, taxonomyDraft = null;
const closedDomains = new Set();
function allTargets() { return [...meta.taxonomy.domains,...meta.taxonomy.subdomains]; }
function targetLabel(id) {
  const targets = allTargets(), target = targets.find(d => d.id === id);
  return target ? (target.parent_id ? targets.find(d => d.id === target.parent_id)?.name + " / " : "") + target.name : id;
}
function chapterMappingBadges(c) {
  const active = (c.mappings || []).filter(m => m.active && current.mapping_enabled);
  return `<small class="mapping-badges">${active.map(m => esc(targetLabel(m.target_id))).join(" · ") || "Keine aktive Domänenzuordnung"}</small><small>${chunkCount(c.id)} Chunks direkt · ${chunkCount(c.id,true)} inkl. Unterkapitel</small>`;
}
function renderMappingControls() {
  $("mapping-enabled").checked = current.mapping_enabled !== false;
  const all = current.chapters.flatMap(c => c.mappings || []);
  const active = current.mapping_enabled ? all.filter(m => m.active).length : 0;
  $("mapping-summary").textContent = `${active} aktive / ${all.length} gespeicherte Zuordnungen${current.mapping_enabled ? "" : " · Mapping pausiert"}`;
  $("add-subchapter").disabled = !selectedChapter() || selectedChapter().level >= 6;
}
function renderChapterMapping(c) {
  c.mappings ||= [];
  const choices = allTargets().filter(d => !c.mappings.some(m => m.target_id === d.id));
  $("chapter-mapping").innerHTML = `<h3>Domänen & Unterdomänen</h3><p class="muted">Mehrfachzuordnung für dieses Kapitel. Unterkapitel werden separat zugeordnet. Mapping steuert die Navigation, nicht die Exportauswahl.</p><div class="mapping-add"><label>Domäne oder Unterdomäne<select id="mapping-target">${choices.map(d => `<option value="${esc(d.id)}">${esc(targetLabel(d.id))}</option>`).join("")}</select></label><button id="add-mapping" ${choices.length ? "" : "disabled"}>Zuordnung hinzufügen</button></div><div id="mapping-edges">${c.mappings.map(m => `<div class="mapping-edge ${current.mapping_enabled && m.active ? "" : "mapping-inactive"}" data-target="${esc(m.target_id)}"><span>${esc(targetLabel(m.target_id))}</span><label class="check"><input type="checkbox" class="edge-active" ${m.active ? "checked" : ""}>Aktiv</label><button class="remove-edge">Entfernen</button></div>`).join("") || '<p class="muted">Noch keine Zuordnung.</p>'}</div><div id="chapter-classification"></div>`;
  $("add-mapping").onclick = () => {
    const target = $("mapping-target").value;
    if (!target || c.mappings.some(m => m.target_id === target)) return;
    c.mappings.push({target_id:target,active:true}); markDirty(); renderChapterMapping(c); tree();
  };
  $("mapping-edges").querySelectorAll(".mapping-edge").forEach(row => {
    const edge = c.mappings.find(m => m.target_id === row.dataset.target);
    row.querySelector(".edge-active").onchange = e => { edge.active = e.target.checked; markDirty(); renderChapterMapping(c); tree(); };
    row.querySelector(".remove-edge").onclick = () => { c.mappings = c.mappings.filter(m => m !== edge); markDirty(); renderChapterMapping(c); tree(); };
  });
  renderClassification(c);
}
async function renderDomainTree() {
  const request = ++domainTreeRequest, id = current.id;
  const result = await api("/api/domain-map", {outline:current,include_inactive:$("show-inactive-mappings").checked});
  if (request !== domainTreeRequest || current?.id !== id || $("tree-mode").value !== "domains") return;
  const nested = nestedChapters(current.chapters);
  function chapterBranch(links) {
    const assigned = new Map(links.map(l => [l.chapter_id,l]));
    function visit(nodes) {
      let html = "";
      for (const node of nodes) {
        const c = node.chapter, link = assigned.get(c.id), children = visit(node.children);
        if (!link && !children) continue;
        const label = `<button class="chapter-row ${c.id === selected ? "selected" : ""} ${!link ? "mapping-context" : !link.effective ? "mapping-inactive" : ""}" data-id="${esc(c.id)}">${esc(node.number)} ${esc(c.title)}<small>${link ? esc(link.reason) : "Übergeordnetes Kapitel · nur Kontext"} · ${chunkCount(c.id)} Chunks</small></button>`;
        html += `<li>${children ? `<details open><summary>${label}</summary><ul>${children}</ul></details>` : label}</li>`;
      }
      return html;
    }
    return `<ul class="domain-chapters">${visit(nested)}</ul>`;
  }
  function section(d) {
    const groupedLinks = d.links.concat((d.subdomains || []).flatMap(s => s.links));
    const ids = new Set(groupedLinks.map(l => l.chapter_id));
    return `<details class="domain-group" data-domain="${esc(d.id)}" ${closedDomains.has(d.id) ? "" : "open"}><summary><strong>${esc(d.name)}</strong><small>${ids.size} Kapitel · ${countChunks(ids)} Chunks</small></summary>${d.links.length ? chapterBranch(d.links) : '<p class="muted">Keine direkten Zuordnungen.</p>'}${(d.subdomains || []).map(section).join("")}</details>`;
  }
  $("chapter-tree").innerHTML = result.groups.map(section).join("") + `<details class="domain-group" open><summary>Ohne aktive Zuordnung (${result.unmapped.length})</summary>${chapterBranch(result.unmapped.map(id => ({chapter_id:id,effective:false,reason:"Keine aktive Zuordnung"})))}</details>`;
  $("chapter-tree").querySelectorAll(".chapter-row").forEach(button => button.onclick = e => { e.preventDefault(); e.stopPropagation(); selected=button.dataset.id; editor(); $("chapter-tree").querySelectorAll(".chapter-row").forEach(b => b.classList.toggle("selected",b.dataset.id === selected)); renderMappingControls(); });
  $("chapter-tree").querySelectorAll("[data-domain]").forEach(el => el.ontoggle = () => { if (!el.isConnected) return; el.open ? closedDomains.delete(el.dataset.domain) : closedDomains.add(el.dataset.domain); });
}
function setDomainExpansion(open) {
  allTargets().forEach(d => open ? closedDomains.delete(d.id) : closedDomains.add(d.id));
  $("chapter-tree").querySelectorAll("details").forEach(d => d.open=open);
}
$("tree-mode").onchange = () => tree();
$("show-inactive-mappings").onchange = () => tree();
$("mapping-enabled").onchange = e => { current.mapping_enabled=e.target.checked; markDirty(); tree(); if(selectedChapter()) renderChapterMapping(selectedChapter()); };
function renderSubdomains() {
  $("subdomain-list").innerHTML = taxonomyDraft.domains.map(d => `<section><h3>${esc(d.name)}</h3>${taxonomyDraft.subdomains.filter(s => s.parent_id === d.id).map(s => `<label>Unterdomäne<input data-subdomain="${esc(s.id)}" value="${esc(s.name)}" maxlength="150"></label>`).join("") || '<p class="muted">Noch keine Unterdomäne.</p>'}</section>`).join("");
  $("subdomain-list").querySelectorAll("[data-subdomain]").forEach(el => el.oninput = () => taxonomyDraft.subdomains.find(s=>s.id===el.dataset.subdomain).name=el.value);
}
$("manage-subdomains").onclick = run(async () => {
  meta.taxonomy=await api("/api/taxonomy",{}); taxonomyDraft=structuredClone(meta.taxonomy);
  $("subdomain-parent").innerHTML=taxonomyDraft.domains.map(d=>`<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("");
  $("subdomain-name").value=""; $("taxonomy-error").hidden=true; renderSubdomains(); $("taxonomy-dialog").showModal();
});
$("add-subdomain").onclick = () => {
  const name=$("subdomain-name").value.trim(); if(!name) return;
  taxonomyDraft.subdomains.push({id:uuid(),name,parent_id:$("subdomain-parent").value}); $("subdomain-name").value=""; renderSubdomains();
};
$("cancel-taxonomy").onclick = () => $("taxonomy-dialog").close();
$("taxonomy-form").onsubmit = async e => {
  e.preventDefault();
  try { meta.taxonomy=await api("/api/taxonomy/save",taxonomyDraft); $("taxonomy-dialog").close(); tree(); editor(); message("Unterdomänen zentral gespeichert. Kapitelzuordnungen mit der Gliederung speichern."); }
  catch(error) { $("taxonomy-error").textContent=error.message; $("taxonomy-error").hidden=false; }
};

$("tree-chunk-role").onchange = () => tree();
