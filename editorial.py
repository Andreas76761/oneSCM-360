"""Editorial rules and lossless outline reimport, independent of transport/UI."""
import copy
import hashlib
import json
import publication

KINDS = ["Redaktionell", "Fachlich", "Automatisch", "Zusammengestellt"]
CONTENT_KINDS = ["Anleitung", "Ziel", "Voraussetzung", "Schritt", "Warnhinweis", "Hintergrund", "Sonderfall", "FAQ", "Glossarbegriff"]
ESSENTIAL = {"Voraussetzung", "Schritt", "Warnhinweis"}


def scope_defaults():
    return {"Kompakt": CONTENT_KINDS[:5] + ["Glossarbegriff"], "Standard": CONTENT_KINDS[:5] + ["FAQ", "Glossarbegriff"], "Ausführlich": list(CONTENT_KINDS)}


def validate_scopes(value):
    from app import Invalid
    if not isinstance(value, dict) or set(value) != set(scope_defaults()):
        raise Invalid("Umfangsregeln fehlen.")
    if any(not isinstance(v, list) or any(k not in CONTENT_KINDS for k in v) for v in value.values()):
        raise Invalid("Ungültige Inhaltstypen in Umfangsregeln.")
    return {k: list(dict.fromkeys(v)) for k, v in value.items()}


def defaults(c):
    return {"titles": {}, "kind": "Fachlich", "inclusion": "Pflicht" if c.get("mandatory") else "Bedingt",
            "selected": True, "conditions": {}, "expected": [], "empty_rule": "Blockieren" if c.get("mandatory") else "Auslassen",
            "status": "Entwurf", "generator": "Keiner"}


def validate_chapter(c):
    from app import Invalid, clean_text, choice, boolean, LANGUAGES, ROLES, SCOPES
    if not isinstance(c.get("config", {}), dict):
        raise Invalid("Ungültige Kapitelkonfiguration.")
    value = {**defaults(c), **c.get("config", {})}
    result = {key: choice(value[key], values, key) for key, values in [
        ("kind", KINDS), ("inclusion", ["Pflicht", "Bedingt", "Manuell"]),
        ("empty_rule", ["Blockieren", "Auslassen"]), ("status", ["Entwurf", "In Prüfung", "Freigegeben"]),
        ("generator", ["Keiner", "Inhaltsverzeichnis", "Glossar", "FAQ"])]}
    result["selected"] = boolean(value["selected"], "Kapitelauswahl")
    if not isinstance(value["titles"], dict) or any(k not in LANGUAGES for k in value["titles"]):
        raise Invalid("Ungültige Titelsprachen.")
    result["titles"] = {k: clean_text(v, "Sprachtitel", 300).strip() for k, v in value["titles"].items()}
    expected = value["expected"]
    if not isinstance(expected, list) or any(x not in ["Text", "Bild", "Klickstrecke", "FAQ"] for x in expected):
        raise Invalid("Ungültige Inhaltsvorgaben.")
    result["expected"] = list(dict.fromkeys(expected))
    conditions = value["conditions"]
    if not isinstance(conditions, dict) or set(conditions) - {"role", "scope", "market", "division", "release", "language"}:
        raise Invalid("Ungültige Kapitelbedingungen.")
    result["conditions"] = {}
    for key, values in conditions.items():
        if not isinstance(values, list) or len(values) > 100 or any(not isinstance(v, str) for v in values):
            raise Invalid("Bedingungen müssen Listen sein.")
        result["conditions"][key] = [clean_text(v, key, 100).strip() for v in values if v]
        choices = {"role": ROLES, "scope": SCOPES, "language": LANGUAGES, "division": ["Van", "PC"]}.get(key)
        if choices and any(v not in choices for v in values):
            raise Invalid("Ungültige Kapitelbedingung: " + key)
    return result


def validate_block(b):
    from app import Invalid, clean_text, choice, SCOPES
    variants = b.get("variants", {})
    if not isinstance(variants, dict) or set(variants) - set(SCOPES):
        raise Invalid("Ungültige Umfangsfassungen.")
    if any(not isinstance(v, dict) for v in variants.values()):
        raise Invalid("Ungültige Textfassung.")
    assignment = b.get("assignment", {})
    if not isinstance(assignment, dict):
        raise Invalid("Ungültige Zuordnung.")
    restrictions = validate_chapter({"config": {"conditions": assignment.get("conditions", {})}})["conditions"]
    result = {"assignment": {"conditions": restrictions, "note": clean_text(assignment.get("note", ""), "Zuordnungsvermerk", 5000)}, "content_kind": choice(b.get("content_kind", "Anleitung"), CONTENT_KINDS, "Inhaltstyp"),
            "variants": {k: {"text": clean_text(v.get("text", ""), "Fassung", 100000),
                             "status": choice(v.get("status", "Entwurf"), ["Entwurf", "Freigegeben"], "Fassungsstatus")}
                         for k, v in variants.items()}}
    result.update(publication.validate_block(b))
    result["text_format"] = choice(b.get("text_format", "plain"), ["plain", "markdown"], "Textformat")
    if b.get("library_ref"):
        ref = b["library_ref"]
        if not isinstance(ref, dict) or type(ref.get("revision")) is not int or ref["revision"] < 1:
            raise Invalid("Ungültige Bausteinreferenz.")
        result["library_ref"] = {"id": clean_text(ref.get("id"), "Bibliotheks-ID", 100), "revision": ref["revision"]}
        result["library_title"] = clean_text(b.get("library_title", ""), "Bibliothekstitel", 300)
        if b.get("translation"):
            result["translation"] = b["translation"]
    return result


def eligible(config, p):
    if config["inclusion"] == "Manuell" and not config["selected"]:
        return False
    return all(not values or p[key] in values or (key == "division" and p[key] == "Beide")
               for key, values in config["conditions"].items())


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def compose(outline, p):
    from app import validate_profile, exclusion
    p = validate_profile(p)
    rows, warnings, stack = [], [], []
    manifest, image_manifest = [], []
    keys = [e["key"] for c in outline["chapters"] for b in c["blocks"] for e in b.get("evidence", [])]
    outline_validity = publication.effective(outline.get("validity", []), p)
    if not outline_validity["matches"]:
        warnings.append(outline_validity["reason"])
    elif outline_validity["state"] not in [None, "Freigegeben"]:
        warnings.append("Zeitlicher Gliederungsstatus ist nicht freigegeben.")
    for c in outline["chapters"]:
        config = validate_chapter(c)
        while stack and stack[-1][0] >= c["level"]:
            stack.pop()
        temporal_profile = p
        if p["division"] == "Beide" and len(config["conditions"].get("division", [])) == 1:
            temporal_profile = {**p, "division": config["conditions"]["division"][0]}
        cv = publication.effective(c.get("validity", []), temporal_profile)
        profile_allowed = outline_validity["matches"] and eligible(config, p) and all(x[1] for x in stack)
        allowed = profile_allowed and cv["matches"]
        if profile_allowed and (cv.get("conflict") or cv.get("requires_date") or (allowed and cv["state"] not in [None, "Freigegeben"])):
            warnings.append(f"Kapitel „{c['title']}“: Zeitstatus prüfen. " + cv["reason"])
        stack.append((c["level"], allowed))
        mandatory = config["inclusion"] == "Pflicht"
        title = config["titles"].get(p["language"]) or c["title"]
        included, excluded = [], []
        if allowed:
            for original in c["blocks"]:
                b = copy.deepcopy(original)
                extra = validate_block(b)
                variant = extra["variants"].get(p["scope"])
                variant_active = bool(variant and variant["text"].strip())
                if variant_active:
                    b["text"] = variant["text"]
                    if variant["status"] != "Freigegeben":
                        b["status"] = "Entwurf"
                # Essential instructions are retained even in compact scope.
                if extra["content_kind"] in ESSENTIAL or variant_active:
                    b["scope"] = "*"
                reason = exclusion(b, p)
                document_type = outline.get("metadata", {}).get("document_type", "Handbuch")
                if document_type in publication.DOCUMENTS and not extra["uses"][document_type]:
                    reason = "Für diese Dokumentart nicht ausgewählt."
                scopes = outline.get("scope_rules", scope_defaults())
                if extra["content_kind"] not in ESSENTIAL and extra["content_kind"] not in scopes[p["scope"]] and not variant_active:
                    reason = "Inhaltstyp ist für diesen Umfang nicht ausgewählt."
                if not eligible({"inclusion": "Bedingt", "conditions": extra["assignment"]["conditions"]}, p):
                    reason = "Gültigkeit dieser Kapitelzuordnung passt nicht zum Ausgabeprofil."
                if not reason:
                    block_profile = {**p, "division": b["division"]} if p["division"] == "Beide" and b["division"] in ["Van", "PC"] else temporal_profile
                    bv = publication.effective(extra["validity"], block_profile)
                    if not bv["matches"]:
                        reason = bv["reason"]
                        if bv.get("conflict") or bv.get("requires_date"):
                            warnings.append(f"Kapitel „{c['title']}“: " + reason)
                    elif bv["state"] not in [None, "Freigegeben"]:
                        b["status"] = "Entwurf"
                        reason = exclusion(b, p)
                if not reason:
                    b["text"] = publication.public_text(b["text"], keys)
                    if not b["text"].strip():
                        reason = "Baustein enthält nach Entfernen interner Ticketverweise keinen Lesertext."
                if reason:
                    excluded.append({"id": b["id"], "reason": reason})
                else:
                    public = {k: b[k] for k in ["text", "source", "status", "division"]}
                    public.update(note="", id=b["id"], content_kind=extra["content_kind"], text_format=extra["text_format"])
                    if extra["evidence"] and any(not e["verified"] for e in extra["evidence"]):
                        warnings.append(f"Kapitel „{c['title']}“: interner Textnachweis noch nicht geprüft.")
                    if extra["content_kind"] in ["Glossarbegriff", "FAQ"] and b.get("library_title"):
                        public["text"] = b["library_title"] + "\n" + public["text"]
                    included.append(public)
                    manifest.append({"chapter_id": c["id"], "block_id": b["id"],
                                     "validity_decision": bv, "content_hash": fingerprint(original), "variant": p["scope"] if variant_active else "Basis",
                                     "language": b["language"], "status": b["status"], "library_ref": original.get("library_ref"), "translation": original.get("translation") })
        from media import compose_chapter
        figures, media_warnings, image_refs = compose_chapter(c, p) if allowed else ([], [], [])
        warnings.extend(media_warnings)
        image_manifest.extend(image_refs)
        generated = allowed and config["generator"] == "Inhaltsverzeichnis"
        visible = allowed and (bool(included) or bool(figures) or mandatory or generated or config["empty_rule"] == "Blockieren")
        row = {"id": c["id"], "title": title, "level": c["level"], "mandatory": mandatory,
               "blocks": included, "figures": figures, "excluded": excluded, "visible": visible, "config": config, "generated": generated}
        if allowed:
            if not included and not figures and not generated and (mandatory or config["empty_rule"] == "Blockieren"):
                warnings.append(f"Kapitel „{title}“ hat keinen passenden Inhalt; Veröffentlichung gesperrt.")
            if config["titles"] and not config["titles"].get(p["language"]):
                warnings.append(f"Kapitel „{title}“: Titelübersetzung für {p['language']} fehlt.")
            for expected in config["expected"]:
                present = {"Text": bool(included) or generated,
                           "FAQ": any(b["content_kind"] == "FAQ" for b in included),
                           "Bild": bool(figures),
                           "Klickstrecke": any(f["kind"] == "Klickstrecke" for f in figures)}[expected]
                if not present:
                    warnings.append(f"Kapitel „{title}“: Erwarteter Inhalt {expected} fehlt.")
        rows.append(row)
    stack, counts = [], [0] * 6
    for i, row in enumerate(rows):
        while stack and rows[stack[-1]]["level"] >= row["level"]:
            stack.pop()
        if row["visible"]:
            for ancestor in stack:
                rows[ancestor]["visible"] = True
        stack.append(i)
    for row in rows:
        row["number"] = ""
        if row["visible"]:
            idx = row["level"] - 1
            counts[idx] += 1
            counts[idx + 1:] = [0] * (5 - idx)
            row["number"] = ".".join(map(str, counts[:idx + 1]))
    toc = "\n".join(r["number"] + " " + r["title"] for r in rows if r["visible"] and not r["generated"])
    for row in rows:
        if row["generated"]:
            row["blocks"].append({"text": toc, "source": "Ausgabestruktur", "status": "Freigegeben", "division": "*", "note": ""})
    plan = {"outline_id": outline["id"], "title": outline["title"], "revision": outline["revision"],
            "metadata": outline["metadata"], "profile": p, "chapters": rows, "warnings": warnings, "draft": True,
            "manifest": {"template_version": "onescm-publishing-3", "validity_decision": outline_validity, "internal_notes": "always_excluded",
                         "texts": manifest, "images": image_manifest, "title_hash": fingerprint([(c["id"], c["title"], c.get("config", {}).get("titles", {})) for c in outline["chapters"]])}}

    plan["layout"] = outline.get("layout", {})
    return publication.sanitize_plan(plan, keys)


def release_errors(plan):
    errors = list(plan["warnings"])
    if not any(c["visible"] for c in plan["chapters"]):
        errors.append("Die Ausgabe enthält keine Kapitel.")
    for c in plan["chapters"]:
        if c["visible"] and c["config"]["status"] != "Freigegeben":
            errors.append(f"Kapitel „{c['title']}“ ist nicht freigegeben.")
        if any(b["status"] != "Freigegeben" for b in c["blocks"]):
            errors.append(f"Kapitel „{c['title']}“ enthält ungeprüfte Textfassungen.")
    return errors


def reimport(base, chapters, decisions=None):
    """Keep IDs/content on matches and retain every unmatched old chapter."""
    from app import validate_outline, compare_outlines, Invalid
    incoming = copy.deepcopy(base)
    incoming["chapters"] = chapters
    incoming = validate_outline(incoming)
    comparison = compare_outlines(base, incoming)
    inferred = {}

    def visit(nodes):
        for n in nodes:
            if n["peer_id"]:
                inferred[n["id"]] = n["peer_id"]
            visit(n["children"])
    visit(comparison["right"])
    choices = inferred if decisions is None else decisions
    if not isinstance(choices, dict) or set(choices) - {c["id"] for c in chapters}:
        raise Invalid("Ungültige Importentscheidungen.")
    old = {c["id"]: c for c in base["chapters"]}
    result, used, unresolved = [], set(), []
    for c in incoming["chapters"]:
        cid = choices.get(c["id"], "")
        if not cid:
            unresolved.append(c["id"])
        if cid and cid != "new":
            if cid not in old or cid in used:
                raise Invalid("Ein bestehendes Kapitel darf nur einmal zugeordnet werden.")
            used.add(cid)
            item = copy.deepcopy(old[cid])
            item.update(title=c["title"], level=c["level"])
        else:
            item = c
        result.append(item)
    retained, ancestry = [], []
    for c in base["chapters"]:
        while ancestry and ancestry[-1][0] >= c["level"]:
            ancestry.pop()
        if c["id"] not in used:
            item = copy.deepcopy(c)
            item["level"] = len(ancestry) + 1
            retained.append(item)
            ancestry.append((c["level"], c["id"]))
    proposed = copy.deepcopy(base)
    proposed["chapters"] = result + retained
    proposed["metadata"]["status"] = "Entwurf"
    if len(proposed["chapters"]) <= 500:
        proposed = validate_outline(proposed)
    elif not unresolved:
        raise Invalid("Die Übernahme hätte mehr als 500 Kapitel. Weitere bestehende Kapitel zuordnen oder Import aufteilen.")
    return {"outline": proposed, "decisions": choices, "unresolved": unresolved,
            "retained": [{"id": c["id"], "title": c["title"]} for c in retained],
            "comparison": compare_outlines(base, proposed)}
