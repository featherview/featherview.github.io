#!/usr/bin/env python3
"""Website translations. index.html stays English; i18n/<lang>.json holds every other language.

python3 tools/i18n.py              annotate new text in index.html, refresh i18n/en.json, translate what's missing
python3 tools/i18n.py de fr        the same, only these languages

Text elements get data-i18n="<key>" (their innerHTML is translated), elements with only translatable
attributes get data-i18n-attr="<key>" (en.json holds "<key>@<attr>"), and strings the demo script shows
are written T("…") there and keyed by their English text. An element with data-keep inside translated
text (a number edited by hand) keeps its English content in every language. translate="no" or a lang
attribute leaves an element out. Strings the app has (Resources/Localizable.xcstrings in ../featherview)
take the app's translation as they are; other app terms go to Claude as a glossary, so the demo matches the app.
"""
import hashlib, json, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from bs4 import BeautifulSoup, NavigableString, Tag

ROOT = Path(__file__).resolve().parent.parent
PAGE, DIR = ROOT / "index.html", ROOT / "i18n"
SOURCES = DIR / "sources.json"  # per language: key -> hash of the English it was translated from
LANGS = "ar ca cs da de el es fi fr he hi hu id it ja ko ms nl pl pt-BR ro ru sv th tr uk vi zh-Hans zh-Hant".split()
SKIP = {"script", "style", "svg", "code", "pre", "kbd", "template", "select", "option", "textarea"}
ATTRS = ["aria-label", "title", "alt", "aria-roledescription", "placeholder"]
LETTER = re.compile(r"[^\W\d_]{2}")
CATALOG = ROOT.parent / "featherview" / "Resources" / "Localizable.xcstrings"


def app_strings():
    """English app string -> {lang: translation}."""
    if not CATALOG.exists():
        return {}
    out = {}
    for key, entry in json.loads(CATALOG.read_text())["strings"].items():
        loc = entry.get("localizations", {})
        en = loc.get("en", {}).get("stringUnit", {}).get("value", key)
        out[en] = {l: v["stringUnit"]["value"] for l, v in loc.items() if "stringUnit" in v}
    return out


def plain(s):
    return re.sub(r"<[^>]+>", "", s).strip()


def skipped(el):
    return el.name in SKIP or el.get("translate") == "no" or el.has_attr("lang") and el.name != "html"


def annotate(src):
    """Adds data-i18n / data-i18n-attr to new elements, at their exact place in the source."""
    soup = BeautifulSoup(src, "html.parser")
    used = {e.get("data-i18n") or e.get("data-i18n-attr") for e in soup.select("[data-i18n],[data-i18n-attr]")}
    count, inserts = {}, []

    def key(el):
        anc = next((a for a in el.parents if isinstance(a, Tag) and a.get("id") and a.name != "html"), None)
        prefix = anc["id"] if anc else ("head" if el.find_parent("head") else "page")
        while True:
            count[prefix] = count.get(prefix, 0) + 1
            k = f"{prefix}.{count[prefix]}"
            if k not in used:
                used.add(k)
                return k

    def walk(el):
        if skipped(el):
            return
        if el.has_attr("data-i18n"):
            return
        direct = any(isinstance(c, NavigableString) and LETTER.search(c) for c in el.children)
        if direct and el.name not in ("html", "head", "body"):
            inserts.append((el, "data-i18n"))
            return
        if not el.has_attr("data-i18n-attr") and any(LETTER.search(el.get(a, "")) for a in ATTRS) or (
                el.name == "meta" and el.get("name") == "description" and not el.has_attr("data-i18n-attr")):
            inserts.append((el, "data-i18n-attr"))
        for c in el.children:
            if isinstance(c, Tag):
                walk(c)

    walk(soup.html)
    lines = src.split("\n")
    starts = [0]
    for line in lines:
        starts.append(starts[-1] + len(line) + 1)
    edits = sorted(((starts[el.sourceline - 1] + el.sourcepos + 1 + len(el.name), f' {attr}="{key(el)}"')
                    for el, attr in inserts), reverse=True)
    for pos, text in edits:
        src = src[:pos] + text + src[pos:]
    return src, len(edits)


def extract(src):
    soup = BeautifulSoup(src, "html.parser")
    en = {}
    for el in soup.select("[data-keep]"):
        el.clear()  # its value comes from the page, so a new version or amount doesn't need a new translation
    for el in soup.select("[data-i18n]"):
        v = el.decode_contents().strip()
        if not re.fullmatch(r"\.\w+", v):  # a file extension stays as it is
            en[el["data-i18n"]] = v
    for el in soup.select("[data-i18n-attr]"):
        for a in ATTRS + ["content"]:
            if el.has_attr(a) and LETTER.search(el[a]) and not re.fullmatch(r"\.\w+", el[a]):
                en[f'{el["data-i18n-attr"]}@{a}'] = el[a]
    for script in soup.find_all("script"):
        for lit in re.findall(r'\bT\(("(?:[^"\\]|\\.)*")', script.string or ""):
            s = json.loads(lit)
            en[s] = s
    return en


PROMPT = """Translate the strings of the website of Featherview, a free, open-source image viewer for the Mac, \
from English into {name} ({code}). The JSON below maps keys to English strings; return the same keys with the \
translations.

- Tone: transcreate, don't translate. The English is witty and understated, with puns, deadpan jokes and \
short punchlines ("Your mouse can take the day off.", "Rotation without regret", "Nosy, on request"). Write \
what a sharp native copywriter would write for this page: equally clever and light, with wordplay rebuilt in \
the language where a literal version would fall flat, never stiff or wordy, never more salesy. Address the reader informally (du, tu, je, ты …) \
where that is natural for a consumer app's website in that language and culture; otherwise use the polite form \
that such sites use there. Stay consistent.
- Many strings are HTML. Keep every tag and attribute exactly as it is, in a natural order for the sentence; \
translate the text and the values of aria-label, title and alt. Keep &nbsp; and other entities where a break \
must not happen. Keep {{name}}-style placeholders unchanged.
- Don't translate: Featherview, IrfanView, Irfan Škiljan, GitHub, Homebrew, MIT, Swift, file names, file \
formats (JPEG, HEIC, PSD …), product names (Photoshop, GIMP, Krita, Procreate …), camera names, commands, \
key names (R, L, I, F, Esc, ⌦, →) and paths.
- Apple's apps and settings by their official names on a Mac set to that language (Finder, Preview, Terminal, \
System Settings › Privacy & Security, Trash, Photos, Quick Look, Maps …).
- Idioms, not literal phrases: "Only one of them moves on" means only one of the two apps gets anywhere \
(German: "Nur einer kommt vom Fleck."); "Your mouse can take the day off" is a holiday joke; "the part you're \
looking at" means right now. The hero heading "Photos at the speed of →" must end with the → key, as a pun on \
"the speed of light/sound" where the language allows ("Fotos, so schnell wie →").
- Money in the reader's currency: euro countries' languages write only euros (99 €, 5 €, "0 of 99 €"), \
others keep US dollars ($99, $5). The fee paragraph is a warm, personal plea in the reader's own idiom.
- Keep it about as long as the English; headings stay punchy. Numbers and units as written in that language.
- The app's own wording for these terms (use it where they appear):
{glossary}

{strings}"""

NAMES = {"ar": "Arabic", "ca": "Catalan", "cs": "Czech", "da": "Danish", "de": "German", "el": "Greek",
         "es": "Spanish", "fi": "Finnish", "fr": "French", "he": "Hebrew", "hi": "Hindi", "hu": "Hungarian",
         "id": "Indonesian", "it": "Italian", "ja": "Japanese", "ko": "Korean", "ms": "Malay", "nl": "Dutch",
         "pl": "Polish", "pt-BR": "Brazilian Portuguese", "ro": "Romanian", "ru": "Russian", "sv": "Swedish",
         "th": "Thai", "tr": "Turkish", "uk": "Ukrainian", "vi": "Vietnamese", "zh-Hans": "Simplified Chinese",
         "zh-Hant": "Traditional Chinese (Taiwan)"}


UNIT = re.compile(r"(\d) (?=(?:ms|s|MB|GB|KB|MP|px|mm|m|%|€|\$|×)(?![\w]))")


def keep_together(s, code=""):
    """A number never wraps away from its unit, whatever the translation did with &nbsp;; in right-to-left
    languages an arrow key is isolated, everywhere it stays with the word before it,, so the bidi order doesn't move it past the punctuation next to it."""
    s = UNIT.sub("\\1\u00a0", s).replace("99 €", "99\u00a0€")
    s = re.sub(" (?=\u2066?[←→](?:\u2069)?[.,;:!?。،]?(?:$|[\s<]))", "\u00a0", s)  # "press →" stays on one line
    if code != "he":  # typographic apostrophes, as in the English (Hebrew's geresh stays)
        s = re.sub(r"(<[^>]*>)|'", lambda m: m.group(1) or "\u2019", s)
    if code in ("ar", "he"):
        s = re.sub("(?<!\u2066)([←→↑↓])(?!\u2069)", "\u2066\\1\u2069", s)
    return s


def tags(s):
    return sorted(re.findall(r"<(/?\w+)", s))


def digest(s):
    return hashlib.sha1(s.encode()).hexdigest()[:10]


def translate(code, en, src, app):
    path = DIR / f"{code}.json"
    have = json.loads(path.read_text()) if path.exists() else {}
    # a key whose English changed since it was translated is translated again; keys gone from the page are dropped
    have = {k: v for k, v in have.items() if k in en and src.get(k, digest(en[k])) == digest(en[k])}
    todo = {k: v for k, v in en.items() if k not in have}
    for k, v in list(todo.items()):
        t = plain(v)
        if code in app.get(t, {}) and t in v:
            have[k] = v.replace(t, app[t][code])
            del todo[k]
    if todo:
        text = " ".join(plain(v) for v in todo.values()).lower()
        glossary = "\n".join(f"  {e} = {tr[code]}" for e, tr in app.items()
                             if code in tr and len(e) > 3 and len(e) < 40 and e.lower() in text) or "  (none)"
        ids = {f"s{i}": k for i, k in enumerate(todo)}  # the API takes only simple property names
        schema = {"type": "object", "additionalProperties": False, "required": list(ids),
                  "properties": {i: {"type": "string"} for i in ids}}
        prompt = PROMPT.format(name=NAMES[code], code=code, glossary=glossary,
                               strings=json.dumps({i: todo[k] for i, k in ids.items()}, ensure_ascii=False, indent=1))
        out = subprocess.run(["claude", "-p", "--model", "sonnet", "--tools", "", "--output-format", "json",
                              "--json-schema", json.dumps(schema)], input=prompt, capture_output=True, text=True)
        res = json.loads(out.stdout or "{}") if out.stdout.startswith("{") else {}
        got = {ids[i]: v for i, v in (res.get("structured_output") or {}).items() if i in ids}
        if not got:
            print(f"{code}: no answer: {(res.get('result') or out.stderr)[:300]}")
        bad = [k for k in todo if k not in got or tags(got[k]) != tags(todo[k])]
        have.update({k: keep_together(v, code) for k, v in got.items() if k in todo and k not in bad})
        if bad:
            print(f"{code}: {len(bad)} strings missing or with changed markup, run again: {', '.join(bad[:5])}")
    path.write_text(json.dumps({k: have[k] for k in en if k in have}, ensure_ascii=False, indent=1) + "\n")
    return code, len(todo), len(have) == len(en), {k: digest(en[k]) for k in en if k in have}


def main():
    langs = sys.argv[1:] or LANGS
    src, added = annotate(PAGE.read_text())
    if added:
        PAGE.write_text(src)
        print(f"annotated {added} new elements")
    DIR.mkdir(exist_ok=True)
    en_path = DIR / "en.json"
    sources = json.loads(SOURCES.read_text()) if SOURCES.exists() else {}
    en = extract(src)
    en_path.write_text(json.dumps(en, ensure_ascii=False, indent=1) + "\n")
    app = app_strings()
    with ThreadPoolExecutor(6) as pool:
        for code, n, done, hashes in pool.map(lambda c: translate(c, en, sources.get(c, {}), app), langs):
            sources[code] = hashes
            print(f"{code}: {n} translated{'' if done else ', incomplete'}")
    SOURCES.write_text(json.dumps(sources, indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
