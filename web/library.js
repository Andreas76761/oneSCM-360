"use strict";
let libraryEntries = [], libraryEdit = null;
const assignmentLabels = {role:"Rolle",scope:"Umfang",market:"Markt",division:"Sparte",release:"Release",language:"Sprache"};
function renderLibraryLink(el,b,c) {
  const panel = document.createElement("section"); panel.className="library-link";
  if (b.library_ref) {
    el.querySelectorAll("input,select,textarea").forEach(input => input.disabled = true);
    panel.innerHTML = `<p>Zentraler Baustein · R${b.library_ref.revision} · ${esc(b.library_ref.id.slice(0,8))}. Änderungen erfolgen in der Bibliothek.</p><button class="library-update">Neueste Revision prüfen</button>`;
    panel.querySelector("button").onclick = run(async () => {
      const rows = await api("/api/library", {}), latest = rows.find(x => x.id === b.library_ref.id);
      if (!latest || latest.archived) throw new Error("Baustein ist archiviert oder nicht vorhanden.");
      if (latest.revision === b.library_ref.revision) return message("Diese Verwendung ist bereits aktuell.");
      if (!confirm(`R${b.library_ref.revision} durch R${latest.revision} ersetzen?\n\nBisher: ${b.text.slice(0,500)}\n\nNeu: ${latest.block.text.slice(0,500)}\n\nAuch Rollen, Sprachen und Gültigkeit der neuen Revision werden übernommen. Danach Ausgabe erneut prüfen.`)) return;
      const updated = structuredClone(latest.block);
      Object.assign(updated,{id:b.id,library_ref:{id:latest.id,revision:latest.revision},assignment:b.assignment});
      c.blocks[c.blocks.indexOf(b)] = updated; c.config.status="Entwurf"; markDirty(); editor();
    });
  } else {
    panel.innerHTML = '<button class="promote-block">In zentraler Bibliothek speichern</button>';
    panel.querySelector("button").onclick = () => editLibraryEntry(null,b);
  }
  b.assignment ||= {conditions:{},note:""};
  panel.insertAdjacentHTML("beforeend", `<div class="actions"><button data-position="-1">↑ Baustein</button><button data-position="1">↓ Baustein</button></div><details><summary>Gültigkeit dieser Zuordnung weiter einschränken</summary><p class="muted">Leere Felder bedeuten keine zusätzliche Einschränkung. Die Regeln des ursprünglichen Bausteins bleiben immer wirksam.</p><div class="config-grid">${Object.entries(assignmentLabels).map(([k,label]) => `<label>${label} (Komma getrennt)<input data-restrict="${k}" value="${esc((b.assignment.conditions[k] || []).join(", "))}"></label>`).join("")}</div><label>Interner Zuordnungsvermerk<textarea class="assignment-note" rows="2">${esc(b.assignment.note)}</textarea></label></details>`);
  panel.querySelectorAll("[data-restrict]").forEach(input => input.oninput = () => { b.assignment.conditions[input.dataset.restrict] = input.value.split(",").map(v => v.trim()).filter(Boolean); markDirty(); });
  panel.querySelector(".assignment-note").oninput = e => { b.assignment.note = e.target.value; markDirty(); };
  panel.querySelectorAll("[data-position]").forEach(button => button.onclick = () => {
    const from=c.blocks.indexOf(b), to=from+Number(button.dataset.position); if (to < 0 || to >= c.blocks.length) return;
    c.blocks.splice(from,1); c.blocks.splice(to,0,b); markDirty(); editor();
  });
  el.append(panel);
}
async function openLibrary() {
  libraryEntries = await api("/api/library", {});
  $("library-chapter").innerHTML = current.chapters.map(c => `<option value="${esc(c.id)}">${esc("— ".repeat(c.level-1) + c.title)}</option>`).join("");
  $("library-chapter").value = selected || current.chapters[0]?.id || "";
  $("library-filters").innerHTML = '<label>Stichwort / Text<input data-filter="query"></label>' + selectField("Domäne","domain",["",...allTargets().map(d=>d.id)],"") + ["role","scope","market","division","release","language","status"].map(k => inputField(assignmentLabels[k] || (k === "status" ? "Status" : "Umfang"),k,"",'data-filter="'+k+'"')).join("");
  $("library-filters").querySelector('[data-key="domain"]').innerHTML = '<option value="">Alle Domänen</option>' + allTargets().map(d=>`<option value="${esc(d.id)}">${esc(d.name)}</option>`).join("");
  $("library-filters").querySelectorAll("input,select").forEach(input=> input.oninput=renderLibraryList);
  renderLibraryList(); $("library-dialog").showModal();
}
function renderLibraryList() {
  const filters={}; $("library-filters").querySelectorAll("input,select").forEach(el=>filters[el.dataset.filter || el.dataset.key]=el.value.trim().toLocaleLowerCase());
  const entries=libraryEntries.filter(e=> Object.entries(filters).every(([k,v])=>!v || (k === "query" ? [e.title,e.tags,e.block.text].join(" ").toLocaleLowerCase().includes(v) : k === "domain" ? e.domains.includes(v) : ["*",v].includes(String(e.block[k]).toLocaleLowerCase()))));
  $("library-list").innerHTML = entries.map(e=>`<article class="source-card"><h3>${esc(e.title)} · R${e.revision}${e.archived ? " · Archiviert" : ""}</h3><p>${esc(e.block.role)} · ${esc(e.block.scope)} · ${esc(e.block.language)} · ${esc(e.block.status)}</p><p>${esc(e.block.text.slice(0,300))}</p><button data-assign="${esc(e.id)}" ${e.archived || !current.chapters.length ? "disabled" : ""}>Dem Kapitel zuordnen</button><button data-library-edit="${esc(e.id)}">Zentral bearbeiten</button><button data-translate-entry="${esc(e.id)}">Sprachfassung anlegen</button>${e.translation_stale ? '<p class="warning">Ausgangsbaustein wurde geändert: Übersetzung auf Aktualität prüfen.</p>' : ""}<details><summary>${e.usage.length} Verwendungen</summary><ul>${e.usage.map(u=>`<li>${esc(u.outline)} → ${esc(u.chapter)} · R${u.revision}</li>`).join("")}</ul></details></article>`).join("") || '<p>Keine passenden Bausteine.</p>';
  $("library-list").querySelectorAll("[data-translate-entry]").forEach(el=>el.onclick=()=>startTranslation(libraryEntries.find(e=>e.id===el.dataset.translateEntry)));
  $("library-list").querySelectorAll("[data-library-edit]").forEach(el=>el.onclick=()=>editLibraryEntry(libraryEntries.find(e=>e.id===el.dataset.libraryEdit)));
  $("library-list").querySelectorAll("[data-assign]").forEach(el=>el.onclick=()=>{
    const entry=libraryEntries.find(e=>e.id===el.dataset.assign), c=current.chapters.find(c=>c.id===$("library-chapter").value);
    if (!c) return;
    if(c.blocks.length>=100) return message("Maximal 100 Bausteine je Kapitel.",true);
    c.blocks.push({...structuredClone(entry.block),id:uuid(),library_ref:{id:entry.id,revision:entry.revision},assignment:{conditions:{},note:""}});
    if (c.config) c.config.status="Entwurf";
    selected=c.id; markDirty(); $("library-dialog").close(); tree(); editor(); message("Zentrale Bausteinrevision zugeordnet. Gliederung speichern und Ausgabe prüfen.");
  });
}
function editLibraryEntry(entry, block) {
  libraryEdit=entry ? structuredClone(entry) : {id:uuid(),revision:0,title:"",tags:"",domains:[],archived:false,block:structuredClone(block || {id:uuid(),text:"",source:"",note:"",role:"*",scope:"*",market:"*",division:"*",language:current.profile.language,release:"*",status:"Entwurf",internal:false})};
  const b=libraryEdit.block;
  $("library-title").value=libraryEdit.title; $("library-tags").value=libraryEdit.tags; $("library-text").value=b.text;
  $("library-mandatory-term").checked=!!libraryEdit.mandatory_term; $("library-internal").checked=b.internal; $("library-archived").checked=libraryEdit.archived;
  $("library-domains").innerHTML=allTargets().map(d=>`<option value="${esc(d.id)}" ${libraryEdit.domains.includes(d.id)?"selected":""}>${esc(d.name)}</option>`).join("");
  $("library-block-fields").innerHTML=selectField("Rolle","role",meta.roles,b.role,"",true)+selectField("Umfang","scope",meta.scopes,b.scope,"",true)+selectField("Sparte","division",["Van","PC"],b.division,"",true)+inputField("Markt","market",b.market)+inputField("Release","release",b.release)+selectField("Sprache","language",meta.languages,b.language)+selectField("Status","status",["Entwurf","Freigegeben"],b.status)+inputField("Quelle","source",b.source);
  $("library-variants").replaceChildren(); renderBlockVariants($("library-variants"),b);
  // This form edits the library independently of unsaved outline changes.
  $("library-variants").querySelector("[data-key]").onchange=e=>b.content_kind=e.target.value;
  $("library-variants").querySelectorAll("[data-variant]").forEach(row=>row.oninput=()=>{b.variants[row.dataset.variant]={text:row.querySelector("textarea").value,status:row.querySelector("select").value};});
  renderLanguageTools();
  $("library-edit-dialog").showModal();
}
$("library-edit-form").onsubmit=run(async e=>{
  e.preventDefault(); const b=libraryEdit.block;
  libraryEdit.mandatory_term=$("library-mandatory-term").checked; libraryEdit.title=$("library-title").value; libraryEdit.tags=$("library-tags").value;
  libraryEdit.domains=[...$("library-domains").selectedOptions].map(o=>o.value); libraryEdit.archived=$("library-archived").checked;
  if(libraryEdit.translation) libraryEdit.translation.reviewed=$("translation-reviewed").checked;
  b.text=$("library-text").value; b.internal=$("library-internal").checked;
  $("library-block-fields").querySelectorAll("[data-key]").forEach(el=>b[el.dataset.key]=el.value);
  await api("/api/library/save",libraryEdit); $("library-edit-dialog").close(); libraryEntries=await api("/api/library",{});
  if($("library-dialog").open) renderLibraryList(); message("Neue Bausteinrevision zentral gespeichert. Kapitelverwendungen behalten ihre bisherige Fassung.");
});
$("assign-content").onclick=run(openLibrary);
$("library-close").onclick=()=>$("library-dialog").close();
$("library-new").onclick=()=>editLibraryEntry();
$("library-edit-cancel").onclick=()=>$("library-edit-dialog").close();

async function collectLibrary(c) {
  const proposal=await api("/api/library/collect", {outline:current,chapter_id:c.id});
  if(!proposal.blocks.length) return message("Keine zusätzlichen passenden Einträge. Domänen, Ausgabeprofil, Umfangsregeln und zentrale Einträge prüfen.");
  if(!confirm(`${proposal.blocks.length} passende ${proposal.kind}-Einträge ergänzen?\n\n${proposal.blocks.map(b=>b.library_title+" · R"+b.library_ref.revision).join("\n")}\n\nVorhandene Texte bleiben unverändert. Neue Einträge werden als feste Revisionen übernommen.`)) return;
  c.blocks.push(...proposal.blocks); c.config.status="Entwurf"; markDirty(); tree(); editor(); message("Zusammenstellung übernommen. Vorschau prüfen und Gliederung speichern.");
}

function startTranslation(entry) {
  editLibraryEntry(entry);
  const source=structuredClone(entry);
  libraryEdit.id=uuid(); libraryEdit.revision=0;libraryEdit.usage=[];
  libraryEdit.translation={source_id:source.id,source_revision:source.revision,source_language:source.block.language,target_language:source.block.language==="en"?"de":"en",method:"Manuell",reviewed:false};
  libraryEdit.block.id=uuid();libraryEdit.block.text="";libraryEdit.block.status="Entwurf";libraryEdit.block.variants={};libraryEdit.block.language=libraryEdit.translation.target_language;
  $("library-text").value="";document.querySelector("#library-block-fields [data-key=language]").value=libraryEdit.block.language;document.querySelector("#library-block-fields [data-key=status]").value="Entwurf";
  $("library-variants").replaceChildren();renderBlockVariants($("library-variants"),libraryEdit.block);
  $("library-variants").querySelector("[data-key]").onchange=e=>libraryEdit.block.content_kind=e.target.value;
  $("library-variants").querySelectorAll("[data-variant]").forEach(row=>row.oninput=()=>{libraryEdit.block.variants[row.dataset.variant]={text:row.querySelector("textarea").value,status:row.querySelector("select").value};});
  renderLanguageTools(source);
}
function renderLanguageTools(source) {
  const translation=libraryEdit.translation;
  $("translation-review-label").hidden=!translation;$("translation-reviewed").checked=!!translation?.reviewed;
  $("translation-origin").textContent=translation?`Ausgangsrevision R${translation.source_revision} · ${translation.source_language} → Zielsprache · ${translation.method}`:"";
  const ref=translation?{id:translation.source_id,revision:translation.source_revision}:{id:libraryEdit.id,revision:libraryEdit.revision};
  $("library-language-tools").innerHTML=`<details><summary>Optionaler KI-Vorschlag (lokales Ollama)</summary><p class="muted">Ein lokal installiertes Modell ist erforderlich. Vorschläge bleiben Entwurf und müssen geprüft werden. Es werden Titel und Basistext gesendet, keine internen Vermerke.</p>${source?`<details><summary>Ausgangstext R${source.revision}</summary><p class="chunk-text">${esc(source.block.text)}</p></details>`:""}<label>Installiertes Modell<input id="language-model" maxlength="150"></label><label>Zielumfang für Kurzfassung<select id="language-scope">${options(meta.scopes,"Kompakt")}</select></label>${translation?'<button type="button" id="generate-translation">Übersetzung vorschlagen</button>':''}<button type="button" id="generate-short" ${!libraryEdit.revision?"disabled":""}>Umfangsfassung vorschlagen</button><p id="language-progress" role="status"></p></details>`;
  async function generate(mode) {
    const id=libraryEdit.id,target=mode==="translate"?document.querySelector("#library-block-fields [data-key=language]").value:$("language-scope").value;
    if(mode==="translate"&&target===translation.source_language)throw new Error("Eine andere Zielsprache wählen.");
    $("language-progress").textContent="Lokales Modell erstellt Vorschlag …";
    const result=await api("/api/library/language",{...ref,mode,target,model:$("language-model").value});
    if(libraryEdit.id!==id)return;
    if(!confirm("KI-Vorschlag in das Bearbeitungsformular übernehmen? Die aktuelle Eingabe in dieser Fassung wird ersetzt; gespeichert wird erst über Bausteinrevision speichern."))return;
    if(mode==="translate") {$("library-title").value=result.title;$("library-text").value=result.text;libraryEdit.translation.method=result.method;libraryEdit.translation.reviewed=false;$("translation-reviewed").checked=false;document.querySelector("#library-block-fields [data-key=status]").value="Entwurf";}
    else {libraryEdit.block.variants[target]={text:result.text,status:"Entwurf"};const row=[...$("library-variants").querySelectorAll("[data-variant]")].find(x=>x.dataset.variant===target);row.querySelector("textarea").value=result.text;row.querySelector("select").value="Entwurf";}
    $("language-progress").textContent=`Ungeprüfter Vorschlag aus R${result.source_revision}. Inhalt, Fachbegriffe, Voraussetzungen und Schritte prüfen.`;
  }
  if($("generate-translation"))$("generate-translation").onclick=run(()=>generate("translate"));
  $("generate-short").onclick=run(()=>generate("shorten"));
  $("library-text").oninput=()=>{if(libraryEdit.translation)$("translation-reviewed").checked=false;};
}
