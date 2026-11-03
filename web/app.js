"use strict";
const $ = (id) => document.getElementById(id);
let meta, current = null, selected = null, dirty = false, importRows = null, previewRequest = 0;
const uuid = () => crypto.randomUUID();
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
function message(text, error = false) { $("message").textContent = text; $("message").hidden = false; $("message").className = error ? "error" : ""; }
async function api(path, data) {
  const response = await fetch(path, {method:"POST", headers:{"Content-Type":"application/json", "X-Local-Token":meta.token}, body:JSON.stringify(data)});
  if (!response.ok) { const result = await response.json(); throw new Error(result.error); }
  return path === "/api/export" ? response : response.json();
}
function run(fn) { return async (...args) => { try { await fn(...args); } catch (e) { message(e.message, true); } }; }
function markDirty() { dirty = true; saveState(); }
function saveState() { $("save-state").textContent = `Revision ${current.revision} · ${dirty ? "Ungespeicherte Änderungen" : "Lokal gespeichert"}`; }
function options(values, value, all = false) {
  return (all ? ["*", ...values] : values).map(v => `<option value="${esc(v)}" ${v === value ? "selected" : ""}>${esc(v === "*" ? "Alle" : v)}</option>`).join("");
}
function selectField(label, key, values, value, attrs = "", all = false) {
  return `<label>${esc(label)}<select data-key="${key}" ${attrs}>${options(values,value,all)}</select></label>`;
}
function inputField(label, key, value, attrs = "") {
  return `<label>${esc(label)}<input data-key="${key}" value="${esc(value)}" ${attrs}></label>`;
}
function list() {
  $("outline-list").innerHTML = meta.outlines.map(o => `<button class="outline-item ${current?.id === o.id ? "selected" : ""}" data-id="${esc(o.id)}">${esc(o.title)}<small>${o.chapters.length} Kapitel · Revision ${o.revision}</small></button>`).join("");
  $("outline-list").querySelectorAll("button").forEach(b => b.onclick = () => {
    if (dirty && !confirm("Ungespeicherte Änderungen verwerfen?")) return;
    current = structuredClone(meta.outlines.find(o => o.id === b.dataset.id));
    selected = current.chapters[0]?.id; dirty = false; render();
  });
}
function render() {
  list(); $("empty").hidden = !!current; $("studio").hidden = !current;
  if (!current) return;
  $("outline-title").value = current.title; saveState(); renderProfile(); tree(); editor(); showTab(false);
}
function renderProfile() {
  const p = current.profile;
  $("profile").innerHTML = selectField("Rolle", "role", meta.roles, p.role) + selectField("Umfang", "scope", meta.scopes, p.scope) + inputField("Markt", "market", p.market, 'placeholder="Noch offen" maxlength="100"') + selectField("Sparte", "division", ["Van","PC","Beide"], p.division) + selectField("Sprache", "language", meta.languages, p.language) + inputField("Release", "release", p.release, 'placeholder="Noch offen" maxlength="100"') + `<div class="muted">SK / KO sind vorläufig vorgesehen.</div><label class="check"><input type="checkbox" data-key="approved_only" ${p.approved_only ? "checked" : ""}>Nur freigegebene Bausteine</label><label class="check"><input type="checkbox" data-key="show_notes" ${p.show_notes ? "checked" : ""}>Interne Vermerke (HQ / intern)</label>`;
  $("profile").querySelectorAll("[data-key]").forEach(el => el.onchange = run(async () => {
    p[el.dataset.key] = el.type === "checkbox" ? el.checked : el.value; markDirty();
    if (!$("preview").hidden) await preview();
  }));
}
function tree() {
  const counts = [0,0,0,0,0,0];
  $("chapter-tree").innerHTML = current.chapters.map(c => {
    counts[c.level-1]++; counts.fill(0,c.level);
    return `<button class="chapter-row ${c.id === selected ? "selected" : ""}" data-id="${esc(c.id)}">${esc(counts.slice(0,c.level).join("."))} ${esc(c.title)}<small>Ebene ${c.level} · ${c.blocks.length} Bausteine${c.mandatory ? " · Pflicht" : ""}</small></button>`;
  }).join("") || '<p class="muted">Noch keine Kapitel.</p>';
  $("chapter-tree").querySelectorAll("button").forEach(b => b.onclick = () => { selected = b.dataset.id; tree(); editor(); });
}
function selectedChapter() { return current.chapters.find(c => c.id === selected); }
function editor() {
  const c = selectedChapter();
  if (!c) { $("chapter-editor").innerHTML = '<p class="muted">Wähle ein Kapitel oder lege ein neues an.</p>'; return; }
  $("chapter-editor").innerHTML = `<div class="eyebrow">KAPITEL BEARBEITEN</div><label>Titel<input id="chapter-title" value="${esc(c.title)}" maxlength="300"></label><div class="form-grid">${selectField("Domäne", "domain", ["",...meta.domains], c.domain)}<label class="check"><input id="mandatory" type="checkbox" ${c.mandatory ? "checked" : ""}>Pflichtkapitel</label></div><label>Kapitelziel<textarea id="chapter-goal" rows="2">${esc(c.goal)}</textarea></label><div class="chapter-controls"><button data-action="up">↑ Nach oben</button><button data-action="down">↓ Nach unten</button><button data-action="out">← Höhere Ebene</button><button data-action="in">→ Unterkapitel</button><button data-action="delete" class="danger">Entfernen</button></div><div class="panel-heading"><h3>Textbausteine</h3><span class="muted">„*“ = alle · leer = ungeklärt</span></div><div id="blocks"></div><button id="add-block" class="full">+ Textbaustein zuordnen</button>`;
  $("chapter-title").oninput = e => { c.title = e.target.value; markDirty(); tree(); };
  $("chapter-goal").oninput = e => { c.goal = e.target.value; markDirty(); };
  $("mandatory").onchange = e => { c.mandatory = e.target.checked; markDirty(); tree(); };
  $("chapter-editor").querySelector('[data-key="domain"]').onchange = e => { c.domain = e.target.value; markDirty(); };
  $("chapter-editor").querySelectorAll("[data-action]").forEach(b => b.onclick = () => chapterAction(b.dataset.action));
  $("blocks").innerHTML = c.blocks.map((b,i) => `<article class="block" data-id="${esc(b.id)}"><div class="block-top"><strong>Baustein ${i+1}</strong><button class="remove-block danger">Entfernen</button></div><label>Text<textarea data-key="text" rows="6">${esc(b.text)}</textarea></label><div class="block-filters">${selectField("Rolle","role",meta.roles,b.role,"",true)}${selectField("Umfang","scope",meta.scopes,b.scope,"",true)}${selectField("Sparte","division",["Van","PC"],b.division,"",true)}${inputField("Markt (* = alle)","market",b.market,'maxlength="100"')}${inputField("Release (* = alle)","release",b.release,'maxlength="100"')}${selectField("Sprache","language",meta.languages,b.language)}${selectField("Status","status",["Entwurf","Freigegeben"],b.status)}</div><label class="check"><input type="checkbox" data-key="internal" ${b.internal ? "checked" : ""}>Interner Inhalt: nur für HQ und intern</label>${inputField("Quelle oder redaktionelle Herkunft","source",b.source)}<label>Interner Vermerk<textarea data-key="note" rows="2">${esc(b.note)}</textarea></label></article>`).join("");
  $("blocks").querySelectorAll(".block").forEach(el => {
    const b = c.blocks.find(x => x.id === el.dataset.id);
    el.querySelectorAll("[data-key]").forEach(field => field.oninput = () => { b[field.dataset.key] = field.type === "checkbox" ? field.checked : field.value; markDirty(); });
    el.querySelector(".remove-block").onclick = () => { if (!confirm("Diesen Baustein aus dem Kapitel entfernen?")) return; c.blocks = c.blocks.filter(x => x.id !== b.id); markDirty(); tree(); editor(); };
  });
  $("add-block").onclick = () => { c.blocks.push({id:uuid(),text:"",source:"",note:"",role:"*",scope:"*",market:"*",division:"*",language:current.profile.language,release:"*",status:"Entwurf",internal:false}); markDirty(); tree(); editor(); };
}
function subtreeEnd(items, start) { let end = start+1; while (end < items.length && items[end].level > items[start].level) end++; return end; }
function chapterAction(action) {
  const a = current.chapters, i = a.findIndex(c => c.id === selected), c = a[i], end = subtreeEnd(a,i);
  if (action === "delete") {
    if (!confirm(`„${c.title}“ mit ${end-i-1} Unterkapiteln und allen zugeordneten Inhalten entfernen?`)) return;
    a.splice(i,end-i); selected = a[Math.min(i,a.length-1)]?.id;
  } else if (action === "up") {
    let previous = i-1;
    while (previous >= 0 && a[previous].level > c.level) previous--;
    if (previous < 0 || a[previous].level !== c.level) return message("Kein vorheriges Kapitel auf derselben Ebene.");
    const part = a.splice(i,end-i); a.splice(previous,0,...part);
  } else if (action === "down") {
    if (end >= a.length || a[end].level !== c.level) return message("Kein folgendes Kapitel auf derselben Ebene.");
    const nextEnd = subtreeEnd(a,end), next = a.splice(end,nextEnd-end); a.splice(i,0,...next);
  } else if (action === "in") {
    if (i === 0 || c.level > a[i-1].level || a.slice(i,end).some(x => x.level === 6)) return message("An dieser Position kann das Kapitel nicht weiter eingerückt werden.");
    a.slice(i,end).forEach(x => x.level++);
  } else if (action === "out") {
    if (c.level === 1) return;
    if (end < a.length && a[end].level === c.level) return message("Zuerst ans Ende der Unterkapitel verschieben, damit nachfolgende Kapitel ihre Zuordnung behalten.");
    a.slice(i,end).forEach(x => x.level--);
  }
  markDirty(); tree(); editor();
}
async function save() {
  const snapshot = structuredClone(current);
  const saved = await api("/api/save", snapshot);
  const i = meta.outlines.findIndex(o => o.id === saved.id);
  if (i < 0) meta.outlines.push(saved); else meta.outlines[i] = saved;
  if (current.id === saved.id) {
    dirty = JSON.stringify(current) !== JSON.stringify(snapshot);
    current.revision = saved.revision;
    saveState();
  }
  list(); return saved;
}
function showTab(isPreview) { $("editing").hidden = isPreview; $("preview").hidden = !isPreview; $("edit-tab").classList.toggle("active",!isPreview); $("preview-tab").classList.toggle("active",isPreview); }
async function preview() {
  const request = ++previewRequest;
  const plan = await api("/api/compose", {outline:current});
  if (request !== previewRequest) return;
  const notes = plan.warnings.map(w => `<div class="warning">${esc(w)}</div>`).join("");
  const content = plan.chapters.map(c => {
    const head = c.visible ? `<h${Math.min(c.level+1,6)}>${esc(c.number)} ${esc(c.title)}</h${Math.min(c.level+1,6)}>` : `<p class="muted">Ausgelassen: ${esc(c.title)}</p>`;
    return head + (c.visible && c.mandatory && !c.blocks.length ? '<p class="placeholder">[Inhalt ergänzen]</p>' : "") + c.blocks.map(b => `${plan.profile.division === "Beide" && b.division !== "*" ? `<small>Gilt für: ${esc(b.division)}</small>` : ""}<p>${esc(b.text)}</p>${b.note ? `<p class="internal-note">Interner Vermerk: ${esc(b.note)}</p>` : ""}`).join("") + (c.excluded.length ? `<details class="excluded"><summary>${c.excluded.length} Baustein(e) ausgeschlossen</summary><ul>${c.excluded.map(b => `<li>${esc(b.reason)}</li>`).join("")}</ul></details>` : "");
  }).join("");
  $("preview").innerHTML = `<div class="preview-paper"><div class="draft-label">PRÜFAUSGABE · ${dirty ? "UNGESPEICHERTE VORSCHAU" : `REVISION ${plan.revision}`}</div><h1>${esc(plan.title)}</h1><p class="muted">${esc(plan.profile.role)} · ${esc(plan.profile.scope)} · ${esc(plan.profile.division)} · ${esc(plan.profile.language.toUpperCase())}</p>${notes}${content}</div>`;
  showTab(true);
}
async function exportFile(format) {
  if (dirty) await save();
  if (dirty) throw new Error("Während des Speicherns wurden Inhalte geändert. Bitte erneut exportieren.");
  const response = await api("/api/export", {id:current.id,revision:current.revision,format});
  const blob = await response.blob(), link = document.createElement("a");
  const url = URL.createObjectURL(blob); link.href = url; link.download = `oneSCM-Pruefausgabe-R${current.revision}.${format}`;
  document.body.append(link); link.click(); link.remove(); setTimeout(() => URL.revokeObjectURL(url),1000);
  message("Prüfausgabe erzeugt. Dateistand und Auswahl wurden lokal festgehalten.");
}
function refreshImportPreview(warnings = []) {
  $("import-preview").innerHTML = warnings.map(w => `<div class="warning">${esc(w)}</div>`).join("") + `<h3>${importRows.length} Kapitel erkannt</h3>` + importRows.map((c,i) => `<div class="import-row"><select aria-label="Ebene für Kapitel ${i+1}" data-index="${i}" data-field="level">${[1,2,3,4,5,6].map(n => `<option value="${n}" ${n===c.level ? "selected" : ""}>Ebene ${n}</option>`).join("")}</select><input aria-label="Titel für Kapitel ${i+1}" value="${esc(c.title)}" data-index="${i}" data-field="title" maxlength="300"></div>`).join("");
  $("import-preview").querySelectorAll("[data-index]").forEach(el => el.oninput = () => { importRows[Number(el.dataset.index)][el.dataset.field] = el.dataset.field === "level" ? Number(el.value) : el.value; });
  $("apply-import").disabled = false;
}
function invalidateImport() { importRows = null; $("import-preview").replaceChildren(); $("apply-import").disabled = true; }

$("outline-title").oninput = e => { current.title = e.target.value; markDirty(); };
$("new-outline").onclick = run(async () => {
  if (dirty && !confirm("Ungespeicherte Änderungen verwerfen?")) return;
  const title = prompt("Name der neuen Gliederung", "Neues Handbuch"); if (!title?.trim()) return;
  current = await api("/api/create", {title}); meta.outlines.push(current); selected = current.chapters[0].id; dirty = false; render();
});
$("copy-outline").onclick = run(async () => {
  if (dirty) await save();
  const copy = structuredClone(current); copy.id = uuid(); copy.title += " – Kopie"; copy.revision = 0;
  copy.chapters.forEach(c => { c.id = uuid(); c.blocks.forEach(b => b.id = uuid()); });
  current = await api("/api/save",copy); meta.outlines.push(current); selected = current.chapters[0]?.id; dirty = false; render();
});
$("save").onclick = run(async () => { await save(); message("Gliederung gespeichert."); });
$("add-chapter").onclick = () => { const c = {id:uuid(),title:"Neues Kapitel",level:1,mandatory:false,domain:"",goal:"",blocks:[]}; current.chapters.push(c); selected = c.id; markDirty(); tree(); editor(); };
$("preview-tab").onclick = run(preview); $("edit-tab").onclick = () => { previewRequest++; showTab(false); };
$("export-docx").onclick = run(() => exportFile("docx")); $("export-pptx").onclick = run(() => exportFile("pptx"));
$("import-outline").onclick = () => { invalidateImport(); $("import-dialog").showModal(); };
$("cancel-import").onclick = () => $("import-dialog").close();
$("import-text").oninput = () => { $("import-file").value = ""; invalidateImport(); };
$("import-file").onchange = () => { $("import-text").value = ""; invalidateImport(); };
$("import-form").onsubmit = run(async e => {
  e.preventDefault(); let payload = {text:$("import-text").value};
  const file = $("import-file").files[0];
  if (file) {
    if (file.size > 5*1024*1024) throw new Error("Bitte eine Datei mit höchstens 5 MB wählen.");
    if (file.name.toLowerCase().endsWith(".docx")) {
      const bytes = new Uint8Array(await file.arrayBuffer()); let binary = "";
      for (let i=0;i<bytes.length;i+=8192) binary += String.fromCharCode(...bytes.subarray(i,i+8192));
      payload = {filename:file.name,base64:btoa(binary)};
    } else if (/\.(md|txt)$/i.test(file.name)) payload = {text:await file.text()};
    else throw new Error("Unterstützt werden TXT, Markdown und DOCX.");
  }
  const result = await api("/api/import",payload); importRows = result.chapters; refreshImportPreview(result.warnings);
});
$("apply-import").onclick = run(async () => {
  if (!importRows) return;
  if (dirty && !confirm("Ungespeicherte Änderungen der aktuellen Gliederung verwerfen?")) return;
  const outline = {id:uuid(),title:$("import-title").value,revision:0,profile:{role:"Retailer",scope:"Standard",market:"",division:"Van",language:"de",release:"",approved_only:false,show_notes:false},chapters:importRows};
  current = await api("/api/save",outline); meta.outlines.push(current); selected = current.chapters[0]?.id; dirty = false;
  $("import-dialog").close(); render(); message("Gliederung importiert. Bitte Pflichtkapitel und Struktur prüfen.");
});
window.addEventListener("beforeunload",e => { if (dirty) { e.preventDefault(); e.returnValue = ""; } });
run(async () => { const response = await fetch("/api/state"); if (!response.ok) throw new Error("Lokale Anwendung nicht erreichbar."); meta = await response.json(); list(); })();
