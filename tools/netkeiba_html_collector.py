from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse


RACE_ID_RE = re.compile(r"(?:race_id=|/race/)?(\d{12})")
DATE_RE = re.compile(r"^\d{4}-?\d{2}-?\d{2}$")
COLLECTOR_VERSION = "Collector version 3"
DEBUG_LINK_LIMIT = 12


@dataclass(frozen=True)
class PageSpec:
    kind: str
    label: str
    url_template: str


@dataclass(frozen=True)
class RaceTarget:
    race_id: str
    source_url: str = ""
    source_text: str = ""
    venue: str = ""
    race_number: str = ""


JRA_PAGE_SPECS: dict[str, PageSpec] = {
    "newspaper": PageSpec(
        "newspaper",
        "newspaper",
        "https://race.netkeiba.com/race/newspaper.html?race_id={race_id}&rf=shutuba_submenu",
    ),
    "oikiri": PageSpec(
        "oikiri",
        "training",
        "https://race.netkeiba.com/race/oikiri.html?race_id={race_id}&rf=race_submenu",
    ),
    "speed": PageSpec(
        "speed",
        "speed",
        "https://race.netkeiba.com/race/speed.html?race_id={race_id}",
    ),
    "style": PageSpec(
        "style",
        "courseanalysis",
        "https://race.netkeiba.com/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=1",
    ),
    "result": PageSpec(
        "result",
        "result",
        "https://race.netkeiba.com/race/result.html?race_id={race_id}",
    ),
}


NAR_PAGE_SPECS: dict[str, PageSpec] = {
    "newspaper": PageSpec(
        "newspaper",
        "newspaper",
        "https://nar.netkeiba.com/race/newspaper.html?race_id={race_id}",
    ),
    "oikiri": PageSpec(
        "oikiri",
        "training",
        "https://nar.netkeiba.com/race/oikiri.html?race_id={race_id}",
    ),
    "speed": PageSpec(
        "speed",
        "speed",
        "https://nar.netkeiba.com/race/speed.html?race_id={race_id}",
    ),
    "style": PageSpec(
        "style",
        "courseanalysis",
        "https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=1",
    ),
    "jockey": PageSpec(
        "jockey",
        "jockey-courseanalysis",
        "https://nar.netkeiba.com/race/data_list.html?race_id={race_id}&mode=courseanalysis&cid=2",
    ),
    "result": PageSpec(
        "result",
        "result",
        "https://nar.netkeiba.com/race/result.html?race_id={race_id}",
    ),
    "shutuba": PageSpec(
        "shutuba",
        "shutuba",
        "https://nar.netkeiba.com/race/shutuba.html?race_id={race_id}",
    ),
}


PAGE_SPECS = {
    "jra": JRA_PAGE_SPECS,
    "nar": NAR_PAGE_SPECS,
}


DEFAULT_KINDS = {
    "jra": ("newspaper", "oikiri", "speed", "style", "result"),
    "nar": ("newspaper", "speed", "style", "result"),
}


KIND_ALIASES = {
    "courseanalysis": "style",
    "course": "style",
    "style": "style",
    "\u811a\u8cea": "style",
    "\u811a\u8cea\u5206\u6790": "style",
    "\u811a\u8cea\u52dd\u7387": "style",
    "jockey": "jockey",
    "jockey-courseanalysis": "jockey",
    "\u9a0e\u624b": "jockey",
    "\u9a0e\u624b\u30b3\u30fc\u30b9\u5206\u6790": "jockey",
    "newspaper": "newspaper",
    "\u65b0\u805e": "newspaper",
    "\u7af6\u99ac\u65b0\u805e": "newspaper",
    "training": "oikiri",
    "oikiri": "oikiri",
    "\u8abf\u6559": "oikiri",
    "speed": "speed",
    "\u30bf\u30a4\u30e0\u6307\u6570": "speed",
    "result": "result",
    "\u7d50\u679c": "result",
    "\u30ec\u30fc\u30b9\u7d50\u679c": "result",
    "shutuba": "shutuba",
    "entry": "shutuba",
    "\u51fa\u99ac\u8868": "shutuba",
}


def main(argv: list[str] | None = None) -> int:
    print(COLLECTOR_VERSION)
    print(f"Collector file: {Path(__file__).resolve()}")
    args = parse_args(argv)
    race_targets = load_race_targets_from_args(args)
    list_urls = list_urls_from_dates(args.mode, args.date) + list(args.list_url or [])

    if not race_targets and not list_urls:
        print("No target was provided. Use --date, --race-id, --race-ids-file, or --list-url.", file=sys.stderr)
        return 2

    try:
        sync_playwright, timeout_error = import_playwright()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    specs = selected_specs(args.mode, args.kinds)
    output_dir = Path(args.out).expanduser().resolve()
    profile_dir = Path(args.profile_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    profile_dir.mkdir(parents=True, exist_ok=True)

    print("Keiba AI Mobile netkeiba HTML collector")
    print(f"mode: {args.mode}")
    print(f"kinds: {', '.join(spec.kind for spec in specs)}")
    print(f"output: {output_dir}")
    print(f"profile: {profile_dir}")
    print("If a login page appears, log in in the opened browser and press Enter in this terminal.")
    print("Please keep delay settings modest so the collection behaves like normal browsing.")
    args.login_pause_used = False

    rows: list[dict[str, str]] = []
    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            str(profile_dir),
            headless=args.headless,
            viewport={"width": args.viewport_width, "height": args.viewport_height},
            locale="ja-JP",
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.set_default_timeout(args.timeout_ms)

        try:
            if list_urls:
                race_targets.extend(collect_race_targets_from_list_urls(page, list_urls, args, timeout_error))
                race_targets = unique_race_targets(race_targets)

            if not race_targets:
                print("Could not find any race links.", file=sys.stderr)
                return 2

            total = len(race_targets) * len(specs)
            print(f"target: {len(race_targets)} races x {len(specs)} kinds = {total} pages")

            done = 0
            for target in race_targets:
                for spec in specs:
                    done += 1
                    row = collect_one_page(page, target, spec, args, timeout_error, done, total, output_dir)
                    rows.append(row)
        finally:
            context.close()

    manifest = write_manifest(output_dir, rows)
    print(f"manifest: {manifest}")
    print("done")
    return 0 if all(row["status"] in {"saved", "skipped"} for row in rows) else 1


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Save netkeiba verification HTML by following race-list links with a local logged-in browser profile.",
    )
    parser.add_argument("--mode", choices=("jra", "nar"), required=True, help="Use jra for central racing, nar for local racing.")
    parser.add_argument("--race-id", action="append", default=[], help="race_id or race URL. Can be repeated.")
    parser.add_argument("--race-ids-file", help="Text/CSV file containing race_id values or URLs.")
    parser.add_argument("--date", action="append", default=[], help="Race date. Example: 2026-07-26 or 20260726. Can be repeated.")
    parser.add_argument("--list-url", action="append", default=[], help="Race-list page URL. Race links on the page are followed in display order. Can be repeated.")
    parser.add_argument(
        "--kinds",
        default="default",
        help="default / all / comma-separated kinds. NAR example: newspaper,speed,style,jockey,result",
    )
    parser.add_argument("--out", default="collected_html", help="Output directory. Default: collected_html")
    parser.add_argument("--profile-dir", default=".collector_profile", help="Persistent browser profile directory for login state.")
    parser.add_argument("--headless", action="store_true", help="Run browser headless. Do not use for first login.")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing saved HTML files.")
    parser.add_argument("--delay-sec", type=float, default=2.5, help="Wait seconds after each saved page. Default: 2.5")
    parser.add_argument("--wait-after-load-sec", type=float, default=1.5, help="Wait seconds after page load before saving HTML.")
    parser.add_argument("--timeout-ms", type=int, default=45_000, help="Page-load timeout in milliseconds.")
    parser.add_argument("--viewport-width", type=int, default=1365)
    parser.add_argument("--viewport-height", type=int, default=900)
    parser.add_argument("--no-pause-on-login", action="store_true", help="Do not pause when a login-like page is detected.")
    return parser.parse_args(argv)


def import_playwright():
    try:
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is not installed.\n"
            "Run the following commands on your local PC:\n\n"
            "  pip install -r tools/requirements-collector.txt\n"
            "  python -m playwright install chromium\n"
        ) from exc
    return sync_playwright, PlaywrightTimeoutError


def load_race_targets_from_args(args: argparse.Namespace) -> list[RaceTarget]:
    values: list[str] = []
    values.extend(args.race_id or [])
    if args.race_ids_file:
        path = Path(args.race_ids_file)
        if not path.exists():
            raise SystemExit(f"race_ids_file was not found: {path}")
        values.append(path.read_text(encoding="utf-8-sig", errors="replace"))
    return [RaceTarget(race_id=race_id) for race_id in unique_race_ids(extract_race_ids("\n".join(values)))]


def list_urls_from_dates(mode: str, date_values: Iterable[str]) -> list[str]:
    urls: list[str] = []
    for value in date_values or []:
        kaisai_date = normalize_kaisai_date(value)
        if mode == "jra":
            urls.append(f"https://race.netkeiba.com/top/race_list.html?kaisai_date={kaisai_date}")
        else:
            urls.append(f"https://nar.netkeiba.com/top/race_list.html?kaisai_date={kaisai_date}")
    return urls


def normalize_kaisai_date(value: str) -> str:
    text = str(value or "").strip()
    if not DATE_RE.fullmatch(text):
        raise SystemExit(f"Unsupported date format: {value}. Use YYYY-MM-DD or YYYYMMDD.")
    return text.replace("-", "")


def collect_race_targets_from_list_urls(page, urls: Iterable[str], args: argparse.Namespace, timeout_error) -> list[RaceTarget]:
    targets: list[RaceTarget] = []
    for url in urls:
        print(f"open race list: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
            wait_network_idle(page, timeout_error)
            page.wait_for_timeout(int(args.wait_after_load_sec * 1000))
            content = page.content()
            if is_login_like(page.url, content) and should_pause_for_login(args):
                args.login_pause_used = True
                wait_for_manual_login(page, url, args, timeout_error)
            links = get_visible_race_link_items(page, args.mode)
            print_visible_link_debug(links)
            found = extract_race_targets_from_links(args.mode, links)
            print(f"  race links: {len(found)}")
            for target in found:
                print(f"    {format_race_target_for_log(target)}")
            targets.extend(found)
        except Exception as exc:
            print(f"  failed to read race list: {exc}", file=sys.stderr)
    return unique_race_targets(targets)


def get_visible_race_link_items(page, mode: str) -> list[dict[str, str]]:
    return page.eval_on_selector_all(
        'a[href*="race_id="]',
        """
        (anchors, mode) => {
            const hrefRe = /(?:[?&]|&amp;)race_id=(\\d{12})(?:[&#]|&amp;|$)/;
            const domainRe = mode === "jra"
                ? /^https?:\\/\\/race\\.netkeiba\\.com\\//i
                : /^https?:\\/\\/nar\\.netkeiba\\.com\\//i;
            const raceNoRe = /(?:^|[^0-9])([1-9]|1[0-2])\\s*R(?:$|[^0-9])/;
            const venueRe = /(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉|門別|盛岡|水沢|浦和|船橋|大井|川崎|金沢|笠松|名古屋|園田|姫路|高知|佐賀)\\s*(?:\\d+日目)?/;

            const cleanText = (value) => (value || "").replace(/\\s+/g, " ").trim();

            const hasVisibleRect = (element) => {
                const rects = Array.from(element.getClientRects ? element.getClientRects() : []);
                if (rects.some(rect => rect.width > 0 && rect.height > 0)) return true;
                return Array.from(element.children || []).some(child => hasVisibleRect(child));
            };

            const isVisible = (element) => {
                if (!element || !element.isConnected) return false;
                if (element.closest("script, template, style, noscript")) return false;

                let node = element;
                while (node && node.nodeType === Node.ELEMENT_NODE) {
                    if (node.hidden || node.getAttribute("aria-hidden") === "true") return false;
                    const style = window.getComputedStyle(node);
                    if (
                        style.display === "none" ||
                        style.visibility === "hidden" ||
                        style.visibility === "collapse" ||
                        Number(style.opacity) === 0
                    ) {
                        return false;
                    }
                    node = node.parentElement;
                }

                return hasVisibleRect(element);
            };

            const contextText = (anchor) => {
                const parts = [];
                let node = anchor;
                for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
                    const text = cleanText(node.innerText || node.textContent || "");
                    if (text) parts.push(text);
                }
                return parts;
            };

            const findRaceNumber = (texts) => {
                for (const text of texts) {
                    const match = text.match(raceNoRe);
                    if (match) return `${match[1]}R`;
                }
                return "";
            };

            const findVenueInAncestors = (texts) => {
                for (const text of texts) {
                    if (text.length > 500) continue;
                    const match = text.match(venueRe);
                    if (match) return match[1];
                }
                return "";
            };

            const findVenueBeforeAnchor = (anchor) => {
                const candidates = Array.from(document.querySelectorAll(
                    "h1, h2, h3, h4, h5, dt, th, .RaceList_Head, .RaceList_Title, .RaceList_DataTitle, .RaceList_CourseTitle, .RaceListHeader, .RaceListTop_MenuItem"
                ));
                let venue = "";
                for (const candidate of candidates) {
                    if (!isVisible(candidate)) continue;
                    const relation = candidate.compareDocumentPosition(anchor);
                    if (!(relation & Node.DOCUMENT_POSITION_FOLLOWING)) continue;
                    const match = cleanText(candidate.innerText || candidate.textContent || "").match(venueRe);
                    if (match) venue = match[1];
                }
                return venue;
            };

            return anchors.flatMap(anchor => {
                if (!isVisible(anchor)) return [];

                const href = anchor.href || anchor.getAttribute("href") || "";
                if (!domainRe.test(href)) return [];
                const hrefMatch = href.match(hrefRe);
                if (!hrefMatch) return [];
                const raceId = hrefMatch[1];

                const texts = contextText(anchor);
                const raceNumber = findRaceNumber(texts) || `${Number(raceId.slice(-2))}R`;

                const venue = findVenueInAncestors(texts) || findVenueBeforeAnchor(anchor);
                const anchorText = cleanText(anchor.innerText || anchor.textContent || "");
                const sourceText = cleanText(`${venue}${raceNumber} ${anchorText}`);

                return [{
                    href,
                    text: sourceText,
                    race_id: raceId,
                    venue,
                    race_number: raceNumber
                }];
            });
        }
        """,
        mode,
    )


def extract_race_targets_from_links(mode: str, links: Iterable[dict[str, str]]) -> list[RaceTarget]:
    targets: list[RaceTarget] = []
    seen: set[str] = set()
    for item in links:
        href = str(item.get("href") or "")
        if not is_race_link_for_mode(mode, href):
            continue
        race_ids = [str(item.get("race_id") or "").strip()] if item.get("race_id") else extract_race_ids(href)
        if not race_ids:
            continue
        race_id = race_ids[0]
        if not re.fullmatch(r"\d{12}", race_id):
            continue
        if race_id in seen:
            continue
        seen.add(race_id)
        venue = safe_title(str(item.get("venue") or ""))
        race_number = normalize_race_number(str(item.get("race_number") or ""))
        source_text = safe_title(str(item.get("text") or ""))
        if venue and race_number and not source_text.startswith(f"{venue}{race_number}"):
            source_text = f"{venue}{race_number} {source_text}".strip()
        targets.append(
            RaceTarget(
                race_id=race_id,
                source_url=href,
                source_text=source_text,
                venue=venue,
                race_number=race_number,
            )
        )
    return targets


def is_race_link_for_mode(mode: str, href: str) -> bool:
    text = (href or "").lower()
    if not re.search(r"race_id=\d{12}(?:[&#]|$)", text):
        return False
    if mode == "jra":
        return re.search(r"https?://race\.netkeiba\.com/", text) is not None
    return re.search(r"https?://nar\.netkeiba\.com/", text) is not None


def normalize_race_number(value: str) -> str:
    match = re.search(r"([1-9]|1[0-2])\s*R", value or "")
    return f"{match.group(1)}R" if match else ""


def format_race_target_for_log(target: RaceTarget) -> str:
    display = f"{target.venue}{target.race_number}".strip()
    if not display:
        display = target.source_text.strip()
    if display:
        return f"{display} {target.race_id}"
    return target.race_id


def print_visible_link_debug(links: Iterable[dict[str, str]]) -> None:
    items = list(links)
    print(f"  visible race_id href candidates: {len(items)}")
    for item in items[:DEBUG_LINK_LIMIT]:
        race_id = str(item.get("race_id") or "")
        race_number = str(item.get("race_number") or "")
        venue = str(item.get("venue") or "")
        href = str(item.get("href") or "")
        text = safe_title(str(item.get("text") or ""))
        label = f"{venue}{race_number}".strip()
        print(f"    candidate: {label or text or '-'} {race_id} {href}")


def collect_one_page(page, race_target: RaceTarget, spec: PageSpec, args: argparse.Namespace, timeout_error, done: int, total: int, output_dir: Path) -> dict[str, str]:
    race_id = race_target.race_id
    race_dir = output_dir / args.mode / race_id
    race_dir.mkdir(parents=True, exist_ok=True)
    target = race_dir / f"{race_id}_{spec.kind}.html"
    url = spec.url_template.format(race_id=race_id)
    base_row = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "mode": args.mode,
        "race_id": race_id,
        "kind": spec.kind,
        "label": spec.label,
        "url": url,
        "path": str(target),
        "title": "",
        "status": "",
        "message": "",
    }

    prefix = f"[{done}/{total}] {race_id} {spec.label}"
    if target.exists() and not args.overwrite:
        print(f"{prefix}: skip")
        return {**base_row, "status": "skipped", "message": "already exists"}

    print(f"{prefix}: open")
    content = ""
    try:
        print(f"{prefix}: url {url}")
        page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
        wait_network_idle(page, timeout_error)
        page.wait_for_timeout(int(args.wait_after_load_sec * 1000))
        content = page.content()

        if is_login_like(page.url, content) and should_pause_for_login(args):
            args.login_pause_used = True
            wait_for_manual_login(page, url, args, timeout_error)
            content = page.content()

        title = safe_title(page.title())
        message = validate_saved_html(race_id, content, page.url)
        target.write_text(content, encoding="utf-8")
        print(f"{prefix}: saved {target.name}" + (f" / {message}" if message else ""))
        page.wait_for_timeout(int(args.delay_sec * 1000))
        return {**base_row, "title": title, "status": "saved", "message": message}
    except Exception as exc:
        print(f"{prefix}: failed {exc}", file=sys.stderr)
        print_page_diagnostics(page, content, prefix)
        return {**base_row, "status": "failed", "message": str(exc)}


def wait_network_idle(page, timeout_error) -> None:
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except timeout_error:
        pass


def wait_for_manual_login(page, url: str, args: argparse.Namespace, timeout_error) -> None:
    print("A login-like page was detected.")
    print("Log in in the opened browser, return to this terminal, and press Enter.")
    input()
    page.goto(url, wait_until="domcontentloaded", timeout=args.timeout_ms)
    wait_network_idle(page, timeout_error)
    page.wait_for_timeout(int(args.wait_after_load_sec * 1000))


def should_pause_for_login(args: argparse.Namespace) -> bool:
    return not args.no_pause_on_login and not bool(getattr(args, "login_pause_used", False))


def validate_saved_html(race_id: str, content: str, current_url: str) -> str:
    messages: list[str] = []
    if len(content.strip()) < 500:
        raise RuntimeError("HTML is too short. It may be a login, error, or blank page.")
    if is_login_like(current_url, content):
        raise RuntimeError("A login page was returned.")
    if is_block_like(content):
        messages.append("possible auth/block page")
    if race_id not in current_url and race_id not in content:
        messages.append("race_id not found in URL/content")
    return " / ".join(messages)


def is_login_like(url: str, content: str) -> bool:
    parsed = urlparse(url or "")
    host = (parsed.netloc or "").lower()
    path = (parsed.path or "").lower()
    query = (parsed.query or "").lower()
    if "regist.netkeiba.com" in host and ("login" in path or "pid=login" in query):
        return True
    if "account.netkeiba.com" in host and "login" in path:
        return True
    if re.search(r"(^|/)login(?:[/.?]|$)", path):
        return True

    text = content[:200_000]
    lower_text = text.lower()
    has_password_input = re.search(r"<input[^>]+type=[\"']?password", lower_text) is not None
    has_login_form = (
        "login_form" in lower_text
        or re.search(r"<form[^>]+(?:id|name|action)=[\"'][^\"']*login", lower_text) is not None
    )
    has_login_submit = re.search(r"<button[^>]*>[^<]*(?:login|\u30ed\u30b0\u30a4\u30f3)", lower_text) is not None
    return bool(has_password_input or has_login_form or has_login_submit)


def is_block_like(content: str) -> bool:
    text = content[:200_000].lower()
    return any(key in text for key in ("captcha", "cloudflare"))


def print_page_diagnostics(page, content: str, prefix: str) -> None:
    try:
        current_url = page.url
    except Exception:
        current_url = ""
    try:
        title = safe_title(page.title())
    except Exception:
        title = ""
    preview = text_preview(content)
    print(f"{prefix}: diagnostic url: {current_url}", file=sys.stderr)
    print(f"{prefix}: diagnostic title: {title}", file=sys.stderr)
    print(f"{prefix}: diagnostic body_head: {preview}", file=sys.stderr)


def text_preview(content: str, limit: int = 300) -> str:
    text = re.sub(r"(?is)<(script|style|template)[^>]*>.*?</\1>", " ", content or "")
    text = re.sub(r"(?s)<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def selected_specs(mode: str, kinds_text: str) -> list[PageSpec]:
    specs = PAGE_SPECS[mode]
    text = (kinds_text or "default").strip()
    if text == "default":
        keys = DEFAULT_KINDS[mode]
    elif text == "all":
        keys = tuple(specs.keys())
    else:
        keys = tuple(normalize_kind(part) for part in re.split(r"[,\u3001\s]+", text) if part.strip())

    unknown = [key for key in keys if key not in specs]
    if unknown:
        valid = ", ".join(specs.keys())
        raise SystemExit(f"Unsupported kind: {', '.join(unknown)} / valid: {valid}")
    return [specs[key] for key in keys]


def normalize_kind(value: str) -> str:
    key = value.strip()
    return KIND_ALIASES.get(key, key)


def extract_race_ids(text: str) -> list[str]:
    return unique_race_ids(match.group(1) for match in RACE_ID_RE.finditer(text or ""))


def unique_race_ids(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        race_id = str(value or "").strip()
        if not re.fullmatch(r"\d{12}", race_id):
            continue
        if race_id not in seen:
            seen.add(race_id)
            result.append(race_id)
    return result


def unique_race_targets(values: Iterable[RaceTarget]) -> list[RaceTarget]:
    result: list[RaceTarget] = []
    seen: set[str] = set()
    for target in values:
        if target.race_id in seen:
            continue
        seen.add(target.race_id)
        result.append(target)
    return result


def write_manifest(output_dir: Path, rows: list[dict[str, str]]) -> Path:
    path = output_dir / f"manifest_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fieldnames = ["timestamp", "mode", "race_id", "kind", "label", "status", "path", "url", "title", "message"]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def safe_title(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


if __name__ == "__main__":
    raise SystemExit(main())
