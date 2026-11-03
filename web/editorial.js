"use strict";
let reimportState = null;
const contentKinds = ["Anleitung","Ziel","Voraussetzung","Schritt","Warnhinweis","Hintergrund","Sonderfall","FAQ","Glossarbegriff"];
function renderChapterConfig(c) {
  c.config ||= {titles:{},kind:"Fachlich",inclusion:c.mandatory ? "Pflicht" : "Bedingt",selected:true,conditions:{},expected:[],empty_rule:c.mandatory ? "Blockieren" : "Auslassen",status:"Entwurf",generator:"Keiner"};
  const q = c.config;
  $("chapter-config").innerHTML = `<details class="chapter-settings"><summary>Kapitelregeln & Sprachtitel</summary><div class="config-grid">${selectField("Kapiteltyp","kind",["Redaktionell","Fachlich","Automatisch","Zusammengestellt"],q.kind)}${selectField("Aufnahmeregel","inclusion",["Pflicht","Bedingt","Manuell"],q.inclusion)}${selectField("Leerstellenregel","empty_rule",["Blockieren","Auslassen"],q.empty_rule)}${selectField("Kapitelstatus","status",["Entwurf","In Prüfung","Freigegeben"],q.status)}${selectField("Automatischer Inhalt","generator",["Keiner","Inhaltsverzeichnis","Glossar","FAQ"],q.generator)}<label class="check"><input type="checkbox" data-config="selected" ${q.selected ? "checked" : ""}>Manuell aufgenommen</label></div><p class="muted">Bedingungen gelten auch für Unterkapitel. Leere Felder gelten für alle. Pflicht gilt innerhalb dieser Bedingungen.</p><div class="config-grid">${["role","scope","market","division","language","release"].map(k => `<label>${esc(({role:"Rollen",scope:"Umfänge",market:"Märkte",division:"Sparten",language:"Sprachen",release:"Releases"})[k])} (Komma getrennt)<input data-condition="${k}" value="${esc((q.conditions[k] || []).join(", "))}"></label>`).join("")}</div><fieldset><legend>Erwartete Inhalte</legend>${["Text","Bild","Klickstrecke","FAQ"].map(v => `<label class="check"><input type="checkbox" data-expected="${v}" ${q.expected.includes(v) ? "checked" : ""}>${v}</label>`).join("")}</fieldset><div class="config-grid">${meta.languages.map(lang => `<label>Titel ${esc(lang)}<input data-language="${lang}" maxlength="300" value="${esc(q.titles[lang] || "")}" placeholder="Basistitel verwenden"></label>`).join("")}</div><button type="button" id="collect-library">Glossar / FAQ aus Bibliothek vorschlagen</button><p class="muted">Bild- und Klickstreckenvorgaben prüfen, ob eine passende freigegebene Medienzuordnung vorhanden ist.</p></details>`;
  $("collect-library").onclick = run(() => collectLibrary(c));
  $("chapter-config").querySelectorAll("[data-key]").forEach(el => el.onchange = () => { q[el.dataset.key] = el.value; c.mandatory = q.inclusion === "Pflicht"; $("mandatory").checked = c.mandatory; markDirty(); tree(); });
  $("chapter-config").querySelectorAll("[data-condition]").forEach(el => el.oninput = () => { q.conditions[el.dataset.condition] = el.value.split(",").map(v => v.trim()).filter(Boolean); markDirty(); });
  $("chapter-config").querySelectorAll("[data-language]").forEach(el => el.oninput = () => { q.titles[el.dataset.language] = el.value; markDirty(); });
  $("chapter-config").querySelectorAll("[data-expected]").forEach(el => el.onchange = () => { q.expected = [...$("chapter-config").querySelectorAll("[data-expected]:checked")].map(x => x.dataset.expected); markDirty(); });
  $("chapter-config").querySelector("[data-config]").onchange = e => { q.selected = e.target.checked; markDirty(); };
}
function renderBlockVariants(el,b) {
  b.variants ||= {};
  const panel = document.createElement("details"); panel.className = "chapter-settings";
  panel.innerHTML = `<summary>Inhaltstyp & Umfangsfassungen</summary>${selectField("Inhaltstyp","content_kind",contentKinds,b.content_kind || "Anleitung")}<p class="muted">Voraussetzungen, Schritte und Warnhinweise bleiben unabhängig vom Umfang erhalten. Eine leere Fassung verwendet den Basistext. Fassungen werden manuell geprüft.</p>${meta.scopes.map(scope => `<fieldset data-variant="${esc(scope)}"><legend>${esc(scope)}</legend><label>Textfassung<textarea rows="4">${esc(b.variants[scope]?.text || "")}</textarea></label><label>Prüfstatus<select>${options(["Entwurf","Freigegeben"],b.variants[scope]?.status || "Entwurf")}</select></label></fieldset>`).join("")}`;
  panel.querySelector("[data-key]").onchange = e => { b.content_kind = e.target.value; markDirty(); };
  panel.querySelectorAll("[data-variant]").forEach(row => row.oninput = () => { b.variants[row.dataset.variant] = {text:row.querySelector("textarea").value,status:row.querySelector("select").value}; markDirty(); });
  el.append(panel);
}
function resetReimport() {
  reimportState = null;
  $("reimport-review").replaceChildren();
  $("apply-import").textContent = $("import-target").value ? "Änderungen prüfen" : "Neue Gliederung übernehmen";
}
$("import-target").onchange = resetReimport;
async function reviewReimport() {
  const id = $("import-target").value;
  if (dirty && current?.id === id) throw new Error("Bitte die Zielgliederung zuerst speichern oder Änderungen verwerfen.");
  const target = meta.outlines.find(o => o.id === id);
  const payload = {id,revision:target.revision,chapters:importRows,decisions:reimportState?.decisions};
  if (reimportState?.ready) {
    if (dirty && !confirm("Ungespeicherte Änderungen der geöffneten Gliederung verwerfen?")) return;
    const saved = await api("/api/reimport", {...payload,apply:true});
    meta.outlines[meta.outlines.findIndex(o => o.id === id)] = structuredClone(saved);
    current = saved; selected = current.chapters[0]?.id; dirty = false;
    await refreshSourceIndex(); $("import-dialog").close(); render();
    return message("Import als neue Revision übernommen. Bestehende Inhalte und Chunk-Zuordnungen bleiben erhalten.");
  }
  const result = await api("/api/reimport",payload);
  reimportState = {decisions:result.decisions,ready:!result.unresolved.length};
  $("reimport-review").innerHTML = `<h3>Kapitelzuordnung prüfen</h3><p>Für neue oder umbenannte Kapitel ausdrücklich „Neu anlegen“ oder ein bestehendes Kapitel wählen. Jede bestehende Kennung ist nur einmal verwendbar.</p>${importRows.map(c => `<label>${esc(c.title)}<select data-import-id="${esc(c.id)}"><option value="">Bitte entscheiden</option><option value="new" ${result.decisions[c.id] === "new" ? "selected" : ""}>Neu anlegen</option>${target.chapters.map(old => `<option value="${esc(old.id)}" ${result.decisions[c.id] === old.id ? "selected" : ""}>${esc("— ".repeat(old.level-1)+old.title)} · ${esc(old.id.slice(0,8))}</option>`).join("")}</select></label>`).join("")}<p class="warning">${result.retained.length} bisherige Kapitel fehlen in der Zuordnung und bleiben am Ende erhalten: ${result.retained.map(c => esc(c.title)).join(", ") || "keine"}.</p><div class="diff-counts">${Object.entries(result.comparison.counts).map(([k,v]) => `<span>${esc(diffLabels[k])}: ${v}</span>`).join(" · ")}</div><div class="reimport-trees"><div><h4>Bisher</h4>${importDiffTree(result.comparison.left)}</div><div><h4>Nach Übernahme</h4>${importDiffTree(result.comparison.right)}</div></div>`;
  $("reimport-review").querySelectorAll("[data-import-id]").forEach(el => el.onchange = () => { reimportState.decisions[el.dataset.importId] = el.value; reimportState.ready = false; $("apply-import").textContent = "Vergleich aktualisieren"; });
  $("apply-import").textContent = reimportState.ready ? "Geprüfte Änderungen übernehmen" : "Zuordnungen erneut prüfen";
}
function importDiffTree(nodes) {
  return `<ul>${nodes.map(n => `<li><details open><summary>${esc(n.number)} ${esc(n.title)} <small>${n.flags.map(f => esc(diffLabels[f])).join(", ")}</small></summary>${n.children.length ? importDiffTree(n.children) : ""}</details></li>`).join("")}</ul>`;
}
$("release-outline").onclick = run(async () => {
  if (dirty) await save();
  if (dirty) throw new Error("Bitte aktuelle Änderungen zuerst speichern.");
  const saved = await api("/api/release", {id:current.id,revision:current.revision});
  meta.outlines[meta.outlines.findIndex(o => o.id === saved.id)] = structuredClone(saved); current = saved; render();
  message("Gliederung für das aktuelle Ausgabeprofil freigegeben. Weitere Änderungen beginnen eine neue Entwurfsrevision.");
});
$("usage-outline").onclick = run(async () => {
  const usage = await api("/api/usage", {id:current.id});
  $("usage-content").innerHTML = `<h3>Erzeugte Ausgaben (${usage.exports.length})</h3><p>Gespeicherte Dateien behalten ihren damaligen Stand. Ältere Ausgaben ohne Gliederungskennung sind hier nicht zugeordnet.</p>${usage.exports.map(e => `<article class="source-card"><b>R${e.revision} · ${esc(e.format.toUpperCase())} · ${e.draft ? "Prüfausgabe" : "Freigegeben"}</b><p>${esc(formatDate(e.created))} · ${esc(Object.values(e.profile).filter(v => typeof v === "string").join(" · "))}</p><button data-download="${esc(e.id)}" data-format="${esc(e.format)}">Originaldatei herunterladen</button><details><summary>Verwendungsnachweis / Inhaltsfingerabdrücke</summary><pre>${esc(JSON.stringify(e.manifest,null,2))}</pre></details></article>`).join("") || '<p>Noch keine zugeordneten Ausgaben.</p>'}<h3>Bestätigte Quellenzuordnungen (${usage.chunks.length})</h3><ul>${usage.chunks.map(c => `<li>${esc(current.chapters.find(x => x.id === c.chapter_id)?.title || c.chapter_id)} ← ${esc(c.source)} · ${esc(c.chunk_id.slice(0,8))}</li>`).join("")}</ul>`;
  $("usage-content").querySelectorAll("[data-download]").forEach(el => el.onclick = run(async () => {
    const response = await api("/api/export/history", {id:el.dataset.download});
    const url = URL.createObjectURL(await response.blob()), a = document.createElement("a");
    a.href=url; a.download=`oneSCM-${el.dataset.download}.${el.dataset.format}`; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
  }));
  $("usage-dialog").showModal();
});
$("close-usage").onclick = () => $("usage-dialog").close();

function renderScopeRules() {
  current.scope_rules ||= {Kompakt:[...contentKinds.slice(0,5),"Glossarbegriff"],Standard:[...contentKinds.slice(0,5),"FAQ","Glossarbegriff"],Ausführlich:[...contentKinds]};
  $("scope-rules").innerHTML=meta.scopes.map(scope=>`<fieldset><legend>${esc(scope)}</legend>${contentKinds.map(kind=>`<label class="check"><input type="checkbox" data-scope="${esc(scope)}" data-kind="${esc(kind)}" ${current.scope_rules[scope].includes(kind) || ["Voraussetzung","Schritt","Warnhinweis"].includes(kind) ? "checked" : ""} ${["Voraussetzung","Schritt","Warnhinweis"].includes(kind) ? "disabled" : ""}>${esc(kind)}</label>`).join("")}</fieldset>`).join("");
  $("scope-rules").querySelectorAll("input").forEach(el=>el.onchange=()=>{current.scope_rules[el.dataset.scope]=[...$("scope-rules").querySelectorAll("input:checked")].filter(x=>x.dataset.scope===el.dataset.scope).map(x=>x.dataset.kind);markDirty();});
}
