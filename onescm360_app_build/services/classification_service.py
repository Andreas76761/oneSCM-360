"""Suggest chapter, language, role and domain for an uploaded file.

Suggestions come from the file name first and the document content second.
They are proposals only: the user confirms or corrects them before import.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from .claim_service import find_roles

CHAPTER_IN_NAME = re.compile(r"(?:^|[^A-Za-z])(?:CH|Kap(?:itel)?|Chapter)[\s_.-]*0?(\d{1,2})(?!\d)", re.I)
QUESTION_PREFIX = re.compile(r"(?:^|\s)(?:CH\s*)?(\d{2})\s*[-–_]\s*F\s*\d{1,2}\b", re.I | re.M)
LANG_IN_NAME = re.compile(r"(?:^|[^A-Za-z])(DE[+_&-]?EN|EN[+_&-]?DE|DE|EN|deutsch|german|englisch|english)(?![A-Za-z])", re.I)
DE_WORDS = set("der die das und ist nicht mit für auf werden wird ein eine des dem den im zum zur oder auch bei können kann sind".split())
EN_WORDS = set("the and is not with for on are be can of to in an or also by this that will".split())


class ClassificationError(ValueError):
    pass


def _words(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß]+", text.lower())


def detect_language(name: str, text: str) -> tuple[str, str]:
    match = LANG_IN_NAME.search(Path(name).stem)
    if match:
        token = match.group(1).lower()
        if re.fullmatch(r"de[+_&-]?en|en[+_&-]?de", token):
            return "DE+EN", "Dateiname"
        if token in ("de", "deutsch", "german"):
            return "DE", "Dateiname"
        if token in ("en", "englisch", "english"):
            return "EN", "Dateiname"
    words = _words(text[:200_000])
    de = sum(1 for w in words if w in DE_WORDS)
    en = sum(1 for w in words if w in EN_WORDS)
    if de + en < 5:
        return "", ""
    if min(de, en) / (de + en) >= 0.3:
        return "DE+EN", "Inhalt"
    return ("DE" if de > en else "EN"), "Inhalt"


def detect_chapter(name: str, text: str, valid: set[str]) -> tuple[str, str]:
    match = CHAPTER_IN_NAME.search(Path(name).stem)
    if match:
        cid = f"CH{int(match.group(1)):02d}"
        if cid in valid:
            return cid, "Dateiname"
    counts = Counter(f"CH{int(m):02d}" for m in QUESTION_PREFIX.findall(text[:500_000]))
    counts = Counter({k: v for k, v in counts.items() if k in valid})
    if counts:
        return counts.most_common(1)[0][0], "Inhalt"
    return "", ""


def _count(term: str, text: str) -> int:
    return len(re.findall(r"(?<![\wÄÖÜäöüß])" + re.escape(term) + r"(?![\wÄÖÜäöüß])", text, re.I))


class ClassificationService:
    def __init__(self, path: Path, chapters):
        self.path = Path(path)
        self.chapters = chapters

    def config(self) -> dict:
        try:
            with self.path.open(encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError) as exc:
            raise ClassificationError("classification.json fehlt oder ist beschädigt.") from exc
        domains = data.get("domains") or []
        ids = [d.get("id") for d in domains]
        if not all(isinstance(i, str) and re.fullmatch(r"[a-z0-9-]{1,60}", i) for i in ids) or len(set(ids)) != len(ids):
            raise ClassificationError("classification.json: Domänen-IDs fehlen oder sind doppelt.")
        roles = []
        for role in data.get("roles") or []:
            if isinstance(role, str):
                role = {"id": role, "name": role, "aliases": [role]}
            if not isinstance(role, dict) or not isinstance(role.get("id"), str) or not role["id"].strip():
                raise ClassificationError("classification.json: jede Rolle braucht eine ID.")
            roles.append({"id": role["id"], "name": role.get("name") or role["id"],
                          "aliases": [str(a) for a in role.get("aliases") or [] if str(a).strip()]})
        if len({r["id"] for r in roles}) != len(roles):
            raise ClassificationError("classification.json: Rollen-IDs sind doppelt.")
        return {"roles": roles, "domains": domains}

    def role_catalog(self) -> list[dict]:
        """Configured roles plus any role a chapter references that is not in the catalog."""
        roles = list(self.config()["roles"])
        known = {r["id"] for r in roles}
        for chapter in self.chapters.list():
            for role in self.chapters.get(chapter["chapterId"]).get("roles", []):
                if role not in known:
                    roles.append({"id": role, "name": role, "aliases": [role]})
                    known.add(role)
        return roles

    def roles(self) -> list[str]:
        return [r["id"] for r in self.role_catalog()]

    def normalize_role(self, value: str) -> str | None:
        """Map an ID, display name or alias (e.g. "Market Operations") to the role ID ("MO")."""
        value = (value or "").strip()
        if not value:
            return ""
        for role in self.role_catalog():
            if value == role["id"]:
                return role["id"]
        for role in self.role_catalog():
            if value.casefold() in {a.casefold() for a in [role["name"], *role["aliases"]]}:
                return role["id"]
        return None

    def domains(self) -> list[dict]:
        return [{"id": d["id"], "name": d["name"]} for d in self.config()["domains"]]

    def domain_name(self, domain_id: str) -> str:
        return next((d["name"] for d in self.config()["domains"] if d["id"] == domain_id), "")

    def validate(self, role: str, domain: str):
        if role and self.normalize_role(role) is None:
            raise ClassificationError(f"Unbekannte Rolle „{role}“.")
        if domain and domain not in {d["id"] for d in self.config()["domains"]}:
            raise ClassificationError(f"Unbekannte Domäne „{domain}“.")

    def classify(self, name: str, blocks: list[dict]) -> dict:
        parts = []
        for block in blocks:
            if block["kind"] == "text":
                parts.append(block["text"])
            elif block["kind"] == "table":
                parts.extend(" ".join(row) for row in block["rows"])
        text = "\n".join(parts)
        valid = {c["chapterId"] for c in self.chapters.list()}
        chapter, chapter_source = detect_chapter(name, text, valid)
        language, language_source = detect_language(name, text)
        stem = Path(name).stem.replace("_", " ").replace("-", " ")

        role, role_source = "", ""
        catalog = self.role_catalog()
        # Domain names such as "Market Setting" must not count as the role "Market".
        domain_names = [d["name"] for d in self.config()["domains"]]

        def without_domains(value: str) -> str:
            for name in domain_names:
                value = re.sub(re.escape(name), " ", value, flags=re.I)
            return value

        name_hits = find_roles(without_domains(stem), catalog)
        if name_hits:
            role, role_source = name_hits[0][1], "Dateiname"
        else:
            scores = Counter(rid for _pos, rid, _text in find_roles(without_domains(text), catalog))
            best = scores.most_common(2)
            # A clear majority is required; documents that cover several roles stay "Alle Rollen".
            if best and best[0][1] >= 2 and (len(best) == 1 or best[0][1] >= 2 * best[1][1]):
                role, role_source = best[0][0], "Inhalt"

        domain, domain_source = "", ""
        config = self.config()["domains"]
        for d in config:
            if _count(d["name"], stem) or any(len(k) > 4 and _count(k, stem) for k in d.get("keywords", [])):
                domain, domain_source = d["id"], "Dateiname"
                break
        if not domain:
            scores = Counter({d["id"]: _count(d["name"], text) * 3 + sum(_count(k, text) for k in d.get("keywords", [])) for d in config})
            best = scores.most_common(2)
            if best and best[0][1] >= 3 and (len(best) == 1 or best[0][1] > best[1][1]):
                domain, domain_source = best[0][0], "Inhalt"

        return {"chapterId": chapter, "chapterSource": chapter_source, "language": language, "languageSource": language_source,
                "role": role, "roleSource": role_source, "domain": domain, "domainSource": domain_source,
                "characters": len(text), "tables": sum(1 for b in blocks if b["kind"] == "table")}
