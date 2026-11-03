"""Domain vocabulary and explicit many-to-many chapter assignments."""
DOMAIN_NAMES = ["Product Management", "Contract Generation", "Contract Management",
                "Customer Management", "Finance Management", "Market Setting",
                "Admin Section", "Domäne 8 – reserviert"]
MAIN_DOMAINS = [{"id": f"d{i}", "name": name, "parent_id": None}
                for i, name in enumerate(DOMAIN_NAMES, 1)]


def catalog(subdomains=()):
    return [dict(d) for d in MAIN_DOMAINS] + [dict(d) for d in subdomains]


def legacy_mappings(chapter):
    if "mappings" in chapter:
        return chapter["mappings"]
    name = chapter.get("domain", "")
    return [{"target_id": f"d{DOMAIN_NAMES.index(name) + 1}", "active": True}] if name in DOMAIN_NAMES else []


def validate_mappings(value, valid_ids=None):
    if not isinstance(value, list) or len(value) > 208:
        raise ValueError("Maximal 208 Domänenzuordnungen pro Kapitel.")
    result, seen = [], set()
    for item in value:
        if not isinstance(item, dict):
            raise ValueError("Ungültige Domänenzuordnung.")
        target = item.get("target_id")
        if not isinstance(target, str) or not target or len(target) > 100 or "\x00" in target or target in seen:
            raise ValueError("Domänenzuordnung fehlt oder ist doppelt.")
        if type(item.get("active")) is not bool:
            raise ValueError("Eine Domänenzuordnung benötigt einen Aktiv-Schalter.")
        if valid_ids is not None and target not in valid_ids:
            raise ValueError("Unbekannte Domäne oder Unterdomäne. Bitte die Domänenliste aktualisieren.")
        seen.add(target)
        result.append({"target_id": target, "active": item["active"]})
    return result


def validate_subdomains(value, previous=()):
    if not isinstance(value, list) or len(value) > 200:
        raise ValueError("Maximal 200 Unterdomänen können verwaltet werden.")
    roots = {d["id"] for d in MAIN_DOMAINS}
    seen, names, result = set(roots), set(), []
    for row in value:
        if not isinstance(row, dict):
            raise ValueError("Ungültige Unterdomäne.")
        sid, name, parent = row.get("id"), row.get("name"), row.get("parent_id")
        if not isinstance(sid, str) or not sid or len(sid) > 100 or "\x00" in sid or sid in seen:
            raise ValueError("Die Kennung der Unterdomäne ist ungültig oder doppelt.")
        if not isinstance(name, str) or not name.strip() or len(name) > 150 or "\x00" in name:
            raise ValueError("Bitte einen Namen mit höchstens 150 Zeichen eingeben.")
        if parent not in roots:
            raise ValueError("Eine Unterdomäne muss einer der acht Hauptdomänen gehören.")
        key = (parent, name.strip().casefold())
        if key in names:
            raise ValueError("Der Name der Unterdomäne ist innerhalb dieser Domäne bereits vergeben.")
        names.add(key)
        seen.add(sid)
        result.append({"id": sid, "name": name.strip(), "parent_id": parent})
    current = {r["id"]: r for r in result}
    for row in previous:
        if row["id"] not in current or current[row["id"]]["parent_id"] != row["parent_id"]:
            raise ValueError("Bestehende Unterdomänen können umbenannt, aber nicht entfernt oder in eine andere Hauptdomäne verschoben werden.")
    return result


def signature(outline, chapter):
    """Compare both relationships and the names recorded with their revision."""
    targets = {d["id"]: d for d in outline.get("domain_catalog", catalog())}
    result = []
    for edge in legacy_mappings(chapter):
        target = targets.get(edge["target_id"], {})
        result.append((edge["target_id"], edge["active"], target.get("name", ""), target.get("parent_id")))
    return sorted(result)


def grouped(outline, targets, include_inactive=False):
    by_id = {d["id"]: d for d in targets}
    links = {key: [] for key in by_id}
    effective_chapters = set()
    enabled = outline.get("mapping_enabled", True)
    total = active = 0
    for chapter in outline["chapters"]:
        for edge in validate_mappings(legacy_mappings(chapter), set(by_id)):
            total += 1
            effective = enabled and edge["active"]
            if effective:
                active += 1
                effective_chapters.add(chapter["id"])
            if effective or include_inactive:
                links[edge["target_id"]].append({"chapter_id": chapter["id"], "effective": effective,
                                                 "active": edge["active"],
                                                 "reason": "Aktiv" if effective else ("Mapping pausiert" if not enabled else "Zuordnung deaktiviert")})
    groups = []
    for domain in MAIN_DOMAINS:
        children = [{**d, "links": links[d["id"]]} for d in targets if d["parent_id"] == domain["id"]]
        aggregate = links[domain["id"]] + [link for child in children for link in child["links"]]
        groups.append({**domain, "links": links[domain["id"]], "subdomains": children,
                       "chapter_count": len({link["chapter_id"] for link in aggregate}),
                       "mapping_count": len(aggregate)})
    return {"groups": groups, "total": total, "active": active,
            "unmapped": [c["id"] for c in outline["chapters"] if c["id"] not in effective_chapters]}
