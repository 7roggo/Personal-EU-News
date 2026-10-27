#!/usr/bin/env python3
"""Hemicycle Brief morning bot.

Reads the news feeds listed in bot/feeds.json, keeps EU-related stories from the
last day and a half, groups headlines that cover the same event, and writes
today's edition to site/data/ for the website to show.

Two modes:
  * Headlines mode (free, default): stories covered by both left- and
    right-leaning outlets, with each side's headlines and links, plus stories
    only one side is covering.
  * Written mode: if the ANTHROPIC_API_KEY environment variable is set, Claude
    picks the main stories and writes a neutral summary plus a short note on how
    each side frames them. Falls back to headlines mode if anything goes wrong.

Usage:
  python bot/update.py              # normal run
  python bot/update.py --no-ai      # force headlines mode
  python bot/update.py --fixtures DIR   # read <feed id>.xml files from DIR instead of the web (testing)
  python bot/update.py --outlets-only   # just rewrite site/data/outlets.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import unicodedata
from pathlib import Path
from zoneinfo import ZoneInfo

import feedparser
import requests

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "site" / "data"
EDITIONS = DATA / "editions"
FEEDS_FILE = Path(__file__).with_name("feeds.json")

TZ = ZoneInfo("Europe/Madrid")
MAX_AGE_HOURS = 36
PER_FEED_LIMIT = 40
UA = "Mozilla/5.0 (compatible; HemicycleBrief/1.0; personal news digest)"
DEFAULT_MODEL = "claude-sonnet-5-5"

# ---------------------------------------------------------------- relevance

EU_TERMS = [
    # English
    r"\beu\b", r"european union", r"\bbrussels\b", r"european commission", r"european parliament",
    r"european council", r"\bmeps?\b", r"eurozone", r"\becb\b", r"schengen", r"frontex",
    r"von der leyen", r"kallas", r"lagarde", r"single market",
    r"member states?", r"strasbourg", r"mercosur", r"\beuro\b",
    # French
    r"\bue\b", r"union europ[ée]enne", r"bruxelles", r"commission europ[ée]enne", r"parlement europ[ée]en",
    r"zone euro",
    # German
    r"\beu-", r"europ[äa]ische union", r"br[üu]ssel", r"eu-kommission", r"europaparlament",
    # Spanish
    r"uni[óo]n europea", r"bruselas", r"comisi[óo]n europea", r"parlamento europeo",
]

COUNTRIES = [
    # EU members, candidates and neighbours, in English / French / German / Spanish where they differ
    "austria", "autriche", "österreich", "belgium", "belgique", "belgien", "bélgica", "bulgaria", "bulgarie",
    "bulgarien", "croatia", "croatie", "kroatien", "croacia", "cyprus", "chypre", "zypern", "chipre",
    "czech", "tchèque", "tschechien", "chequia", "denmark", "danemark", "dänemark", "dinamarca",
    "estonia", "estonie", "estland", "finland", "finlande", "finnland", "finlandia", "france", "frankreich",
    "francia", "germany", "allemagne", "deutschland", "alemania", "greece", "grèce", "griechenland",
    "grecia", "hungary", "hongrie", "ungarn", "hungría", "ireland", "irlande", "irland", "irlanda",
    "italy", "italie", "italien", "italia", "latvia", "lettonie", "lettland", "letonia", "lithuania",
    "lituanie", "litauen", "lituania", "luxembourg", "luxemburg", "luxemburgo", "malta", "malte",
    "netherlands", "dutch", "pays-bas", "niederlande", "países bajos", "poland", "pologne", "polen",
    "polonia", "portugal", "romania", "roumanie", "rumänien", "rumanía", "slovakia", "slovaquie",
    "slowakei", "eslovaquia", "slovenia", "slovénie", "slowenien", "eslovenia", "spain", "espagne",
    "spanien", "españa", "sweden", "suède", "schweden", "suecia", "ukraine", "ucrania", "moldova",
    "moldavie", "serbia", "serbie", "serbien", "albania", "albanie", "albanien", "montenegro",
    "macedonia", "bosnia", "bosnie", "bosnien", "kosovo", "georgia", "géorgie", "georgien",
    "turkey", "türkiye", "turquie", "türkei", "turquía", "orbán", "orban", "macron", "merz", "meloni",
    "sánchez", "sanchez", "tusk", "zelensky", "le pen", "bardella",
]

EU_RE = re.compile("|".join(EU_TERMS), re.IGNORECASE)
COUNTRY_RE = re.compile(r"\b(" + "|".join(re.escape(c) for c in COUNTRIES) + r")\b", re.IGNORECASE)


def is_relevant(item: dict, scope: str) -> bool:
    if scope in ("eu", "europe"):
        return True
    text = f"{item['title']} {item['summary']}"
    if EU_RE.search(text):
        return True
    if scope == "world":
        return bool(COUNTRY_RE.search(item["title"]))
    return False


# ---------------------------------------------------------------- fetching

TAG_RE = re.compile(r"<[^>]+>")
SPACE_RE = re.compile(r"\s+")


def clean(text: str | None, limit: int | None = None) -> str:
    if not text:
        return ""
    text = html.unescape(TAG_RE.sub(" ", text))
    text = SPACE_RE.sub(" ", text).strip()
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "…"
    return text


def entry_time(entry) -> dt.datetime | None:
    for key in ("published_parsed", "updated_parsed", "created_parsed"):
        t = entry.get(key)
        if t:
            try:
                return dt.datetime(*t[:6], tzinfo=dt.timezone.utc)
            except (TypeError, ValueError):
                pass
    return None


def fetch(feed: dict, fixtures: Path | None) -> tuple[list[dict], str | None]:
    """Return (items, error)."""
    try:
        if fixtures:
            path = fixtures / f"{feed['id']}.xml"
            if not path.exists():
                return [], "no fixture"
            parsed = feedparser.parse(path.read_bytes())
        else:
            resp = requests.get(feed["url"], headers={"User-Agent": UA}, timeout=25)
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
    except Exception as exc:  # network errors, HTTP errors
        return [], str(exc)[:200]

    if not parsed.entries:
        return [], "feed had no entries"

    now = dt.datetime.now(dt.timezone.utc)
    items = []
    for entry in parsed.entries[:PER_FEED_LIMIT]:
        title = clean(entry.get("title"))
        link = entry.get("link") or ""
        if not title or not link.startswith("http"):
            continue
        when = entry_time(entry)
        if when and (now - when).total_seconds() > MAX_AGE_HOURS * 3600:
            continue
        items.append({
            "title": title,
            "url": link.replace("http://", "https://", 1),
            "summary": clean(entry.get("summary") or entry.get("description"), 280),
            "published": when.isoformat() if when else None,
            "outlet": feed["name"],
            "lean": feed["lean"],
            "side": feed["side"],
        })
    return items, None


# ---------------------------------------------------------------- grouping

STOPWORDS = set("""
a an the and or but of in on at to for from by with as is are was were be been being it its this that these those
after before over under into about against between amid among says said say new more most than then also not no
will would could should may might can just how why what who when where which while up down out off his her their
our your they them he she we you i us all any some one two three first last year years week day days time back
le la les un une des du de et ou en au aux pour par sur dans avec sans est sont été pas plus ce cette ces qui que
quoi dont son sa ses leur leurs il elle ils elles nous vous après avant contre entre selon face fait faire
der die das den dem des ein eine einer eines und oder in im am an auf aus bei mit nach von vor zu zum zur für ist
sind war nicht mehr als auch wie was wer wo nach gegen über unter durch sich sein seine ihre
el la los las un una unos unas y o en de del al con sin por para sobre tras ante es son fue no más que como
se su sus lo le les entre contra según hasta desde
live update updates latest news video watch opinion analysis explained exclusive
""".split())

WORD_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")

# Same name in other languages -> one token, so French, German and Spanish headlines
# can be grouped with English ones about the same event (accents already removed).
_ALIAS_GROUPS = {
    "eu": "ue",
    "brussels": "bruxelles brussel bruselas",
    "commission": "kommission comision",
    "parliament": "parlement parlament parlamento europaparlament",
    "ukraine": "ucrania",
    "russia": "russie russland rusia",
    "serbia": "serbie serbien",
    "hungary": "hongrie ungarn hungria",
    "poland": "pologne polen polonia",
    "germany": "allemagne deutschland alemania",
    "france": "frankreich francia",
    "spain": "espagne spanien espana",
    "italy": "italie italien italia",
    "greece": "grece griechenland grecia",
    "romania": "roumanie rumanien rumania",
    "brazil": "bresil brasilien brasil",
    "migrant": "migrants migranten migrantes",
    "election": "elections elecciones wahl wahlen",
    "sanction": "sanktionen sanciones",
}
# Words in nearly every EU headline: too common to show two headlines are about the same event.
GENERIC = {"eu", "european", "europe", "brussels", "commission", "union", "parliament", "bloc", "minister", "government"}
ALIASES = {alt: main for main, alts in _ALIAS_GROUPS.items() for alt in alts.split()}


def tokens(title: str) -> set[str]:
    text = unicodedata.normalize("NFKD", title.lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    out = set()
    for w in WORD_RE.findall(text):
        w = ALIASES.get(w, w)
        if len(w) < 3 or w.isdigit() or w in STOPWORDS or w in GENERIC:
            continue
        if len(w) > 4 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(ALIASES.get(w, w))
    return out


def cluster(items: list[dict]) -> list[list[dict]]:
    toks = [tokens(i["title"]) for i in items]
    parent = list(range(len(items)))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            A, B = toks[a], toks[b]
            if not A or not B:
                continue
            shared = A & B
            if len(shared) >= 2 and len(shared) / min(len(A), len(B)) >= 0.34:
                parent[find(a)] = find(b)

    groups: dict[int, list[dict]] = {}
    for idx, item in enumerate(items):
        groups.setdefault(find(idx), []).append(item)
    return list(groups.values())


def group_score(group: list[dict]) -> float:
    outlets = {i["outlet"] for i in group}
    sides = {i["side"] for i in group}
    score = len(outlets)
    if "left" in sides and "right" in sides:
        score += 3
    if "centre" in sides:
        score += 1
    return score


def latest_first(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda i: i["published"] or "", reverse=True)


def outlet_entry(item: dict, note: str | None = None) -> dict:
    out = {"name": item["outlet"], "lean": item["lean"], "url": item["url"], "headline": item["title"]}
    if note:
        out["note"] = note
    return out


def one_per_outlet(items: list[dict], limit: int) -> list[dict]:
    seen, out = set(), []
    for item in latest_first(items):
        if item["outlet"] in seen:
            continue
        seen.add(item["outlet"])
        out.append(item)
        if len(out) == limit:
            break
    return out


def headlines_edition(items: list[dict]) -> dict:
    groups = sorted(cluster(items), key=group_score, reverse=True)
    stories, left_only, right_only = [], [], []
    for g in groups:
        sides = {i["side"] for i in g}
        if "left" in sides and "right" in sides:
            if len(stories) >= 6:
                continue
            centre = [i for i in g if i["side"] == "centre"]
            lead = latest_first(centre or g)[0]
            stories.append({
                "topic": f"Covered by {len({i['outlet'] for i in g})} outlets",
                "title": lead["title"],
                "left": {"outlets": [outlet_entry(i) for i in one_per_outlet([i for i in g if i["side"] == "left"], 4)]},
                "right": {"outlets": [outlet_entry(i) for i in one_per_outlet([i for i in g if i["side"] == "right"], 4)]},
                "sources": [{"name": i["outlet"], "url": i["url"]} for i in one_per_outlet(centre, 3)],
            })
        elif "left" in sides:
            left_only.append(latest_first([i for i in g if i["side"] == "left"])[0])
        elif "right" in sides:
            right_only.append(latest_first([i for i in g if i["side"] == "right"])[0])

    def brief(item):
        return {"title": item["title"], "outlet": item["outlet"], "lean": item["lean"], "url": item["url"]}

    return {
        "mode": "headlines",
        "topline": (f"{len(stories)} stories are being covered on both sides today." if stories
                    else "No single story is being covered on both sides yet today."),
        "stories": stories,
        "oneSided": {
            "left": [brief(i) for i in latest_first(left_only)[:8]],
            "right": [brief(i) for i in latest_first(right_only)[:8]],
        },
    }


# ---------------------------------------------------------------- written mode

SYSTEM_PROMPT = """You edit a daily EU news brief that shows how left-leaning and right-leaning outlets cover the same stories.
You will receive a numbered list of recent headlines (with short feed descriptions) from outlets labelled left, right or centre.
Rules:
- Use only facts supported by the items given. Do not add facts, numbers or quotes from memory.
- Write everything in your own words. No quotes longer than 12 words, at most one per story.
- Be even-handed. Describe how each side frames a story (what it leads with, stresses or leaves out); never say which side is right.
- If one side has no item about a story, say so plainly in that side's angle.
- Reply with JSON only, no commentary, no code fences."""

USER_TEMPLATE = """Today's date: {date}

Items (id | side | outlet | headline | description):
{items}

Pick the 3 to 5 most important EU-related stories, preferring ones that both left- and right-leaning outlets covered. Group items about the same event even across languages. Then pick up to 6 notable stories that only the left covered and up to 6 that only the right covered.

Return exactly this JSON shape:
{{
  "topline": "One sentence naming today's main stories.",
  "stories": [
    {{
      "topic": "Area · subject, e.g. Migration · Frontex",
      "title": "Neutral headline in your own words",
      "summary": "3 to 4 neutral sentences on what happened.",
      "why": "1 to 2 sentences on why it matters for the EU.",
      "left":  {{ "angle": "2 sentences on how left-leaning coverage frames it.", "items": [{{"id": 12, "note": "one short line on that piece's angle"}}] }},
      "right": {{ "angle": "...", "items": [{{"id": 40, "note": "..."}}] }},
      "differ": "One or two short sentences contrasting the framings.",
      "source_ids": [3, 7]
    }}
  ],
  "only_left": [5, 9],
  "only_right": [21]
}}
Use only ids from the list. source_ids are centre items."""


def written_edition(items: list[dict], date: str) -> dict | None:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        print("anthropic package not installed; using headlines mode", file=sys.stderr)
        return None

    pool = latest_first(items)[:180]
    lines = []
    for n, i in enumerate(pool):
        lines.append(f"{n} | {i['side']} | {i['outlet']} | {i['title']} | {clean(i['summary'], 200)}")

    model = os.environ.get("CLAUDE_MODEL") or DEFAULT_MODEL
    try:
        client = anthropic.Anthropic(api_key=key)
        msg = client.messages.create(
            model=model,
            max_tokens=8000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": USER_TEMPLATE.format(date=date, items="\n".join(lines))}],
        )
        text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text")
        start, end = text.find("{"), text.rfind("}")
        data = json.loads(text[start:end + 1])
    except Exception as exc:
        print(f"Written mode failed ({exc}); using headlines mode", file=sys.stderr)
        return None

    def pick(i):
        try:
            return pool[int(i)]
        except (ValueError, TypeError, IndexError):
            return None

    stories = []
    for s in data.get("stories", [])[:5]:
        story = {k: str(s.get(k, "")).strip() for k in ("topic", "title", "summary", "why", "differ")}
        for side in ("left", "right"):
            block = s.get(side) or {}
            outlets = []
            for ref in block.get("items", [])[:4]:
                item = pick(ref.get("id") if isinstance(ref, dict) else ref)
                if item and item["side"] == side:
                    outlets.append(outlet_entry(item, str(ref.get("note", "")).strip() if isinstance(ref, dict) else None))
            story[side] = {"angle": str(block.get("angle", "")).strip(), "outlets": outlets}
        story["sources"] = [{"name": it["outlet"], "url": it["url"]}
                            for it in (pick(x) for x in s.get("source_ids", [])[:3]) if it]
        if story["title"]:
            stories.append(story)
    if not stories:
        return None

    def brief_list(ids, side):
        out = []
        for x in ids[:6]:
            item = pick(x)
            if item and item["side"] == side:
                out.append({"title": item["title"], "outlet": item["outlet"], "lean": item["lean"], "url": item["url"]})
        return out

    return {
        "mode": "written",
        "model": model,
        "topline": str(data.get("topline", "")).strip(),
        "stories": stories,
        "oneSided": {"left": brief_list(data.get("only_left", []), "left"),
                     "right": brief_list(data.get("only_right", []), "right")},
    }


# ---------------------------------------------------------------- output

def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_outlets(feeds: list[dict]) -> None:
    shelf: dict[str, list[dict]] = {"left": [], "centre": [], "right": []}
    seen = set()
    for f in feeds:
        if f["name"] in seen:
            continue
        seen.add(f["name"])
        shelf.setdefault(f["side"], []).append({"name": f["name"], "lean": f["lean"], "country": f.get("country", "")})
    write_json(DATA / "outlets.json", shelf)


def update_index(date: str) -> None:
    path = DATA / "index.json"
    try:
        dates = json.loads(path.read_text(encoding="utf-8")).get("editions", [])
    except (FileNotFoundError, json.JSONDecodeError):
        dates = []
    dates = sorted(set(dates) | {date}, reverse=True)[:400]
    write_json(path, {"editions": dates})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-ai", action="store_true", help="force headlines mode")
    ap.add_argument("--fixtures", type=Path, help="read <feed id>.xml files from this folder")
    ap.add_argument("--outlets-only", action="store_true")
    args = ap.parse_args()

    feeds = json.loads(FEEDS_FILE.read_text(encoding="utf-8"))["feeds"]
    write_outlets(feeds)
    if args.outlets_only:
        return 0

    now = dt.datetime.now(TZ)
    date = now.strftime("%Y-%m-%d")

    items, failed, seen_urls = [], [], set()
    for feed in feeds:
        got, err = fetch(feed, args.fixtures)
        if err:
            failed.append(feed["name"])
            print(f"  ✗ {feed['id']}: {err}", file=sys.stderr)
            continue
        kept = 0
        for item in got:
            if item["url"] in seen_urls or not is_relevant(item, feed.get("scope", "general")):
                continue
            seen_urls.add(item["url"])
            items.append(item)
            kept += 1
        print(f"  ✓ {feed['id']}: {kept} EU items")

    if not items:
        print("No items fetched from any feed; leaving the site unchanged.", file=sys.stderr)
        return 1

    edition = None if args.no_ai else written_edition(items, date)
    if edition is None:
        edition = headlines_edition(items)

    edition = {
        "date": date,
        "generatedAt": now.astimezone(dt.timezone.utc).isoformat(timespec="seconds"),
        **edition,
        "feeds": {"ok": len(feeds) - len(failed), "total": len(feeds), "failed": sorted(set(failed))},
        "itemCount": len(items),
    }
    write_json(EDITIONS / f"{date}.json", edition)
    write_json(DATA / "latest.json", edition)
    update_index(date)
    print(f"Wrote {date} edition ({edition['mode']} mode, {len(edition['stories'])} stories, {len(items)} items).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
