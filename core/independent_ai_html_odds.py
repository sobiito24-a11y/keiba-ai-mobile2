"""Parse user-saved HTML only. No HTTP, JavaScript execution or provider endpoint discovery."""
import hashlib,re,unicodedata,json
from urllib.parse import urlparse,parse_qs
from datetime import datetime
from bs4 import BeautifulSoup,Comment
from .independent_ai import JST,number
from .independent_ai_odds import timestamp

def norm(s):return re.sub(r'\s+','',unicodedata.normalize('NFKC',str(s)))

def saved_odds(result):
    """Archive baseline only. Never use actual_odds or label unknown time as fresh."""
    from .prediction_table_ui import horse_key
    out={}
    for table in (result.overall_table,result.horse_evaluation):
        if table is None:continue
        for row in table.to_dict('records'):
            no=horse_key(row);v=number(row.get('odds_at_prediction'))
            if no and v is not None:out[no]=dict(win=v,source='saved_odds_at_prediction',observed_at=row.get('odds_observed_at'),latest=False)
    return out

def identity(soup):
    urls=[x.get('href','') for x in soup.select('link[rel="canonical"]')]+[x.get('content','') for x in soup.select('meta[property="og:url"]')]
    urls += re.findall(r'https?://[^\s<>]+', ' '.join(str(c) for c in soup.find_all(string=lambda x:isinstance(x,Comment)) if 'saved from url' in str(c)))
    found=[]
    for url in urls:
        u=urlparse(url.strip('"'));host=u.hostname or ''
        if host not in ('race.netkeiba.com','nar.netkeiba.com','race.sp.netkeiba.com','nar.sp.netkeiba.com'):continue
        rid=parse_qs(u.query).get('race_id',[''])[0]
        if re.fullmatch(r'\d{12}',rid):found.append((rid,'nar' if host.startswith('nar.') else 'jra',url))
    if not found or len({x[:2] for x in found})!=1:raise ValueError('HTMLの正本URLからレースIDを一意に確認できません')
    return found[0]

def horse_inventory(soup):
    """Read JSON literal only; never evaluate JavaScript or resolve remote APIs."""
    found={}
    for script in soup.find_all('script'):
        match=re.search(r"var\s+horse_list\s*=\s*JSON\.parse\('([^']*)'\)",script.get_text())
        if not match:continue
        try:values=json.loads(match[1])
        except (ValueError,TypeError):continue
        for h in values.values():
            no=h.get('Umaban');name=h.get('Bamei')
            if str(no).isdigit() and name:
                if int(no) in found and found[int(no)]!=name:raise ValueError('馬名定義が重複しています')
                found[int(no)]=name
    return found


def parse(raw,prediction,captured_at=None,now=None):
    if len(raw)>12_000_000:raise ValueError('HTMLが大きすぎます')
    now=now or datetime.now(JST);soup=BeautifulSoup(raw,'html.parser');rid,mode,url=identity(soup)
    if rid!=prediction.get('race_id') or mode!=prediction.get('mode'):raise ValueError('表示中の予想とHTMLのレースID・JRA/NARが一致しません')
    expected={int(h['horse_no']):norm(h['name']) for h in prediction.get('horses',[])}
    prices=[];identities={};withdrawn=set();seen={}
    inventory=horse_inventory(soup)
    for no,name in inventory.items():
        if no not in expected or norm(name)!=expected[no]:raise ValueError(f'{no}番の馬名が保存予想と一致しません')
        identities[str(no)]=name
    def add(kind,ns,names,txt):
        if len(ns)!=len(names):raise ValueError('馬名との対応が不明です')
        for no,name in zip(ns,names):
            if no not in expected or norm(name)!=expected[no]:raise ValueError(f'{no}番の馬名が保存予想と一致しません')
            identities[str(no)]=name
        if re.search(r'取消|除外',txt):withdrawn.update(ns);return
        value=norm(txt).replace('倍','');m=re.fullmatch(r'(\d+(?:\.\d+)?)(?:[~〜～\-–](\d+(?:\.\d+)?))?',value)
        if not m:return
        lo=float(m[1]);hi=float(m[2] or m[1])
        if not 1<=lo<=hi:return
        key=(kind,tuple(sorted(ns)))
        if key in seen and seen[key]!=(lo,hi):raise ValueError('同じ券種・馬番に異なる価格が含まれます')
        if key not in seen:prices.append(dict(kind=kind,horses=list(sorted(ns)),low=lo,high=hi))
        seen[key]=(lo,hi)
    popularity={}
    def add_popularity(no, value):
        raw_pop=norm(value).removesuffix('人気')
        if raw_pop.isdigit() and 1<=int(raw_pop)<=len(expected) and str(no) in identities:
            if str(no) in popularity and popularity[str(no)]!=int(raw_pop):raise ValueError('人気順位が競合しています')
            popularity[str(no)]=int(raw_pop)
    # Verified newspaper DOM: odds-1_NN belongs to Horse02 in the same dl.
    for node in soup.select('[id^="odds-1_"]'):
        match=re.fullmatch(r'odds-1_(\d+)',node.get('id',''))
        block=node.find_parent('dl');name=block.select_one('.Horse02 a[href*="/horse/"]') if block else None
        if match and name:add('win',[int(match[1])],[name.get_text(' ',strip=True)],node.get_text(' ',strip=True))
    # Odds page rows: map the row horse number, not the popularity sequence in element ids.
    for tr in soup.select('tr'):
        name_node=tr.select_one('.Horse_Name')
        number_node=tr.select_one('.Umaban, .Horse_Num, [id^="uno-1_"]')
        if not name_node or not number_node:continue
        raw_no=norm(number_node.get_text())
        if not raw_no.isdigit():continue
        no=int(raw_no);name=name_node.get_text(' ',strip=True) or inventory.get(no)
        if not name:continue
        for prefix,kind in [('odds-1_', 'win'),('odds-2_', 'place')]:
            node=tr.select_one('[id^="'+prefix+'"]')
            if node:add(kind,[no],[name],node.get_text(' ',strip=True))
        pop=tr.select_one('.Popular, .Popularity, [id^="ninki-1_"]')
        if pop:add_popularity(no,pop.get_text(' ',strip=True))
    # Explicit tabular exports only; never infer column positions or execute JS.
    for table in soup.select('table'):
        header=table.find('tr');heads=[norm(x.get_text()) for x in header.find_all(['th','td'],recursive=False)] if header else []
        if not heads:continue
        for tr in table.find_all('tr')[1:]:
            cs=[x.get_text(' ',strip=True) for x in tr.find_all(['td','th'],recursive=False)]
            if len(cs)!=len(heads):continue
            row=dict(zip(heads,cs))
            if '馬番' in row and '馬名' in row and norm(row['馬番']).isdigit():
                no=int(norm(row['馬番']))
                for label,kind in [('単勝','win'),('単勝オッズ','win'),('複勝','place'),('複勝オッズ','place')]:
                    if label in row:add(kind,[no],[row['馬名']],row[label])
                for label in ('単勝人気','人気','人気順位'):
                    if label in row:add_popularity(no,row[label])
            elif all(k in row for k in ('馬番1','馬名1','馬番2','馬名2','ワイド')):
                if norm(row['馬番1']).isdigit() and norm(row['馬番2']).isdigit():
                    ns=[int(norm(row['馬番1'])),int(norm(row['馬番2']))]
                    if len(set(ns))==2:add('wide',ns,[row['馬名1'],row['馬名2']],row['ワイド'])
    title=soup.select_one('#odds_title');predicted=bool(title and '予想' in title.get_text())
    # Only an explicit price timestamp, not race date, file mtime or upload time.
    observed=None
    for node in soup.select('.OddsUpdateTime, #odds_update_time, time[data-odds-updated-at]'):
        value=node.get('datetime') or node.get('data-odds-updated-at') or node.get_text(' ',strip=True)
        t=timestamp(value)
        if t:observed=t.isoformat();break
        m=re.search(r'(20\d{2})[年/\-](\d{1,2})[月/\-](\d{1,2})日?\s+(\d{1,2}):(\d{2})(?::(\d{2}))?',value)
        if m:
            try:observed=datetime(*[int(x or 0) for x in m.groups()],tzinfo=JST).isoformat()
            except ValueError:pass
    prices=[p for p in prices if not withdrawn.intersection(p['horses'])]
    return dict(page_kind='odds' if '/odds' in url else 'newspaper',recognition_status='identified',
        collection_status='prices_found' if prices else 'prices_missing',
        race_id=rid,mode=mode,source='netkeiba_user_saved_html',source_url=url,
        authorization_reference='user-provided private-session file; not permission for public redistribution',
        received_at=now.isoformat(),observed_at=observed,user_reported_captured_at=captured_at,
        html_sha256=hashlib.sha256(raw).hexdigest(),popularity=popularity,identities=identities,withdrawn=sorted(withdrawn),prices=prices,
        price_status='predicted_odds' if predicted else 'timestamp_unknown' if not observed else 'saved_observation',
        parser_scope='verified newspaper win DOM; explicit named tables; other structures unsupported',
        warnings=['予想オッズは実売価格ではありません'] if predicted else ['HTML内の価格時刻が不明。アップロード時刻で補完しません'] if not observed else [],
        missing_kinds=[k for k in ('win','place','wide') if not any(p['kind']==k for p in prices)])
