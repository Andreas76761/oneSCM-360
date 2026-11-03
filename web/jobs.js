"use strict";
const agentNames={triage:"Wissensagent",structure:"Gliederungsagent",media:"Bildagent",translation:"Übersetzungsagent (KI)",quality:"Qualitätsagent",finalization:"Finalisierung",validation:"Validierung",layout:"Layout",documentation:"Dokumentation"};
let activeJob=null,jobLoop=false,jobRequestActive=false;
async function openJobs(){
  const sources=await api("/api/sources",{});
  $("job-outline").innerHTML=meta.outlines.map(o=>`<option value="${esc(o.id)}">${esc(o.title)} · R${o.revision}</option>`).join("");if(current)$("job-outline").value=current.id;
  $("job-sources").innerHTML=sources.sources.map(s=>`<option value="${esc(s.id)}">${esc(s.name)} · ${s.chunks} Chunks</option>`).join("");
  $("job-source-language").innerHTML=options(meta.languages,"de");$("job-target-language").innerHTML=options(meta.languages,"en");
  $("job-agents").innerHTML=Object.entries(agentNames).map(([k,v])=>`<label class="check"><input type="checkbox" data-agent="${k}" ${["finalization","validation","layout","documentation"].includes(k)?"checked":""}>${esc(v)}</label>`).join("");
  $("job-preset").value="final";
  $("job-agents").querySelectorAll("input").forEach(el=>el.onchange=()=>$("job-preset").value="custom");
  await listJobs();$("jobs-dialog").showModal();
}
async function listJobs(){const rows=await api("/api/jobs",{});$("job-list").innerHTML='<h3>Gespeicherte Läufe</h3>'+rows.map(r=>`<button data-job="${esc(r.id)}">${esc(r.title)} · ${esc(r.status)} · ${r.index}/${r.steps.length}</button>`).join(" ");$("job-list").querySelectorAll("[data-job]").forEach(el=>el.onclick=run(async()=>{if(jobLoop||jobRequestActive)throw new Error("Aktuellen Schritt zuerst beenden lassen.");activeJob=await api("/api/job/get",{id:el.dataset.job});renderJob();}));}
function renderJob(){
  if(!activeJob)return;const r=activeJob;
  $("job-detail").innerHTML=`<h3>${esc(r.title)} · ${esc(r.status)} · ${r.index}/${r.steps.length}</h3><p>Gespeicherte Gliederungsrevision ${r.outline.revision} · ${r.mode==="rules"?"Regelbasierte Wissensaufbereitung":"Lokale KI"}</p>${r.error?`<p class="warning">${esc(r.error)}</p>`:""}<div class="actions"><button id="job-run" ${jobLoop||["review","completed","cancelled"].includes(r.status)?"disabled":""}>Fortsetzen / erneut versuchen</button><button id="job-pause" ${!jobLoop?"disabled":""}>Nach aktuellem Schritt pausieren</button><button id="job-cancel" ${["review","completed","cancelled"].includes(r.status)?"disabled":""}>Lauf abbrechen</button></div><details><summary>Agentenschritte</summary><ol>${r.steps.map(s=>`<li>${esc(agentNames[s.agent])}${s.chunk!==undefined?` · Chunk ${s.chunk+1}`:""} · ${esc(s.status)}</li>`).join("")}</ol></details>${r.reports.map(report=>`<article><b>${esc(agentNames[report.agent])}</b><p>${esc(report.text)}</p>${(report.warnings||[]).map(w=>`<p>${esc(w)}</p>`).join("")}</article>`).join("")}${["review","completed"].includes(r.status)&&r.candidates.length?`<h4>Vorschläge prüfen</h4><p>Die Übernahme bestätigt ausgewählte Chunk-Labels und ergänzt Kapitelzuordnungen. Optionale Texte bleiben Entwürfe in der Bibliothek; sie werden nicht automatisch veröffentlicht.</p><label class="check"><input id="job-drafts" type="checkbox" ${r.status==="completed"?"disabled":""}>Zusätzlich als Textentwürfe in die Bibliothek übernehmen</label>${r.candidates.map(c=>`<article><label class="check"><input type="checkbox" data-candidate="${esc(c.id)}" ${r.status==="completed"?"disabled":""}>${esc(c.location)} · ${esc(c.language)}</label><p class="chunk-text">${esc(c.text)}</p><p>Rollen: ${esc((c.labels.roles||[]).join(", "))}<br>Domänen: ${esc((c.labels.domain_ids||[]).map(targetLabel).join(", "))}<br>Kapitel: ${esc((c.labels.chapter_ids||[]).map(id=>r.outline.chapters.find(ch=>ch.id===id)?.title||id).join(", "))}<br>Labels: ${esc((c.labels.labels||[]).join(", "))}</p></article>`).join("")}<button id="job-apply" class="primary" ${r.status==="completed"?"disabled":""}>Ausgewählte Vorschläge bestätigen</button>`:""}`;
  if(r.report_markdown){const button=document.createElement("button");button.textContent="Dokumentationsbericht herunterladen";button.id="job-report-download";button.onclick=run(async()=>downloadResponse(await api("/api/job/report",{id:r.id}),"Finalisierungsbericht.md"));$("job-detail").append(button);}
  $("job-run").onclick=run(runJob);$("job-pause").onclick=()=>{jobLoop=false;message("Der laufende Schritt wird beendet; danach pausiert der Lauf.");};
  $("job-cancel").onclick=run(async()=>{jobLoop=false;activeJob=await api("/api/job/cancel",{id:r.id});renderJob();await listJobs();});
  if($("job-apply"))$("job-apply").onclick=run(async()=>{activeJob=await api("/api/job/apply",{id:r.id,selected:[...$("job-detail").querySelectorAll("[data-candidate]:checked")].map(el=>el.dataset.candidate),create_drafts:$("job-drafts").checked});await refreshSourceIndex();renderJob();await listJobs();message("Geprüfte Vorschläge übernommen. Textentwürfe gegebenenfalls in Inhalte zuordnen bearbeiten.");});
}
async function runJob(){
  if(jobLoop)return;jobLoop=true;renderJob();
  try{while(jobLoop&&activeJob&&!["review","completed","cancelled"].includes(activeJob.status)){
    jobRequestActive=true;try{activeJob=await api("/api/job/step",{id:activeJob.id});}finally{jobRequestActive=false;}renderJob();if(activeJob.status==="failed")break;
  }}finally{jobLoop=false;renderJob();await listJobs();}
}
$("job-start-form").onsubmit=run(async e=>{e.preventDefault();if(jobLoop||jobRequestActive)throw new Error("Aktuellen Schritt zuerst beenden lassen.");if(dirty&&current?.id===$("job-outline").value)throw new Error("Gliederung zuerst speichern. Der Lauf verwendet einen festen gespeicherten Stand.");activeJob=await api("/api/job/start",{outline_id:$("job-outline").value,sources:[...$("job-sources").selectedOptions].map(o=>o.value),agents:[...$("job-agents").querySelectorAll("input:checked")].map(el=>el.dataset.agent),mode:$("job-mode").value,model:$("job-model").value,source_language:$("job-source-language").value,target_language:$("job-target-language").value});renderJob();await runJob();});
$("jobs-button").onclick=run(openJobs);$("jobs-close").onclick=()=>{jobLoop=false;$("jobs-dialog").close();};
$("jobs-dialog").addEventListener("cancel",()=>{jobLoop=false;});

$("job-preset").onchange=()=>{const preset=$("job-preset").value;if(preset==="custom")return;const chosen=preset==="final"?["finalization","validation","layout","documentation"]:["triage","structure","media","quality"];$("job-agents").querySelectorAll("input").forEach(el=>el.checked=chosen.includes(el.dataset.agent));};
