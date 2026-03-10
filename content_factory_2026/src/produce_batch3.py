#!/usr/bin/env python3
import os, json, datetime, pathlib, urllib.request

BASE=pathlib.Path('/data/.openclaw/workspace/content_factory_2026')
OUT=BASE/'outputs'/f"batch3_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}"
OUT.mkdir(parents=True, exist_ok=True)

for line in (BASE/'.env').read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        k,v=line.split('=',1); os.environ[k]=v

api_key=os.environ.get('OPENAI_API_KEY','')

def ask(prompt:str)->str:
    body={"model":"gpt-4o-mini","input":prompt}
    data=json.dumps(body).encode('utf-8')
    req=urllib.request.Request('https://api.openai.com/v1/responses', data=data, headers={
        'Authorization':f'Bearer {api_key}',
        'Content-Type':'application/json'
    })
    with urllib.request.urlopen(req, timeout=60) as r:
        resp=json.loads(r.read().decode('utf-8'))
    return resp.get('output_text','').strip()

ideas=[
    '3 automatisations simples qui te font gagner 2h/jour',
    'Comment arrêter de perdre des leads avec une relance automatique',
    'Le système no-code minimum pour vendre pendant que tu dors'
]

for i,topic in enumerate(ideas, start=1):
    prompt=f"Ecris un script vidéo courte FR (35-50s) pour Reels/TikTok sur: {topic}. Format: Hook, Valeur en 3 points, CTA. Ton direct startup."
    script=ask(prompt)
    d={
        'id':i,
        'topic':topic,
        'script':script,
        'caption':f"{topic} 🚀\\nCommente START si tu veux le template.",
        'hashtags':'#ia #automatisation #nocode #business #entrepreneur #reelsfr #tiktokfr',
        'post_time':['09:30','14:00','19:30'][i-1]
    }
    (OUT/f'video_{i}.json').write_text(json.dumps(d,ensure_ascii=False,indent=2),encoding='utf-8')

(OUT/'batch_summary.json').write_text(json.dumps({'count':3,'created':datetime.datetime.now().isoformat()},indent=2),encoding='utf-8')
print(str(OUT))
