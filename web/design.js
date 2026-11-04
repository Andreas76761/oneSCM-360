"use strict";
(() => {
  const defaults = {primary:"#123443",accent:"#00858b",text:"#203640",font:"Arial",size:11,
    chapter:"#123443",subchapter:"#00858b",image_width:100,captions:true,page_numbers:true,icons:true,icon_style:"symbols",
    keywords:[],highlight:"#fff1a8",link:"#006b8f",notice:"#eaf4f5",exception:"#fff0e5",tip:"#eaf5e9"};
  const colors = [["primary","Hauptfarbe"],["accent","Akzentfarbe"],["chapter","Kapitel"],
    ["subchapter","Unterkapitel"],["text","Fließtext"],["link","Links"],["highlight","Hervorhebungen"],
    ["notice","Hinweise"],["exception","Ausnahmen"],["tip","Tipps"]];
  const presets={
    oneSCM:{...defaults},
    print:{...defaults,primary:"#202020",accent:"#555555",chapter:"#202020",subchapter:"#444444",text:"#202020",link:"#333333",highlight:"#eeeeee",notice:"#f4f4f4",exception:"#ededed",tip:"#f7f7f7",icon_style:"letters"},
    highcontrast:{...defaults,primary:"#000000",accent:"#003b70",chapter:"#000000",subchapter:"#003b70",text:"#000000",link:"#003b70",highlight:"#fff066",notice:"#e5f1ff",exception:"#ffe5ce",tip:"#e5f5df",size:12}
  };
  let entries=[], outlineId=null, baseTheme={};
  const field = key => document.querySelector(`#design-form [data-design="${key}"]`);
  function init() {
    if($("design-dialog"))return;
    const dialog=document.createElement("dialog");dialog.id="design-dialog";dialog.setAttribute("aria-labelledby","design-heading");
    dialog.innerHTML=`<div class="panel-heading"><div><div class="eyebrow">GESTALTUNG DER AUSGABE</div><h2 id="design-heading">Designstudio</h2></div><button type="button" id="design-cancel">Abbrechen</button></div>
      <p id="design-outline" class="muted"></p><form id="design-form"><div class="design-workspace"><section class="design-settings">
      <fieldset><legend>Designvorlagen</legend><label>Vorlage auswählen<select id="design-preset"><option value="">Eigene Gestaltung</option><option value="oneSCM">oneSCM · Petrol</option><option value="print">Druck · Graustufen</option><option value="highcontrast">Hoher Kontrast</option></select></label><button type="button" id="design-preset-apply" disabled>Designvorlage einsetzen</button><p class="muted">Eine Vorlage ersetzt die Gestaltungswerte. Gewählte Office-Templates und Hervorhebungsbegriffe bleiben erhalten.</p></fieldset>
      <fieldset><legend>Office-Templates</legend><label>Word-Template<select id="design-docx"></select></label><label>PowerPoint-Template<select id="design-pptx"></select></label>
      <p class="muted">Die gewählte Revision bleibt fest gebunden. Neue DOCX-/PPTX-Templates lassen sich unter „Layouttemplates“ hochladen. Native Templates behalten ihre Formatvorlagen und Master.</p></fieldset>
      <fieldset><legend>Farben und Schrift</legend><div class="design-colors">${colors.map(([key,label])=>`<label>${label}<input type="color" data-design="${key}" aria-label="Farbe ${label}"></label>`).join("")}</div>
      <div class="design-row"><label>Schriftfamilie<input data-design="font" required maxlength="80"></label><label>Schriftgröße (pt)<input data-design="size" type="number" min="8" max="18" step="1" required></label></div></fieldset>
      <fieldset><legend>Bilder und Orientierung</legend><label>Bildbreite (% der verfügbaren Breite)<input data-design="image_width" type="number" min="25" max="100" step="1" required></label>
      <label class="check"><input type="checkbox" data-design="captions">Bildunterschriften anzeigen</label><label class="check"><input type="checkbox" data-design="page_numbers">Seiten- / Foliennummern anzeigen</label><label class="check"><input type="checkbox" data-design="icons">Symbole bei Hinweisen, Ausnahmen und Tipps</label><label>Symbolstil<select data-design="icon_style"><option value="symbols">Symbole · ℹ / ! / ✓</option><option value="letters">Buchstaben · H / A / T</option><option value="minimal">Minimal · •</option></select></label></fieldset>
      <fieldset><legend>Stichwörter hervorheben</legend><label>Ein Begriff pro Zeile, höchstens 50<textarea data-design="keywords" rows="5" maxlength="4050" placeholder="Vertrag&#10;Laufzeit"></textarea></label><p class="muted">Begriffe werden als Text gesucht, ohne reguläre Ausdrücke. Maximal 80 Zeichen pro Begriff.</p></fieldset>
      </section><aside class="design-preview-panel"><h3>Gestaltungsbeispiel</h3><p class="muted">Schematische Vorschau mit Beispieltext. Seitenumbrüche und native Office-Master bitte in der erzeugten Datei prüfen.</p>
      <article id="design-preview" class="design-paper" aria-label="Gestaltungsbeispiel"><div class="design-sample-brand">oneSCM · Benutzerhandbuch</div><h2>1 Contract Management</h2><h3>1.1 Vertrag bearbeiten</h3><p>Prüfen Sie den <mark id="design-sample-keyword">Vertrag</mark> und ergänzen Sie die erforderlichen Angaben.</p><p><a href="#" id="design-sample-link">Weitere Informationen zum Ablauf</a></p>
      <figure><div class="design-sample-screen" role="img" aria-label="Schematischer Beispielscreen ohne personenbezogene Daten"><div>oneSCM · Vertrag</div><span>Vertragsdaten</span><span>Status: Entwurf</span><span>Änderungen speichern</span></div><figcaption>Abbildung 1: Vertragsdaten bearbeiten</figcaption></figure>
      <p class="design-sample-note" data-note="notice"><b><span data-icon>ℹ </span>Hinweis:</b> Pflichtfelder vor dem Speichern prüfen.</p><p class="design-sample-note" data-note="exception"><b><span data-icon>! </span>Ausnahme:</b> Länderspezifische Vorgaben beachten.</p><p class="design-sample-note" data-note="tip"><b><span data-icon>✓ </span>Tipp:</b> Häufige Abläufe als Quick Reference bereitstellen.</p><footer>1</footer></article></aside></div>
      <div class="dialog-actions"><button type="button" id="design-reset">Standarddesign einsetzen</button><button class="primary" type="submit">Design übernehmen</button></div><p class="muted">Übernehmen ändert die aktuelle Gliederung. Anschließend speichern, um das Design dauerhaft zu sichern.</p></form>`;
    document.body.append(dialog);
    $("design-cancel").onclick=()=>dialog.close();
    $("design-sample-link").onclick=e=>e.preventDefault();
    $("design-form").oninput=preview;
    $("design-preset").onchange=()=>$("design-preset-apply").disabled=!$("design-preset").value;
    $("design-preset-apply").onclick=()=>{const preset=presets[$("design-preset").value];if(preset){fillTheme({...preset,keywords:readTheme().keywords});preview();}};
    $("design-reset").onclick=()=>{fillTheme(defaults);preview();};
    $("design-form").onsubmit=run(async e=>{
      e.preventDefault();if(!current||current.id!==outlineId)throw new Error("Die Gliederung hat gewechselt. Designstudio erneut öffnen.");
      const theme=readTheme(true),layout={theme};
      for(const fmt of ["docx","pptx"]){const value=$("design-"+fmt).value;if(value)layout[fmt]=JSON.parse(value);}
      current.layout=layout;markDirty();dialog.close();message("Design übernommen. Gliederung speichern und gewünschte Ausgabe erzeugen.");
    });
    document.querySelectorAll("[data-design-open]").forEach(button=>button.onclick=run(open));
    if($("design-button"))$("design-button").onclick=run(open);
  }
  function fillTheme(theme) {
    for(const key of Object.keys(defaults)){const el=field(key);if(!el)continue;if(el.type==="checkbox")el.checked=!!theme[key];else el.value=key==="keywords"?(theme[key]||[]).join("\n"):theme[key];}
  }
  function readTheme(validate=false) {
    const theme={...baseTheme};
    for(const key of Object.keys(defaults)){const el=field(key);theme[key]=el.type==="checkbox"?el.checked:el.type==="number"?Number(el.value):key==="keywords"?el.value.split(/\r?\n/).map(s=>s.trim()).filter(Boolean):el.value;}
    if(validate&&(!theme.font.trim()||!/^[\p{L}\p{N}_ ,.-]+$/u.test(theme.font)))throw new Error("Schriftfamilie mit Buchstaben, Ziffern, Leerzeichen, Komma, Punkt oder Bindestrich angeben.");
    if(validate&&(theme.keywords.length>50||theme.keywords.some(k=>k.length>80)))throw new Error("Höchstens 50 Hervorhebungsbegriffe mit jeweils maximal 80 Zeichen verwenden.");
    return theme;
  }
  function preview() {
    const t=readTheme(),paper=$("design-preview");
    for(const [key] of colors)paper.style.setProperty("--design-"+key,t[key]);
    paper.style.fontFamily=t.font;paper.style.fontSize=`${Math.max(8,Math.min(18,t.size||11))}pt`;
    paper.querySelector("figure").style.width=`${Math.max(25,Math.min(100,t.image_width||100))}%`;
    paper.querySelector("figcaption").hidden=!t.captions;paper.querySelector("footer").hidden=!t.page_numbers;
    const symbols=t.icon_style==="letters"?{notice:"H",exception:"A",tip:"T"}:t.icon_style==="minimal"?{notice:"•",exception:"•",tip:"•"}:{notice:"ℹ",exception:"!",tip:"✓"};
    paper.querySelectorAll("[data-icon]").forEach(el=>{el.hidden=!t.icons;el.textContent=symbols[el.closest("[data-note]").dataset.note]+" ";});
    $("design-sample-keyword").textContent=t.keywords[0]||"Vertrag";
    $("design-sample-keyword").style.backgroundColor=t.keywords.length?t.highlight:"transparent";
  }
  function templateSelect(fmt,ref) {
    const select=$("design-"+fmt);select.replaceChildren(new Option("Standardlayout",""));
    const value=ref?JSON.stringify({id:ref.id,revision:ref.revision}):"";
    for(const entry of entries.filter(e=>e.format===fmt))select.add(new Option(`${entry.name} · V${entry.version} · R${entry.revision}`,JSON.stringify({id:entry.id,revision:entry.revision})));
    if(value&&![...select.options].some(o=>o.value===value))select.add(new Option(`Gebundene Templaterevision R${ref.revision}`,value));
    select.value=value;
  }
  async function open() {
    if(!current)throw new Error("Zuerst eine Gliederung öffnen, um deren Design zu bearbeiten.");
    init();const targetId=current.id;entries=await api("/api/layouts",{});
    if(!current||current.id!==targetId)throw new Error("Die Gliederung hat gewechselt. Designstudio erneut öffnen.");
    outlineId=targetId;const old=current.layout?.theme||{};baseTheme={...defaults,...old,chapter:old.chapter||old.primary||defaults.chapter,subchapter:old.subchapter||old.accent||defaults.subchapter};
    $("design-outline").textContent=`Für „${current.title}“ · Version ${current.metadata?.version||"1.0"} · Revision ${current.revision}`;
    for(const fmt of ["docx","pptx"])templateSelect(fmt,current.layout?.[fmt]);
    $("design-preset").value="";$("design-preset-apply").disabled=true;
    fillTheme(baseTheme);preview();if(!$("design-dialog").open)$("design-dialog").showModal();
  }
  window.oneSCMDesign={init,open:run(open)};
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init);else init();
})();
