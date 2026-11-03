"""Local revisioned media, irreversible raster redaction, OCR and output selection."""
import base64
import copy
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

MAX_PIXELS = 16_000_000
Image.MAX_IMAGE_PIXELS = MAX_PIXELS
MEDIA_FIELDS = ["role", "scope", "market", "division", "release", "language"]


def read_image(raw):
    from app import Invalid
    if len(raw) > 10 * 1024 * 1024:
        raise Invalid("Maximal 10 MB je Bild.")
    try:
        image = Image.open(io.BytesIO(raw))
        if image.format not in ["PNG", "JPEG"] or image.width * image.height > MAX_PIXELS:
            raise Invalid("PNG/JPEG bis 16 Millionen Pixel verwenden.")
        image.load()
        return ImageOps.exif_transpose(image).convert("RGB")
    except Exception as exc:
        raise Invalid("Kein unterstütztes PNG/JPEG oder Bild zu groß.") from exc


def png(image):
    output = io.BytesIO()
    image.save(output, format="PNG")  # No original EXIF/text metadata is copied.
    return output.getvalue()


def box(value, width, height):
    from app import Invalid
    if not isinstance(value, dict) or any(type(value.get(k)) is not int for k in ["x", "y", "w", "h"]):
        raise Invalid("Ungültige Bildregion.")
    x, y, w, h = (value[k] for k in ["x", "y", "w", "h"])
    if min(x, y) < 0 or min(w, h) < 1 or x + w > width or y + h > height:
        raise Invalid("Bildregion liegt außerhalb des Bildes.")
    return x, y, x + w, y + h


def render(raw, redactions, markers):
    from app import Invalid, clean_text, choice
    image = read_image(raw)
    if not isinstance(redactions, list) or len(redactions) > 300 or not isinstance(markers, list) or len(markers) > 100:
        raise Invalid("Zu viele Bildregionen oder Markierungen.")
    draw = ImageDraw.Draw(image)
    for region in redactions:
        bounds = box(region, image.width, image.height)
        mode = choice(region.get("mode", "mask"), ["mask", "blur"], "Unkenntlichmachung")
        if mode == "mask":
            draw.rectangle((bounds[0], bounds[1], bounds[2]-1, bounds[3]-1), fill="#253b46")
        else:
            patch = image.crop(bounds)
            # Coarse pixel reduction plus blur, permanently rasterized.
            patch = patch.resize((1, 1)).resize(patch.size).filter(ImageFilter.GaussianBlur(20))
            image.paste(patch, bounds[:2])
    draw = ImageDraw.Draw(image)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", max(14, min(32, image.width // 45)))
    except OSError:
        font = ImageFont.load_default(size=max(14, min(32, image.width // 45)))
    for mark in markers:
        bounds = box(mark, image.width, image.height)
        text = clean_text(mark.get("text", ""), "Bildmarkierung", 120)
        draw.rectangle((bounds[0], bounds[1], bounds[2]-1, bounds[3]-1), outline="#e05227", width=4)
        if text:
            text_box = draw.textbbox((0, 0), text, font=font)
            tw, th = text_box[2] - text_box[0] + 12, text_box[3] - text_box[1] + 12
            x, y = min(bounds[0], max(0, image.width-tw)), max(0, bounds[1]-th)
            draw.rectangle((x, y, min(image.width, x+tw), min(image.height, y+th)), fill="#e05227")
            draw.text((x+6, y+3-text_box[1]), text, fill="white", font=font)
    return png(image)


def validate_assignments(value):
    from app import Invalid, clean_text, choice, uid
    from editorial import validate_chapter
    if not isinstance(value, list) or len(value) > 100:
        raise Invalid("Maximal 100 Medienzuordnungen je Kapitel.")
    result, ids = [], set()
    for item in value:
        mid = clean_text(item.get("id"), "Medienzuordnung", 100)
        if not mid or mid in ids:
            raise Invalid("Doppelte oder fehlende Medienzuordnung.")
        ids.add(mid)
        frames = item.get("frames", [])
        kind = choice(item.get("kind"), ["Bild", "Klickstrecke"], "Medienart")
        if not isinstance(frames, list) or not 1 <= len(frames) <= 50 or (kind == "Bild" and len(frames) != 1):
            raise Invalid("Ein Bild benötigt eine Position, eine Klickstrecke 1–50 Schritte.")
        row = {"id": mid, "title": clean_text(item.get("title", ""), "Medientitel", 300), "kind": kind,
               "conditions": validate_chapter({"config": {"conditions": item.get("conditions", {})}})["conditions"],
               "note": clean_text(item.get("note", ""), "Medienvermerk", 5000), "frames": []}
        for frame in frames:
            variants = frame.get("variants", [])
            if not isinstance(variants, list) or not 1 <= len(variants) <= 20:
                raise Invalid("Pro Bildposition 1–20 Bildvarianten wählen.")
            refs, seen = [], set()
            for ref in variants:
                aid = clean_text(ref.get("asset_id"), "Bild-ID", 100)
                if type(ref.get("revision")) is not int or ref["revision"] < 1 or aid in seen:
                    raise Invalid("Bildvariante fehlt oder wurde doppelt gewählt.")
                seen.add(aid)
                refs.append({"asset_id": aid, "revision": ref["revision"]})
            row["frames"].append({"caption": clean_text(frame.get("caption", ""), "Verwendungsuntertitel", 2000), "variants": refs})
        result.append(row)
    return result


class Media:
    def __init__(self, store):
        self.store = store
        with store.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS media(id TEXT PRIMARY KEY, revision INTEGER, payload TEXT, original BLOB, sha256 TEXT UNIQUE);
                CREATE TABLE IF NOT EXISTS media_history(id TEXT, revision INTEGER, payload TEXT, rendered BLOB, PRIMARY KEY(id,revision));
            """)

    def listing(self):
        with self.store.connect() as db:
            rows = [json.loads(r[0]) for r in db.execute("SELECT payload FROM media ORDER BY rowid DESC")]
        usage = {}
        for o in self.store.all():
            for c in o["chapters"]:
                for assignment in c.get("media", []):
                    for f in assignment["frames"]:
                        for ref in f["variants"]:
                            usage.setdefault(ref["asset_id"], []).append({"outline": o["title"], "chapter": c["title"], "revision": ref["revision"]})
        for row in rows:
            row["usage"] = usage.get(row["id"], [])
        return rows

    def upload(self, raw, name, language="de"):
        from app import uid, now, block, clean_text, choice, LANGUAGES
        image = read_image(raw)
        normalized = png(image)
        digest = hashlib.sha256(normalized).hexdigest()
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            existing = db.execute("SELECT payload FROM media WHERE sha256=?", (digest,)).fetchone()
            if existing:
                return {**json.loads(existing[0]), "duplicate": True}
            p = block()
            item = {"id": uid(), "revision": 1, "title": clean_text(name, "Bildtitel", 300),
                    "caption": "", "note": "", "width": image.width, "height": image.height,
                    "profile": {k: p[k] for k in MEDIA_FIELDS}, "status": "Entwurf", "pii_reviewed": False,
                    "redactions": [], "markers": [], "archived": False, "updated": now()}
            item["classification"] = {"roles": [], "domain_ids": [], "keywords": [], "labels": [], "topic": ""}
            item["profile"]["language"] = choice(language, LANGUAGES, "Bildsprache")
            raw_json = json.dumps(item, ensure_ascii=False)
            db.execute("INSERT INTO media VALUES(?,?,?,?,?)", (item["id"], 1, raw_json, normalized, digest))
            db.execute("INSERT INTO media_history VALUES(?,?,?,?)", (item["id"], 1, raw_json, None))
        return item

    def extract_source(self, sid, language="de"):
        from app import Invalid
        with self.store.connect() as db:
            row = db.execute("SELECT name, raw FROM sources WHERE id=?", (sid,)).fetchone()
        if not row:
            raise Invalid("Quelle nicht gefunden.")
        name, raw = row
        ext = Path(name).suffix.lower()
        images, warnings = [], []
        if ext in [".docx", ".pptx"]:
            with zipfile.ZipFile(io.BytesIO(raw)) as archive:
                prefix = "word/media/" if ext == ".docx" else "ppt/media/"
                files = [f for f in archive.infolist() if f.filename.startswith(prefix) and not f.is_dir()]
                if len(files) > 100 or sum(f.file_size for f in files) > 32*1024*1024:
                    raise Invalid("Maximal 100 Bilder / 32 MB extrahierte Bilddaten je Quelle.")
                for f in files:
                    if Path(f.filename).suffix.lower() in [".png", ".jpg", ".jpeg"]:
                        images.append((f.filename, archive.read(f)))
                    else:
                        warnings.append(f"Nicht unterstütztes Bildformat: {f.filename}")
        elif ext == ".pdf":
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            total = 0
            for index, page in enumerate(reader.pages):
                try:
                    for image in page.images:
                        total += len(image.data)
                        if len(images) >= 100 or total > 32*1024*1024:
                            raise Invalid("Maximal 100 Bilder / 32 MB extrahierte Bilddaten je Quelle.")
                        # pypdf can return non-PNG embedded formats; normalize supported decoded images.
                        decoded = image.image
                        if decoded.width * decoded.height > MAX_PIXELS:
                            warnings.append(f"Seite {index+1}: Bild zu groß.")
                            continue
                        images.append((f"Seite {index+1} / {image.name}", png(decoded.convert("RGB"))))
                except Invalid:
                    raise
                except Exception:
                    warnings.append(f"Seite {index+1}: eingebettete Bilder nicht vollständig lesbar.")
        else:
            raise Invalid("Bildextraktion unterstützt DOCX, PPTX und PDF.")
        result = []
        for location, image_raw in images:
            try:
                result.append(self.upload(image_raw, (name+" · "+location)[:300], language))
            except Invalid as exc:
                warnings.append(location+": "+str(exc))
        return {"images": [{"id": i["id"], "title": i["title"], "duplicate": i.get("duplicate", False)} for i in result],
                "warnings": warnings, "notice": "Extrahierte Bilder sind eigenständige Medienkopien. Das Löschen der Quelldatei entfernt diese Kopien nicht."}

    def snapshot(self, aid, revision):
        from app import Invalid
        with self.store.connect() as db:
            row = db.execute("SELECT payload FROM media_history WHERE id=? AND revision=?", (aid, revision)).fetchone()
        if not row:
            raise Invalid("Bildrevision nicht gefunden.")
        return json.loads(row[0])

    def original(self, aid):
        from app import Invalid
        with self.store.connect() as db:
            row = db.execute("SELECT original FROM media WHERE id=?", (aid,)).fetchone()
        if not row:
            raise Invalid("Bild nicht gefunden.")
        return row[0]

    def delete(self, aid):
        from app import Invalid
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            for (payload,) in db.execute("SELECT payload FROM history"):
                outline = json.loads(payload)
                if any(ref["asset_id"] == aid for c in outline["chapters"] for item in c.get("media", []) for frame in item["frames"] for ref in frame["variants"]):
                    raise Invalid("Das Bild wird von einer gespeicherten Gliederungsrevision verwendet. Zum Erhalt der Nachvollziehbarkeit bitte archivieren.")
            db.execute("DELETE FROM media_history WHERE id=?", (aid,))
            db.execute("DELETE FROM media WHERE id=?", (aid,))

    def save(self, data):
        from app import Invalid, Conflict, clean_text, choice, boolean, now, ROLES, SCOPES, LANGUAGES
        aid = clean_text(data.get("id"), "Bild-ID", 100)
        old = self.snapshot(aid, data.get("revision"))
        rendered = render(self.original(aid), data.get("redactions", []), data.get("markers", []))
        p = data.get("profile", {})
        profile = {k: choice(p.get(k), values, k) for k, values in [
            ("role", ["*"]+ROLES), ("scope", ["*"]+SCOPES), ("division", ["*", "Van", "PC"]), ("language", LANGUAGES)]}
        for k in ["market", "release"]:
            profile[k] = clean_text(p.get(k, "*"), k, 100).strip()
        item = {**old, "profile": profile, "redactions": data.get("redactions", []), "markers": data.get("markers", []),
                "title": clean_text(data.get("title"), "Bildtitel", 300), "caption": clean_text(data.get("caption", ""), "Bilduntertitel", 2000),
                "note": clean_text(data.get("note", ""), "Bildvermerk", 5000), "status": choice(data.get("status"), ["Entwurf", "Freigegeben"], "Bildstatus"),
                "pii_reviewed": boolean(data.get("pii_reviewed", False), "PII-Prüfung"), "archived": boolean(data.get("archived", False), "Archiv"),
                "revision": old["revision"]+1, "updated": now()}
        if item["status"] == "Freigegeben" and not item["pii_reviewed"]:
            raise Invalid("Vor der Bildfreigabe die anonymisierte Fassung prüfen und bestätigen.")
        from sources import validate_labels
        item["classification"] = validate_labels(data.get("classification", {}), {d["id"] for d in self.store.get_catalog()})
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            rev = db.execute("SELECT revision FROM media WHERE id=?", (aid,)).fetchone()[0]
            if rev != old["revision"]:
                raise Conflict("Bild wurde inzwischen geändert. Medienübersicht erneut öffnen.")
            payload = json.dumps(item, ensure_ascii=False)
            db.execute("UPDATE media SET revision=?, payload=? WHERE id=?", (item["revision"],payload,aid))
            db.execute("INSERT INTO media_history VALUES(?,?,?,?)", (aid,item["revision"],payload,rendered))
        return item

    def image(self, aid, revision, working_role, original=False):
        from app import Invalid
        item = self.snapshot(aid, revision)
        if (original or not item["pii_reviewed"]) and working_role not in ["HQ", "intern"]:
            raise Invalid("Originale und ungeprüfte Bilder sind im Redaktionsmodus nur für HQ / intern verfügbar.")
        if original:
            return self.original(aid)
        with self.store.connect() as db:
            row = db.execute("SELECT rendered FROM media_history WHERE id=? AND revision=?", (aid,revision)).fetchone()
        if not row[0]:
            raise Invalid("Zuerst eine bearbeitete Bildrevision speichern.")
        return row[0]

    def resolve(self, data):
        data = copy.deepcopy(data)
        for c in data.get("chapters", []):
            c["media"] = validate_assignments(c.get("media", []))
            snapshots = {}
            for item in c["media"]:
                for f in item["frames"]:
                    for ref in f["variants"]:
                        asset = self.snapshot(ref["asset_id"], ref["revision"])
                        key = ref["asset_id"] + ":" + str(ref["revision"])
                        snapshots[key] = {k: asset[k] for k in ["id", "revision", "title", "caption", "profile", "status", "pii_reviewed", "width", "height"]}
            c["media_snapshots"] = snapshots
        return data

    def ocr(self, aid):
        from app import Invalid
        binary = shutil.which("tesseract")
        if not binary:
            raise Invalid("Tesseract ist nicht installiert. Unter Windows lokal installieren und zum PATH hinzufügen; manuelle Markierungen sind weiterhin möglich.")
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "image.png"
            source.write_bytes(self.original(aid))
            try:
                result = subprocess.run([binary, str(source), "stdout", "tsv"], capture_output=True, timeout=45, check=True)
            except (subprocess.SubprocessError, OSError) as exc:
                raise Invalid("Lokale OCR fehlgeschlagen. Tesseract und Sprachdaten prüfen.") from exc
        import csv
        words = []
        for row in csv.DictReader(io.StringIO(result.stdout.decode("utf-8", errors="replace")), delimiter="\t"):
            text = row.get("text", "").strip()
            if text:
                words.append({"text": text, "x": int(row["left"]), "y": int(row["top"]), "w": int(row["width"]), "h": int(row["height"]), "line": (row["block_num"],row["par_num"],row["line_num"])})
        suggestions, pii_lines = [], set()
        for word in words:
            text = word["text"].strip(":;.,").casefold()
            if text in {"userid", "user-id", "login", "iban", "fin", "vin", "kennzeichen", "benutzer", "e-mail", "email"}:
                pii_lines.add(word["line"])
        for word in words:
            if word["line"] in pii_lines or re.search(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|\b[A-Z]{2}\d{2}[A-Z0-9]{10,}\b|\b[A-HJ-NPR-Z0-9]{17}\b", word["text"]):
                suggestions.append({k: word[k] for k in ["x", "y", "w", "h"]} | {"mode": "mask"})
        return {"text": " ".join(w["text"] for w in words), "regions": suggestions,
                "warning": "OCR-Hinweise sind unvollständig möglich. Namen, FIN, Kontodaten und weitere PII immer visuell prüfen."}


def compose_chapter(c, p):
    from editorial import eligible
    figures, warnings, manifest = [], [], []
    snapshots = c.get("media_snapshots", {})
    for item in c.get("media", []):
        if not eligible({"inclusion": "Bedingt", "conditions": item["conditions"]}, p):
            continue
        frames, incomplete = [], False
        for index, frame in enumerate(item["frames"]):
            candidates = []
            for ref in frame["variants"]:
                asset = snapshots.get(ref["asset_id"] + ":" + str(ref["revision"]))
                if not asset:
                    continue
                profile = asset["profile"]
                matches = all(profile[k] == "*" or profile[k] == p[k] or (k == "division" and p[k] == "Beide") for k in MEDIA_FIELDS)
                if matches and asset["pii_reviewed"] and asset["status"] == "Freigegeben":
                    candidates.append(asset)
            if len(candidates) != 1:
                warnings.append(f"Kapitel „{c['title']}“, {item['title'] or item['kind']}, Schritt {index+1}: " + ("keine passende freigegebene Bildfassung." if not candidates else "mehrere passende Bildfassungen; Varianten eindeutig eingrenzen."))
                incomplete = True
                continue
            asset = candidates[0]
            frames.append({"asset_id": asset["id"], "revision": asset["revision"], "width": asset["width"], "height": asset["height"],
                           "caption": frame["caption"] or asset["caption"], "step": index+1})
        if not incomplete:
            figures.append({"id": item["id"], "title": item["title"], "kind": item["kind"], "frames": frames})
            manifest.extend({"chapter_id": c["id"], "assignment_id": item["id"], "asset_id": f["asset_id"], "revision": f["revision"]} for f in frames)
    return figures, warnings, manifest
