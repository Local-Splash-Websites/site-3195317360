"""Render a Dudaport site: src/ templates + data/site.json -> public/.

This file is copied verbatim into every migrated site repository as build/render.py and runs in stage 1 of the site's
Dockerfile, so it depends on Jinja2 and the standard library only. The Dudaport worker imports the same module to
verify that every page renders before it opens a pull request.

    python build/render.py [--src src] [--data data/site.json] [--out public]
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

from jinja2 import ChainableUndefined, Environment, FileSystemLoader, select_autoescape
from markupsafe import Markup

DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
TEMPLATE_SUFFIXES = (".html", ".htm")


class RecordingUndefined(ChainableUndefined):
    """Renders as empty text (a variable removed in Deploy must not break the build) and remembers the name."""

    missing: set[str] = set()

    def __str__(self) -> str:
        if self._undefined_name:
            RecordingUndefined.missing.add(self._undefined_name)
        return ""


# ---------------------------------------------------------------- phone


def _nanp(value) -> str:
    d = re.sub(r"\D", "", str(value or ""))
    return d[1:] if len(d) == 11 and d.startswith("1") else ""


def phone_national(value) -> str:
    n = _nanp(value)
    return f"({n[:3]}) {n[3:6]}-{n[6:]}" if n else str(value or "")


def phone_dashed(value) -> str:
    n = _nanp(value)
    return f"{n[:3]}-{n[3:6]}-{n[6:]}" if n else str(value or "")


def phone_dotted(value) -> str:
    n = _nanp(value)
    return f"{n[:3]}.{n[3:6]}.{n[6:]}" if n else str(value or "")


def phone_spaced(value) -> str:
    n = _nanp(value)
    return f"{n[:3]} {n[3:6]} {n[6:]}" if n else str(value or "")


def phone_international(value) -> str:
    n = _nanp(value)
    return f"+1 {n[:3]}-{n[3:6]}-{n[6:]}" if n else str(value or "")


def phone_digits(value) -> str:
    n = _nanp(value)
    return n or re.sub(r"\D", "", str(value or ""))


def tel_uri(value) -> str:
    v = re.sub(r"[^\d+]", "", str(value or ""))
    return f"tel:{v}" if v else ""


# ---------------------------------------------------------------- hours

_TIME_TOKEN = re.compile(r"(\d{1,2})(?::(\d{2}))?(\s*[AaPp]\.?\s?[Mm]\.?)?")


def _time_style(sample: str) -> dict:
    tokens = list(_TIME_TOKEN.finditer(sample or ""))[:2]
    style = {"ampm": None, "space": True, "minutes": "always", "pad": False, "sep": " - ", "h24": False}
    if len(tokens) < 2:
        return style
    a, b = tokens
    style["sep"] = sample[a.end():b.start()] or "-"
    marker = a.group(3) or b.group(3)
    if marker:
        style["ampm"] = marker.replace(" ", "")
        style["space"] = marker[:1].isspace()
        minutes = [t.group(2) for t in tokens]
        style["minutes"] = "always" if all(minutes) else "nonzero"
    else:
        style["h24"] = True
        style["pad"] = a.group(1).startswith("0") or len(a.group(1)) == 2
    return style


def _fmt_time(hhmm: str, style: dict) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    if style["h24"]:
        return f"{h:02d}:{m:02d}" if style["pad"] else f"{h}:{m:02d}"
    marker = style["ampm"] or "am"
    pm = h >= 12 and h != 24
    h12 = h % 12 or 12
    word = "pm" if pm else "am"
    if marker.isupper() or marker[:1].isupper():
        word = word.upper()
    if "." in marker:
        word = f"{word[0]}.{word[1]}."
    mins = f":{m:02d}" if style["minutes"] == "always" or m else ""
    return f"{h12}{mins}{' ' if style['space'] else ''}{word}"


def hours_range(spec, days, sample: str = "9:00 am - 5:00 pm") -> str:
    """The opening hours of the first of `days`, written in the style of `sample` (the text Duda rendered)."""
    days = [days] if isinstance(days, str) else list(days or [])
    if not days:
        return ""
    closed_word = sample.strip() if sample and not _TIME_TOKEN.search(sample) else "Closed"
    for entry in spec or []:
        if isinstance(entry, dict) and days[0] in (entry.get("dayOfWeek") or []):
            if entry.get("opens") == "00:00" and entry.get("closes") in ("23:59", "24:00"):
                return "Open 24 hours"
            style = _time_style(sample)
            return f"{_fmt_time(entry['opens'], style)}{style['sep']}{_fmt_time(entry['closes'], style)}"
    return closed_word


# ---------------------------------------------------------------- address, links, JSON-LD


def address_line(address) -> str:
    a = address if isinstance(address, dict) else {}
    region_zip = " ".join(x for x in (a.get("addressRegion"), a.get("postalCode")) if x)
    return ", ".join(x for x in (a.get("streetAddress"), a.get("addressLocality"), region_zip) if x)


def same_as(urls, network: str) -> str:
    for u in urls or []:
        if network.lower() in str(u).lower():
            return str(u)
    return ""


def mailto(email) -> str:
    return f"mailto:{email}" if email else ""


def _absolute(url: str, base: str) -> str:
    if not url or url.startswith(("http://", "https://")):
        return url
    return base.rstrip("/") + "/" + url.lstrip("/") if base else url


def jsonld(business) -> Markup:
    """schema.org LocalBusiness block written straight from `business` (the names already match)."""
    b = dict(business or {}) if isinstance(business, dict) else {}
    base = b.get("url") or ""
    doc = {"@context": "https://schema.org", "@type": "LocalBusiness"}
    for k, v in b.items():
        if k == "address" and isinstance(v, dict):
            v = {"@type": "PostalAddress", **v}
        elif k == "geo" and isinstance(v, dict):
            v = {"@type": "GeoCoordinates", **v}
        elif k == "openingHoursSpecification" and isinstance(v, list):
            v = [{"@type": "OpeningHoursSpecification", **h} for h in v if isinstance(h, dict)]
        elif k == "logo":
            v = _absolute(str(v), base)
        doc[k] = v
    if "logo" in doc:
        doc.setdefault("image", doc["logo"])
    text = json.dumps(doc, ensure_ascii=False, indent=2)
    return Markup(text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026"))


FILTERS = {
    "phone_national": phone_national, "phone_dashed": phone_dashed, "phone_dotted": phone_dotted, "phone_spaced": phone_spaced,
    "phone_international": phone_international, "phone_digits": phone_digits, "tel_uri": tel_uri, "hours_range": hours_range,
    "address_line": address_line, "same_as": same_as, "mailto": mailto, "jsonld": jsonld,
}


# ---------------------------------------------------------------- rendering


def environment(src: Path) -> Environment:
    env = Environment(loader=FileSystemLoader(str(src)), autoescape=select_autoescape(["html", "htm"]), undefined=RecordingUndefined,
                      keep_trailing_newline=True, auto_reload=False)
    env.filters.update(FILTERS)
    return env


def load_data(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must hold a JSON object")
    return data


def render_tree(src: Path, data: dict, out: Path) -> dict:
    """Render every page under `src` into `out` and copy everything else. Returns {"pages": n, "files": n, "missing": [...]}."""
    RecordingUndefined.missing = set()
    env = environment(src)
    context = {k: v for k, v in data.items() if not k.startswith("$")}
    if out.exists():
        shutil.rmtree(out)
    pages = files = 0
    for path in sorted(src.rglob("*")):
        if path.is_dir():
            continue
        rel = path.relative_to(src)
        target = out / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.suffix.lower() in TEMPLATE_SUFFIXES:
            target.write_text(env.get_template(rel.as_posix()).render(**context), encoding="utf-8")
            pages += 1
        else:
            shutil.copy2(path, target)
            files += 1
    return {"pages": pages, "files": files, "missing": sorted(RecordingUndefined.missing)}


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--src", default="src")
    p.add_argument("--data", default="data/site.json")
    p.add_argument("--out", default="public")
    a = p.parse_args(argv)
    result = render_tree(Path(a.src), load_data(Path(a.data)), Path(a.out))
    print(f"rendered {result['pages']} pages, copied {result['files']} files")
    if result["missing"]:
        print("warning: variables used by the pages but missing from data/site.json: " + ", ".join(result["missing"]), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
