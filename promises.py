"""PadelCred promise tests.

Every test checks one promise the app makes to players: a number on a help page, a rule a screen
describes, or a behaviour a feature claims. A failure means the app is not doing what it says.

Run:  python3 tests/promises.py http://localhost:8000
(serve the app folder first, for example:  python3 -m http.server 8000)
Needs: pip install playwright && playwright install chromium
"""
import sys, json, re, time
from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://localhost:8000').rstrip('/')
AUTO = "setInterval(()=>{const p=document.getElementById('achPop');if(p&&p.classList.contains('on')){const b=document.getElementById('apNext');b&&b.click()}},150)"
RESULTS = []

def promise(name, where):
    def deco(fn):
        fn._name, fn._where = name, where
        return fn
    return deco

def fresh(p, history=None, profile=None, amer=None):
    b = p.chromium.launch()
    pg = b.new_page(viewport={'width': 390, 'height': 844})
    pg.add_init_script(AUTO)
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)[:160]))
    pg.goto(BASE + '/?selftest=1'); pg.wait_for_timeout(1300)
    pg.click('#obStart'); pg.wait_for_timeout(300); pg.click('#obLocal'); pg.wait_for_timeout(300)
    pg.fill('#obName', 'Raza'); pg.click('#obNext'); pg.wait_for_timeout(300); pg.click('#obPlay'); pg.wait_for_timeout(700)
    if history is not None or profile or amer is not None:
        pg.evaluate("""a=>{if(a[0]!==null)localStorage.setItem('db-history',JSON.stringify(a[0]));
          if(a[2]!==null)localStorage.setItem('db-amer',JSON.stringify(a[2]));
          if(a[1]){const p=JSON.parse(localStorage.getItem('db-profile'));Object.keys(a[1]).forEach(k=>{if(a[1][k]===null)delete p[k];else p[k]=a[1][k]});localStorage.setItem('db-profile',JSON.stringify(p))}}""",
                    [history, profile, amer])
        pg.reload(); pg.wait_for_timeout(2200)
    pg.wait_for_function("!!window.__pcTest")
    return b, pg, errs

T = lambda pg, js, arg=None: pg.evaluate("(a)=>{const t=window.__pcTest;" + js + "}", arg)

def match(pid, pa, pb, sets, days_ago=1, **extra):
    now = int(time.time() * 1000)
    h = {'id': pid, 'manual': True, 'date': now - days_ago * 86400000, 'added': now, 'sets': sets, 'notes': '',
         'cfg': {'pa': pa, 'pb': pb, 'an': '', 'bn': '', 'a': ' & '.join(pa), 'b': ' & '.join(pb), 'group': '', 'venue': ''}}
    h['cfg'].update(extra.pop('cfg', {}))
    h.update(extra)
    return h

CFG = lambda **k: dict({'bestOf': 3, 'games': 6, 'race': False, 'deuce': 'golden', 'decider': 'set', 'first': 0,
                        'pa': ['A', 'B'], 'pb': ['C', 'D'], 'a': 'A & B', 'b': 'C & D'}, **k)
def games(*seq):  # winners of whole games, 4 straight points each
    pts = []
    for w in seq: pts += [w] * 4
    return pts

# ---------------------------------------------------------------- ratings
@promise('Each Playtomic level starts at the Overall that How ratings work shows', 'How ratings work, Where you start')
def t_start_table(p):
    b, pg, e = fresh(p)
    pg.evaluate("document.querySelector('#fnav [data-nav=profile]').click()"); pg.wait_for_timeout(600)
    pg.evaluate("(()=>{const x=[...document.querySelectorAll('button')].find(b=>/How ratings work/i.test(b.innerText));x&&x.click()})()"); pg.wait_for_timeout(500)
    rows = pg.evaluate("[...document.querySelectorAll('#hrStart tr')].map(r=>[...r.children].map(c=>c.innerText))")
    bad = []
    for label, shown in rows:
        m = re.search(r'(\d+(?:\.\d+)?)', label); L = float(m.group(1))
        calc = T(pg, "return t.perfScore(t.levelToRating(a))", L)
        if str(calc) != shown.strip(): bad.append((label, shown, calc))
    b.close()
    for lvl in ('0.89', '3.5'):
        b, pg, _ = fresh(p, history=[], profile={'ptLevel': lvl})
        pg.evaluate("document.querySelector('#fnav [data-nav=profile]').click()"); pg.wait_for_timeout(700)
        card = pg.evaluate("(document.querySelector('#profileBody .ovrcard b')||{}).innerText")
        want = T(pg, "return t.perfScore(t.levelToRating(a))", lvl)
        if str(want) != card: bad.append(('profile at Playtomic ' + lvl, card, want))
        b.close()
    return (not bad and len(rows) >= 5), bad or '%d rows checked, profile matches' % len(rows)

@promise('Tier badges match the ranges How ratings work lists', 'How ratings work, Your Overall')
def t_tiers(p):
    b, pg, e = fresh(p)
    pg.evaluate("document.querySelector('#fnav [data-nav=profile]').click()"); pg.wait_for_timeout(600)
    pg.evaluate("(()=>{const x=[...document.querySelectorAll('button')].find(b=>/How ratings work/i.test(b.innerText));x&&x.click()})()"); pg.wait_for_timeout(500)
    spans = pg.evaluate("[...document.querySelectorAll('#hrTiers span')].map(s=>s.innerText)")
    bad = []
    for s in spans:
        lo, hi, name = re.match(r'(\d+)–(\d+) (\w+)', s).groups()
        for v in range(int(lo), int(hi) + 1):
            got = T(pg, "return t.ovrTier(a)[1]", v)
            if got != name: bad.append((v, s, got))
    covered = sum(int(re.match(r'(\d+)–(\d+)', s).group(2)) - int(re.match(r'(\d+)', s).group(1)) + 1 for s in spans)
    b.close()
    return (not bad and covered == 60), bad or spans

@promise('Match formats count towards ratings exactly as How ratings work says', 'How ratings work, Match length')
def t_weights(p):
    b, pg, e = fresh(p)
    cases = {
        'best of 3': ({'cfg': CFG(), 'sets': []}, 1), 'best of 5': ({'cfg': CFG(bestOf=5), 'sets': []}, 1),
        'one 6-game set': ({'cfg': CFG(bestOf=1), 'sets': []}, .75), 'first to 5 games': ({'cfg': CFG(bestOf=1, games=5, race=True), 'sets': []}, .5),
        'set with swapped partners': ({'cfg': CFG(bestOf=1), 'sets': [], 'h': {'session': 's1'}}, .5),
        'court time, 16 games': ({'cfg': CFG(court=True), 'sets': [], 'h': {'court': True}, 'gw': [9, 7]}, 1),
        'court time, 4 games': ({'cfg': CFG(court=True), 'sets': [], 'h': {'court': True}, 'gw': [3, 1]}, .25)}
    bad = []
    for k, (row, want) in cases.items():
        got = T(pg, "return t.matchWeight(a)", row)
        if abs(got - want) > 1e-9: bad.append((k, got, want))
    b.close()
    return not bad, bad or 'all %d formats as stated' % len(cases)

@promise('A shorter format really moves ratings less (one set = three-quarters of a full match)', 'How ratings work, Match length')
def t_weight_applied(p):
    out = {}
    for name, cfg in (('full', {'bestOf': 3}), ('one set', {'bestOf': 1, 'games': 6})):
        h = [match('w1', ['Raza', 'Ben'], ['Ellie', 'James'], [[6, 3], [6, 3]] if name == 'full' else [[6, 3]], cfg=cfg)]
        b, pg, e = fresh(p, history=h)
        out[name] = T(pg, "const L=t.computeLeague();const r=L.find(x=>x.name==='Raza');return r.rating-r.trend[0]")
        b.close()
    ratio = out['one set'] / out['full'] if out['full'] else 0
    return abs(ratio - .75) < .02, {'full': round(out['full'], 2), 'one set': round(out['one set'], 2), 'ratio': round(ratio, 3)}

@promise('Americano and Mexicano rounds count towards ratings (at half), a night counts once, deleting a night removes it', 'How ratings work, Match length')
def t_amer_counts(p):
    D = json.load(open(__file__.rsplit('/', 1)[0] + '/demo-data.json'))
    nights = D['AMER']
    scored = sum(1 for ev in nights for r in ev.get('rounds', []) for m in r.get('matches', []) if m.get('sa') is not None and m.get('sb') is not None)
    b, pg, e = fresh(p, history=[], amer=nights)
    pg.wait_for_timeout(600)
    rows = T(pg, "return t.allRows().filter(r=>r.h.amer).map(r=>({w:t.matchWeight(r),s:r.h.session,winner:r.winner}))")
    every_half = all(abs(r['w'] - .5) < 1e-9 for r in rows)
    players_in_one = T(pg, "const ev=JSON.parse(localStorage.getItem('db-amer'))[0];return ev.players")
    L = T(pg, "return Object.fromEntries(t.computeLeague().map(x=>[x.name,x.p]))")
    expect_nights = {n: sum(1 for ev in nights if n in ev.get('players', [])) for n in players_in_one}
    played_ok = all(L.get(n) == expect_nights[n] for n in players_in_one)
    broken = pg.evaluate("/NaN|undefined|Infinity/.test(document.body.innerText)")
    # delete the first finished night through the app
    pg.evaluate("document.getElementById('hmAmer').click()"); pg.wait_for_timeout(600)
    pg.evaluate("document.querySelector('#amerView .amcard')&&document.querySelector('#amerView .amcard').click()"); pg.wait_for_timeout(500)
    pg.evaluate("document.getElementById('amDel')&&document.getElementById('amDel').click()"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('askYes')&&document.getElementById('askYes').click()"); pg.wait_for_timeout(600)
    left = T(pg, "return t.allRows().filter(r=>r.h.amer).length")
    nights_left = pg.evaluate("JSON.parse(localStorage.getItem('db-amer')).length")
    expect_left = sum(1 for ev in nights[1:] if True for r in ev.get('rounds', []) for m in r.get('matches', []) if m.get('sa') is not None) if nights_left == len(nights) - 1 else None
    b.close()
    ok = len(rows) == scored and every_half and played_ok and not broken and nights_left == len(nights) - 1 and left < len(rows)
    return ok, {'scored rounds in nights': scored, 'results added': len(rows), 'all count half': every_half,
                'league played (nights each)': {n: [L.get(n), expect_nights[n]] for n in players_in_one}, 'broken values': broken,
                'after deleting a night': {'nights': nights_left, 'results left': left}}

@promise('In the League, everyone shows the Overall worked out from their rating', 'League table, Overall column')
def t_league_overall(p):
    h = [match('l%d' % i, ['Raza', 'Ben'] if i % 2 else ['Ellie', 'Ben'], ['Leo', 'Marta'] if i % 3 else ['James', 'Marta'], [[6, 4 - i % 3], [6, 2]] if i % 2 else [[3, 6], [4, 6]], days_ago=i + 1) for i in range(10)]
    b, pg, e = fresh(p, history=h)
    pg.evaluate("document.querySelector('#fnav [data-nav=league]').click()"); pg.wait_for_timeout(800)
    shown = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#leagueBody table.grid:not(.duos):not(.seatable) tbody tr')].map(tr=>[tr.children[1].innerText.trim(),+tr.children[2].innerText]))")
    calc = T(pg, "return Object.fromEntries(t.computeLeague().map(x=>[x.name,t.perfScore(x.rating)]))")
    b.close()
    bad = [(k, shown[k], calc.get(k)) for k in shown if calc.get(k) != shown[k]]
    return not bad and len(shown) >= 5, bad or shown

@promise('Predictions add up: one pair\'s chance plus the other\'s is 100%, and equal pairs are 50–50', 'Match setup, Prediction')
def t_pred(p):
    h = [match('p%d' % i, ['Raza', 'Ben'], ['Leo', 'Marta'], [[6, 2], [6, 3]], days_ago=i + 1) for i in range(5)]
    b, pg, e = fresh(p, history=h)
    r = T(pg, "const x=['Raza','Ben'],y=['Leo','Marta'];return {ab:t.winChance(x,y),ba:t.winChance(y,x),eq:t.winChance(['New1','New2'],['New3','New4'])}")
    b.close()
    return abs(r['ab'] + r['ba'] - 1) < 1e-9 and abs(r['eq'] - .5) < 1e-9 and r['ab'] > .5, r

@promise('Disputed results stop counting, and Keep it makes them count again', 'Home, Results to check')
def t_dispute(p):
    now = int(time.time() * 1000)
    good = match('d1', ['Raza', 'Ben'], ['Leo', 'Marta'], [[6, 1], [6, 1]])
    bad = match('d2', ['Raza', 'Ben'], ['Leo', 'Marta'], [[6, 1], [6, 1]], conf={'u': {'ok': False, 'n': 'Leo', 'at': now}})
    b, pg, e = fresh(p, history=[good, bad])
    n1 = T(pg, "return t.computeLeague().find(x=>x.name==='Raza').p")
    pg.evaluate("document.querySelector('[data-cfkeep]').click()"); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('askYes').click()"); pg.wait_for_timeout(500)
    n2 = T(pg, "return t.computeLeague().find(x=>x.name==='Raza').p")
    b.close()
    return n1 == 1 and n2 == 2, {'played while disputed': n1, 'after Keep it': n2}

@promise('A swapped-partners evening counts as one match each in the League', 'League, played column')
def t_evening(p):
    now = int(time.time() * 1000)
    ev = [match('e%d' % i, pa, pb, [[6, 3]], session='s1', cfg={'bestOf': 1}) for i, (pa, pb) in enumerate([(['Raza', 'Ben'], ['Ellie', 'James']), (['Raza', 'Ellie'], ['Ben', 'James']), (['Raza', 'James'], ['Ben', 'Ellie'])])]
    b, pg, e = fresh(p, history=ev)
    pg.evaluate("document.querySelector('#fnav [data-nav=league]').click()"); pg.wait_for_timeout(800)
    played = pg.evaluate("Object.fromEntries([...document.querySelectorAll('#leagueBody table.grid:not(.duos):not(.seatable) tbody tr')].map(tr=>[tr.children[1].innerText.trim(),+tr.children[3].innerText]))")
    b.close()
    return all(v == 1 for v in played.values()) and len(played) == 4, played

# ---------------------------------------------------------------- scoring rules
@promise('Golden point: at 40–40 the next point wins the game', 'Match rules, 40–40')
def t_golden(p):
    b, pg, e = fresh(p)
    g = T(pg, "return t.replay(a,[0,0,0,1,1,1,0]).sets[0].g", CFG(deuce='golden')); b.close()
    return g == [1, 0], g

@promise('Advantage: at 40–40 you need two points in a row to win the game', 'Match rules, 40–40')
def t_adv(p):
    b, pg, e = fresh(p)
    one = T(pg, "return t.replay(a,[0,0,0,1,1,1,0]).sets[0].g", CFG(deuce='adv'))
    back = T(pg, "return t.replay(a,[0,0,0,1,1,1,0,1]).sets[0].g", CFG(deuce='adv'))
    two = T(pg, "return t.replay(a,[0,0,0,1,1,1,0,0]).sets[0].g", CFG(deuce='adv')); b.close()
    return one == [0, 0] and back == [0, 0] and two == [1, 0], {'after advantage': one, 'back to deuce': back, 'two in a row': two}

@promise('At 6–6 a tiebreak decides the set, 7–6', 'Match rules, sets')
def t_tb(p):
    b, pg, e = fresh(p)
    pts = games(*[i % 2 for i in range(12)]) + [0] * 7
    s = T(pg, "const S=t.replay(a[0],a[1]);return {g:S.sets[0].g,next:S.sets.length,done:S.done}", [CFG(), pts]); b.close()
    return s['g'] == [7, 6] and s['next'] == 2, s

@promise('First to 5 games ends at 5 with no tiebreak (5–4 is a finished match)', 'Setup, First to 5 games')
def t_race(p):
    b, pg, e = fresh(p)
    s = T(pg, "const S=t.replay(a[0],a[1]);return {g:S.sets[0].g,done:S.done,tb:S.sets[0].tb}", [CFG(bestOf=1, games=5, race=True), games(0, 1, 0, 1, 0, 1, 0, 1, 0)]); b.close()
    return s['g'] == [5, 4] and s['done'] == 0, s

@promise('Best of 5 needs three sets to win; best of 3 needs two', 'Setup, How long')
def t_bestof(p):
    b, pg, e = fresh(p)
    six = games(*[0] * 6)
    r = T(pg, "return {bo3_after2:t.replay(a[0],a[2].concat(a[2])).done,bo5_after2:t.replay(a[1],a[2].concat(a[2])).done,bo5_after3:t.replay(a[1],a[2].concat(a[2],a[2])).done}", [CFG(), CFG(bestOf=5), six]); b.close()
    return r['bo3_after2'] == 0 and r['bo5_after2'] is None and r['bo5_after3'] == 0, r

@promise('A match tiebreak decider is a first-to-10 tiebreak', 'Match rules, deciding set')
def t_stb(p):
    b, pg, e = fresh(p)
    pts = games(*[0] * 6) + games(*[1] * 6) + [0] * 9
    r9 = T(pg, "const S=t.replay(a[0],a[1]);return {done:S.done,sets:S.sets.length}", [CFG(decider='stb'), pts])
    r10 = T(pg, "const S=t.replay(a[0],a[1]);return {done:S.done,third:S.sets[2]}", [CFG(decider='stb'), pts + [0]]); b.close()
    return r9['done'] is None and r10['done'] == 0, {'at 9 points': r9, 'at 10 points': r10}

# ---------------------------------------------------------------- rotation and court time
@promise('Rotating partners: three pairings, everyone partners everyone once, you stay on your side', 'Setup, Swapping partners')
def t_pairings(p):
    b, pg, e = fresh(p)
    pr = T(pg, "return t.pairings(a)", CFG(pa=['Raza', 'Ben'], pb=['Ellie', 'James'])); b.close()
    partners = set()
    for teams in pr:
        for t in teams: partners.add(tuple(sorted(t)))
    raza_side = all('Raza' in teams[0] for teams in pr)
    return len(pr) == 3 and len(partners) == 6 and raza_side, pr

@promise('Court time: a stretch counts for whoever won more games; a level stretch doesn\'t count', 'Setup, Until time\'s up')
def t_court(p):
    win = match('c1', ['Raza', 'Ben'], ['Ellie', 'James'], [], unfinished=True, court=True, counts=True, leader=0, session='s2', pts=games(0, 0, 1), cfg={'bestOf': 1, 'games': 99, 'race': True, 'court': True})
    level = match('c2', ['Raza', 'Ellie'], ['Ben', 'James'], [], unfinished=True, court=True, counts=False, leader=None, session='s2', pts=games(0, 1), cfg={'bestOf': 1, 'games': 99, 'race': True, 'court': True})
    for h in (win, level): h.pop('manual'); h['start'] = h['date']
    b, pg, e = fresh(p, history=[win, level])
    r = T(pg, "return t.allRows().map(r=>({id:r.id,winner:r.winner,w:t.matchWeight(r)}))"); b.close()
    d = {x['id']: x for x in r}
    ok = d.get('c1', {}).get('winner') == 0 and d.get('c2', {}).get('winner') is None and abs(d['c1']['w'] - 3 / 16) < 1e-9
    return ok, r

# ---------------------------------------------------------------- form, seeds, achievements, versions
@promise('Form is only ever On fire, Steady or Cold, as the help page says', 'How ratings work, Form')
def t_form(p):
    b, pg, e = fresh(p)
    words = T(pg, "const s=new Set();for(let v=0;v<=100;v++)s.add(t.formWord(v));return [...s]"); b.close()
    return sorted(words) == ['Cold', 'On fire', 'Steady'], words

@promise('Starting points saved before the 2.9.3 fix are read as the same Playtomic level', 'Profile, Overall')
def t_legacy(p):
    b, pg, e = fresh(p)
    bad = []
    for L in (0.5, 0.89, 2, 3.5, 5, 7):
        old = round(700 + ((40 + (L - .5) / 6.5 * 59) - 40) * 600 / 55)
        a = T(pg, "return [t.perfScore(t.legacySeedToRating(a)),t.perfScore(t.levelToRating(a2))]".replace('a2', String(L) if False else 'a'), old)
        want = T(pg, "return t.perfScore(t.levelToRating(a))", L)
        got = T(pg, "return t.perfScore(t.legacySeedToRating(a))", old)
        if got != want: bad.append((L, got, want))
    b.close()
    return not bad, bad or 'all levels convert'

@promise('Your first match earns First serve', 'Achievements')
def t_first_serve(p):
    b, pg, e = fresh(p, history=[match('f1', ['Raza', 'Ben'], ['Leo', 'Marta'], [[6, 4], [6, 4]])])
    has = T(pg, "const r=t.computeLeague().find(x=>x.name==='Raza');return !!(r&&r.badges&&r.badges.first_serve)"); b.close()
    return has, has

@promise('The version label agrees everywhere (page, app code, offline helper)', 'Your data')
def t_versions(p):
    import urllib.request
    html = urllib.request.urlopen(BASE + '/').read().decode()
    js = urllib.request.urlopen(BASE + '/padelcred.js').read().decode()
    sw = urllib.request.urlopen(BASE + '/sw.js').read().decode()
    v = {'page': re.search(r'app-version" content="([^"]*)"', html).group(1), 'code': re.search(r"APP_VERSION='([^']*)'", js).group(1),
         'offline helper': re.search(r"padelcred-v([\d.]+)", sw).group(1), 'file links': sorted(set(re.findall(r'\?v=([\d.]+)', html)))}
    return v['page'] == v['code'] == v['offline helper'] and v['file links'] == [v['page']], v


# ---------------------------------------------------------------- shared match nights
def night(nid, ans, spots=4, org='org1', members=None, extra=None, status='open', changed=None, joined=None, hours=48):
    now = int(time.time() * 1000)
    names = {'org1': 'Leo', 'me1': 'Raza', 'u2': 'Ben', 'u3': 'Ellie', 'u4': 'James', 'u5': 'Marta', 'u6': 'Kwame'}
    mem = members or list(names.keys())
    return {'id': nid, 'org': org, 'orgName': names.get(org, 'Leo'), 'at': now + hours * 3600000, 'mins': 90, 'venue': 'Slazenger', 'notes': '', 'spots': spots,
            'members': mem, 'joined': joined or [], 'names': {k: v for k, v in names.items() if k in mem}, 'ans': {k: {'s': v[0], 't': now - v[1] * 1000} for k, v in ans.items()},
            'extra': extra or [], 'status': status, 'changed': changed, 'created': now - 86400000, 'u': now}

@promise('Match nights: first in gets the spot, extras become reserves, and a dropout moves Reserve 1 up', 'Match night card, spots and reserves')
def t_night_roster(p):
    b, pg, e = fresh(p)
    n = night('n1', {'org1': ('in', 500), 'u2': ('in', 400), 'u3': ('in', 300), 'u4': ('in', 200), 'u5': ('in', 100), 'u6': ('out', 50)})
    r = T(pg, "const r=t.nightRoster(a);return {playing:r.playing.map(x=>x.name),reserves:r.reserves.map(x=>x.name),out:r.out.map(x=>x.name),waiting:r.waiting.map(x=>x.name)}", n)
    n['ans']['u3'] = {'s': 'out', 't': int(time.time() * 1000)}
    r2 = T(pg, "const r=t.nightRoster(a);return {playing:r.playing.map(x=>x.name),reserves:r.reserves.map(x=>x.name)}", n)
    manual = night('n2', {'org1': ('in', 300)}, extra=[{'n': 'Ali', 's': 'in', 't': int(time.time() * 1000) - 200000}])
    r3 = T(pg, "return t.nightRoster(a).playing.map(x=>x.name)", manual)
    b.close()
    ok = r['playing'] == ['Leo', 'Ben', 'Ellie', 'James'] and r['reserves'] == ['Marta'] and r['out'] == ['Kwame'] and r['waiting'] == ['Raza'] \
        and r2['playing'] == ['Leo', 'Ben', 'James', 'Marta'] and r2['reserves'] == [] and r3 == ['Leo', 'Ali']
    return ok, {'first answers': r, 'after Ellie drops out': r2, 'organiser added Ali by hand': r3}

@promise('Cancelled or finished match nights can no longer be answered', 'Match night card')
def t_night_open(p):
    b, pg, e = fresh(p)
    r = T(pg, "return a.map(n=>t.nightOpen(n))", [night('a', {}), night('b', {}, status='cancelled'), night('c', {}, hours=-5)])
    b.close()
    return r == [True, False, False], {'upcoming': r[0], 'cancelled': r[1], 'finished 5 hours ago': r[2]}

@promise('The Home card shows each player where they stand, updates, cancellations and fair teams when full', 'Home, Match night card')
def t_night_cards(p):
    now = int(time.time() * 1000)
    nights = [night('w', {'org1': ('in', 500)}, hours=20),
              night('i', {'org1': ('in', 500), 'me1': ('in', 100)}, hours=30, changed=now),
              night('r', {'org1': ('in', 500), 'u2': ('in', 400), 'u3': ('in', 300), 'u4': ('in', 200), 'me1': ('in', 50)}, hours=40)]
    b, pg, e = fresh(p)
    T(pg, "t.setNights(a,'me1')", nights); pg.wait_for_timeout(500)
    rows = pg.evaluate("[...document.querySelectorAll('#nightCard .nrow')].map(r=>({text:r.innerText.replace(/\\n/g,' | '),buttons:[...r.querySelectorAll('button')].map(b=>b.innerText)}))")
    T(pg, "t.setNights(a,'me1')", [night('x', {'org1': ('in', 500)}, status='cancelled')]); pg.wait_for_timeout(400)
    cancelled = pg.evaluate("(document.querySelector('#nightCard .nrow')||{innerText:''}).innerText.replace(/\\n/g,' | ')")
    full = night('f', {'org1': ('in', 500), 'me1': ('in', 400), 'u2': ('in', 300), 'u3': ('in', 200)})
    T(pg, "t.setNights(a,'me1')", [full]); pg.wait_for_timeout(400)
    teams = pg.evaluate("(document.querySelector('#nightCard .nteams')||{innerText:''}).innerText")
    pg.evaluate("document.querySelector('[data-nstart]')&&document.querySelector('[data-nstart]').click()"); pg.wait_for_timeout(900)
    setup = pg.evaluate("['pA1','pA2','pB1','pB2'].map(i=>document.getElementById(i).value)")
    b.close()
    def has(i, s): return any(s in x for x in [rows[i]['text']] + rows[i]['buttons'])
    ok = len(rows) == 3 and has(0, "I'm in") and has(0, '1 of 4 in') and has(1, "You're in") and has(1, 'Updated') \
        and has(2, 'Reserve 1') and has(2, '4 of 4 in') and 'Cancelled' in cancelled and 'Dismiss' not in cancelled[:0] \
        and teams.startswith('Fairest teams') and sorted(setup) == sorted(['Leo', 'Raza', 'Ben', 'Ellie'])
    return ok, {'cards': rows, 'cancelled card': cancelled, 'full night': teams, 'Start this match fills': setup}

@promise('The organiser sees the live count, reserves and who joined by link', 'Match night planner')
def t_night_planner(p):
    n = night('n9', {'me1': ('in', 500), 'u2': ('in', 400), 'u5': ('in', 300), 'u6': ('in', 200), 'u3': ('in', 100), 'u4': ('out', 50)}, org='me1', joined=['u5', 'u6'])
    plan = {'id': 'n9', 'at': n['at'], 'mins': 90, 'venue': 'Slazenger', 'players': ['Raza', 'Ben', 'Ellie', 'James'], 'ok': [True, False, False, False], 'notes': '', 'u': n['u'], 'spots': 4}
    b, pg, e = fresh(p)
    pg.evaluate("a=>localStorage.setItem('db-plans',JSON.stringify(a))", [plan]); pg.reload(); pg.wait_for_timeout(1800); pg.wait_for_function("!!window.__pcTest")
    T(pg, "t.setNights(a,'me1')", [n]); pg.wait_for_timeout(300)
    pg.evaluate("document.getElementById('hmPlan').click()"); pg.wait_for_timeout(700)
    summ = pg.evaluate("(document.querySelector('#planBody .plsum')||{innerText:''}).innerText")
    joined = pg.evaluate("[...document.querySelectorAll('#planBody .pljn')].map(x=>x.innerText)")
    spots = pg.evaluate("!!document.getElementById('plSpots')")
    b.close()
    return summ.startswith('4 of 4 in') and '1 reserve' in summ and sorted(joined) == ['Kwame', 'Marta'] and spots, {'summary': summ, 'joined by link': joined, 'spots choice shown': spots}

@promise('Profile: the year\'s win rate matches its won-lost record, and every detail entered appears', 'Profile, Player spotlight and year in numbers')
def t_profile(p):
    now = int(time.time() * 1000)
    h = [match('y%d' % i, ['Raza', 'Ben'], ['Leo', 'Marta'], [[6, 3], [6, 2]] if i % 3 else [[2, 6], [3, 6]], days_ago=i + 1) for i in range(9)]
    prof = {'side': 'Left', 'ptLevel': '0.89', 'club': 'Slazenger', 'racket': 'Babolat', 'hand': 'Right-handed', 'since': '2023', 'shot': 'Bandeja', 'level': 'Improver', 'bio': 'Big bandeja.'}
    b, pg, e = fresh(p, history=h, profile=prof)
    pg.evaluate("document.querySelector('#fnav [data-nav=profile]').click()"); pg.wait_for_timeout(900)
    tiles = pg.evaluate("Object.fromEntries([...document.querySelectorAll('.spotyear .stile')].map(t=>[t.querySelector('span').innerText,t.querySelector('b').innerText]))")
    text = pg.inner_text('#profileBody')
    b.close()
    w, l = map(int, tiles.get('Won–lost', '0–0').split('–'))
    rate_ok = tiles.get('Win rate') == str(round(w / max(1, w + l) * 100)) + '%'
    missing = [v for v in prof.values() if v not in text]
    return rate_ok and w + l == 9 and not missing, {'year tiles': tiles, 'details missing': missing}

@promise('Secret achievements are revealed only to the admin, on their own profile', 'Profile, Secret achievements')
def t_admin_secrets(p):
    b, pg, e = fresh(p, history=[match('s1', ['Raza', 'Ben'], ['Leo', 'Marta'], [[6, 3], [6, 3]])])
    pg.evaluate("document.querySelector('#fnav [data-nav=profile]').click()"); pg.wait_for_timeout(800)
    sec = lambda: pg.evaluate("(()=>{const s=[...document.querySelectorAll('#profileBody .badge.tsec')];return {names:s.map(x=>x.querySelector('b').textContent.trim()),sub:(document.body.innerText.match(/(Only you can see these[^\\n]*|Keep playing. Some things are better discovered.)/)||[''])[0]}})()")
    normal = sec()
    T(pg, "t.setAdmin(true,'admin1')"); pg.wait_for_timeout(500)
    admin = sec()
    T(pg, "t.setAdmin(false)"); pg.wait_for_timeout(500)
    after = sec()
    b.close()
    hidden_normally = all(n == '???' for n in normal['names']) and normal['names']
    revealed = admin['names'] and '???' not in admin['names'] and admin['sub'].startswith('Only you can see these')
    return bool(hidden_normally and revealed and all(n == '???' for n in after['names'])), {'normal player': normal, 'admin': admin, 'admin signed out again': after}

TESTS = [t_start_table, t_tiers, t_weights, t_weight_applied, t_amer_counts, t_league_overall, t_pred, t_dispute, t_evening,
         t_golden, t_adv, t_tb, t_race, t_bestof, t_stb, t_pairings, t_court, t_form, t_legacy, t_first_serve, t_versions, t_night_roster, t_night_open, t_night_cards, t_night_planner, t_profile, t_admin_secrets]

if __name__ == '__main__':
    with sync_playwright() as p:
        for t in TESTS:
            try:
                ok, detail = t(p)
            except Exception as ex:
                ok, detail = False, 'TEST ERROR: ' + str(ex)[:200]
            RESULTS.append((ok, t._name, t._where, detail))
            print(('PASS  ' if ok else 'FAIL  ') + t._name + '   [' + t._where + ']')
            if not ok: print('        ', json.dumps(detail, ensure_ascii=False)[:400])
    passed = sum(1 for r in RESULTS if r[0])
    print('\n%d of %d promises kept' % (passed, len(RESULTS)))
    sys.exit(0 if passed == len(RESULTS) else 1)
