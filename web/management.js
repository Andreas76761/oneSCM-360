"use strict";
const outlineStatuses = ["Entwurf", "In Prüfung", "Freigegeben", "Archiviert"];
const documentTypes = ["Handbuch", "Releaseletter", "Quickreference", "Sonstiges"];
const compareSelection = new Set(), collapsedChapters = new Set();
let comparisonData = null, comparisonRequest = 0, comparisonSetup = 0;
const revisionRequests = {left:0,right:0};
const diffLabels = {added:"Neu",removed:"Entfernt",renamed:"Umbenannt",moved:"Verschoben",changed:"Geändert",unchanged:"Unverändert"};
const fieldLabels = {mandatory:"Pflichtkapitel",domain:"Domäne",goal:"Kapitelziel",blocks:"Textbausteine",title:"Titel",
  "metadata.version":"Gliederungsversion","metadata.document_type":"Dokumentart","metadata.status":"Status",
  "metadata.owner":"Verantwortlich","metadata.description":"Beschreibung","metadata.tags":"Tags",
  "profile.role":"Rolle","profile.scope":"Umfang","profile.market":"Markt","profile.release":"Produktrelease",
  "profile.division":"Sparte","profile.language":"Sprache","profile.show_notes":"Interne Vermerke",
  "profile.approved_only":"Nur freigegebene Bausteine"};

function openOutline(id) {
  if (current?.id === id) { render(); return; }
  if (dirty && !confirm("Ungespeicherte Änderungen verwerfen?")) return;
  current = structuredClone(meta.outlines.find(o => o.id === id));
  selected = current.chapters[0]?.id; dirty = false; render();
}
function openOverview() {
  previewRequest++;
  $("message").hidden = true;
  $("studio").hidden = true; $("empty").hidden = true; $("comparison").hidden = true; $("overview").hidden = false;
  renderOverview();
}
function formatDate(value) {
  return value ? new Date(value).toLocaleString("de-DE", {dateStyle:"short",timeStyle:"short"}) : "Noch nicht erfasst";
}
function renderOverview() {
  const query = $("overview-search").value.trim().toLocaleLowerCase("de");
  const status = $("overview-status").value, role = $("overview-role").value;
  const rows = meta.outlines.filter(o => (!status || o.metadata.status === status) && (!role || o.profile.role === role)
    && [o.title,...Object.values(o.metadata),...Object.values(o.profile)].join(" ").toLocaleLowerCase("de").includes(query));
  const sort = $("overview-sort").value;
  rows.sort((a,b) => sort === "updated" ? (b.updated_at || "").localeCompare(a.updated_at || "") :
    (sort === "version" ? a.metadata.version.localeCompare(b.metadata.version,"de",{numeric:true}) : a.title.localeCompare(b.title,"de")));
  $("overview-count").textContent = `${rows.length} von ${meta.outlines.length} Gliederungen · gespeicherte Stände${dirty ? " · offene Bearbeitung noch nicht gespeichert" : ""}`;
  $("overview-rows").innerHTML = rows.map(o => `<tr data-id="${esc(o.id)}"><td><input type="checkbox" class="compare-choice" aria-label="${esc(o.title)} für Vergleich auswählen" ${compareSelection.has(o.id) ? "checked" : ""}></td><td><button class="table-title" data-open="${esc(o.id)}">${esc(o.title)}</button><small>${esc(o.metadata.document_type)}${o.metadata.owner ? " · " + esc(o.metadata.owner) : ""}</small><small>${esc(o.metadata.tags)}</small></td><td><strong>${esc(o.metadata.version)}</strong><small>Revision ${o.revision}</small></td><td><span class="status-pill">${esc(o.metadata.status)}</span></td><td>${esc(o.profile.role)}<small>${esc(o.profile.scope)} · ${esc(o.profile.language.toUpperCase())}</small></td><td>${o.chapters.length}</td><td>${esc(formatDate(o.updated_at))}</td><td><button data-open="${esc(o.id)}">Bearbeiten</button><button data-history="${esc(o.id)}">Stände</button></td></tr>`).join("") || '<tr><td colspan="8" class="empty-table">Keine Gliederung gefunden. Lege eine Gliederung an oder passe die Filter an.</td></tr>';
  $("overview-rows").querySelectorAll("[data-open]").forEach(button => button.onclick = () => openOutline(button.dataset.open));
  $("overview-rows").querySelectorAll("[data-history]").forEach(button => button.onclick = run(() => openComparison(button.dataset.history,button.dataset.history,true)));
  $("overview-rows").querySelectorAll(".compare-choice").forEach(input => input.onchange = () => {
    const id = input.closest("tr").dataset.id;
    if (input.checked && compareSelection.size >= 2 && !compareSelection.has(id)) {
      input.checked = false; return message("Für den direkten Vergleich bitte höchstens zwei Gliederungen auswählen.");
    }
    input.checked ? compareSelection.add(id) : compareSelection.delete(id);
    updateCompareSelection();
  });
  updateCompareSelection();
}
function updateCompareSelection() {
  $("compare-selected").textContent = `Auswahl vergleichen (${compareSelection.size}/2)`;
  $("compare-selected").disabled = compareSelection.size !== 2;
}
function renderMetadata() {
  const m = current.metadata;
  $("outline-metadata").innerHTML = inputField("Gliederungsversion","version",m.version,'maxlength="60" required')
    + selectField("Dokumentart","document_type",documentTypes,m.document_type)
    + selectField("Bearbeitungsstatus","status",outlineStatuses,m.status)
    + inputField("Verantwortlich","owner",m.owner,'maxlength="200"')
    + inputField("Tags / Stichwörter","tags",m.tags,'maxlength="500" placeholder="z. B. Blueprint, Vertrag"')
    + `<label class="description-field">Beschreibung<textarea data-key="description" rows="2" maxlength="5000">${esc(m.description)}</textarea></label>`;
  $("outline-metadata").querySelectorAll("[data-key]").forEach(el => el.oninput = () => { m[el.dataset.key] = el.value; markDirty(); });
}
function nestedChapters(chapters) {
  const roots = [], stack = [], counts = [0,0,0,0,0,0];
  for (const c of chapters) {
    while (stack.length && stack.at(-1).chapter.level >= c.level) stack.pop();
    counts[c.level-1]++; counts.fill(0,c.level);
    const node = {chapter:c,number:counts.slice(0,c.level).join("."),children:[]};
    (stack.length ? stack.at(-1).children : roots).push(node); stack.push(node);
  }
  return roots;
}
function renderChapterTree() {
  const nodes = nestedChapters(current.chapters);
  function branch(items) {
    return `<ul class="folder-tree">${items.map(({chapter:c,number,children}) => {
      const collapsed = collapsedChapters.has(c.id);
      return `<li><div class="tree-node">${children.length ? `<button class="node-toggle" data-toggle="${esc(c.id)}" aria-expanded="${!collapsed}" aria-label="${esc(c.title)} ${collapsed ? "aufklappen" : "zuklappen"}">${collapsed ? "▸" : "▾"}</button>` : '<span class="node-leaf" aria-hidden="true">·</span>'}<button class="chapter-row ${c.id === selected ? "selected" : ""}" data-id="${esc(c.id)}">${esc(number)} ${esc(c.title)}<small>${c.blocks.length} Bausteine${c.mandatory ? " · Pflicht" : ""}</small></button></div>${children.length ? `<div ${collapsed ? "hidden" : ""}>${branch(children)}</div>` : ""}</li>`;
    }).join("")}</ul>`;
  }
  $("chapter-tree").innerHTML = nodes.length ? branch(nodes) : '<p class="muted">Noch keine Kapitel.</p>';
  $("chapter-tree").querySelectorAll(".chapter-row").forEach(button => button.onclick = () => { selected = button.dataset.id; tree(); editor(); });
  $("chapter-tree").querySelectorAll("[data-toggle]").forEach(button => button.onclick = () => {
    const id = button.dataset.toggle; collapsedChapters.has(id) ? collapsedChapters.delete(id) : collapsedChapters.add(id); tree();
  });
  $("add-subchapter").disabled = !selectedChapter() || selectedChapter().level >= 6;
}
function openChapterDialog(subchapter) {
  if (current.chapters.length >= 500) return message("Die Gliederung enthält bereits 500 Kapitel.",true);
  $("new-chapter-title").value = ""; $("new-chapter-mandatory").checked = false;
  $("new-chapter-parent").innerHTML = '<option value="">Hauptebene</option>' + current.chapters.filter(c => c.level < 6).map(c => `<option value="${esc(c.id)}">${esc("— ".repeat(c.level-1) + c.title)}</option>`).join("");
  $("new-chapter-parent").value = subchapter ? selected || "" : "";
  $("chapter-dialog").showModal(); $("new-chapter-title").focus();
}
$("chapter-form").onsubmit = e => {
  e.preventDefault();
  const title = $("new-chapter-title").value.trim(); if (!title) return;
  const parent = current.chapters.find(c => c.id === $("new-chapter-parent").value);
  const id = uuid(), c = {id,lineage_id:id,title,level:parent ? parent.level+1 : 1,mandatory:$("new-chapter-mandatory").checked,domain:parent?.domain || "",goal:"",blocks:[]};
  const insert = parent ? subtreeEnd(current.chapters,current.chapters.indexOf(parent)) : current.chapters.length;
  current.chapters.splice(insert,0,c); selected = c.id;
  // Reveal the new node, including any previously collapsed ancestor.
  let level = c.level;
  for (let i=insert-1;i>=0;i--) if (current.chapters[i].level < level) { collapsedChapters.delete(current.chapters[i].id); level=current.chapters[i].level; }
  markDirty(); tree(); editor(); $("chapter-dialog").close(); $("chapter-title").focus();
};
$("cancel-chapter").onclick = () => $("chapter-dialog").close();
$("add-subchapter").onclick = () => openChapterDialog(true);
$("expand-tree").onclick = () => { current.chapters.forEach(c => collapsedChapters.delete(c.id)); tree(); };
$("collapse-tree").onclick = () => { current.chapters.forEach(c => collapsedChapters.add(c.id)); tree(); };

function clearComparison() { comparisonRequest++; comparisonData = null; $("compare-results").innerHTML = '<p class="muted">Auswahl geändert. Bitte den Vergleich aktualisieren.</p>'; }
async function loadRevisions(side, previous = false) {
  clearComparison();
  const request = ++revisionRequests[side], select = $(`compare-${side}-revision`);
  select.disabled = true; select.replaceChildren();
  const rows = await api("/api/history", {id:$(`compare-${side}`).value});
  if (request !== revisionRequests[side]) return;
  select.innerHTML = rows.map(r => `<option value="${r.revision}">V${esc(r.metadata.version)} · R${r.revision} · ${esc(formatDate(r.created))}</option>`).join("");
  if (previous && rows.length > 1) select.selectedIndex = 1;
  select.disabled = false;
}
async function openComparison(left, right, history = false) {
  if (!meta.outlines.length) return message("Lege zuerst eine Gliederung an.");
  const setup = ++comparisonSetup;
  $("message").hidden = true;
  previewRequest++; $("studio").hidden = true; $("overview").hidden = true; $("empty").hidden = true; $("comparison").hidden = false;
  $("compare-dirty").hidden = !dirty;
  for (const side of ["left","right"]) $(`compare-${side}`).innerHTML = meta.outlines.map(o => `<option value="${esc(o.id)}">${esc(o.title)} · V${esc(o.metadata.version)}</option>`).join("");
  $("compare-left").value = left || current?.id || meta.outlines[0].id;
  $("compare-right").value = right || meta.outlines.find(o => o.id !== $("compare-left").value)?.id || $("compare-left").value;
  await Promise.all([loadRevisions("left",history),loadRevisions("right")]);
  if (setup === comparisonSetup) await compareNow();
}
async function compareNow() {
  if ($("compare-left-revision").disabled || $("compare-right-revision").disabled) return;
  const request = ++comparisonRequest;
  const result = await api("/api/compare", {left_id:$("compare-left").value,right_id:$("compare-right").value,
    left_revision:Number($("compare-left-revision").value),right_revision:Number($("compare-right-revision").value)});
  if (request !== comparisonRequest) return;
  comparisonData = result; renderComparison();
}
function renderComparison() {
  if (!comparisonData) return;
  const data = comparisonData, only = $("differences-only").checked;
  const differs = node => node.flags.some(f => f !== "unchanged") || node.children.some(differs);
  function branch(nodes, side) {
    return `<ul class="comparison-tree">${nodes.filter(n => !only || differs(n)).map(n => {
      const label = `<button class="compare-node ${n.flags.map(f => "diff-"+f).join(" ")}" data-side="${side}" data-node="${esc(n.id)}" data-peer="${esc(n.peer_id || "")}"><span>${esc(n.number)} ${esc(n.title)}</span><span class="diff-badges">${n.flags.map(f => `<span class="diff-tag diff-${f}">${diffLabels[f]}</span>`).join("")}</span>${n.changed_fields.length ? `<small>${n.changed_fields.map(f => esc(fieldLabels[f])).join(", ")}</small>` : ""}${n.match_basis ? `<small>Zuordnung: ${esc(n.match_basis)}</small>` : ""}</button>`;
      return `<li>${n.children.length ? `<details open><summary>${label}</summary>${branch(n.children,side)}</details>` : label}</li>`;
    }).join("")}</ul>`;
  }
  const format = v => typeof v === "boolean" ? (v ? "Ja" : "Nein") : String(v || "—");
  $("compare-results").innerHTML = `<div class="diff-summary">${Object.entries(data.counts).map(([key,count]) => `<span class="diff-tag diff-${key}">${count} ${diffLabels[key]}</span>`).join("")}</div><p class="muted">Ein Kapitel kann mehrere Änderungsmerkmale haben. Ein Klick markiert sein Gegenstück.</p><details class="metadata-diff" ${data.metadata_changes.length ? "open" : ""}><summary>Metadaten & Ausgabeprofil: ${data.metadata_changes.length} Unterschiede</summary>${data.metadata_changes.length ? `<div class="table-scroll"><table><thead><tr><th>Feld</th><th>Links</th><th>Rechts</th></tr></thead><tbody>${data.metadata_changes.map(c => `<tr><td>${esc(fieldLabels[c.field] || c.field)}</td><td>${esc(format(c.left))}</td><td>${esc(format(c.right))}</td></tr>`).join("")}</tbody></table></div>` : '<p class="muted">Keine Unterschiede.</p>'}</details><div class="comparison-columns"><section><h2>${esc(data.left_label)}</h2>${branch(data.left,"left")}</section><section><h2>${esc(data.right_label)}</h2>${branch(data.right,"right")}</section></div>`;
  $("compare-results").querySelectorAll(".compare-node").forEach(button => button.onclick = e => {
    e.preventDefault(); e.stopPropagation();
    $("compare-results").querySelectorAll(".compare-node").forEach(node => node.classList.remove("matched-node"));
    button.classList.add("matched-node");
    const peer = [...$("compare-results").querySelectorAll(".compare-node")].find(node => node.dataset.side !== button.dataset.side && node.dataset.node === button.dataset.peer);
    if (peer) { peer.classList.add("matched-node"); for (let parent = peer.parentElement; parent; parent = parent.parentElement) if (parent.tagName === "DETAILS") parent.open = true; peer.scrollIntoView({block:"nearest",behavior:"smooth"}); }
  });
}
$("overview-button").onclick = openOverview;
for (const id of ["overview-search","overview-status","overview-role","overview-sort"]) $(id).oninput = renderOverview;
$("compare-selected").onclick = run(() => openComparison(...compareSelection));
$("compare-button").onclick = run(() => openComparison());
$("history-button").onclick = run(() => openComparison(current.id,current.id,true));
for (const side of ["left","right"]) {
  $(`compare-${side}`).onchange = run(() => loadRevisions(side));
  $(`compare-${side}-revision`).onchange = clearComparison;
}
$("run-compare").onclick = run(compareNow);
$("differences-only").onchange = renderComparison;
$("expand-compare").onclick = () => $("compare-results").querySelectorAll(".comparison-tree details").forEach(d => d.open = true);
$("collapse-compare").onclick = () => $("compare-results").querySelectorAll(".comparison-tree details").forEach(d => d.open = false);
