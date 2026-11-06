"use strict";
(() => {
  const $ = (id) => document.getElementById(id);
  const state = { meta: null, tab: "dashboard", ruleFilter: "", claims: [], selectedClaim: null, chapterCache: {} };

  // ---------- helpers ----------
  function el(tag, attrs = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else if (key === "dataset") Object.assign(node.dataset, value);
      else if (value === true) node.setAttribute(key, "");
      else node.setAttribute(key, value);
    }
    for (const child of children.flat()) {
      if (child === null || child === undefined || child === false) continue;
      node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    }
    return node;
  }
  const badge = (value, cls) => el("span", { class: `badge ${cls || value || ""}`, text: value || "—" });
  const fmtDate = (iso) => (iso ? new Date(iso).toLocaleString("de-DE") : "—");
  const fmtSize = (n) => (n < 1024 ? `${n} B` : n < 1048576 ? `${(n / 1024).toFixed(1)} KB` : `${(n / 1048576).toFixed(1)} MB`);
  const pct = (v) => `${Number(v || 0).toLocaleString("de-DE", { maximumFractionDigits: 1 })} %`;

  function toast(message, isError = false) {
    const node = $("toast");
    node.textContent = message;
    node.className = `toast${isError ? " error" : ""}`;
    node.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => { node.hidden = true; }, isError ? 7000 : 3500);
  }

  async function api(path, options = {}) {
    const init = { method: options.method || "GET", headers: {} };
    if (init.method !== "GET") init.headers["X-oneSCM360"] = "1";
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }
    let response;
    try {
      response = await fetch(path, init);
    } catch (err) {
      throw new Error("Server nicht erreichbar. Läuft start_onescm360.ps1 noch?");
    }
    let data = null;
    try { data = await response.json(); } catch { data = null; }
    if (!response.ok) throw new Error((data && data.error) || `Serverfehler (${response.status}).`);
    return data;
  }

  function fillSelect(select, options, { empty, value } = {}) {
    const previous = value !== undefined ? value : select.value;
    select.replaceChildren();
    if (empty !== undefined) select.append(el("option", { value: "", text: empty }));
    for (const opt of options) {
      const [val, label] = Array.isArray(opt) ? opt : [opt, opt];
      select.append(el("option", { value: val, text: label }));
    }
    if ([...select.options].some((o) => o.value === previous)) select.value = previous;
  }

  const chapterOptions = () => state.meta.chapters.map((c) => [c.chapterId, `${c.chapterId} – ${c.title}${c.schemaStatus === "DRAFT" ? " (Schema-Entwurf)" : ""}`]);

  async function chapter(id) {
    if (!state.chapterCache[id]) state.chapterCache[id] = await api(`/api/chapters/${id}`);
    return state.chapterCache[id];
  }

  function emptyRow(tbody, cols, text) {
    tbody.replaceChildren(el("tr", {}, el("td", { colspan: cols, class: "empty", text })));
  }

  // ---------- navigation ----------
  const loaders = {};
  function showTab(name) {
    state.tab = name;
    for (const button of $("tabs").querySelectorAll("button")) {
      const active = button.dataset.tab === name;
      button.classList.toggle("active", active);
      if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current");
    }
    for (const panel of document.querySelectorAll(".panel")) panel.hidden = panel.id !== `tab-${name}`;
    try { localStorage.setItem("onescm360-tab", name); } catch { /* storage unavailable */ }
    const loader = loaders[name];
    if (loader) loader().catch((err) => toast(err.message, true));
  }
  $("tabs").addEventListener("click", (event) => {
    const button = event.target.closest("button[data-tab]");
    if (button) showTab(button.dataset.tab);
  });
  window.addEventListener("onescm-changed", () => { refreshTopStatus(); if (state.tab === "dashboard") loaders.dashboard(); });

  async function refreshTopStatus() {
    try {
      const status = await api("/api/sync/status");
      const pill = $("top-onedrive");
      pill.textContent = `OneDrive lokal: ${status.localStatus}`;
      pill.title = `${status.path || "nicht konfiguriert"} · Cloud: ${status.cloudStatus}`;
    } catch { /* ignore */ }
  }

  // ---------- Dashboard ----------
  loaders.dashboard = async () => {
    const data = await api("/api/dashboard");
    const labels = [["imports", "Importläufe"], ["sourceFiles", "Quelldateien"], ["outputFiles", "Output-Dateien"], ["json", "JSON"], ["csv", "CSV"], ["packages", "Uploadpakete"]];
    $("kpis").replaceChildren(...labels.map(([key, label]) => el("div", { class: "kpi", dataset: { kpi: key } }, el("div", { class: "label", text: label }), el("div", { class: "value", text: data.kpis[key] }))));
    const od = data.onedrive;
    $("dash-onedrive").replaceChildren(
      el("h2", { text: "OneDrive-Pfadprüfung" }),
      el("dl", { class: "kv" },
        el("dt", { text: "Pfad" }), el("dd", { class: "mono", text: od.path || "nicht konfiguriert" }),
        el("dt", { text: "Existiert" }), el("dd", { text: od.exists ? "ja" : "nein" }),
        el("dt", { text: "Beschreibbar" }), el("dd", { text: od.writable ? "ja" : "nein" }),
        el("dt", { text: "Letzte lokale Änderung" }), el("dd", { text: fmtDate(od.lastLocalChange) }),
        el("dt", { text: "Lokaler Status" }), el("dd", {}, badge(od.localStatus), " ", el("span", { class: "muted", text: od.reason })),
        el("dt", { text: "Cloudstatus" }), el("dd", {}, badge(od.cloudStatus), " ", el("span", { class: "muted", text: od.cloudNote }))));
    const tbody = $("dash-imports").tBodies[0];
    const groupKey = $("dash-group").value;
    if (!data.imports.length) emptyRow(tbody, 12, "Noch keine Importe.");
    else {
      const rows = [];
      for (const group of groupBy(data.imports, groupKey, labelFor[groupKey] || ((v) => v))) {
        if (groupKey) rows.push(el("tr", { class: "group-row" }, el("td", { colspan: 12, text: `${group.label} (${group.items.length})` })));
        for (const r of group.items) rows.push(el("tr", { dataset: { importId: r.importId } },
          el("td", { class: "mono", text: r.importId }), el("td", { text: r.chapterId || "—" }), el("td", { text: r.file }),
          el("td", { text: r.language || "—" }), el("td", { text: r.status === "INVALID_JSON" ? "—" : labelFor.role(r.role) }),
          el("td", { text: r.status === "INVALID_JSON" ? "—" : labelFor.domain(r.domain) }),
          el("td", {}, badge(r.status)), el("td", {}, badge(r.validationStatus)), el("td", { text: r.questions }),
          el("td", { text: r.tables }), el("td", { class: "gate-cell" }, badge(r.gate)),
          el("td", {}, r.status === "INVALID_JSON" ? "" : el("div", { class: "actions" },
            el("button", { class: "small", text: "Details", onclick: () => showImportDetails(r.importId) }),
            el("button", { class: "small", text: "Archivieren", onclick: () => archiveImport(r) }),
            el("button", { class: "small danger", text: "Löschen", onclick: () => deleteImport(r) })))));
      }
      tbody.replaceChildren(...rows);
    }
    const otbody = $("dash-outputs").tBodies[0];
    if (!data.outputs.length) emptyRow(otbody, 4, "Keine Output-Dateien im OneDrive-Ziel.");
    else otbody.replaceChildren(...data.outputs.map((o) => el("tr", {}, el("td", { text: o.name }), el("td", { class: "mono", text: o.path }), el("td", { text: fmtSize(o.size) }), el("td", { text: fmtDate(o.modifiedAt) }))));
  };
  $("dash-group").addEventListener("change", () => loaders.dashboard().catch((e) => toast(e.message, true)));
  $("dash-refresh").addEventListener("click", () => loaders.dashboard().then(() => toast("Dashboard aktualisiert.")).catch((e) => toast(e.message, true)));

  async function showImportDetails(id) {
    const record = await api(`/api/imports/${id}`);
    showTab("import");
    renderImportResult(record, null);
  }
  async function archiveImport(row) {
    let force = false;
    if (!row.exportedAt) {
      if (!confirm(`${row.importId} wurde noch nicht exportiert. Trotzdem archivieren?`)) return;
      force = true;
    } else if (!confirm(`${row.importId} archivieren? Import-JSON und Rohdatei werden nach data/archive verschoben.`)) return;
    try { await api(`/api/imports/${row.importId}/archive`, { method: "POST", body: { force } }); toast("Import archiviert."); loaders.dashboard(); }
    catch (e) { toast(e.message, true); }
  }
  async function deleteImport(row) {
    if (!confirm(`${row.importId} und alle daraus erzeugten Claims/Evidence löschen?`)) return;
    try { await api(`/api/imports/${row.importId}`, { method: "DELETE" }); toast("Import gelöscht."); loaders.dashboard(); }
    catch (e) { toast(e.message, true); }
  }

  // ---------- Import (Mehrfachimport) ----------
  loaders.import = async () => {};
  const queue = [];
  let queueSeq = 0;
  let importing = false;
  const FIELDS = ["chapterId", "language", "role", "domain", "sourceType"];
  const DEFAULT_IDS = { chapterId: "imp-chapter", language: "imp-language", role: "imp-role", domain: "imp-domain", sourceType: "imp-source" };

  const labelFor = {
    chapterId: (v) => { const c = state.meta.chapters.find((x) => x.chapterId === v); return c ? `${c.chapterId} – ${c.title}` : "Kapitel fehlt"; },
    language: (v) => v || "Sprache fehlt",
    role: (v) => (v ? (state.meta.roles.find((r) => r.id === v) || { name: v }).name : "Alle Rollen"),
    domain: (v) => (state.meta.domains.find((d) => d.id === v) || {}).name || "Ohne Domäne",
    name: (v) => (v || "?").slice(0, 1).toUpperCase(),
  };
  const fieldOptions = {
    chapterId: () => [["", "— Kapitel wählen —"], ...chapterOptions()],
    language: () => [["", "— Sprache wählen —"], ...state.meta.languages],
    role: () => [["", "Alle Rollen"], ...state.meta.roles.map((r) => [r.id, r.name])],
    domain: () => [["", "Ohne Domäne"], ...state.meta.domains.map((d) => [d.id, d.name])],
    sourceType: () => state.meta.sourceTypes,
  };

  /** Sort items by a key and return [{label, items}] groups (used by the queue and the dashboard). */
  function groupBy(items, key, label) {
    if (!key) return [{ label: "", items }];
    const groups = new Map();
    for (const item of [...items].sort((a, b) => String(label(a[key] ?? "")).localeCompare(String(label(b[key] ?? "")), "de") || String(a.name || a.file || "").localeCompare(String(b.name || b.file || ""), "de"))) {
      const text = label(item[key] ?? "");
      if (!groups.has(text)) groups.set(text, []);
      groups.get(text).push(item);
    }
    return [...groups].map(([text, list]) => ({ label: text, items: list }));
  }

  function defaults() {
    return Object.fromEntries(FIELDS.map((f) => [f, $(DEFAULT_IDS[f]).value]));
  }

  function clientCheck(file) {
    const ext = file.name.includes(".") ? file.name.split(".").pop().toLowerCase() : "";
    if (!["docx", "html", "htm"].includes(ext)) return `Dateityp „.${ext || "?"}“ wird nicht unterstützt. Erlaubt sind .docx, .html und .htm.`;
    if (file.size === 0) return "Die Datei ist leer.";
    if (file.size > state.meta.maxUploadBytes) return "Die Datei ist größer als 50 MB (Pilotgrenze).";
    return "";
  }

  async function addFiles(files) {
    $("imp-error").hidden = true;
    const added = [];
    for (const file of files) {
      if (queue.some((q) => q.file.name === file.name && q.file.size === file.size && q.file.lastModified === file.lastModified && q.status !== "done")) continue;
      const base = defaults();
      const item = { id: ++queueSeq, file, name: file.name, status: "checking", error: "", origin: {}, ...base };
      for (const f of FIELDS) item.origin[f] = "default";
      const problem = clientCheck(file);
      if (problem) { item.status = "invalid"; item.error = problem; }
      queue.push(item);
      added.push(item);
    }
    renderQueue();
    for (const item of added.filter((i) => i.status === "checking")) {
      try {
        const form = new FormData();
        form.append("file", item.file);
        const response = await fetch("/api/import/classify", { method: "POST", headers: { "X-oneSCM360": "1" }, body: form });
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error((data && data.error) || `Serverfehler (${response.status}).`);
        for (const [field, source] of [["chapterId", "chapterSource"], ["language", "languageSource"], ["role", "roleSource"], ["domain", "domainSource"]]) {
          if (data[field] && item.origin[field] !== "user") { item[field] = data[field]; item.origin[field] = data[source]; }
        }
        item.status = "ready";
      } catch (err) {
        item.status = "invalid";
        item.error = err.message;
      }
      renderQueue();
    }
  }

  function selectFor(item, field) {
    const select = el("select", { "aria-label": { chapterId: "Kapitel", language: "Sprache", role: "Rolle", domain: "Domäne", sourceType: "Quelltyp" }[field], disabled: importing || item.status === "done" || item.status === "running" });
    fillSelect(select, fieldOptions[field](), { value: item[field] });
    select.addEventListener("change", () => { item[field] = select.value; item.origin[field] = "user"; if (item.status === "failed") item.status = "ready"; renderQueue(); });
    const origin = item.origin[field];
    const hint = origin && origin !== "default" && origin !== "user" ? el("span", { class: "origin", text: `erkannt: ${origin}` }) : origin === "user" ? el("span", { class: "origin", text: "manuell" }) : null;
    return el("td", {}, select, hint);
  }

  function statusCell(item) {
    switch (item.status) {
      case "checking": return el("td", {}, badge("PRÜFT …", "warn"));
      case "invalid": return el("td", {}, badge("NICHT IMPORTIERBAR", "bad"), el("div", { class: "row-error", text: item.error }));
      case "ready": return el("td", {}, badge(item.chapterId && item.language ? "BEREIT" : "ANGABE FEHLT", item.chapterId && item.language ? "ok" : "warn"));
      case "running": return el("td", {}, badge("LÄUFT …", "warn"));
      case "done": return el("td", {}, badge(item.duplicate ? "BEREITS IMPORTIERT" : "IMPORTIERT", "ok"), " ", badge(item.gate));
      case "failed": return el("td", {}, badge("FEHLER", "bad"), el("div", { class: "row-error", text: item.error }));
      default: return el("td", {});
    }
  }

  function renderQueue() {
    const card = $("imp-queue-card");
    card.hidden = queue.length === 0;
    const ready = queue.filter((q) => q.status === "ready" || q.status === "failed").length;
    $("imp-queue-title").textContent = `Dateien (${queue.length}) · ${ready} importierbar`;
    $("imp-submit").textContent = ready > 1 ? `${ready} Dateien importieren` : "Importieren";
    const key = $("imp-group").value;
    const rows = [];
    for (const group of groupBy(queue, key, labelFor[key] || ((v) => v))) {
      if (key) rows.push(el("tr", { class: "group-row" }, el("td", { colspan: 8, text: `${{ chapterId: "Kapitel", language: "Sprache", role: "Rolle", domain: "Domäne", name: "Dateiname" }[key]}: ${group.label} (${group.items.length})` })));
      for (const item of group.items) {
        rows.push(el("tr", { dataset: { queueId: item.id, file: item.name } },
          el("td", {}, el("div", { text: item.name }), el("span", { class: "origin", text: fmtSize(item.file.size) })),
          ...FIELDS.map((f) => selectFor(item, f)),
          statusCell(item),
          el("td", {}, el("div", { class: "actions" },
            item.result ? el("button", { type: "button", class: "small", text: "Ergebnis", onclick: () => renderImportResult(item.result.importRecord, item.result.coverage) }) : null,
            el("button", { type: "button", class: "small", text: "Entfernen", disabled: importing, onclick: () => { queue.splice(queue.indexOf(item), 1); renderQueue(); } })))));
      }
    }
    $("imp-queue").tBodies[0].replaceChildren(...rows);
  }

  for (const f of FIELDS) {
    $(DEFAULT_IDS[f]).addEventListener("change", () => {
      for (const item of queue) if (item.origin[f] === "default" && item.status !== "done") item[f] = $(DEFAULT_IDS[f]).value;
      renderQueue();
    });
  }
  $("imp-group").addEventListener("change", renderQueue);
  $("imp-clear").addEventListener("click", () => { if (!importing) { queue.length = 0; renderQueue(); $("imp-batch-summary").replaceChildren(); } });
  $("imp-file").addEventListener("change", (e) => { const files = [...e.target.files]; e.target.value = ""; addFiles(files); });
  const drop = document.querySelector(".drop");
  ["dragenter", "dragover"].forEach((t) => drop.addEventListener(t, () => drop.classList.add("dragover")));
  ["dragleave", "drop"].forEach((t) => drop.addEventListener(t, () => drop.classList.remove("dragover")));

  function setProgress(text, value) {
    $("imp-status-text").textContent = text;
    const bar = $("imp-bar");
    if (value === null) { bar.classList.add("indeterminate"); } else { bar.classList.remove("indeterminate"); bar.style.width = `${value}%`; }
  }

  function upload(item, onProgress) {
    const form = new FormData();
    form.append("file", item.file);
    for (const f of FIELDS) form.append(f, item[f]);
    if ($("imp-force").checked) form.append("force", "1");
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      xhr.open("POST", "/api/import");
      xhr.setRequestHeader("X-oneSCM360", "1");
      xhr.upload.onprogress = (e) => { if (e.lengthComputable) onProgress(e.loaded / e.total); };
      xhr.upload.onload = () => onProgress(1);
      xhr.onload = () => {
        let data = null;
        try { data = JSON.parse(xhr.responseText); } catch { data = null; }
        if (xhr.status >= 200 && xhr.status < 300 && data) resolve(data);
        else reject(new Error((data && data.error) || (xhr.status === 413 ? "Die Datei ist größer als 50 MB (Pilotgrenze)." : `Serverfehler (${xhr.status}).`)));
      };
      xhr.onerror = () => reject(new Error("Server nicht erreichbar. Läuft start_onescm360.ps1 noch?"));
      xhr.ontimeout = () => reject(new Error("Zeitüberschreitung beim Import."));
      xhr.timeout = 10 * 60 * 1000;
      xhr.send(form);
    });
  }

  $("import-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (importing) return;
    const errorBox = $("imp-error");
    errorBox.hidden = true;
    const fail = (msg) => { errorBox.textContent = msg; errorBox.hidden = false; };
    if (!queue.length) return fail("Bitte eine Datei auswählen.");
    if (queue.some((q) => q.status === "checking")) return fail("Die Dateien werden noch geprüft. Bitte einen Moment warten.");
    const todo = queue.filter((q) => q.status === "ready" || q.status === "failed");
    if (!todo.length) {
      const invalid = queue.filter((q) => q.status === "invalid");
      return fail(invalid.length ? invalid.map((q) => `${q.name}: ${q.error}`).join(" · ") : "Alle Dateien der Liste sind bereits importiert.");
    }
    const incomplete = todo.filter((q) => !q.chapterId || !q.language);
    if (incomplete.length) return fail(`Für ${incomplete.length} Datei(en) fehlen Kapitel oder Sprache: ${incomplete.map((q) => q.name).join(", ")}.`);

    importing = true;
    $("imp-submit").disabled = true;
    $("imp-file").disabled = true;
    $("imp-progress").hidden = false;
    $("imp-result").replaceChildren();
    $("imp-batch-summary").replaceChildren();
    let ok = 0, failed = 0, last = null, lastError = "";
    try {
      for (const [index, item] of todo.entries()) {
        item.status = "running";
        item.error = "";
        renderQueue();
        const prefix = todo.length > 1 ? `Datei ${index + 1} von ${todo.length} · ${item.name}: ` : "";
        setProgress(`${prefix}Datei wird eingelesen …`, Math.round((index / todo.length) * 100) + 1);
        try {
          const result = await upload(item, (fraction) => {
            if (fraction < 1) setProgress(`${prefix}Datei wird eingelesen … ${Math.round(fraction * 100)} %`, Math.round(((index + fraction * 0.5) / todo.length) * 100));
            else setProgress(`${prefix}Analyse läuft (Parser, Tabellen, Regelwerk, Claims) …`, todo.length > 1 ? Math.round(((index + 0.5) / todo.length) * 100) : null);
          });
          item.status = "done";
          item.result = result;
          item.duplicate = !!result.importRecord.duplicate;
          item.gate = result.coverage.gate;
          last = result;
          ok += 1;
        } catch (err) {
          item.status = "failed";
          item.error = err.message;
          lastError = err.message;
          failed += 1;
        }
        renderQueue();
      }
      setProgress("Fertig.", 100);
    } finally {
      importing = false;
      $("imp-submit").disabled = false;
      $("imp-file").disabled = false;
      $("imp-progress").hidden = true;
      $("imp-bar").classList.remove("indeterminate");
      renderQueue();
      window.dispatchEvent(new Event("onescm-changed"));
    }
    if (todo.length > 1) {
      $("imp-batch-summary").replaceChildren(el("div", { class: `alert ${failed ? "warn" : "ok"}`, id: "imp-batch-result", text: `${ok} von ${todo.length} Dateien importiert${failed ? `, ${failed} mit Fehler (siehe Liste)` : ""}.` }));
    }
    if (failed && !ok) fail(todo.length > 1 ? "Keine Datei konnte importiert werden. Details stehen in der Liste." : lastError);
    if (last) {
      renderImportResult(last.importRecord, last.coverage);
      toast(todo.length > 1 ? `${ok} von ${todo.length} Dateien importiert.` : last.importRecord.duplicate ? "Diese Datei wurde bereits importiert – vorhandenes Ergebnis angezeigt." : "Import abgeschlossen.", failed > 0);
    }
  });

  function renderImportResult(record, coverage) {
    const answered = record.questions.filter((q) => q.answerStatus === "ANSWERED").length;
    const parts = [
      el("div", { class: "card", id: "imp-summary" },
        el("h2", { text: "Ergebnis" }),
        el("dl", { class: "kv" },
          el("dt", { text: "Import-ID" }), el("dd", { class: "mono", id: "imp-result-id", text: record.importId }),
          el("dt", { text: "Kapitel" }), el("dd", { text: `${record.chapterId} · ${record.language} · ${record.sourceType}` }),
          el("dt", { text: "Rolle · Domäne" }), el("dd", { id: "imp-result-scope", text: `${labelFor.role(record.role || "")} · ${labelFor.domain(record.domain || "")}` }),
          el("dt", { text: "Datei" }), el("dd", { text: `${record.sourceFile.name} (${fmtSize(record.sourceFile.size)})` }),
          el("dt", { text: "Status" }), el("dd", {}, badge(record.status), record.duplicate ? el("span", { class: "muted", text: " · bereits importiert (idempotent)" }) : ""),
          el("dt", { text: "Validierung" }), el("dd", {}, badge(record.validationStatus)),
          el("dt", { text: "Erkannte Fragen" }), el("dd", { id: "imp-result-questions", text: `${answered} von 20 beantwortet` }),
          el("dt", { text: "Tabellen" }), el("dd", { id: "imp-result-tables", text: String(record.tables.length) }),
          el("dt", { text: "Claims / Evidence" }), el("dd", { text: record.counts ? `${record.counts.claims} / ${record.counts.evidence}` : "—" }),
          el("dt", { text: "Medien" }), el("dd", { text: String((record.media || []).length) }),
          coverage ? [el("dt", { text: "Coverage" }), el("dd", {}, badge(coverage.gate), ` Readiness ${pct(coverage.readiness)} · ${coverage.gateReason}`)] : "")),
    ];
    if (record.errors && record.errors.length) parts.push(el("div", { class: "alert error" }, el("strong", { text: "Fehler: " }), el("ul", { class: "list" }, record.errors.map((e) => el("li", { text: e.message })))));
    if (record.warnings && record.warnings.length) parts.push(el("div", { class: "alert warn" }, el("strong", { text: "Hinweise: " }), el("ul", { class: "list" }, record.warnings.map((w) => el("li", { text: w })))));
    parts.push(el("h2", { text: "Fragen" }), el("div", { class: "table-wrap" }, el("table", { id: "imp-questions" },
      el("thead", {}, el("tr", {}, ["Frage", "Titel", "Kritikalität", "Status", "Regelbefunde", "Antwort (normalisiert)"].map((h) => el("th", { text: h })))),
      el("tbody", {}, record.questions.map((q) => el("tr", {}, el("td", { class: "mono", text: q.questionId }), el("td", { text: q.title }), el("td", {}, badge(q.criticality)), el("td", {}, badge(q.answerStatus)), el("td", { text: (q.ruleFindings || []).join(", ") || "—" }), el("td", { text: q.normalizedText ? q.normalizedText.slice(0, 220) + (q.normalizedText.length > 220 ? " …" : "") : "—" })))))));
    if (record.media && record.media.length) {
      const viewable = /\.(png|jpe?g|gif|bmp|webp)$/i;
      parts.push(el("h2", { text: `Medien (${record.media.length})` }), el("div", { class: "media-grid", id: "imp-media" }, record.media.map((m) => {
        const url = `/api/media/${encodeURIComponent(record.importId)}/${encodeURIComponent(m.name)}`;
        return el("a", { href: url, target: "_blank", rel: "noopener" },
          viewable.test(m.name) ? el("img", { src: url, alt: m.name, loading: "lazy" }) : el("div", { class: "file", text: m.name.split(".").pop().toUpperCase() }),
          el("span", { text: `${m.name} · ${fmtSize(m.size)}` }));
      })));
    }
    parts.push(el("h2", { text: "Regelbefunde" }));
    if (record.findings.length) parts.push(el("div", { class: "table-wrap" }, el("table", { id: "imp-findings" },
      el("thead", {}, el("tr", {}, ["Regel", "Kategorie", "Befund", "Anzahl", "Fragen"].map((h) => el("th", { text: h })))),
      el("tbody", {}, record.findings.map((f) => el("tr", {}, el("td", { class: "mono", text: f.ruleId }), el("td", { text: state.meta.ruleCategories[f.category] || f.category }), el("td", { text: f.message }), el("td", { text: f.count }), el("td", { text: (f.questions || []).join(", ") })))))));
    else parts.push(el("p", { class: "muted", text: "Keine Regelbefunde." }));
    $("imp-result").replaceChildren(...parts);
  }

  // ---------- Regelwerk ----------
  loaders.rules = async () => {
    const rules = await api("/api/rules");
    const cats = state.meta.ruleCategories;
    $("rule-filter").replaceChildren(el("button", { class: state.ruleFilter === "" ? "active" : "", text: `Alle (${rules.length})`, onclick: () => { state.ruleFilter = ""; loaders.rules(); } }),
      ...Object.entries(cats).map(([key, label]) => el("button", { class: state.ruleFilter === key ? "active" : "", text: `${label} (${rules.filter((r) => r.category === key).length})`, onclick: () => { state.ruleFilter = key; loaders.rules(); } })));
    const tbody = $("rules-table").tBodies[0];
    const shown = rules.filter((r) => !state.ruleFilter || r.category === state.ruleFilter);
    if (!shown.length) return emptyRow(tbody, 6, "Keine Regeln in dieser Kategorie.");
    tbody.replaceChildren(...shown.map((rule) => ruleRow(rule)));
  };

  function ruleRow(rule) {
    const cats = state.meta.ruleCategories;
    return el("tr", { dataset: { ruleId: rule.id } },
      el("td", { class: "mono", text: rule.id }), el("td", { text: cats[rule.category] }), el("td", { text: rule.source }),
      el("td", { text: rule.target || "—" }), el("td", { text: rule.note || "" }),
      el("td", {}, el("div", { class: "actions" },
        el("button", { class: "small", text: "Bearbeiten", onclick: (e) => editRule(e.target.closest("tr"), rule) }),
        el("button", { class: "small danger", text: "Löschen", onclick: () => deleteRule(rule) }))));
  }

  function editRule(row, rule) {
    const cats = state.meta.ruleCategories;
    const category = el("select", { "aria-label": "Kategorie" });
    fillSelect(category, Object.entries(cats), { value: rule.category });
    const source = el("input", { value: rule.source, "aria-label": "Begriff" });
    const target = el("input", { value: rule.target, "aria-label": "Ziel" });
    const note = el("input", { value: rule.note, "aria-label": "Notiz" });
    row.replaceChildren(el("td", { class: "mono", text: rule.id }), el("td", {}, category), el("td", {}, source), el("td", {}, target), el("td", {}, note),
      el("td", {}, el("div", { class: "actions" },
        el("button", { class: "small primary", text: "Speichern", onclick: async () => {
          try { await api(`/api/rules/${rule.id}`, { method: "PUT", body: { category: category.value, source: source.value, target: target.value, note: note.value } }); toast("Regel gespeichert."); loaders.rules(); }
          catch (e) { toast(e.message, true); }
        } }),
        el("button", { class: "small", text: "Abbrechen", onclick: () => row.replaceWith(ruleRow(rule)) }))));
    source.focus();
  }

  async function deleteRule(rule) {
    if (!confirm(`Regel ${rule.id} („${rule.source}“) wirklich löschen?`)) return;
    try { await api(`/api/rules/${rule.id}`, { method: "DELETE" }); toast("Regel gelöscht."); loaders.rules(); }
    catch (e) { toast(e.message, true); }
  }

  $("rule-new").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await api("/api/rules", { method: "POST", body: { category: $("rule-category").value, source: $("rule-source").value, target: $("rule-target").value, note: $("rule-note").value } });
      $("rule-source").value = ""; $("rule-target").value = ""; $("rule-note").value = "";
      toast("Regel angelegt.");
      loaders.rules();
    } catch (e) { toast(e.message, true); }
  });
  $("rule-preview").addEventListener("click", async () => {
    try {
      const result = await api("/api/rules/preview", { method: "POST", body: { text: $("rule-preview-text").value } });
      $("rule-preview-out").textContent = `${result.normalizedText}\n\n${result.findings.map((f) => `• ${f.ruleId}: ${f.message}`).join("\n") || "Keine Befunde."}`;
    } catch (e) { toast(e.message, true); }
  });

  // ---------- Claims ----------
  loaders.claims = async () => {
    const chapterId = $("claim-chapter").value;
    const status = $("claim-status").value;
    const params = new URLSearchParams();
    if (chapterId) params.set("chapterId", chapterId);
    if (status) params.set("status", status);
    state.claims = await api(`/api/claims?${params}`);
    if (chapterId) {
      const cfg = await chapter(chapterId);
      fillSelect($("claim-new-question"), cfg.questions.map((q) => [q.questionId, `${q.questionId} – ${q.title}`]));
      $("claim-new-box").hidden = false;
    } else {
      $("claim-new-box").hidden = true;
    }
    renderClaims();
  };
  function renderClaims() {
    const term = $("claim-search").value.trim().toLowerCase();
    const rows = state.claims.filter((c) => !term || [c.claimId, c.canonicalStatement, c.role, c.subject, c.questionId].join(" ").toLowerCase().includes(term));
    const tbody = $("claims-table").tBodies[0];
    if (!rows.length) return emptyRow(tbody, 6, "Keine Claims für diese Auswahl.");
    tbody.replaceChildren(...rows.map((c) => el("tr", { class: `clickable${state.selectedClaim === c.claimId ? " selected" : ""}`, dataset: { claimId: c.claimId }, onclick: () => openClaim(c.claimId) },
      el("td", { class: "mono", text: c.claimId }), el("td", { class: "mono", text: c.questionId }),
      el("td", {}, c.canonicalStatement, c.uncertain ? el("span", { class: "badge warn", text: " unsicher" }) : ""),
      el("td", {}, badge(c.criticality)), el("td", { text: `${c.evidenceStatus} (${c.evidenceFactor.toFixed(2).replace(".", ",")})` }), el("td", {}, badge(c.validationStatus)))));
  }
  $("claim-search").addEventListener("input", renderClaims);
  $("claim-chapter").addEventListener("change", () => { state.selectedClaim = null; $("claim-editor").hidden = true; loaders.claims(); });
  $("claim-status").addEventListener("change", () => loaders.claims());

  async function openClaim(claimId) {
    const token = (state.openToken = (state.openToken || 0) + 1);
    state.selectedClaim = claimId;
    renderClaims();
    const claim = state.claims.find((c) => c.claimId === claimId);
    if (!claim) return;
    const cfg = await chapter(claim.chapterId);
    const evidence = await api(`/api/evidence?claimId=${encodeURIComponent(claimId)}`);
    if (token !== state.openToken) return; // a newer claim was opened meanwhile; never render stale data
    const field = (label, name, input) => { input.name = name; input.dataset.field = name; return el("label", {}, label, input); };
    const select = (options, value) => { const s = el("select"); fillSelect(s, options, { value }); return s; };
    const check = (name, label, value) => el("label", { class: "check" }, Object.assign(el("input", { type: "checkbox", "data-field": name }), { checked: !!value }), label);
    const form = el("form", { class: "form-grid", id: "claim-form" },
      el("label", { class: "wide" }, "Aussage (eine überprüfbare Aussage)", Object.assign(el("textarea", { rows: 3, "data-field": "canonicalStatement" }), { value: claim.canonicalStatement })),
      field("Frage", "questionId", select(cfg.questions.map((q) => [q.questionId, `${q.questionId} – ${q.title}`]), claim.questionId)),
      field("Typ", "claimType", select(["FACT", "PERMISSION", "PROCESS", "STATUS", "SOURCE_SYSTEM", "RESTRICTION", "PLAN", "OTHER"], claim.claimType)),
      field("Subject", "subject", el("input", { value: claim.subject || "" })),
      field("Predicate", "predicate", el("input", { value: claim.predicate || "" })),
      el("label", { class: "wide" }, "Object (normalisierte Begriffe)", el("input", { "data-field": "object", value: claim.object || "" })),
      field("Rolle", "role", select([["", "—"], ...state.meta.roles.map((r) => [r.id, r.name]), ...(claim.role && !state.meta.roles.some((r) => r.id === claim.role) ? [[claim.role, claim.role]] : [])], claim.role || "")),
      field("Division", "division", select([["", "—"], "PC", "VAN", "CV", "BOTH"], claim.division || "")),
      field("Markt", "market", el("input", { value: claim.market || "" })),
      field("PI", "pi", el("input", { type: "number", min: 0, max: 99, value: claim.pi ?? "" })),
      field("Reifegrad", "maturity", select([["", "—"], "PRODUCTION", "ACCEPTED", "IN_TEST", "IMPLEMENTED", "PLANNED"], claim.maturity || "")),
      field("Kritikalität", "criticality", select(["CRITICAL", "HIGH", "MEDIUM", "LOW"], claim.criticality)),
      field("Evidence-Status", "evidenceStatus", select(["EVIDENCED", "NOT_EVIDENCED", "NOT_RELEVANT"], claim.evidenceStatus)),
      field("Validierung", "validationStatus", select(state.meta.validationStatuses, claim.validationStatus)),
      field("Confidence (0–1)", "confidence", el("input", { type: "number", min: 0, max: 1, step: 0.05, value: claim.confidence })),
      field("Tags (permission, financial, irreversible, security)", "tags", el("input", { value: (claim.tags || []).join(", ") })),
      el("div", { class: "wide actions" }, check("negated", "Negation", claim.negated), check("conditional", "Bedingung", claim.conditional), check("uncertain", "unsicher", claim.uncertain)),
      el("label", { class: "wide" }, "Review-Notiz", Object.assign(el("textarea", { rows: 2, "data-field": "reviewNote" }), { value: claim.reviewNote || "" })),
      el("div", { class: "wide actions" },
        el("button", { type: "submit", class: "primary", text: "Speichern" }),
        el("button", { type: "button", class: "secondary", text: "Bestätigen (CONFIRMED)", id: "claim-confirm" }),
        el("button", { type: "button", class: "danger", text: "Löschen", id: "claim-delete" })));
    form.addEventListener("submit", async (e) => { e.preventDefault(); await saveClaim(claim, form); });
    form.querySelector("#claim-confirm").addEventListener("click", async () => { form.querySelector('[data-field="validationStatus"]').value = "CONFIRMED"; await saveClaim(claim, form); });
    form.querySelector("#claim-delete").addEventListener("click", async () => {
      if (!confirm(`Claim ${claim.claimId} und zugehörige Evidence löschen?`)) return;
      try { await api(`/api/claims/${claim.claimId}`, { method: "DELETE" }); toast("Claim gelöscht."); $("claim-editor").hidden = true; state.selectedClaim = null; loaders.claims(); }
      catch (err) { toast(err.message, true); }
    });
    const evList = el("div", { class: "table-wrap" }, el("table", {}, el("thead", {}, el("tr", {}, ["Quelle", "Titel/Key", "Stufe", "Status", ""].map((h) => el("th", { text: h })))),
      el("tbody", {}, evidence.length ? evidence.map((ev) => el("tr", {}, el("td", { text: ev.sourceType }), el("td", { text: ev.jiraKey || ev.sourceTitle }), el("td", {}, badge(ev.evidenceStrength, "")), el("td", {}, badge(ev.evidenceStatus)),
        el("td", {}, el("button", { class: "small", text: "Bearbeiten", onclick: () => { showTab("evidence"); } })))) : el("tr", {}, el("td", { colspan: 5, class: "empty", text: "Keine Evidence." })))));
    const evSource = select(state.meta.sourceTypes, "JIRA");
    const evStrength = select(Object.keys(state.meta.evidenceStrengths), "DIRECT");
    const evKey = el("input", { placeholder: "z. B. ONESCM-123" });
    const evTitle = el("input", { placeholder: "Titel oder URL" });
    const evForm = el("form", { class: "form-grid", id: "evidence-new" },
      el("label", {}, "Quelltyp", evSource), el("label", {}, "Stufe", evStrength), el("label", {}, "Jira-Key", evKey), el("label", {}, "Titel / URL", evTitle),
      el("div", { class: "wide actions" }, el("button", { type: "submit", class: "secondary", text: "Evidence zuordnen" })));
    evForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      const title = evTitle.value.trim();
      const isUrl = /^https?:\/\//.test(title);
      try {
        await api("/api/evidence", { method: "POST", body: { claimId: claim.claimId, sourceType: evSource.value, evidenceStrength: evStrength.value, jiraKey: evKey.value.trim(), sourceTitle: isUrl ? "" : title, sourceURL: isUrl ? title : "", evidenceStatus: evStrength.value === "DIRECT_VALIDATED" ? "VALIDATED" : "PROPOSED" } });
        toast("Evidence zugeordnet.");
        await loaders.claims();
        openClaim(claim.claimId);
      } catch (err) { toast(err.message, true); }
    });
    $("claim-editor").dataset.claimId = claim.claimId;
    $("claim-editor").replaceChildren(el("h2", { text: `Claim ${claim.claimId}` }), el("p", { class: "muted", text: `Knowledge Block ${claim.knowledgeId} · Quelle ${claim.sourceImportId}` }), form, el("h2", { text: "Evidence" }), evList, evForm);
    $("claim-editor").hidden = false;
  }

  async function saveClaim(claim, form) {
    const payload = {};
    for (const node of form.querySelectorAll("[data-field]")) {
      const key = node.dataset.field;
      if (node.type === "checkbox") payload[key] = node.checked;
      else if (key === "pi") payload[key] = node.value === "" ? null : Number(node.value);
      else if (key === "confidence") payload[key] = Number(node.value);
      else payload[key] = node.value;
    }
    try {
      await api(`/api/claims/${claim.claimId}`, { method: "PUT", body: payload });
      toast("Claim gespeichert.");
      await loaders.claims();
      openClaim(claim.claimId);
    } catch (e) { toast(e.message, true); }
  }

  $("claim-new").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const claim = await api("/api/claims", { method: "POST", body: { chapterId: $("claim-chapter").value, questionId: $("claim-new-question").value, canonicalStatement: $("claim-new-text").value } });
      $("claim-new-text").value = "";
      toast("Claim angelegt.");
      await loaders.claims();
      openClaim(claim.claimId);
    } catch (e) { toast(e.message, true); }
  });

  // ---------- Evidence ----------
  loaders.evidence = async () => {
    const chapterId = $("ev-chapter").value;
    const rows = await api(`/api/evidence${chapterId ? `?chapterId=${chapterId}` : ""}`);
    const tbody = $("evidence-table").tBodies[0];
    if (!rows.length) return emptyRow(tbody, 8, "Keine Evidence für diese Auswahl.");
    tbody.replaceChildren(...rows.map((ev) => {
      const strength = el("select", { "aria-label": "Evidence-Stufe" });
      fillSelect(strength, Object.keys(state.meta.evidenceStrengths), { value: ev.evidenceStrength });
      const status = el("select", { "aria-label": "Evidence-Status" });
      fillSelect(status, state.meta.evidenceStatuses, { value: ev.evidenceStatus });
      return el("tr", { dataset: { evidenceId: ev.evidenceId } }, el("td", { class: "mono", text: ev.evidenceId }), el("td", { class: "mono", text: ev.claimId }), el("td", { text: ev.sourceType }),
        el("td", { text: ev.jiraKey || ev.sourceTitle || ev.sourceURL }), el("td", {}, strength), el("td", {}, status), el("td", { text: ev.factor.toFixed(2).replace(".", ",") }),
        el("td", {}, el("div", { class: "actions" },
          el("button", { class: "small primary", text: "Speichern", onclick: async () => {
            try { await api(`/api/evidence/${ev.evidenceId}`, { method: "PUT", body: { evidenceStrength: strength.value, evidenceStatus: status.value } }); toast("Evidence gespeichert."); loaders.evidence(); }
            catch (e) { toast(e.message, true); }
          } }),
          el("button", { class: "small danger", text: "Löschen", onclick: async () => {
            if (!confirm(`Evidence ${ev.evidenceId} löschen?`)) return;
            try { await api(`/api/evidence/${ev.evidenceId}`, { method: "DELETE" }); toast("Evidence gelöscht."); loaders.evidence(); }
            catch (e) { toast(e.message, true); }
          } }))));
    }));
  };
  $("ev-chapter").addEventListener("change", () => loaders.evidence());

  // ---------- Tabellen ----------
  loaders.tables = async () => {
    const chapterId = $("tbl-chapter").value;
    const rows = await api(`/api/tables${chapterId ? `?chapterId=${chapterId}` : ""}`);
    const tbody = $("tables-table").tBodies[0];
    if (!rows.length) { $("tbl-preview").hidden = true; return emptyRow(tbody, 6, "Keine Tabellen für diese Auswahl."); }
    const result = [];
    for (const t of rows) {
      const cfg = await chapter(t.chapterId);
      const select = el("select", { "aria-label": "Quellfrage" });
      fillSelect(select, cfg.questions.map((q) => [q.questionId, q.questionId]), { empty: "— keine (Review) —", value: t.sourceQuestionId || "" });
      select.addEventListener("change", async () => {
        try { await api(`/api/tables/${t.tableId}`, { method: "PUT", body: { sourceQuestionId: select.value || null, reviewed: true } }); toast("Zuordnung gespeichert."); loaders.tables(); }
        catch (e) { toast(e.message, true); }
      });
      result.push(el("tr", { class: "clickable", dataset: { tableId: t.tableId } },
        el("td", { class: "mono", text: t.tableId, onclick: () => previewTable(t) }), el("td", { class: "mono", text: t.importId }), el("td", {}, select),
        el("td", { text: `${t.rowCount} × ${t.columnCount}${t.unevenRows ? " (ungleiche Zeilen)" : ""}` }), el("td", {}, t.reviewRequired ? badge("REVIEW") : badge("ok", "ok")),
        el("td", {}, el("div", { class: "actions" }, el("a", { href: `/api/tables/${t.tableId}.json`, text: "JSON" }), el("a", { href: `/api/tables/${t.tableId}.csv`, text: "CSV" }), el("button", { class: "small", text: "Ansehen", onclick: () => previewTable(t) })))));
    }
    tbody.replaceChildren(...result);
  };
  function previewTable(t) {
    const width = t.columnCount;
    const header = t.header && t.header.length ? t.header : Array.from({ length: width }, (_, i) => `Spalte ${i + 1}`);
    $("tbl-preview").replaceChildren(el("h2", { text: `${t.tableId} · Quellfrage ${t.sourceQuestionId || "nicht zugeordnet"}` }),
      el("div", { class: "table-wrap" }, el("table", { id: "tbl-preview-table" }, el("thead", {}, el("tr", {}, header.map((h) => el("th", { text: h })))),
        el("tbody", {}, t.rows.map((r) => el("tr", {}, Array.from({ length: width }, (_, i) => el("td", { text: r[i] ?? "" }))))))));
    $("tbl-preview").hidden = false;
  }
  $("tbl-chapter").addEventListener("change", () => loaders.tables());

  // ---------- Coverage ----------
  loaders.coverage = async () => {
    const chapterId = $("cov-chapter").value;
    const cov = await api(`/api/coverage/${chapterId}`);
    const conflicts = await api(`/api/conflicts?chapterId=${chapterId}`);
    $("cov-summary").replaceChildren(el("div", { class: "summary-grid" },
      el("div", {}, el("div", { class: "muted", text: "Gate" }), el("div", { class: "gate", id: "cov-gate" }, badge(cov.gate))),
      el("div", {}, el("div", { class: "muted", text: "Readiness" }), el("div", { class: "gate", id: "cov-readiness", text: pct(cov.readiness) })),
      el("div", {}, el("div", { class: "muted", text: "Begründung" }), el("div", { text: cov.gateReason })),
      el("div", {}, el("div", { class: "muted", text: "Claims · kritische Fragen · kritische Claims belegt" }), el("div", { text: `${cov.details.claims} · ${cov.details.criticalQuestions} · ${cov.details.criticalClaimsEvidenced}` }))));
    const dims = [["questionCoverage", "Questions", 20], ["evidenceCoverage", "Evidence", 30], ["roleCoverage", "Roles", 15], ["divisionCoverage", "PC/VAN", 15], ["piCoverage", "PI", 10], ["confidence", "Confidence", 10]];
    $("cov-dims").replaceChildren(...dims.map(([key, label, weight]) => {
      const fill = el("div", { class: "bar-fill" });
      fill.style.width = `${Math.min(100, cov[key])}%`;
      return el("div", { class: "kpi", dataset: { dim: key } }, el("div", { class: "label" }, el("strong", { text: label }), el("span", { class: "weight", text: `Gewicht ${weight} %` })), el("div", { class: "value", text: pct(cov[key]) }), el("div", { class: "bar" }, fill));
    }));
    $("cov-blockers").replaceChildren(...(cov.blockers.length ? cov.blockers.map((b) => el("li", { text: b })) : [el("li", { class: "muted", text: "Keine Hard Blocker." })]));
    const tbody = $("conflicts-table").tBodies[0];
    if (!conflicts.length) emptyRow(tbody, 7, "Keine Konflikte erkannt.");
    else tbody.replaceChildren(...conflicts.map((c) => {
      const status = el("select", { "aria-label": "Konfliktstatus" });
      fillSelect(status, state.meta.conflictStatuses, { value: c.status });
      const note = el("input", { value: c.resolutionNote || "", placeholder: "Begründung" });
      return el("tr", { dataset: { conflictId: c.conflictId } }, el("td", { class: "mono", text: c.conflictId }), el("td", { text: c.type }), el("td", {}, badge(c.severity)), el("td", { text: c.description }), el("td", { class: "mono", text: c.claimIds.join(", ") }),
        el("td", {}, status, note), el("td", {}, el("button", { class: "small primary", text: "Speichern", onclick: async () => {
          try { await api(`/api/conflicts/${c.conflictId}`, { method: "PUT", body: { status: status.value, resolutionNote: note.value } }); toast("Konflikt aktualisiert."); loaders.coverage(); }
          catch (e) { toast(e.message, true); }
        } })));
    }));
    const roles = cov.details.roles || {};
    const names = Object.keys(roles);
    const checks = names.length ? Object.keys(roles[names[0]]) : [];
    const table = $("cov-roles");
    table.tHead.replaceChildren(el("tr", {}, el("th", { text: "Rolle" }), checks.map((c) => el("th", { text: c }))));
    if (!names.length) emptyRow(table.tBodies[0], 1, "Keine Rollen im Kapitel konfiguriert.");
    else table.tBodies[0].replaceChildren(...names.map((n) => el("tr", {}, el("td", { text: labelFor.role(n) }), checks.map((c) => el("td", { text: roles[n][c] ? "✓" : "—" })))));
  };
  $("cov-chapter").addEventListener("change", () => loaders.coverage());
  $("cov-refresh").addEventListener("click", () => loaders.coverage().then(() => toast("Coverage neu berechnet.")).catch((e) => toast(e.message, true)));

  // ---------- Synchronisation ----------
  loaders.sync = async () => {
    const status = await api("/api/sync/status");
    renderSyncStatus(status);
    await loadCleanup();
  };
  function renderSyncStatus(s) {
    $("sync-path").value = s.path || "";
    $("sync-status").replaceChildren(
      el("dt", { text: "Konfiguriert durch" }), el("dd", { text: s.configuredBy === "settings" ? "App-Einstellung" : s.configuredBy === "none" ? "—" : s.configuredBy }),
      el("dt", { text: "Existiert" }), el("dd", { text: s.exists ? "ja" : "nein" }),
      el("dt", { text: "Beschreibbar" }), el("dd", { text: s.writable ? "ja" : "nein" }),
      el("dt", { text: "Letzte lokale Änderung" }), el("dd", { text: fmtDate(s.lastLocalChange) }),
      el("dt", { text: "Lokaler Status" }), el("dd", { id: "sync-local-status" }, badge(s.localStatus), " ", el("span", { class: "muted", text: s.reason })),
      el("dt", { text: "Cloudstatus" }), el("dd", {}, badge(s.cloudStatus), " ", el("span", { class: "muted", text: s.cloudNote })));
  }
  $("sync-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    try { renderSyncStatus(await api("/api/sync/settings", { method: "POST", body: { onedriveRoot: $("sync-path").value } })); toast("Pfad gespeichert."); window.dispatchEvent(new Event("onescm-changed")); }
    catch (e) { toast(e.message, true); }
  });
  $("sync-reset").addEventListener("click", async () => {
    try { renderSyncStatus(await api("/api/sync/settings", { method: "POST", body: { onedriveRoot: "" } })); toast("Pfad aus ONESCM_LOCAL_ONEDRIVE_ROOT wird verwendet."); window.dispatchEvent(new Event("onescm-changed")); }
    catch (e) { toast(e.message, true); }
  });
  $("sync-structure").addEventListener("click", async () => {
    try { const r = await api("/api/sync/structure", { method: "POST", body: {} }); toast(r.created.length ? `${r.created.length} Ordner angelegt.` : "Ordnerstruktur ist vollständig."); loaders.sync(); }
    catch (e) { toast(e.message, true); }
  });
  $("sync-export").addEventListener("click", async () => {
    const button = $("sync-export");
    button.disabled = true;
    try {
      const r = await api("/api/sync/export", { method: "POST", body: { chapterId: $("sync-chapter").value } });
      $("sync-result").replaceChildren(el("div", { class: "alert ok", id: "sync-export-ok" }, `Export ${r.chapterId}: ${r.files.length} Dateien lokal bereitgestellt. Manifest: ${r.manifest} · Paket: ${r.package}. Cloudstatus: ${r.cloudStatus}.`),
        el("ul", { class: "list mono" }, r.files.map((f) => el("li", { text: f }))));
      toast("Export abgeschlossen.");
      window.dispatchEvent(new Event("onescm-changed"));
      loaders.sync();
    } catch (e) {
      $("sync-result").replaceChildren(el("div", { class: "alert error", text: e.message }));
    } finally { button.disabled = false; }
  });

  // ---------- Handbuchstand ----------
  $("man-preview").addEventListener("click", async () => {
    const url = `/api/manual/${$("man-chapter").value}/preview?stage=${encodeURIComponent($("man-stage").value)}`;
    const response = await fetch(url);
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      $("man-frame").hidden = true;
      $("man-result").replaceChildren(el("div", { class: "alert error", id: "man-error", text: data.error || `Fehler (${response.status}).` }));
      return;
    }
    $("man-result").replaceChildren();
    $("man-frame").src = url;
    $("man-frame").hidden = false;
  });
  $("man-generate").addEventListener("click", async () => {
    const button = $("man-generate");
    button.disabled = true;
    try {
      const r = await api(`/api/manual/${$("man-chapter").value}`, { method: "POST", body: { stage: $("man-stage").value } });
      $("man-result").replaceChildren(el("div", { class: "alert ok", id: "man-ok" },
        `Handbuchstand ${r.stage} für ${r.chapterId}: ${r.stats.claims} Aussagen in ${r.stats.questionsWithContent} von ${r.stats.questions} Fragen, ${r.stats.tables} Tabelle(n). Cloudstatus: ${r.cloudStatus}.`),
        el("ul", { class: "list mono" }, r.files.map((f) => el("li", { text: f }))));
      window.dispatchEvent(new Event("onescm-changed"));
    } catch (e) {
      $("man-result").replaceChildren(el("div", { class: "alert error", id: "man-error", text: e.message }));
    } finally { button.disabled = false; }
  });

  // ---------- Datenbereinigung ----------
  let cleanupItems = [];
  async function loadCleanup() {
    const r = await api("/api/cleanup/preview");
    $("clean-rules").replaceChildren(...r.rules.map((rule) => el("li", {}, el("code", { text: rule.id }), " – ", rule.description)));
    cleanupItems = r.items;
    if (!cleanupItems.length) {
      $("clean-result").replaceChildren(el("p", { class: "muted", id: "clean-empty", text: "Nach den Regeln ist derzeit nichts zu bereinigen." }));
      $("clean-run").disabled = true;
      return;
    }
    $("clean-result").replaceChildren(el("div", { class: "table-wrap" }, el("table", { id: "clean-table" },
      el("thead", {}, el("tr", {}, ["", "Aktion", "Eintrag", "Datei", "Regel", "Grund"].map((h) => el("th", { text: h })))),
      el("tbody", {}, cleanupItems.map((item) => el("tr", { dataset: { target: item.target } },
        el("td", {}, Object.assign(el("input", { type: "checkbox", "aria-label": `${item.target} bereinigen` }), { checked: true })),
        el("td", {}, badge(item.action.toUpperCase(), item.action === "archive" ? "warn" : "bad")), el("td", { class: "mono", text: item.target }),
        el("td", { text: item.label }), el("td", { class: "mono", text: item.rule }), el("td", { text: item.reason })))))));
    $("clean-run").disabled = false;
  }
  $("clean-preview").addEventListener("click", () => loadCleanup().catch((e) => toast(e.message, true)));
  $("clean-run").addEventListener("click", async () => {
    const targets = [...document.querySelectorAll("#clean-table tbody tr")].filter((tr) => tr.querySelector("input").checked).map((tr) => tr.dataset.target);
    if (!targets.length) return toast("Keine Einträge ausgewählt.", true);
    if (!confirm(`${targets.length} Einträge bereinigen? Gelöschte Einträge lassen sich nicht wiederherstellen.`)) return;
    try {
      const r = await api("/api/cleanup", { method: "POST", body: { targets, confirm: true } });
      toast(`${r.done.length} bereinigt${r.skipped.length ? `, ${r.skipped.length} übersprungen` : ""}.`);
      window.dispatchEvent(new Event("onescm-changed"));
      await loadCleanup();
    } catch (e) { toast(e.message, true); }
  });

  // ---------- Interner Chat ----------
  let chatInfo = null;
  let chatSession = "";
  try { chatSession = sessionStorage.getItem("onescm360-session") || ""; } catch { /* ignore */ }
  if (!chatSession) {
    chatSession = (crypto.randomUUID ? crypto.randomUUID() : String(Date.now()) + Math.random().toString(16).slice(2)).replace(/[^A-Za-z0-9-]/g, "");
    try { sessionStorage.setItem("onescm360-session", chatSession); } catch { /* ignore */ }
  }
  const CHAT_EXAMPLES = ["Was gilt bei Service Contract Cancellation für PC?", "Berechne die Coverage für CH01", "Validiere Kapitel 1",
    "Zeige unbelegte kritische Claims", "Wofür steht PI?", "Was steht in Jira zu ONESCM-123?", "Exportiere CH01 als Review-Paket",
    "Suche im Internet nach dem Aktienkurs"];

  async function chatApi(path, body) {
    const response = await fetch(path, { method: "POST", headers: { "X-oneSCM360": "1", "X-oneSCM360-Session": chatSession, "Content-Type": "application/json" }, body: JSON.stringify(body) });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error((data && data.error) || `Serverfehler (${response.status}).`);
    return data;
  }

  loaders.chat = async () => {
    if (!chatInfo) {
      chatInfo = await api("/api/chat/info");
      const p = chatInfo.policy;
      const yesNo = (v) => (v ? "ja" : "nein");
      $("chat-policy").replaceChildren(
        el("dt", { text: "Modus" }), el("dd", {}, badge(p.securityMode, "ok")),
        el("dt", { text: "Default" }), el("dd", {}, badge(p.defaultPolicy, "bad")),
        el("dt", { text: "Internet / externes LLM" }), el("dd", { text: `${yesNo(p.externalNetwork)} / ${yesNo(p.externalLlm)}` }),
        el("dt", { text: "Externe Suche / Telemetrie" }), el("dd", { text: `${yesNo(p.externalSearch)} / ${yesNo(p.telemetryExternal)}` }),
        el("dt", { text: "Netzwerksperre" }), el("dd", { id: "chat-network-guard", text: p.networkGuard ? "aktiv (nur localhost)" : "inaktiv" }),
        el("dt", { text: "Benutzer" }), el("dd", { text: `${p.user} – ${p.authentication}` }),
        el("dt", { text: "Quellen" }), el("dd", { text: p.allowedSources.join(", ") }),
        el("dt", { text: "Local First" }), el("dd", {}, el("ol", { class: "local-first" }, [...p.localFirstOrder.map((step) => {
          const [tool, status] = step.split(":");
          return el("li", {}, el("code", { text: tool }), status ? ` (${status.replace(",", ", ")})` : "");
        }), el("li", { text: "Ende: „Keine freigegebene Quelle gefunden.“ – kein Internet" })])));
      $("chat-registry").tBodies[0].replaceChildren(...chatInfo.tools.map((t) => el("tr", { dataset: { tool: t.name } },
        el("td", { class: "mono", text: t.name }), el("td", { text: t.purpose }), el("td", { text: t.source }),
        el("td", {}, badge(t.operation, t.writes ? "warn" : "ok")), el("td", { text: t.network }),
        el("td", { text: t.writes ? "Ja (mit Bestätigung)" : "Nein" }),
        el("td", {}, t.connector ? badge("aktiv", "ok") : badge("Connector fehlt", "warn")))));
      $("chat-examples").replaceChildren(...CHAT_EXAMPLES.map((q) => el("button", { type: "button", text: q, onclick: () => sendChat(q) })));
      updateRouterInfo();
    }
    if (!$("chat-log").children.length) $("chat-log").append(el("div", { class: "chat-empty", text: "Stellen Sie eine Frage zum internen Wissensbestand – oder wählen Sie ein Beispiel." }));
    loadAudit();
  };
  function updateRouterInfo() {
    if (!chatInfo) return;
    $("chat-router-info").textContent = $("chat-mode").value === "model"
      ? `Modell „${chatInfo.router.model}“ unter ${chatInfo.router.url} (nur localhost). Erhält nur die Funktionsdeklarationen der Registry. Ist es nicht erreichbar, antwortet der Regel-Router.`
      : "Regelbasierte Zuordnung – ohne KI-Modell, offline und reproduzierbar.";
  }
  $("chat-mode").addEventListener("change", updateRouterInfo);

  async function loadAudit() {
    try {
      const entries = await api("/api/chat/audit");
      $("chat-audit").replaceChildren(...(entries.length ? entries.slice(0, 30).map((e) => el("li", {},
        el("span", { class: "muted", text: new Date(e.timestamp).toLocaleTimeString("de-DE") }), badge(e.result), el("span", { class: "mono", text: e.tool }),
        el("span", { class: "muted", text: `${e.operation || "—"}${e.executed ? " · ausgeführt" : ""}` }))) : [el("li", { class: "muted", text: "Noch keine Einträge." })]));
    } catch { /* ignore */ }
  }
  $("chat-audit-refresh").addEventListener("click", loadAudit);

  const callText = (call) => `${call.tool}(${JSON.stringify(call.arguments)})`;

  async function goTo(link) {
    if (!link) return;
    if (link.tab === "claims") {
      $("claim-chapter").value = link.chapterId || "";
      showTab("claims");
      await loaders.claims();
      if (link.claimId) openClaim(link.claimId);
      return;
    }
    if (link.tab === "coverage" && link.chapterId) $("cov-chapter").value = link.chapterId;
    showTab(link.tab);
  }

  function resultItem(item) {
    if (item.type === "metric") {
      const fill = el("div", { class: "bar-fill" });
      fill.style.width = `${Math.min(100, item.value)}%`;
      return el("li", {}, el("div", { class: "metric" }, el("span", { text: item.label }), el("div", { class: "bar" }, fill), el("strong", { text: pct(item.value) })));
    }
    const link = item.type === "claim" ? { tab: "claims", chapterId: item.chapterId, claimId: item.id }
      : item.type === "evidence" && item.claimId ? { tab: "claims", chapterId: item.chapterId, claimId: item.claimId }
      : item.type === "example" ? null : null;
    const node = el("li", { class: link || item.type === "example" ? "clickable" : "", title: link ? "Im Register öffnen" : null,
      onclick: link ? () => goTo(link) : item.type === "example" ? () => sendChat(item.label) : null },
      item.id ? el("span", { class: "mono", text: item.id }) : null,
      item.chapterId ? el("span", { class: "mono", text: item.questionId || item.chapterId }) : null,
      el("span", { class: "label", text: item.label }),
      item.role ? el("span", { class: "badge", text: labelFor.role(item.role) }) : null,
      item.division ? el("span", { class: "badge", text: item.division }) : null,
      item.criticality ? badge(item.criticality) : null,
      item.status ? badge(item.status, { Released: "ok", Reviewed: "warn", Draft: "warn", BLOCKED: "bad", WARNING: "warn" }[item.status]) : null,
      item.evidence !== undefined ? el("span", { class: "muted", text: `Evidence ${Number(item.evidence).toFixed(2).replace(".", ",")}` }) : null);
    return node;
  }

  function feedbackBar(answer) {
    const box = el("div", { class: "feedback" }, "Passt die Funktion?");
    const done = (text) => box.replaceChildren(el("span", { text }));
    const send = async (tool) => {
      try {
        await api("/api/chat/feedback", { method: "POST", body: { message: answer.message, tool, arguments: tool === answer.call.tool ? answer.call.arguments : {}, correct: true } });
        done(tool === answer.call.tool ? "✓ Als Trainingsbeispiel gespeichert." : `✓ Korrektur „${tool}“ als Trainingsbeispiel gespeichert.`);
      } catch (e) { toast(e.message, true); }
    };
    const select = el("select", { "aria-label": "Richtige Funktion" });
    fillSelect(select, chatInfo.tools.map((t) => t.name).filter((n) => n !== answer.call.tool), { empty: "andere Funktion wählen …" });
    select.addEventListener("change", () => { if (select.value) send(select.value); });
    if (chatInfo.tools.some((t) => t.name === answer.call.tool)) box.append(el("button", { type: "button", class: "small", text: "✓ Ja", onclick: () => send(answer.call.tool) }));
    box.append(select);
    return box;
  }

  function stepList(steps) {
    if (!steps || !steps.length) return null;
    return el("ol", { class: "steps" }, steps.map((step, i) => el("li", { class: step.found === false ? "skipped" : "" },
      el("span", { class: "muted", text: `${i + 1}.` }), el("span", { class: "call", text: callText(step) }), badge(step.policy.result),
      step.found === false ? el("span", { class: "muted", text: "kein Treffer → nächste Quelle" }) : null,
      step.policy.result === "DENIED" ? el("span", { class: "row-error", text: step.policy.reason }) : null)));
  }

  function renderAnswer(answer) {
    const parts = [
      el("div", {}, el("span", { class: "call", text: answer.call.tool === "none" ? "keine Funktion" : callText(answer.call) }),
        el("span", { class: "call-meta", text: answer.router === "model" ? "Router: lokales Modell" : answer.router === "confirmed" ? "bestätigt" : "Router: Regeln" })),
      ...answer.notes.map((n) => el("div", { class: "chat-note", text: n })),
      stepList(answer.steps && answer.steps.length > 1 || answer.denied ? answer.steps : null),
      el("h3", { text: answer.title }),
      el("p", { text: answer.text }),
    ];
    if (answer.items && answer.items.length) parts.push(el("ul", { class: "result-list" }, answer.items.map(resultItem)));
    if (answer.pendingConfirmation) {
      const button = el("button", { type: "button", class: "primary", text: "Export jetzt ausführen" });
      button.addEventListener("click", async () => {
        button.disabled = true;
        try {
          const result = await chatApi("/api/chat/execute", { tool: answer.call.tool, arguments: answer.call.arguments, confirm: true });
          button.closest(".msg").after(renderAnswer({ ...result, message: answer.message }));
          button.replaceWith(el("span", { class: "muted", text: "✓ Bestätigt und ausgeführt." }));
          window.dispatchEvent(new Event("onescm-changed"));
        } catch (e) { toast(e.message, true); button.disabled = false; }
        loadAudit();
      });
      parts.push(el("div", { class: "actions" }, button, el("span", { class: "muted", text: "Schreibt nur in den lokalen OneDrive-Ordner." })));
    }
    if (answer.link) parts.push(el("div", { class: "actions" }, el("button", { type: "button", class: "small secondary", text: "Im Register öffnen", onclick: () => goTo(answer.link) })));
    if (answer.message && !answer.denied) parts.push(feedbackBar(answer));
    return el("div", { class: `msg bot${answer.denied ? " denied" : ""}`, dataset: { tool: answer.call.tool } }, parts);
  }

  async function sendChat(text) {
    const message = (text ?? $("chat-input").value).trim();
    if (!message) return;
    await loaders.chat();
    const log = $("chat-log");
    log.querySelector(".chat-empty")?.remove();
    log.append(el("div", { class: "msg user", text: message }));
    const pending = el("div", { class: "msg bot pending", text: "Router wählt eine Funktion, Policy prüft …" });
    log.append(pending);
    log.scrollTop = log.scrollHeight;
    $("chat-input").value = "";
    $("chat-send").disabled = true;
    try {
      const answer = await chatApi("/api/chat", { message, mode: $("chat-mode").value });
      pending.replaceWith(renderAnswer(answer));
    } catch (e) {
      pending.replaceWith(el("div", { class: "msg bot" }, el("div", { class: "chat-note", text: e.message })));
    } finally {
      $("chat-send").disabled = false;
      log.scrollTop = log.scrollHeight;
      $("chat-input").focus();
      loadAudit();
    }
  }
  $("chat-form").addEventListener("submit", (e) => { e.preventDefault(); sendChat(); });
  $("chat-input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); sendChat(); } });
  $("chat-eval").addEventListener("click", async () => {
    const button = $("chat-eval");
    button.disabled = true;
    $("chat-eval-result").replaceChildren(el("p", { class: "muted", text: "Testsuite läuft …" }));
    try {
      const r = await api("/api/chat/evaluate", { method: "POST", body: { mode: $("chat-mode").value } });
      const failed = r.results.filter((x) => !x.ok);
      $("chat-eval-result").replaceChildren(
        el("div", { class: `alert ${failed.length ? "warn" : "ok"}`, id: "chat-eval-score", text: `Success: ${r.passed} / ${r.total}` }),
        failed.length ? el("ul", { class: "list" }, failed.map((f) => el("li", {}, `„${f.message}“: erwartet `, el("code", { text: f.expected.tool }), ", erhalten ", el("code", { text: callText(f.actual) })))) : "");
    } catch (e) { $("chat-eval-result").replaceChildren(el("div", { class: "alert error", text: e.message })); }
    finally { button.disabled = false; loadAudit(); }
  });

  // ---------- Dokumentation ----------
  loaders.docs = async () => {
    const { readme } = await api("/api/docs");
    $("docs-body").replaceChildren(...renderMarkdown(readme));
  };
  function inline(text) {
    const parts = [];
    const re = /(`[^`]+`|\*\*[^*]+\*\*)/g;
    let last = 0, m;
    while ((m = re.exec(text))) {
      if (m.index > last) parts.push(text.slice(last, m.index));
      parts.push(m[0].startsWith("`") ? el("code", { text: m[0].slice(1, -1) }) : el("strong", { text: m[0].slice(2, -2) }));
      last = m.index + m[0].length;
    }
    parts.push(text.slice(last));
    return parts;
  }
  function renderMarkdown(md) {
    const out = [];
    const lines = md.split(/\r?\n/);
    let list = null, code = null, table = null;
    for (const line of lines) {
      if (line.startsWith("```")) {
        if (code) { out.push(el("pre", {}, el("code", { text: code.join("\n") }))); code = null; } else code = [];
        continue;
      }
      if (code) { code.push(line); continue; }
      if (/^\|.*\|$/.test(line.trim())) {
        const cells = line.trim().slice(1, -1).split("|").map((c) => c.trim());
        if (cells.every((c) => /^:?-+:?$/.test(c))) continue;
        if (!table) { table = el("table", {}, el("thead", {}, el("tr", {}, cells.map((c) => el("th", {}, inline(c))))), el("tbody")); out.push(el("div", { class: "table-wrap" }, table)); }
        else table.tBodies[0].append(el("tr", {}, cells.map((c) => el("td", {}, inline(c)))));
        continue;
      }
      table = null;
      const heading = line.match(/^(#{1,3})\s+(.*)/);
      const item = line.match(/^\s*(?:[-*]|\d+\.)\s+(.*)/);
      if (item) { if (!list) { list = el("ul"); out.push(list); } list.append(el("li", {}, inline(item[1]))); continue; }
      list = null;
      if (heading) out.push(el(`h${heading[1].length}`, {}, inline(heading[2])));
      else if (line.trim()) out.push(el("p", {}, inline(line)));
    }
    return out;
  }

  // ---------- init ----------
  async function init() {
    state.meta = await api("/api/meta");
    $("app-version").textContent = `v${state.meta.version}`;
    for (const id of ["cov-chapter", "sync-chapter", "man-chapter"]) fillSelect($(id), chapterOptions());
    fillSelect($("imp-chapter"), fieldOptions.chapterId());
    fillSelect($("imp-role"), fieldOptions.role());
    fillSelect($("imp-domain"), fieldOptions.domain());
    for (const id of ["claim-chapter", "ev-chapter", "tbl-chapter"]) fillSelect($(id), chapterOptions(), { empty: "Alle Kapitel" });
    fillSelect($("imp-language"), state.meta.languages, { value: "DE" });
    fillSelect($("imp-source"), state.meta.sourceTypes);
    fillSelect($("claim-status"), state.meta.validationStatuses, { empty: "Alle" });
    fillSelect($("rule-category"), Object.entries(state.meta.ruleCategories));
    let start = "dashboard";
    try { start = localStorage.getItem("onescm360-tab") || "dashboard"; } catch { /* ignore */ }
    if (!document.querySelector(`#tabs button[data-tab="${start}"]`)) start = "dashboard";
    refreshTopStatus();
    showTab(start);
  }
  init().catch((err) => toast(err.message, true));
})();
