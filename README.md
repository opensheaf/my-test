# An OpenSheaf archive

> [!WARNING]
> **Draft.** OpenSheaf 0.1 is a draft specification. Until version 1.0, any
> revision may change the format in incompatible ways. Archives and collections made now
> may have to be rebuilt or migrated, and the tools follow the latest draft.
> Do not rely on it yet for anything you cannot redo.

A template for an archive of papers, and for collections of papers from any
archive: your own papers, every version with its sources and PDF, fixed by
digests, with standard metadata, a website with a page per paper (read by
Google Scholar), and optionally DOIs from Zenodo; and collections, such as
a reading list, a journal issue or the papers of a group, which pin papers of
any OpenSheaf archive without copying them. A repository can be mainly an
author's archive, mainly a collection, or both. The archive is plain files in
a git repository, following the
[OpenSheaf specification](https://opensheaf.org) (an
[OCFL](https://ocfl.io) storage root with [DataCite](https://datacite.org)
metadata), and is kept with [opensheaf-py](https://github.com/opensheaf/opensheaf-py)
(the `osheaf` command). The first archive made this way is
[mgubi.org/papers](https://mgubi.org/papers/).

There are two ways to keep it: from the browser, without git or any
installation (next section), or with the `osheaf` command (sections 1 to 6).
Both give the same archive, and can be mixed.

## From the browser

1. Press **Use this template** on GitHub, for instance as a repository called
   `papers`.
2. In your new repository: **Actions**, **Set up the archive**, **Run
   workflow**, and fill in the form: the name, what the repository is mainly
   for (**papers**; a **selection**, such as a reading list or a journal
   issue, whose curator vets particular versions; or a **catalogue**, which
   follows its members whatever their authors add), and your name; the rest
   can stay empty. For a selection or a catalogue, it creates that
   collection and features it on the home page. It sets the archive up and
   turns GitHub Pages on; if it cannot (usually), the run's page says how to turn it on yourself
   (**Settings**, **Pages**, **Deploy from a branch**, branch `main`, folder
   `/ (root)`). The site is at `https://USER.github.io/papers/`; if your
   GitHub Pages use a domain of your own, give the address on that domain in
   the form's last field.
3. To deposit a paper: **Issues**, **New issue**, **New deposit**. Fill in the
   form and drag in the PDF and the sources (best as one zip: GitHub does not
   accept every kind of file, such as `.tex`, as an attachment), then submit.
   The workflow `from issue` deposits the paper, publishes the site and
   answers in the issue with the link to the paper's page. A new version: the
   same form, with the same identifier.
4. Notices, withdrawals and new licences have forms of their own (**Notice**,
   **Withdrawal**, **New licence**).
5. Collections:
   - **New collection**: a selection or a catalogue of this archive, possibly
     inside another (a section of a reading list, an issue of a journal),
     possibly featured on the home page;
   - **Add a member**: a paper (or a collection) of any OpenSheaf archive,
     this one included, given by the address of its archive and its
     identifier, and, in a selection, the versions you vet;
   - **Vet a new version** (selections) and **Remove a member**;
   - a deposit can also name a collection to join (**In collection**).

   When a collection inside another changes, the collections that include it
   follow (in a selection, its new version is vetted). To follow new versions
   of the members: **Actions**, **Update the collections**, **Run workflow**;
   a catalogue moves on, a selection never changes by itself and the run's
   page lists the versions you have not vetted.

Only the owner of the repository and its collaborators can change the
archive this way; issues opened by others are answered and closed. What is
attached to an issue is public at once. If something is wrong, the workflow
says so in the issue and changes nothing: edit the issue, then close and
reopen it to try again. Each issue stays as the record of what was done.

## 1. Make your copy

Press **Use this template** on GitHub (for instance a repository called
`papers`), clone it, and install the tools (Python 3.9 or later):

```
pipx install "opensheaf[validate] @ git+https://github.com/opensheaf/opensheaf-py"
```

## 2. Set it up

In your clone, edit [archive.yaml](archive.yaml) and run

```
osheaf init . --from archive.yaml
```

or give the settings on the command line:

```
osheaf init . \
  --archive-id tag:example.org,2026:papers \
  --name "Papers of Jane Doe" \
  --base-url https://janedoe.github.io/papers/ \
  --curator "Doe, Jane" --affiliation "Example University" \
  --contact https://example.org/~jane
```

- `--archive-id` names the archive forever, also if it moves: a
  [tag URI](https://www.rfc-editor.org/rfc/rfc4151) built from a domain or an
  e-mail address you control and the year (`tag:janedoe@example.org,2026:papers`
  works too).
- `--base-url` is where the site is served: with GitHub Pages,
  `https://USER.github.io/REPOSITORY/`, or your own domain.

This writes `osheaf.json` (the settings), the storage root `ocfl/`, the main
collection, the discovery document `opensheaf.json` and the website.

## 3. Deposit a paper

Describe the paper in a YAML file, as in
[deposits/example.yaml](deposits/example.yaml), and run

```
osheaf deposit --from deposits/kpz-uniqueness.yaml
osheaf collect
osheaf index
osheaf verify
git add -A && git commit -m "Deposit kpz-uniqueness" && git push
```

Files and options are read as text, relative to the YAML file; a list of
entries deposits several papers or versions in order. The same can be done on
the command line:

```
osheaf deposit kpz-uniqueness paper.tex --pdf paper.pdf \
  --extra-source refs.bib --extra-source figures/fig1.pdf=figures/fig1.pdf \
  --title 'Energy solutions of KPZ are unique' \
  --author "Doe, Jane|Example University" --author "Roe, Richard|Another University" \
  --abstract-file abstract.txt --rights cc-by-4.0 \
  --related "IsIdenticalTo:arxiv:1508.07764"
```

- The identifier (`kpz-uniqueness`) is permanent and appears in the URL of
  the paper: short (at most 32 characters), lower case, words joined by `-`.
- Sources are any files (LaTeX, Markdown, ...); `--extra-source FILE=PATH`
  puts a file at the path the main source refers to. The PDF is yours: the
  archive keeps exactly the files you give. A paper whose sources are lost can
  be deposited as a PDF alone (`--no-source "the sources were lost"`).
- Titles and abstracts are plain text with mathematics in `$...$`.
- Licence: `--rights cc-by-4.0` (or `cc0-1.0`, or a statement such as
  "All rights reserved", the default); check what your publisher allows for
  papers published in journals.
- A new version: deposit again with the same identifier (`--changes "..."`
  says what changed; abstract, keywords and licence are kept unless given).
  A version written earlier but never public (a submitted manuscript) is
  deposited with `--created DATE`; one found later goes in its place in the
  history with `--after N`.
- Dates: `--available DATE` when the version became public (default today),
  `--issued DATE` when the paper first appeared anywhere.

Nothing deposited is ever changed: corrections are new versions, and a
licence or a link is changed by a description-only version
(`osheaf relicense`, `osheaf relate`). `osheaf --help` lists everything.

## 4. Collections

A collection is an object of the archive that lists papers (and other
collections) of any OpenSheaf archive, each pinned by the SHA-512 digest of an
inventory, so that it fixes exactly what it lists and anyone can check it
(section 10 of the specification):

- a **selection** vets particular versions: a reading list the versions you
  read and recommend, a journal issue the versions its editors accepted. Its
  members pin those versions (their *revisions*), and nothing changes unless
  you change it;
- a **catalogue** follows its members whatever their authors add: the papers
  of a group, the objects a repository preserves.

The main collection of the archive lists the archive's own papers and is kept
by `osheaf collect`; collections are kept apart, each with its members in
`collections/ID.yaml`:

```yaml
title: A reading list on stochastic quantisation
description: Papers on the stochastic quantisation of Euclidean field theories.
type: selection
order: manual
members:
  - {archive: https://mgubi.org/papers/, id: fractional-phi42-mass-gap}
  - {archive: https://mgubi.org/papers/, id: paracontrolled-distributions, revisions: [5]}
```

`revisions` lists the document versions you vet (1, 2, ...); a member without
it is vetted in its current version when first synced, and keeps that
revision. For a catalogue write `type: catalogue`: its members follow their
objects, unless you fix one with `version: vN`. A member may be a paper or a
collection, in any OpenSheaf archive, this one included. Then

```
osheaf collection sync reading-list --from collections/reading-list.yaml
osheaf index
osheaf verify --remote
```

`sync` reads each member's archive, pins the revisions you vet (or, in a
catalogue, the newest object version), checks each pin, and caches a
citation, so that the list stays readable even if a member's archive
disappears. `osheaf collection update reading-list` moves a catalogue's
members on, and lists, for a selection, the versions not yet vetted. To show
a collection first on the home page, before the archive's own papers, set
`"featured": "reading-list"` under `index.html` in `osheaf.json`.

## 5. Publish

On GitHub: **Settings → Pages → Deploy from a branch**, branch `main`, folder
`/ (root)`. The site is then at the base URL you chose. Every push is
checked by the workflow `verify` (`osheaf verify`, with the JSON Schemas and
an independent OCFL validator).

## 6. Make it yours

- The look: edit `templates/index.html`, `templates/paper.html` and
  `templates/style.css` (placeholders like `{{title}}`), then `osheaf index`.
- DOIs: `osheaf zenodo ID` deposits the current version of a paper on Zenodo
  and records its DOI (on the Zenodo sandbox, on a copy, unless
  `--production`; tokens in the macOS keychain, see `osheaf zenodo --help`).
- Papers from arXiv: `osheaf arxiv fetch downloads --author YOUR_ARXIV_ID`,
  then `osheaf arxiv import downloads` (every version, with arXiv's files and
  licences; see the README of opensheaf-py).
- Collections of other people's papers, mirrors and signatures: see the
  [specification](https://opensheaf.org) and the
  [FAQ](https://github.com/opensheaf/opensheaf.github.io/blob/main/FAQ.md).

## A testing ground

`examples/run.sh` builds a throwaway archive from the
[example papers](https://github.com/opensheaf/example-papers) (invented
papers, TeXmacs papers and slides from tm-forge, fake arXiv downloads) and
runs every workflow of the tools, also the unusual ones: versions deposited
out of order, a notice with an erratum, a version after a notice, the sources
of a PDF-only version found later, a new licence, an arXiv import, a
withdrawal. Clone the example papers next to your repository and run

```
examples/run.sh
```

to see what each command does (the archive goes to a temporary folder; this
repository is not changed). The workflow `examples` runs it on every push and
every week, together with the two scripts below, and keeps the archives
they built as artifacts. Delete `examples/` when you start your own archive
if you like.

`examples/collections.sh` builds a member archive from the
[example papers](https://github.com/opensheaf/example-papers) and two
collections with members from it and from a real archive: a
catalogue (followed members, a fixed version, a member that is itself a
collection) and a selection (a reading list). It goes through their
workflows: a new version, followed by the catalogue and only
reported by the selection until the curator vets it; a withdrawal, followed
by one and shown by both; a member that disappears and is reported by
`verify --remote`. Clone the example papers next to this repository and run
`examples/collections.sh` (`OFFLINE=1` leaves out the real archive).

### Journals

`examples/journals.sh` builds two journals from real papers of
[Quantum](https://quantum-journal.org) (volume 7, 2023, CC BY 4.0; an
unofficial demonstration, not made by or for Quantum):

- a journal that **accepts** vetted versions: the authors keep every version
  in their own archive; the journal copies exactly the version it vetted
  (`osheaf accept ... --version v2`) into a document of its own archive, byte
  for byte, with its source and pin, and its issue is a selection of these
  documents, pinning the revisions the editors vetted.
  The authors' later versions change nothing at the journal: a correction is
  an editorial act (a new version of the journal's document, or a notice),
  and enters the issue only when the editors vet it (a new version of the
  issue).
  Only the vetted version needs an open licence, so a paper whose first arXiv
  version is not openly licensed (and could not be mirrored as a whole) can
  be accepted; and the journal still verifies when the authors' archive is
  gone;
- a journal that **repackages** the papers: it deposits its versions of record
  (its typeset PDF, its DOI, its licence, the authors' agreement in
  `object.json`) as documents of its own archive, linked to the authors'
  arXiv versions.

## Licence

This template (the pages, style and workflow) is dedicated to the public
domain under [CC0 1.0](LICENSE): use it as you like. The papers you deposit
carry the licences you give them; the archive's metadata is placed under CC0,
as the specification asks.
