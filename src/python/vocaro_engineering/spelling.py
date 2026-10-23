"""British spellings in a project's text, identifiers included (agents/core.md, Writing).

The words arrive one at a time and are invisible in review, and later sessions copy the spelling
they read, so they are caught mechanically. The checker began as mpm's tree-wide gate.

How a line is read: every run of letters is split at its camelCase, snake_case and SCREAMING_CASE
boundaries, and each subword is judged whole, never as a substring, because
`QuiescentRegionCount` contains "centRe" case-insensitively. A subword is British when it is
  * on the irregular list (licence, grey, whilst, catalogue, judgement, plough, misspelt, ...),
  * a doubled-l inflection of a known stem (travelled, labelling, modeller, counsellor, ...), or
  * a pattern hit (-ise/-yse/-our/-tre/-bre and their inflections) whose uninflected base is not
    an American word that merely looks British (AMERICAN_OK: exercise, contour, genre, ...).
Detection is by pattern rather than by word list, so a British form nobody anticipated is still
caught; the irregular list covers only what no pattern describes.

File names are judged the same way, binary files and directories included, because tests, docs
and scripts link to a file by its name and every reference must move when it is renamed. A name
is read like a line, so it splits at `/`, `.`, `-`, `_` and its camelCase boundaries; each
directory is judged once, reported as `dir/`. A content check alone passed `colour-chart.png`,
which has no text, and caught `NeighbourAlignmentTests.swift` only because its class repeated it.

What is exempt, each learned by breaking it:
  * Someone else's name, verbatim: another project's API (Unity's `MonoBehaviour`, Apple's
    `isCancelled`), a file name searched for literally (`LICENCE`). A project adds its own in
    engineering.json: proper names, a standard's terms, retained upstream text.
  * A cited title. The first <em> of a list item is a bibliography entry's title slot, kept
    verbatim even when the source is British; annotations after it are checked like any prose.
  * URLs, which are addresses rather than prose.
  * A line marked `spelling: keep` and a reason, such as a decoder that still reads a name
    stored before a rename.
  * The directional adverbs towards/backwards/forwards/afterwards: good American English, and a
    sweep that "corrected" one rewrote a cited title into one its authors never published.
  * Words only context can judge: "disc" and the temporal "any more". Review owns those.
  * A skipped path's own name, with its contents: recorded observations and retained upstream
    text keep the names they were given. The directories above it are still judged, and the
    skip entry's text is exempt wherever it appears, as a link to the kept name must spell it.
A hit is fixed by spelling the word the American way. A name that trips the rule goes into the
project's exemptions with its reason; a pattern is never widened to make a hit go away.

Positive controls run first, every time: a detector that has stopped detecting looks exactly like
a clean tree. Exit 0 when clean, 1 when a British spelling is found or a control fails, and 2 when
the run never happened.
"""
import os
from pathlib import Path
import re
import subprocess

BINARY = {".pdf", ".png", ".jpg", ".jpeg", ".gif", ".heic", ".tif", ".tiff", ".ico", ".icns",
          ".mp4", ".mov", ".m4a", ".wav", ".caf", ".aiff", ".mp3", ".exr", ".psd", ".ttf", ".otf",
          ".woff", ".woff2", ".zip", ".gz", ".xz", ".bz2", ".tar", ".epub", ".sqlite", ".car",
          ".meta"}

SUBWORD = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+")
URL = re.compile(r"https?://\S+")
# A string escape's letter would otherwise join the word after it: "\nraise" is not "nraise".
ESCAPE = re.compile(r"\\[nrtfvb0]")
KEEP = re.compile(r"spelling: keep\b\W*\w")

# Pattern families, each matched against a whole lowercase subword. `stem` + the family's base
# ending rebuilds the uninflected word that AMERICAN_OK is checked against.
ISE = re.compile(r"(?P<stem>[a-z]{3,}?)is(?P<suf>e|es|ed|ing|ation|ations|ational|able|er|ers)")
YSE = re.compile(r"(?P<stem>[a-z]{2,}?)ys(?P<suf>e|es|ed|ing|er|ers)")
OUR = re.compile(r"(?P<stem>[a-z]{2,}?)our(?P<suf>s|ed|ing|al|able|ably|ite|ites|ful|fully|less"
                 r"|hood|hoods|er|ers|ist|ists|ism|ly|ish)?")
TRE = re.compile(r"(?P<stem>[a-z]{2,}?)(?P<end>tre|bre)(?P<suf>s|d)?")   # me-tre, fi-bre
# The doubled-l inflections, by stem, with the prefixes that keep the doubling.
DOUBLE_L = re.compile(
    r"(?P<stem>(?:re|un|mis|pre)?(?:travel|cancel|model|label|marshal|signal|level|total|tunnel"
    r"|channel|counsel|dial|funnel|fuel|equal|panel|parcel|pedal|quarrel|rival|shovel|snorkel"
    r"|swivel|unravel|revel|jewel|bevel|chisel|cudgel|duel|enamel|gambol|grovel|kennel|libel"
    r"|marvel|pencil|spiral|tassel|towel|trammel|yodel|initial|dishevel))"
    r"l(?P<suf>ed|ing|er|ers|or|ors)")

IRREGULAR = {
    "licence": "license", "licences": "licenses", "licenced": "licensed", "licencing": "licensing",
    "defence": "defense", "defences": "defenses", "offence": "offense", "offences": "offenses",
    "pretence": "pretense", "pretences": "pretenses", "practise": "practice",
    "practises": "practices", "practised": "practiced", "practising": "practicing",
    "grey": "gray", "greys": "grays", "greyed": "grayed", "greying": "graying",
    "greyscale": "grayscale", "greyish": "grayish", "catalogue": "catalog", "catalogues": "catalogs",
    "catalogued": "cataloged", "cataloguing": "cataloging", "analogue": "analog",
    "analogues": "analogs", "judgement": "judgment", "judgements": "judgments",
    "acknowledgement": "acknowledgment", "acknowledgements": "acknowledgments",
    "artefact": "artifact", "artefacts": "artifacts", "encyclopaedia": "encyclopedia",
    "whilst": "while", "amongst": "among", "orientate": "orient", "orientated": "oriented",
    "orientating": "orienting", "manoeuvre": "maneuver", "manoeuvres": "maneuvers",
    "manoeuvred": "maneuvered", "manoeuvring": "maneuvering", "programme": "program",
    "programmes": "programs", "sulphur": "sulfur", "aluminium": "aluminum", "mould": "mold",
    "moulds": "molds", "moulded": "molded", "moulding": "molding", "storey": "story",
    "storeys": "stories", "tyre": "tire", "tyres": "tires", "kerb": "curb", "draught": "draft",
    "draughts": "drafts", "cheque": "check", "cheques": "checks", "plough": "plow",
    "ploughs": "plows", "ploughed": "plowed", "ploughing": "plowing", "skilful": "skillful",
    "wilful": "willful", "fulfil": "fulfill", "fulfils": "fulfills", "fulfilment": "fulfillment",
    "instil": "instill", "distil": "distill", "enthral": "enthrall", "instalment": "installment",
    "enrol": "enroll", "enrols": "enrolls", "enrolment": "enrollment", "learnt": "learned",
    "misspelt": "misspelled", "dreamt": "dreamed", "spoilt": "spoiled", "ageing": "aging",
    "sceptic": "skeptic", "sceptical": "skeptical", "scepticism": "skepticism", "cosy": "cozy",
    "maths": "math", "aeroplane": "airplane", "speciality": "specialty",
    "specialities": "specialties", "jewellery": "jewelry", "woollen": "woolen",
    "marvellous": "marvelous", "focussed": "focused", "focussing": "focusing",
    "benefitted": "benefited", "benefitting": "benefiting", "targetted": "targeted",
    "targetting": "targeting", "biassed": "biased", "enquire": "inquire", "enquiry": "inquiry",
    "enquiries": "inquiries", "tranquillity": "tranquility", "sizeable": "sizable",
    "useable": "usable", "moveable": "movable", "likeable": "likable", "liveable": "livable",
}

# American words the patterns mistake for British ones, as UNINFLECTED bases (the base of
# "revised" is "revise"). "analyses" is the American plural of "analysis", not the British
# verb; "redisable" is re-disable.
AMERICAN_OK = frozenset("""
advertise advise arise chastise comprise compromise concise cruise demise despise devise
disguise enterprise excise exercise expertise franchise guise improvise incise merchandise
paradise poise praise precise premise promise raise reprise revise rise sunrise moonrise
supervise surmise surprise televise treatise turquoise tortoise porpoise noise denoise bruise
appraise apprise
analyses
four hour our pour sour tour your flour scour devour contour detour dour amour glamour velour
acre cadre genre macabre massacre mediocre ogre lucre padre nacre timbre libre
redisable
""".split())

# A prefix that leaves an American word American: "unexercised" is un + exercised.
PREFIXES = ("un", "re", "pre", "non", "over", "under", "mis", "counter", "out", "self", "super",
            "sub", "semi", "multi", "inter")

# Whole identifier runs other projects named the British way: Unity's and Apple's APIs.
EXEMPT_RUNS = frozenset({
    "MonoBehaviour", "MonoBehaviours", "StateMachineBehaviour", "StateMachineBehaviours",
    "isCancelled", "userCancelled", "paymentCancelled", "operationCancelled",
    "NSUserCancelledError", "NSURLErrorCancelled", "touchesCancelled", "documentPickerWasCancelled",
    "matchmakerViewControllerWasCancelled", "turnBasedMatchmakerViewControllerWasCancelled",
    "reindexAllSearchableItemsWithAcknowledgementHandler", "acknowledgementHandler"})
# Case-sensitive subwords: a file name some projects use and audits search for literally, and
# Vocaro's Pagepour, a product name that ends in "pour".
EXEMPT_TOKENS = frozenset({"LICENCE", "Pagepour", "pagepour", "PAGEPOUR"})


def _family(word):
    """(suggestion, base) when `word` matches a pattern family; None otherwise."""
    if word.endswith("wise"):                 # otherwise, pairwise, nodewise: never -ize
        return None
    m = ISE.fullmatch(word)
    if m:
        return m.group("stem") + "iz" + m.group("suf"), m.group("stem") + "ise"
    m = YSE.fullmatch(word)
    if m:
        return m.group("stem") + "yz" + m.group("suf"), m.group("stem") + "yse"
    m = OUR.fullmatch(word)
    if m:
        return m.group("stem") + "or" + (m.group("suf") or ""), m.group("stem") + "our"
    m = TRE.fullmatch(word)
    if m:
        end = "ter" if m.group("end") == "tre" else "ber"
        suf = {"s": "s", "d": "ed"}.get(m.group("suf") or "", "")
        return m.group("stem") + end + suf, m.group("stem") + m.group("end")
    return None


def american_for(subword):
    """The American spelling of a British subword, or None when it is not British."""
    w = subword.lower()
    if w in IRREGULAR:
        return IRREGULAR[w]
    m = DOUBLE_L.fullmatch(w)
    if m:
        return m.group("stem") + m.group("suf")
    hit = _family(w)
    if hit is None or w in AMERICAN_OK or hit[1] in AMERICAN_OK:
        return None
    for p in PREFIXES:                        # un + exercised: judge what follows the prefix
        if w.startswith(p) and len(w) > len(p) + 3:
            rest = _family(w[len(p):])
            if rest is not None and rest[1] in AMERICAN_OK:
                return None
    return hit[0]


class Rules:
    """The built-in exemptions plus a project's own from engineering.json's `spelling`."""

    def __init__(self, project=None):
        project = project or {}
        self.skip = tuple(project.get("skip", {}))
        # A skipped path keeps its name, so its skip entry and a link to it spell it as kept.
        self.phrases = tuple(sorted({*project.get("exemptPhrases", {}), *self.skip}, key=len,
                                    reverse=True))
        self.runs = EXEMPT_RUNS | set(project.get("exemptRuns", {}))
        self.tokens = EXEMPT_TOKENS | set(project.get("exemptTokens", {}))

    def skips(self, path):
        return any(path == s or (s.endswith("/") and path.startswith(s)) for s in self.skip)

    def british_in(self, line):
        """[(subword, american)] for every British subword on one line of text."""
        if KEEP.search(line):
            return []
        line = ESCAPE.sub(" ", URL.sub(" ", line))
        for phrase in self.phrases:
            line = line.replace(phrase, " ")
        found = []
        for m in re.finditer(r"[A-Za-z]+", line):
            run = m.group(0)
            if run in self.runs:
                continue
            for sub in SUBWORD.findall(run):
                if sub in self.tokens:
                    continue
                american = american_for(sub)
                if american:
                    found.append((sub, american))
        return found


BRITISH_SAMPLES = r"""colour Colour COLOUR colourRamp NEIGHBOUR_OFFSETS HarbourBreachStage
    normalised Normalisation renormalised unnormalised analyse centre centres Centred fibre licence
    defence grey whilst catalogue analogue travelled labelling relabelled modeller counsellor
    bevelled unfavourable unrecognised behaviour misspelt practise kilometres
    BehaviourBoundError licence_display wasCancelled \ncolour""".split()
AMERICAN_SAMPLES = r"""QuiescentRegionCount MonoBehaviour aria-labelledby towards afterwards exercise
    unexercised advertised revised surprising unsurprising contour hours yours Fourier genre acres
    timbre controlled installer cancellation distilled fulfilled nodewise pairwise otherwise
    LICENCE disc redisable analyses center color behavior normalize harbor isCancelled
    userCancelled LibreSSL Pagepour \nraise sunrise https://example.com/colour-grading""".split()
# Tracked paths: a binary file's name, a directory's, and a file name split at camelCase.
BRITISH_PATHS = ("Docs/colour-chart.png", "centre/README.md", "Tests/NeighbourAlignmentTests.swift",
                 "Fonts/grey_sans.ttf")
AMERICAN_PATHS = ("LICENCE", "Sources/QuiescentRegionCount.swift", "Unity/MonoBehaviour.cs",
                  "center/color-chart.png")


def names_of(paths, rules):
    """Every file and directory name the paths hold, each once and a directory as `dir/`, with
    skipped paths' own names left out."""
    held = set(paths)
    for path in paths:
        parts = path.split("/")
        held.update("/".join(parts[:i]) + "/" for i in range(1, len(parts)))
    return sorted(name for name in held if not rules.skips(name))


def british_names(names, rules):
    """[(name, subword, american)] for every British subword in each name's last component."""
    return [(name, sub, american) for name in names
            for sub, american in rules.british_in(name.rstrip("/").rsplit("/", 1)[-1])]


def controls():
    """Failures of the built-in positive controls; empty when the detector still detects."""
    rules = Rules()
    failures = [f"'{s}' was not flagged" for s in BRITISH_SAMPLES if not rules.british_in(s)]
    failures += [f"'{s}' was flagged as {rules.british_in(s)}" for s in AMERICAN_SAMPLES
                 if rules.british_in(s)]
    flagged = {s: british_names(names_of([s], rules), rules) for s in BRITISH_PATHS + AMERICAN_PATHS}
    failures += [f"file name '{s}' was not flagged" for s in BRITISH_PATHS if not flagged[s]]
    failures += [f"file name '{s}' was flagged as {flagged[s]}" for s in AMERICAN_PATHS if flagged[s]]
    return failures


LIST_ITEM = re.compile(r"<li>.*?</li>", re.S)
FIRST_EM = re.compile(r"<em>.*?</em>", re.S)


def problems_in(text, rules):
    """[(line, subword, american)] in one file's text, cited titles aside."""
    # The first <em> of each <li> is a bibliography entry's verbatim title slot. Blank only the
    # title, keeping its line breaks, so an annotation on the same line is still read.
    if "<li>" in text:
        titles = [em.span() for li in LIST_ITEM.finditer(text)
                  for em in [FIRST_EM.search(text, li.start(), li.end())] if em]
        for start, end in reversed(titles):
            text = text[:start] + re.sub(r"[^\n]", " ", text[start:end]) + text[end:]
    return [(i, sub, american) for i, line in enumerate(text.split("\n"), 1)
            for sub, american in rules.british_in(line)]


def check(root, config, paths=(), out=print):
    """Report every British spelling in the project's file names and text; return the exit status.

    With no paths it reads what a push carries: tracked files. Named paths, relative to the
    current directory, also read untracked files Git does not ignore, so a page about to be
    published from disk is checked before it is committed.
    """
    root = Path(root).resolve()
    failures = controls()
    if failures:
        for failure in failures:
            out(f"eng spelling: CONTROL FAILED — {failure}")
        out("eng spelling: FAIL — the detector itself is wrong; no file result can be trusted")
        return 1
    rules = Rules(config.get("spelling"))
    named = []
    for path in paths:
        relative = os.path.relpath(Path(path).resolve(), root)
        if relative == ".." or relative.startswith("../"):
            out(f"eng spelling: {path} is outside {root}; nothing was checked.")
            return 2
        named.append(relative)
    untracked = ["--others", "--exclude-standard"] if named else []
    try:
        listed = subprocess.run(["git", "-C", str(root), "ls-files", "-z", "--cached", *untracked,
                                 "--", *named], check=True, capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError) as error:
        out(f"eng spelling: cannot list tracked files ({error}); nothing was checked.")
        return 2
    this = Path(__file__).resolve()
    tracked = sorted({f for f in os.fsdecode(listed.stdout).split("\0") if f})
    names = names_of(tracked, rules)
    files = [f for f in tracked if not rules.skips(f) and os.path.splitext(f)[1].lower() not in BINARY
             and (root / f).is_file() and (root / f).resolve() != this]
    if named and not names:
        out(f"eng spelling: no files under {' '.join(paths)}; nothing was checked.")
        return 2
    found = 0
    for name, sub, american in british_names(names, rules):
        out(f"{name}: British spelling in file name '{sub}' -> {american}")
        found += 1
    for f in files:
        raw = (root / f).read_bytes()
        if b"\0" in raw[:8192]:
            continue                                  # binary content under a text-looking name
        for line, sub, american in problems_in(raw.decode("utf-8", "replace"), rules):
            out(f"{f}:{line}: British spelling '{sub}' -> {american}")
            found += 1
    if found:
        out(f"eng spelling: FAIL — {found} British spelling(s) in {len(files)} text file(s) and "
            f"{len(names)} file name(s). Spell them the American way (agents/core.md, Writing).")
        return 1
    out(f"eng spelling: PASS — {len(files)} text file(s) and {len(names)} file name(s), identifiers "
        f"split at their word boundaries, {len(BRITISH_SAMPLES)}/{len(AMERICAN_SAMPLES)} British/"
        f"American word and {len(BRITISH_PATHS)}/{len(AMERICAN_PATHS)} file name controls held")
    return 0
