# featherview.github.io

The website for Featherview, a fast, keyboard-driven image viewer for macOS:
https://featherview.mynetx.net

One static `index.html`, no build step and no dependencies. GitHub Pages publishes every push to
`main` within a minute. To preview it locally, open `index.html` in a browser.

The demo photos are generated in the page itself, so the repo holds no image files.

## Languages

`index.html` stays English. Every other language lives in `i18n/<lang>.json`: a small script in the
page's `<head>` picks the visitor's choice for this session (the picker in the nav), else the
browser's language, loads that file and shows the page once it's applied. English loads nothing extra.

After changing text in `index.html`, run `python3 tools/i18n.py`. It marks new text elements, refreshes
`i18n/en.json` and translates whatever is new or changed in every language (one `claude -p` call per
language; strings the app already has take the app's translation from `../featherview`).
`i18n/sources.json` records which English each translation came from, so running it for a few
languages (`python3 tools/i18n.py de fr`) leaves nothing stale in the others.

Hand corrections in `i18n/<lang>.json` stay until the English of that string changes; then the
string is translated again and the correction is gone, so check those strings after the run.
Numbers that are edited by hand inside translated text (the sponsor amount) are marked `data-keep`
and keep their English value in every language. The version on the Download button sits in
`#dlv`, which the app's `scripts/release.sh` updates.
