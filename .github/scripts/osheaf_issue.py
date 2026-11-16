#!/usr/bin/env python3
"""Carry out on the archive the operation described by an issue form.

Run by .github/workflows/from-issue.yml, in the root of the archive, after the
workflow has checked that the issue's author may write to the repository.
Reads the issue from the event file (GITHUB_EVENT_PATH), never from the
command line.

The archive holds documents, listed by its main collection (a catalogue of
its own documents, kept by `osheaf collect`), and collections: reading
lists, journal issues, sections, each an object of the archive whose members
are kept in collections/ID.yaml and pinned by `osheaf collection sync ID`.
The forms deposit documents (and new versions), give notices, withdraw, give
new licences, create collections, and add, vet and remove their members. A
collection that includes a changed collection is brought up to date in turn
(in a selection, the new version is vetted: the same curator made it). Then
`osheaf collect`, `osheaf index` and `osheaf verify`.

Writes a message for the issue to RESULT_FILE (Markdown), the commit message
to COMMIT_FILE and the issue's new title to TITLE_FILE. Exits 0 on success, 1
on an error the author can fix (explained in RESULT_FILE; the lists are
restored and nothing is committed), 2 if the issue is not one of the forms.
"""
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

import yaml

OSHEAF = shlex.split(os.environ.get("OSHEAF", "osheaf"))
NO_RESPONSE = "_No response_"
LINK = re.compile(r"!?\[([^\]]*)\]\((https?://[^)\s]+)\)")
IDENT = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
COLLECTIONS = Path("collections")
SOURCE_SUFFIXES = {".tex", ".ltx", ".tm", ".md", ".typ", ".lyx", ".rst", ".org", ".txt"}
LICENCES = {"cc-by-4.0", "cc-by-sa-4.0", "cc0-1.0", "gpl-3.0-only", "gpl-3.0-or-later"}
HEADER = """\
# The members of a collection of this archive, in order, for
# `osheaf collection sync ID --from collections/ID.yaml`: kept by the issue
# forms of this repository (Issues, New issue) or by hand (see the README).
# Each member is an object of an OpenSheaf archive: the archive's address and
# the object's identifier; in a selection, `revisions` lists the document
# versions vetted (1, 2, ...).
"""

# The heading that identifies each form (a label of one of its fields).
FORMS = {
    "PDF of this version": "deposit",
    "Text of the notice": "notice",
    "Reason for the withdrawal": "withdraw",
    "New licence": "relicense",
    "Identifier of the new collection": "new_collection",
    "Archive of the new member": "add",
    "Versions to vet": "vet",
    "Member to remove": "remove",
}


class Problem(Exception):
    """An error the author can fix, explained in plain words."""


# --- reading the form ------------------------------------------------------

def sections(body):
    out, label, lines_ = {}, None, []
    for line in (body or "").splitlines():
        m = re.match(r"^### (.+?)\s*$", line)
        if m:
            if label is not None:
                out[label] = "\n".join(lines_).strip()
            label, lines_ = m.group(1), []
        elif label is not None:
            lines_.append(line)
    if label is not None:
        out[label] = "\n".join(lines_).strip()
    return {k: ("" if v == NO_RESPONSE else v) for k, v in out.items()}


def field(form, label, required=False):
    value = str(form.get(label, "") or "").strip()
    if required and not value:
        raise Problem(f"The field **{label}** is empty, and it is needed.")
    return value


def lines(text):
    return [l.strip() for l in text.splitlines() if l.strip() and not LINK.fullmatch(l.strip())]


def identifier(form, label, limit=32):
    ident = field(form, label, required=True)
    if not IDENT.match(ident) or len(ident) > limit:
        raise Problem(f"`{ident}` is not a valid identifier: at most {limit} characters, "
                      "lower-case letters and digits, words joined by `-` (for instance "
                      "`kpz-uniqueness`).")
    return ident


def archive_url(form, label, required=True):
    url = field(form, label, required)
    if not url:
        return ""
    if not re.match(r"^https?://\S+$", url):
        raise Problem(f"**{label}** should be the address of an OpenSheaf archive, the folder "
                      f"that holds its `opensheaf.json` (for instance `https://mgubi.org/papers/`), "
                      f"not `{url}`.")
    url = re.sub(r"opensheaf\.json$", "", url)
    return url if url.endswith("/") else url + "/"


def versions(form, label, required=False):
    text = field(form, label, required)
    found = re.findall(r"\d+", text)
    if text and (not found or re.sub(r"[\d,;\s]", "", text)):
        raise Problem(f"**{label}** should be document versions, numbers such as `5` or `5, 6`, "
                      f"not `{text}`.")
    return [int(n) for n in found]


def position(form):
    value = field(form, "Position")
    if value and not value.isdigit():
        raise Problem(f"**Position** should be a number (1 for the first), not `{value}`.")
    return int(value) if value else None


def date(form, label):
    value = field(form, label)
    if value and not re.match(r"^\d{4}(-\d{2}(-\d{2})?)?$", value):
        raise Problem(f"The field **{label}** should be a date written as YYYY-MM-DD, not `{value}`.")
    return value


def licence(form, label):
    value = field(form, label)
    m = re.search(r"\(([a-z0-9.-]+)\)\s*$", value)
    if m and m.group(1) in LICENCES:
        return m.group(1)
    if value.lower().startswith("all rights reserved"):
        return "All rights reserved"
    return None


# --- the archive and its collections ----------------------------------------

def settings():
    return json.loads(Path("osheaf.json").read_text(encoding="utf-8"))


def own_base():
    return settings().get("baseUrl", "")


def same_archive(a, b):
    return str(a or "").rstrip("/") == str(b or "").rstrip("/")


def list_path(cid):
    return COLLECTIONS / f"{cid}.yaml"


def all_collections():
    return sorted(p.stem for p in COLLECTIONS.glob("*.yaml")) if COLLECTIONS.exists() else []


def collection(form, required):
    """The collection a form names in **In collection**, or '' when it may be
    left empty."""
    cid = field(form, "In collection")
    if not cid:
        if required:
            known = all_collections()
            raise Problem("Name the collection in **In collection**"
                          + (": the archive's collections are " + ", ".join(f"`{k}`" for k in known)
                             if known else "; the archive has none yet (create one with the form "
                             "**New collection**)") + ".")
        return ""
    if not IDENT.match(cid) or not list_path(cid).exists():
        known = all_collections()
        raise Problem(f"The archive has no collection `{cid}`"
                      + (": its collections are " + ", ".join(f"`{k}`" for k in known)
                         if known else " (none has been created yet)") + ".")
    return cid


def load(cid):
    data = yaml.safe_load(list_path(cid).read_text(encoding="utf-8")) or {}
    if data.get("members") is None:
        data["members"] = []
    return data


def save(cid, data):
    path = list_path(cid)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=100)
    path.write_text(HEADER + text, encoding="utf-8")


def find(data, ident, archive=""):
    hits = [m for m in data["members"] if m.get("id") == ident
            and (not archive or same_archive(m.get("archive"), archive))]
    if not hits:
        raise Problem(f"`{ident}` is not a member" + (f" from `{archive}`" if archive else "") + ".")
    if len(hits) > 1:
        raise Problem(f"Several members are called `{ident}`: give **Archive of the member** to "
                      "say which.")
    return hits[0]


def insert(data, member, where):
    if where and 1 <= where <= len(data["members"]):
        data["members"].insert(where - 1, member)
    else:
        data["members"].append(member)


def own_children(cid):
    base = own_base()
    return [m["id"] for m in load(cid)["members"]
            if same_archive(m.get("archive"), base) and list_path(m["id"]).exists()]


def descendants(cid, seen=None):
    seen = set() if seen is None else seen
    for child in own_children(cid):
        if child not in seen:
            seen.add(child)
            descendants(child, seen)
    return seen


def parents(cid):
    base = own_base()
    return [c for c in all_collections() if c != cid and any(
        m.get("id") == cid and same_archive(m.get("archive"), base) for m in load(c)["members"])]


def head_file(obj, name):
    """A file of the head version of an object of this archive, as JSON."""
    inv_path = Path("ocfl") / obj / "inventory.json"
    if not inv_path.exists():
        return None
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    state = inv["versions"][inv["head"]]["state"]
    digest = next((d for d, paths in state.items() if name in paths), None)
    if digest is None:
        return None
    return json.loads((Path("ocfl") / obj / inv["manifest"][digest][0]).read_text(encoding="utf-8"))


def document_version(ident):
    return head_file(ident, "object.json")["documentVersion"]


def vetted(cid, ident):
    """The document versions of a member of this archive that a selection
    pins now (from its members.json), also when its list names none."""
    members = (head_file(cid, "members.json") or {}).get("members", [])
    s = settings()
    for m in members:
        if m.get("id") == ident and (m.get("archive") == s.get("archiveId")
                                     or same_archive(m.get("archiveUrl"), s.get("baseUrl"))):
            return [r["documentVersion"] for r in m.get("revisions", [])]
    return []


# --- running osheaf ----------------------------------------------------------

def osheaf(*args):
    result = subprocess.run(OSHEAF + [str(a) for a in args], capture_output=True, text=True)
    if result.returncode != 0:
        out = (result.stderr or result.stdout).strip().splitlines()
        errors = [l for l in out if l.startswith("osheaf: error:")]
        raise Problem("osheaf stopped with this message:\n\n```\n"
                      + "\n".join(errors or out[-15:]) + "\n```")
    return result.stdout


def sync(cid, message):
    osheaf("collection", "sync", cid, "--from", list_path(cid), "--message", message)


def propagate(cid, message, seen=None):
    """Bring the collections that include a changed collection up to date."""
    seen = set() if seen is None else seen
    for parent in parents(cid):
        if parent in seen:
            continue
        seen.add(parent)
        data = load(parent)
        member = find(data, cid, own_base())
        if data.get("type") == "selection":
            dv = document_version(cid)
            revisions = list(member.get("revisions") or vetted(parent, cid))
            if dv not in revisions:
                member["revisions"] = sorted(revisions + [dv])
            save(parent, data)
        sync(parent, message)
        propagate(parent, message, seen)


# --- attachments ---------------------------------------------------------------

def safe_name(text):
    text = Path(text.strip() or "file").name
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.") or "file"


def download(form, label, folder):
    """The files attached to a field: links in an issue, or files of the
    request's folder (a page's request, see main), copied into folder."""
    files = []
    for name in form.get("__files__", {}).get(label, []):
        source = (form["__dir__"] / name).resolve()
        if form["__dir__"].resolve() not in source.parents or not source.is_file():
            raise Problem(f"The file `{name}` of **{label}** is not in the request.")
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_name(Path(name).name)
        path.write_bytes(source.read_bytes())
        files.append(path)
    for text, url in LINK.findall(form.get(label, "")):
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / safe_name(text or url.rsplit("/", 1)[-1])
        n = 1
        while path.exists():
            path = path.with_name(f"{path.stem}-{n}{path.suffix}")
            n += 1
        cmd = ["curl", "-fsSL", "--retry", "3", "-o", str(path)]
        token = os.environ.get("GITHUB_TOKEN")
        if token and url.startswith("https://github.com/"):
            cmd += ["-H", f"Authorization: Bearer {token}"]  # not sent on to other hosts
        result = subprocess.run(cmd + [url], capture_output=True, text=True)
        if result.returncode != 0:
            raise Problem(f"The file `{text}` attached to **{label}** could not be downloaded "
                          f"({result.stderr.strip() or 'curl failed'}).")
        files.append(path)
    return files


def unpack(archive, folder):
    """Extract a zip safely: no absolute paths, no '..', no system files."""
    names = []
    with zipfile.ZipFile(archive) as z:
        for info in z.infolist():
            parts = Path(info.filename).parts
            if info.is_dir() or not parts or info.filename.startswith("/") or ".." in parts \
                    or parts[0] == "__MACOSX" or parts[-1] == ".DS_Store":
                continue
            target = folder / Path(*parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as dst:
                dst.write(src.read())
            names.append(Path(*parts).as_posix())
    tops = {n.split("/", 1)[0] for n in names}
    if len(tops) == 1 and all("/" in n for n in names):
        top = tops.pop()
        return folder / top, [n.split("/", 1)[1] for n in names]
    return folder, names


def sources(form, work):
    attached = download(form, "Sources", work / "attached")
    main_name = field(form, "Main source")
    if not attached:
        return None, []
    if len(attached) == 1 and attached[0].suffix.lower() == ".zip":
        root, names = unpack(attached[0], work / "sources")
        if not names:
            raise Problem("The zip of the sources is empty.")
        if main_name:
            if main_name not in names:
                raise Problem(f"The main source `{main_name}` is not in the zip; it holds: "
                              + ", ".join(f"`{n}`" for n in sorted(names)[:30]) + ".")
            main = main_name
        else:
            candidates = [n for n in names if "/" not in n
                          and Path(n).suffix.lower() in SOURCE_SUFFIXES]
            if len(candidates) != 1:
                raise Problem("Say which file of the zip is the main source, in the field "
                              "**Main source** (for instance `paper.tex`).")
            main = candidates[0]
        return root / main, [(root / n, n) for n in names if n != main]
    if len(attached) == 1:
        return attached[0], []
    if not main_name:
        raise Problem("Several source files are attached: put them in one zip, or say which one "
                      "is the main source in the field **Main source**.")
    named = [p for p in attached if p.name == safe_name(main_name)]
    if not named:
        raise Problem(f"The main source `{main_name}` is not among the attached files.")
    return named[0], [(p, p.name) for p in attached if p is not named[0]]


def current_description(ident):
    d = head_file(ident, "datacite.json")
    if d is None:
        return None, []
    title = (d.get("titles") or [{}])[0].get("title")
    authors = []
    for c in d.get("creators", []):
        aff = [a.get("name") if isinstance(a, dict) else a for a in c.get("affiliation", [])]
        authors.append(c["name"] + (f"|{aff[0]}" if aff and aff[0] else ""))
    return title, authors


# --- the operations ------------------------------------------------------------
# Each returns (collection changed or '', commit message, issue title, what was done).

def deposit(form, origin):
    ident = identifier(form, "Identifier")
    cid = collection(form, required=False)
    if list_path(ident).exists():
        raise Problem(f"`{ident}` is a collection of this archive, not a document.")
    exists = (Path("ocfl") / ident / "inventory.json").exists()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        pdfs = [p for p in download(form, "PDF of this version", work / "pdf")
                if p.suffix.lower() == ".pdf"]
        if not pdfs:
            raise Problem("Attach the PDF of this version to the field **PDF of this version**.")
        main, others = sources(form, work)
        missing = field(form, "If there are no sources, why")
        if main is None and not missing:
            raise Problem("Attach the sources (one file, or a zip), or say why there are none in "
                          "the field **If there are no sources, why**.")
        args = ["deposit", ident] + ([main] if main is not None else []) + ["--pdf", pdfs[0]]
        if main is None:
            args += ["--no-source", missing]
        for path, logical in others:
            args += ["--extra-source", f"{path}={logical}"]
        title, authors = field(form, "Title"), lines(field(form, "Authors"))
        if exists and (not title or not authors):
            # a new version: what is left empty stays as in the current version
            old_title, old_authors = current_description(ident)
            title, authors = title or old_title, authors or old_authors
        if not title or not authors:
            raise Problem("Give the **Title** and the **Authors** (they can be left empty only for "
                          "a new version of a paper already in the archive).")
        args += ["--title", title]
        for author in authors:
            args += ["--author", author]
        if abstract := field(form, "Abstract"):
            (work / "abstract.txt").write_text(abstract + "\n", encoding="utf-8")
            args += ["--abstract-file", work / "abstract.txt"]
        for keyword in re.split(r"[,;\n]", field(form, "Keywords")):
            if keyword.strip():
                args += ["--keyword", keyword.strip()]
        rights = licence(form, "Licence")
        if rights:
            args += ["--rights", rights]
        elif not exists:
            raise Problem("Choose a **Licence** for a new paper (\"Keep as before\" is for new "
                          "versions). \"All rights reserved\" lets readers read the paper but not "
                          "copy it; CC BY 4.0 lets anyone copy it with credit. Check what your "
                          "publisher allows for papers published in journals.")
        for related in lines(field(form, "Related identifiers")):
            args += ["--related", related]
        if changes := field(form, "What changed (for a new version)"):
            args += ["--changes", changes]
        if available := date(form, "Date this version became public"):
            args += ["--available", available]
        if issued := date(form, "Date the paper first appeared"):
            args += ["--issued", issued]
        args += ["--message", f"Deposit from {origin}"]
        osheaf(*args)
    where = ""
    if cid:
        data = load(cid)
        base = own_base()
        member = next((m for m in data["members"]
                       if m.get("id") == ident and same_archive(m.get("archive"), base)), None)
        if member is None:
            insert(data, {"archive": base, "id": ident}, position(form))
        elif data.get("type") == "selection":
            # the curator deposited this version: it is vetted
            dv = document_version(ident)
            member["revisions"] = sorted(set(list(member.get("revisions") or vetted(cid, ident))
                                             + [dv]))
        save(cid, data)
        where = f" in the collection `{cid}`"
    return (cid, f"Deposit {ident}{where} ({origin})", f"Deposit: {ident}",
            f"`{ident}` was deposited{where}")


def notice(form, origin):
    ident = identifier(form, "Identifier", limit=64)
    about = field(form, "Document version it is about", required=True)
    if not about.isdigit():
        raise Problem(f"**Document version it is about** should be a number (1, 2, ...), "
                      f"not `{about}`.")
    args = ["notice", ident, "--about", about, "--text", field(form, "Text of the notice", True)]
    with tempfile.TemporaryDirectory() as tmp:
        files = download(form, "Full statement (optional)", Path(tmp))
        if files:
            args += ["--file", files[0]]
        args += ["--message", f"Notice from {origin}"]
        osheaf(*args)
    return ("", f"Notice about {ident}, version {about} ({origin})",
            f"Notice: {ident}, version {about}", f"`{ident}` was given a notice")


def withdraw(form, origin):
    ident = identifier(form, "Identifier", limit=64)
    osheaf("withdraw", ident, "--reason", field(form, "Reason for the withdrawal", True),
           "--message", f"Withdrawal from {origin}")
    return ("", f"Withdraw {ident} ({origin})", f"Withdrawal: {ident}",
            f"`{ident}` was withdrawn (its files stay in the archive)")


def relicense(form, origin):
    ident = identifier(form, "Identifier", limit=64)
    rights = licence(form, "New licence")
    if rights not in LICENCES:
        raise Problem("Choose the new licence in the field **New licence**.")
    args = ["relicense", ident, "--rights", rights, "--method",
            field(form, "How the authors agreed", required=True)]
    args += ["--message", f"New licence from {origin}"]
    osheaf(*args)
    return ("", f"Relicense {ident} as {rights} ({origin})", f"Licence: {ident}, {rights}",
            f"`{ident}` was relicensed as {rights}")


def new_collection(form, origin):
    ident = identifier(form, "Identifier of the new collection")
    if list_path(ident).exists() or (Path("ocfl") / ident).exists() or \
            ident == settings().get("mainCollection"):
        raise Problem(f"`{ident}` is already taken in this archive.")
    title = field(form, "Title of the collection", required=True)
    kind = "catalogue" if field(form, "Kind").lower().startswith("catalogue") else "selection"
    parent = collection(form, required=False)
    data = {"title": title}
    if description := field(form, "Description"):
        data["description"] = description
    data.update({"type": kind, "order": "manual", "members": []})
    save(ident, data)
    sync(ident, f"New collection {ident} ({origin})")
    if field(form, "Feature it on the home page").lower().startswith("yes"):
        s = settings()
        s.setdefault("index", {}).setdefault("html", {"templates": "templates"})["featured"] = ident
        Path("osheaf.json").write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
    if parent:
        pdata = load(parent)
        insert(pdata, {"archive": own_base(), "id": ident}, position(form))
        save(parent, pdata)
        where = f" in the collection `{parent}`"
    else:
        where = ""
    return (parent, f"New collection {ident}{where} ({origin})", f"Collection: {ident}",
            f"the collection `{ident}` was created{where}")


def add(form, origin):
    cid = collection(form, required=True)
    data = load(cid)
    archive = archive_url(form, "Archive of the new member")
    ident = identifier(form, "Identifier of the new member", limit=64)
    revisions = versions(form, "Versions you vet (selection)")
    if any(m.get("id") == ident and same_archive(m.get("archive"), archive)
           for m in data["members"]):
        raise Problem(f"`{ident}` from `{archive}` is already a member of `{cid}`.")
    if same_archive(archive, own_base()) and (
            ident == settings().get("mainCollection") or ident == cid
            or (list_path(ident).exists() and cid in descendants(ident))):
        raise Problem(f"`{ident}` cannot be a member of itself, or of a collection inside it.")
    if revisions and data.get("type") != "selection":
        raise Problem(f"Versions are vetted only in a selection; `{cid}` is a catalogue, which "
                      "follows its members. Leave **Versions you vet** empty.")
    member = {"archive": archive, "id": ident}
    if revisions:
        member["revisions"] = revisions
    insert(data, member, position(form))
    save(cid, data)
    return (cid, f"Add {ident} from {archive} to {cid} ({origin})",
            f"Member added: {ident} (in {cid})", f"`{ident}` was added to `{cid}`")


def vet(form, origin):
    cid = collection(form, required=True)
    data = load(cid)
    if data.get("type") != "selection":
        raise Problem(f"Versions are vetted only in a selection; `{cid}` is a catalogue, which "
                      "follows its members (run **Update the collections** in the Actions tab to "
                      "move them on).")
    ident = identifier(form, "Member", limit=64)
    member = find(data, ident, archive_url(form, "Archive of the member", required=False))
    new = versions(form, "Versions to vet", required=True)
    old = list(member.get("revisions") or vetted(cid, ident))
    added = [v for v in new if v not in old]
    if not added:
        raise Problem(f"`{ident}` already has the versions {', '.join(map(str, new))} vetted.")
    member["revisions"] = sorted(old + added)
    save(cid, data)
    vs = ", ".join(map(str, added))
    return (cid, f"Vet version {vs} of {ident} in {cid} ({origin})",
            f"Vetted: {ident}, version {vs} (in {cid})", f"version {vs} of `{ident}` was vetted")


def remove(form, origin):
    cid = collection(form, required=True)
    data = load(cid)
    ident = identifier(form, "Member to remove", limit=64)
    member = find(data, ident, archive_url(form, "Archive of the member", required=False))
    data["members"].remove(member)
    save(cid, data)
    return (cid, f"Remove {ident} from {cid} ({origin})",
            f"Member removed: {ident} (from {cid})", f"`{ident}` was removed from `{cid}`")


def setup(form, origin):
    """Set the archive up (osheaf init), as the workflow "Set up the archive"
    does: for a page, which cannot start workflows."""
    if Path("osheaf.json").exists():
        raise Problem("The archive is already set up.")
    repo = os.environ.get("GITHUB_REPOSITORY", "owner/archive")
    owner, name_ = repo.split("/", 1)[0].lower(), repo.split("/", 1)[1]
    base = field(form, "Base URL") or (f"https://{owner}.github.io/" if name_.lower() == f"{owner}.github.io"
                                       else f"https://{owner}.github.io/{name_}/")
    base = base if base.endswith("/") else base + "/"
    import datetime
    archive_id = field(form, "Archive identifier") or \
        f"tag:{owner}.github.io,{datetime.date.today().year}:{name_.lower()}"
    title = field(form, "Name", required=True)
    args = ["init", ".", "--archive-id", archive_id, "--name", title, "--base-url", base,
            "--curator", field(form, "Curator", required=True)]
    for label, option in (("Affiliation", "--affiliation"), ("Contact", "--contact")):
        if value := field(form, label):
            args += [option, value]
    osheaf(*args)
    purpose = field(form, "Purpose").lower() or "papers"
    if purpose in ("selection", "catalogue"):
        ident = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:32].strip("-") or "collection"
        data = {"title": title}
        if description := field(form, "Description"):
            data["description"] = description
        data.update({"type": purpose, "order": "manual", "members": []})
        save(ident, data)
        sync(ident, f"The collection is set up ({origin})")
        s = settings()
        s.setdefault("index", {}).setdefault("html", {"templates": "templates"})["featured"] = ident
        Path("osheaf.json").write_text(json.dumps(s, indent=2, ensure_ascii=False) + "\n",
                                       encoding="utf-8")
        done = f"the archive was set up, with the collection `{ident}` featured on its home page"
    else:
        done = "the archive was set up"
    return ("", f"Set up the archive: {title} ({origin})", f"Setup: {title}", done)


OPERATIONS = {"setup": setup, "deposit": deposit, "notice": notice, "withdraw": withdraw, "relicense": relicense,
              "new_collection": new_collection, "add": add, "vet": vet, "remove": remove}


def snapshot():
    files = [Path("osheaf.json")] + (sorted(COLLECTIONS.glob("*.yaml")) if COLLECTIONS.exists() else [])
    return {p: p.read_text(encoding="utf-8") for p in files if p.exists()}


def restore(saved):
    for p in (list(COLLECTIONS.glob("*.yaml")) if COLLECTIONS.exists() else []):
        if p not in saved:
            p.unlink()
    for p, text in saved.items():
        p.write_text(text, encoding="utf-8")


def read_request(path):
    """A page's request: requests/ID/request.json, with the operation, the
    fields of the corresponding form (by their labels), and the files
    attached to fields, in the request's folder."""
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    form = {k: str(v) for k, v in (data.get("fields") or {}).items()}
    form["__files__"] = {k: list(v) for k, v in (data.get("files") or {}).items()}
    form["__dir__"] = path.parent
    return data.get("operation"), form, f"request {path.parent.name}"


def main():
    result_file = Path(os.environ.get("RESULT_FILE", "result.md"))
    if len(sys.argv) == 3 and sys.argv[1] == "--request":
        kind, form, origin = read_request(sys.argv[2])
        if kind not in OPERATIONS:
            result_file.write_text(f"Unknown operation `{kind}`.\n", encoding="utf-8")
            return 1
    else:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        issue = event["issue"]
        form = sections(issue.get("body"))
        kind = next((FORMS[h] for h in FORMS if h in form), None)
        origin = f"issue #{issue['number']}"
        if kind is None:
            result_file.write_text("This issue is not one of the archive's forms.\n",
                                   encoding="utf-8")
            return 2
    saved = snapshot() if Path("osheaf.json").exists() else {}
    try:
        if kind != "setup" and not Path("osheaf.json").exists():
            raise Problem("The archive is not set up yet: set it up first (the workflow **Set up "
                          "the archive** in the Actions tab, or the manager's setup).")
        cid, message, title, done = OPERATIONS[kind](form, origin)
        if why := field(form, "Why (optional)"):
            message += f": {why}"
        osheaf("collect")
        if cid:
            sync(cid, message)
            propagate(cid, message)
        osheaf("index")
        osheaf("verify")
    except Problem as p:
        restore(saved)
        result_file.write_text(
            f"Nothing was changed in the archive.\n\n{p}\n\n"
            + ("Edit this issue to correct it, then close and reopen it to try again.\n"
               if origin.startswith("issue") else "Correct it and send the request again.\n"),
            encoding="utf-8")
        return 1
    result_file.write_text(
        f"Done: {done}.\n\nThe archive's site, <{own_base()}>, shows it once GitHub Pages has "
        "published it (usually within a few minutes).\n", encoding="utf-8")
    Path(os.environ.get("COMMIT_FILE", "commit.txt")).write_text(message + "\n", encoding="utf-8")
    Path(os.environ.get("TITLE_FILE", "title.txt")).write_text(title + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
