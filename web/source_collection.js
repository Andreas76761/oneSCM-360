"use strict";
const selectedSources=new Set();
let sourceSelectionProcessing=false;
function filteredSources(){const query=$('source-search').value.toLowerCase(),type=$('source-type').value;return sourceRows.filter(s=>{let ext=s.name.split('.').pop().toLowerCase();if(ext==='htm')ext='html';return [s.name,s.kind,s.origin,s.release].join(' ').toLowerCase().includes(query)&&(!type||(type==='other'?!['docx','pdf','md','html'].includes(ext):ext===type));});}
function updateSourceSelection(){const visible=filteredSources();$('sources-selection').textContent=`${selectedSources.size} Dateien markiert · ${visible.length} angezeigt · ${[...selectedSources].filter(id=>!visible.some(s=>s.id===id)).length} markierte außerhalb des Filters`;
 for(const id of ['sources-process','sources-merge'])$(id).disabled=!selectedSources.size||sourceSelectionProcessing;
}
$('source-type').onchange=renderSources;
$('sources-select-all').onclick=()=>{filteredSources().forEach(s=>selectedSources.add(s.id));renderSources();};
$('sources-select-none').onclick=()=>{selectedSources.clear();renderSources();};
$('sources-process').onclick=run(async()=>{
 if(sourceSelectionProcessing||triageRunning)throw new Error('Laufende Verarbeitung zuerst abwarten.');
 if(!$('triage-outline').value)throw new Error('Zuerst eine Zielgliederung auswählen.');
 const ids=[...selectedSources],results=[];sourceSelectionProcessing=true;updateSourceSelection();
 try{for(const [index,id] of ids.entries()){
  if(!sourceRows.some(s=>s.id===id)){results.push('Gelöschte Datei übersprungen');continue;}
  try{await triageSource(id);results.push(`${index+1}/${ids.length}: ${sourceRows.find(s=>s.id===id).name} verarbeitet`);}catch(error){results.push(`${sourceRows.find(s=>s.id===id)?.name}: ${error.message}`);}
  if(triageCancelled){results.push('Verarbeitung angehalten.');break;}
 }message(results.join(' · '));}finally{sourceSelectionProcessing=false;updateSourceSelection();}
});
(() => {
 let collection=null,ids=[];
 const dialog=document.createElement('dialog');dialog.id='source-collection-dialog';dialog.className='knowledge-dialog';
 dialog.innerHTML=`<div class="panel-heading"><h2>Texte ansehen und zusammenstellen</h2><button id="collection-close">Schließen</button></div><p id="collection-info"></p><p>Extrahierte Texte mit Fundstellen. Originaldateien bleiben erhalten. Die neue Zusammenstellung ist eine redaktionelle Quelle; sie übernimmt keine Freigaben oder Kapitelzuordnungen.</p><div class="actions"><button id="collection-full">Volltexte einsetzen</button><button id="collection-summary">Kurze Textauszüge einsetzen</button></div><p class="muted">Textauszüge enthalten je Chunk maximal 500 Zeichen, keine KI-Zusammenfassung. Voraussetzungen und Ausnahmen können fehlen. Für eine sprachliche Zusammenfassung die neue Quelle anschließend im KI-Austausch verwenden.</p><label>Dateiname<input id="collection-name" value="Zusammenstellung.md" maxlength="240"></label><label>Inhalt ansehen und bearbeiten<textarea id="collection-text" rows="20" maxlength="3000000"></textarea></label><div class="actions"><button id="collection-download">Als Markdown-Datei herunterladen</button><button id="collection-save" class="primary">Als neue Quelle speichern</button></div>`;
 document.body.append(dialog);
 $('sources-merge').onclick=run(async()=>{ids=[...selectedSources];collection=await api('/api/source/collection',{ids});$('collection-info').textContent=`${collection.files} Dateien · ${collection.chunks} Chunks`;$('collection-text').value=collection.text;$('collection-save').disabled=false;dialog.showModal();});
 $('collection-close').onclick=()=>dialog.close();
 function replace(text){if($('collection-text').value!==collection.text&&$('collection-text').value!==collection.summary&&!confirm('Bearbeitete Zusammenstellung durch die gewählte Ansicht ersetzen?'))return;$('collection-text').value=text;}
 $('collection-full').onclick=()=>replace(collection.text);$('collection-summary').onclick=()=>replace(collection.summary);
 $('collection-download').onclick=run(async()=>{const text=$('collection-text').value;if(!text.trim())throw new Error('Text ist leer.');const url=URL.createObjectURL(new Blob([text],{type:'text/markdown;charset=utf-8'}));const a=document.createElement('a');a.href=url;const name=$('collection-name').value.trim()||'Zusammenstellung.md';a.download=name.toLowerCase().endsWith('.md')?name:name+'.md';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
 $('collection-save').onclick=run(async()=>{const result=await api('/api/source/collection/save',{ids,fingerprint:collection.fingerprint,name:$('collection-name').value,text:$('collection-text').value});await loadSources();$('collection-save').disabled=true;message(result.duplicate?'Gleicher Inhalt ist bereits als Quelle vorhanden.':'Zusammenstellung als neue Quelle gespeichert. Labels und Zuordnungen anschließend prüfen.');dialog.close();await openSource(result.id);});
})();
