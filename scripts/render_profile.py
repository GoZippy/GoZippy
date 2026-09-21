"""Create portable Zippy profile SVGs from curated projects and sanitized activity.

No network or private-repository discovery. Animations are decorative, finite and
respect reduced motion. Every asset has a useful static state.
"""
import json
import math
import re
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

from fontTools.ttLib import TTFont
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "assets"
NS = "http://www.w3.org/2000/svg"
ET.register_namespace("", NS)
FONTS = {False: TTFont(ASSETS/"fonts/OpenSans-Regular.ttf"), True: TTFont(ASSETS/"fonts/OpenSans-Bold.ttf")}


def text(x, y, value, size=22, color="#f8f4f1", bold=False, extra=""):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{700 if bold else 400}" fill="{color}" {extra}>{escape(str(value))}</text>'


def base(title, width, height, body, animated=False):
    css = """.trace{stroke-dasharray:8 12;animation:flow 7s linear 2}.pulse{animation:arrive 1.4s ease-out 1}.orbit{transform-origin:950px 165px;animation:orbit 14s linear 1}@keyframes flow{to{stroke-dashoffset:-140}}@keyframes arrive{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}@keyframes orbit{from{transform:rotate(-12deg)}to{transform:rotate(0deg)}}@media(prefers-reduced-motion:reduce){*{animation:none!important}}""" if animated else ""
    return f'<svg xmlns="{NS}" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-labelledby="title"><title id="title">{escape(title)}</title><style>{css}</style><rect width="{width}" height="{height}" rx="20" fill="#1b0c12"/>{body}</svg>'


def save(name, svg, mark=None):
    root = ET.fromstring(svg)
    if mark:
        x,y,size=mark
        art=ET.parse(ASSETS/"zippy-z-sphere.svg").getroot()
        art.attrib.update(x=str(x),y=str(y),width=str(size),height=str(size))
        root.append(art)
    # Outlines keep the real font consistent in GitHub image rendering, with no
    # remote fonts, tracking endpoints, scripting or external image references.
    for parent in list(root.iter()):
        for child in list(parent):
            if child.tag != f'{{{NS}}}text':
                continue
            label=child.text or ''
            font=FONTS[child.get('font-weight')=='700']
            glyphs,cmap=font.getGlyphSet(),font.getBestCmap()
            scale=float(child.get('font-size'))/font['head'].unitsPerEm
            x,y=float(child.get('x')),float(child.get('y'))
            group=ET.Element(f'{{{NS}}}g',{'aria-label':label,'fill':child.get('fill','#fff')})
            for char in label:
                glyph=cmap.get(ord(char))
                if glyph is None:
                    raise ValueError(f'Unsupported glyph: {char!r}')
                pen=SVGPathPen(glyphs)
                glyphs[glyph].draw(TransformPen(pen,(scale,0,0,-scale,x,y)))
                if pen.getCommands():
                    ET.SubElement(group,f'{{{NS}}}path',{'d':pen.getCommands()})
                x += font['hmtx'][glyph][0]*scale
            parent.insert(list(parent).index(child),group)
            parent.remove(child)
    ET.ElementTree(root).write(ASSETS/name,encoding='utf-8',xml_declaration=True)


def hero():
    body='<defs><radialGradient id="halo"><stop stop-color="#c20000" stop-opacity=".28"/><stop offset="1" stop-color="#c20000" stop-opacity="0"/></radialGradient></defs><circle cx="950" cy="165" r="230" fill="url(#halo)"/>'
    body+=text(44,43,'ZIPPY TECHNOLOGIES / ERIC HENDERSON',16,'#e4b2b8',True)
    body+=text(40,124,'AI systems that',58,bold=True)+text(40,195,'move real work.',58,bold=True)
    body+=text(44,250,'From ambitious idea to working operation.',24,'#dfc9ca')
    body+='<rect x="44" y="280" width="530" height="1" fill="#62404b"/>'
    body+=text(44,309,'BUILDER / OPERATOR   /   KIRO AMBASSADOR',15,'#e4b2b8',True)
    body+='<g class="orbit" fill="none" stroke="#63414e"><ellipse cx="950" cy="165" rx="172" ry="102" transform="rotate(-28 950 165)"/><ellipse cx="950" cy="165" rx="172" ry="102" transform="rotate(28 950 165)"/><circle cx="950" cy="165" r="127"/></g>'
    body+='<g class="trace" fill="none" stroke="#de555b" stroke-width="2"><path d="M770 165h80M1050 165h95M950 40v35M950 254v44"/></g>'
    for x,y,color in [(798,82,'#efbc68'),(1102,82,'#b5a2ff'),(798,245,'#78cdd0'),(1102,245,'#d75c70')]:
        body+=f'<circle class="pulse" cx="{x}" cy="{y}" r="6" fill="{color}"/>'
    body+='<circle cx="950" cy="165" r="73" fill="#fffaf7"/>'
    body+=text(800,319,'CONCEPT / CONNECTED WORKSHOP',13,'#bea9b3')
    for name,motion in [('hero-motion.svg',True),('hero-static.svg',False)]:
        save(name,base('Eric Henderson / Zippy - AI systems that move real work.',1200,340,body,motion),(885,100,130))


def project_scenes():
    groups=json.loads((ROOT/'data/projects.json').read_text())['groups']
    for group in groups:
        color=group['accent']
        body=text(34,42,group['status'].upper(),14,color,True)
        body+=text(34,89,group['title'],32,bold=True)
        for i,name in enumerate(group['projects']):
            body+=text(34,132+i*33,name,22,'#dfc9ca')
        body+=text(34,238,'CONCEPT VISUAL / SELECTED WORK IN PROGRESS',12,'#ae969f')
        if group['id']=='compute':
            points=[(700,74),(811,74),(756,141),(654,193),(860,193)]
            for a,b in [(0,1),(0,2),(1,2),(2,3),(2,4),(3,4)]:
                x,y=points[a];u,v=points[b]
                body+=f'<path class="trace" d="M{x} {y}L{u} {v}" stroke="{color}" stroke-opacity=".6" fill="none" stroke-width="2"/>'
            for i,(x,y) in enumerate(points):
                body+=f'<circle cx="{x}" cy="{y}" r="{24 if i==2 else 12}" fill="#302325" stroke="{color}" stroke-width="2"/>'
        elif group['id']=='worlds':
            body+=f'<ellipse cx="760" cy="131" rx="122" ry="43" transform="rotate(-25 760 131)" fill="none" stroke="{color}" stroke-width="2"/><circle cx="760" cy="131" r="65" fill="#27203e" stroke="{color}"/><ellipse cx="760" cy="131" rx="24" ry="65" fill="none" stroke="{color}" stroke-opacity=".4"/><path class="trace" d="M695 131h130M710 98h100M710 164h100" stroke="{color}" fill="none"/><circle cx="864" cy="83" r="9" fill="#78cdd0"/>'
        else:
            for i,label in enumerate(['BRIEF','BUILD','REVIEW']):
                x=612+i*99
                body+=f'<rect x="{x}" y="103" width="84" height="64" rx="10" fill="#173036" stroke="{color}"/>'
                body+=text(x+10,142,label,13,color,True)
                if i<2: body+=f'<path class="trace" d="M{x+84} 135h15" stroke="{color}" stroke-width="3"/>'
        save('scene-'+group['id']+'.svg',base(group['title']+' - conceptual illustration, not product footage',960,264,body,True))


def activity():
    path=ROOT/'data/activity.json'
    data=json.loads(path.read_text()) if path.exists() else None
    body=text(32,37,'BUILD ACTIVITY',15,'#e4b2b8',True)
    if data is None:
        body+=text(32,99,'Snapshot unavailable',36,bold=True)+text(32,144,'No contribution counts have been invented.',20,'#dfc9ca')
        save('activity.svg',base('GitHub contribution snapshot unavailable',1100,230,body))
        return
    daily=data['daily']
    total=data['total_contributions']
    active=sum(d['count']>0 for d in daily)
    body+=text(30,94,f'{total:,}',48,bold=True)+text(32,126,'GitHub contributions',20,'#dfc9ca')
    body+=text(32,164,f'{active} active days',22,'#efbc68',True)
    body+=text(32,202,'SNAPSHOT / '+data['captured_at'][:10],13,'#bea9b3')
    start=date.fromisoformat(daily[0]['date'])
    peak=max((d['count'] for d in daily),default=0)
    for row in daily:
        d=date.fromisoformat(row['date']);offset=(d-start).days+(start.weekday()+1)%7
        col,day=divmod(offset,7)
        x,y=420+col*12,47+day*15
        level=0 if not row['count'] else min(4,1+int(3*math.log1p(row['count'])/math.log1p(max(1,peak))))
        color=['#35212a','#61303b','#943342','#c94451','#f0767d'][level]
        body+=f'<rect x="{x}" y="{y}" width="9" height="11" rx="2" fill="{color}"><title>{row["date"]}: {row["count"]} contributions</title></rect>'
    body+=text(420,185,data['window']['start'][:10]+' to '+data['window']['end'][:10],16,'#dfc9ca')
    body+=text(420,211,'Aggregate only. No repository details.',15,'#bea9b3')
    save('activity.svg',base(f'{total:,} GitHub contributions, {active} active days; dated viewer-visible aggregate',1100,235,body))
    readme=ROOT/'README.md'
    if readme.exists():
        s=readme.read_text(encoding='utf-8')
        line=f'**{total:,} contributions · {active} active days** · {data["window"]["start"][:10]} to {data["window"]["end"][:10]}. Snapshot: {data["captured_at"][:10]}.'
        s=re.sub(r'<!-- ACTIVITY:START -->.*?<!-- ACTIVITY:END -->','<!-- ACTIVITY:START -->\n'+line+'\n<!-- ACTIVITY:END -->',s,flags=re.S)
        readme.write_text(s,encoding='utf-8')


def proof():
    data=json.loads((ROOT/'data/activity.json').read_text())
    active=sum(d['count']>0 for d in data['daily'])
    total=data['total_contributions']
    body=text(30,37,'SELECTED PUBLIC SIGNALS',15,'#e4b2b8',True)
    cards=[
        (28,'PUBLIC PROOF','#efbc68','3','Merged Kiro Crew fixes','Inspect the upstream PR trail.'),
        (373,'DATED ACTIVITY','#78cdd0',str(active),'Active contribution days',f'{total:,} contributions / aggregate.'),
        (718,'WORKING STACK','#b5a2ff','Rust · TS · Python','Systems + apps + automation','Tools selected for the job.'),
    ]
    for x,label,color,value,title,detail in cards:
        body+=f'<rect x="{x}" y="56" width="314" height="142" rx="12" fill="#281922" stroke="#4e3440"/>'
        body+=text(x+20,83,label,12,color,True)
        body+=text(x+20,126,value,30,'#fff5ed',True)
        body+=text(x+20,157,title,15,'#dfc9ca',True)
        body+=text(x+20,184,detail,13,'#ad929d')
    save('proof.svg',base('Selected signals: three merged Kiro Crew fixes, dated aggregate activity and a working systems stack',1060,224,body))


def toolkit():
    body=text(30,37,'THE WORKING TOOLKIT',15,'#e4b2b8',True)
    for x,title,items,color in [
        (30,'BUILD',['Rust / TypeScript','Python / Flutter'],'#efbc68'),
        (340,'COORDINATE',['Kiro IDE / CLI / Crew','Claude Code / Codex'],'#78cdd0'),
        (650,'DELIVER',['Git / GitHub / Docker','Windows / Linux'],'#b5a2ff')]:
        body+=f'<rect x="{x}" y="59" width="280" height="125" rx="12" fill="#281922" stroke="#4e3440"/>'
        body+=text(x+18,89,title,15,color,True)
        body+=text(x+18,128,items[0],20)
        body+=text(x+18,158,items[1],20,'#dfc9ca')
    save('toolkit.svg',base('Working tools: systems, applications, agent workflows and delivery',960,209,body))


def collaboration():
    body=text(32,37,'HOW I HELP TEAMS MOVE',15,'#e4b2b8',True)
    cards=[
        (28,'CLARIFY','#efbc68','Opportunity','Find the bottleneck\nand define a useful win.'),
        (373,'BUILD','#78cdd0','Working system','Prototype the smallest\nthing people can run.'),
        (718,'OPERATE','#b5a2ff','Compounding motion','Create owners, metrics\nand a rhythm that lasts.'),
    ]
    for x,label,color,title,description in cards:
        body+=f'<rect x="{x}" y="58" width="314" height="145" rx="12" fill="#281922" stroke="#4e3440"/>'
        body+=f'<circle cx="{x+28}" cy="91" r="8" fill="{color}"/>'
        body+=text(x+49,96,label,13,color,True)
        body+=text(x+20,133,title,20,'#fff5ed',True)
        lines=description.split('\n')
        for i,line in enumerate(lines):
            body+=text(x+20,163+i*23,line,15,'#dfc9ca')
    save('collab.svg',base('How Eric helps teams: clarify, build and operationalize useful AI systems',1060,229,body))


if __name__=='__main__':
    (ROOT/'README.md').write_text((ROOT/'templates/README.md').read_text(encoding='utf-8'),encoding='utf-8')
    hero()
    project_scenes()
    activity()
    proof()
    toolkit()
    collaboration()
    print('Rendered branded hero, proof, project scenes and sanitized activity card.')
