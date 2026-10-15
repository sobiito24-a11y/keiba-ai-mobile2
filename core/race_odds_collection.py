"""Optional local-browser collection after explicit operator rights configuration.

No private API discovery. No login or access-limit bypass. A failure here never
prevents the ordinary newspaper/prediction pipeline from completing.
"""
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import json
import time
from . import race_odds as odds


def collect(page, race_id, mode, output_dir, config_path=None):
    root = Path(output_dir) / mode / race_id
    root.mkdir(parents=True, exist_ok=True)
    status = dict(race_id=race_id, mode=mode, received_at=datetime.now(odds.JST).isoformat(),
                  status='not_configured', pages=[])
    try:
        config = json.loads(Path(config_path).read_text(encoding='utf-8-sig')) if config_path else {}
        if not (config.get('enabled') is True and config.get('rights_confirmed') is True
                and config.get('authorization_reference')):
            return status
        pages = config.get('pages', {}).get(mode, [])
        if not pages:
            status['status'] = 'no_authorized_pages'
            return status
        if not isinstance(pages, list) or len(pages) > 4:
            raise ValueError('Maximum four explicitly configured public odds pages')
        for index, template in enumerate(pages):
            url = template.format(race_id=race_id)
            parsed = urlparse(url)
            host = 'race.netkeiba.com' if mode == 'jra' else 'nar.netkeiba.com'
            if (parsed.scheme != 'https' or parsed.hostname != host or parsed.username or parsed.password
                    or not parsed.path.startswith('/odds/') or parse_qs(parsed.query).get('race_id') != [race_id]):
                raise ValueError('Only explicitly authorized public odds pages are allowed')
            item = dict(url=url, status='communication_error')
            status['pages'].append(item)
            try:
                response = page.goto(url, wait_until='domcontentloaded', timeout=30_000)
                if response and response.status in (401, 403, 429):
                    item['status'] = 'access_restricted'
                    break
                if response and response.status >= 400:
                    continue
                actual_url = urlparse(page.url)
                if actual_url.hostname != host or parse_qs(actual_url.query).get('race_id') != [race_id]:
                    item['status'] = 'redirect_or_login'
                    break
                deadline = time.monotonic() + 15
                quote = None
                while True:
                    from bs4 import BeautifulSoup
                    from .independent_ai_html_odds import horse_inventory, norm
                    html = page.content()
                    soup = BeautifulSoup(html, 'html.parser')
                    title = soup.title.get_text() if soup.title else ''
                    if 'login' in page.url.lower() or 'ログイン' in title:
                        item['status'] = 'login_required'; break
                    if any(s in title for s in ('アクセス制限', 'アクセスが制限', 'Access Denied')):
                        item['status'] = 'access_restricted'; break
                    names = horse_inventory(soup)
                    for tr in soup.select('tr'):
                        n, name = tr.select_one('.Umaban, .Horse_Num, [id^="uno-1_"]'), tr.select_one('.Horse_Name')
                        if n and name and norm(n.get_text()).isdigit():
                            names[int(norm(n.get_text()))] = name.get_text(strip=True)
                    if names:
                        identity = dict(race_id=race_id, mode=mode, horses=[dict(horse_no=n, name=v) for n,v in sorted(names.items())])
                        # DOM HTML does not always carry a canonical URL. Add the
                        # actual visited public URL, then still validate its identity.
                        raw = (f'<meta charset="utf-8"><link rel="canonical" href="{url}">' + html).encode()
                        quote = odds.import_files([('rendered.html', raw)], identity)[0]
                        if quote['prices']: break
                    if time.monotonic() >= deadline: break
                    page.wait_for_timeout(1000)
                if quote is not None:
                    quote['received_at'] = datetime.now(odds.JST).isoformat()
                    quote['authorization_reference'] = config['authorization_reference']
                    quote['source'] = 'netkeiba_authorized_browser'
                    quote['acquisition_method'] = 'authorized_browser'
                    item['status'] = quote['collection_status']
                    item['price_count'] = len(quote['prices'])
                    # Immutable observations: repeated collection creates a new file.
                    stamp = datetime.now(odds.JST).strftime('%Y%m%dT%H%M%S%f')
                    stem = root / f'{race_id}_{stamp}_{index}_odds'
                    stem.with_suffix('.html').write_bytes(raw)
                    Path(str(stem)+'.odds.json').write_text(json.dumps(quote, ensure_ascii=False, indent=2), encoding='utf-8')
                elif item['status'] == 'communication_error':
                    item['status'] = 'unrecognized_dom'
                if item['status'] in ('access_restricted', 'login_required'): break
            except Exception:
                item['status'] = 'collection_error'
            page.wait_for_timeout(2500)
        status['status'] = 'completed_with_page_statuses'
    except Exception:
        status['status'] = 'configuration_or_collection_error'
    finally:
        stamp = datetime.now(odds.JST).strftime('%Y%m%dT%H%M%S%f')
        (root / f'{race_id}_{stamp}.odds_status.json').write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    return status


def attach_collected(event, input_dir):
    """Enrich only the odds sibling; prediction inputs and hashes stay intact."""
    from copy import deepcopy
    from .independent_ai_odds_io import restore_race
    out = deepcopy(event)
    files = list(Path(input_dir).rglob('*.odds.json'))
    for race in out['races']:
        try:
            result = restore_race(race)
            identity = odds.identity_from_result(result)
        except (ValueError, TypeError, KeyError):
            race.setdefault(odds.KEY, dict(schema_version=1, saved=[], history=[]))
            race[odds.KEY]['collection_audit'] = [dict(status='identity_unavailable')]
            continue
        state = odds.state_for(result)
        audit = []
        incoming = []
        for file in files:
            try:
                payload = json.loads(file.read_text(encoding='utf-8-sig'))
                if payload.get('race_id') != identity['race_id']: continue
                incoming.extend(odds.import_files([(file.name, file.read_bytes())], identity))
            except (ValueError, TypeError, KeyError, UnicodeError):
                audit.append(dict(file=file.name, status='rejected'))
        if incoming:
            state['saved'] = odds.merge([], incoming, identity)
        state['collection_audit'] = audit
        race[odds.KEY] = state
    return out
