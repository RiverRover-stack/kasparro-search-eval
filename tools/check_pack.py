#!/usr/bin/env python3
"""Validate the supplied inputs and their checksums without network access."""
import hashlib,json,sys
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def rows(name):return [json.loads(s) for s in (ROOT/name).read_text(encoding='utf-8').splitlines() if s.strip()]
def require(condition,message):
    if not condition:raise ValueError(message)
try:
    m=json.loads((ROOT/'PACK_MANIFEST.json').read_text(encoding='utf-8'))
    for rel,digest in m['sha256'].items():
        p=ROOT/rel
        require(p.is_file(),'Missing file: '+rel)
        require(hashlib.sha256(p.read_bytes()).hexdigest()==digest,'Checksum mismatch: '+rel)
    ps=rows('data/prompts.jsonl');rs=rows('data/responses.jsonl');cs=rows('data/citations.jsonl')
    require(len(ps)==m['counts']['prompts'],'Prompt count mismatch')
    require(len(rs)==m['counts']['responses'],'Response count mismatch')
    require(len(cs)==m['counts']['citations'],'Citation count mismatch')
    pids={p['prompt_id'] for p in ps};rids={r['response_id'] for r in rs}
    require(len(pids)==len(ps),'Duplicate prompt ID')
    require(len(rids)==len(rs),'Duplicate response ID')
    require(len({c['citation_id'] for c in cs})==len(cs),'Duplicate citation ID')
    require(all(r['prompt_id'] in pids for r in rs),'Response has an unknown prompt')
    require(all(c['response_id'] in rids for c in cs),'Citation has an unknown response')
    require(all(r['answer_text'] and r['engine'] in ['aimode','gemini','chatgpt'] for r in rs),'Invalid response')
    pairs=Counter((r['prompt_id'],r['engine']) for r in rs)
    require(all(n==1 for n in pairs.values()),'Duplicate prompt-engine pair')
    if m['track']!='pm':
        require(len(ps)==50 and len(rs)==150,'Core dataset should contain 50 prompts and 150 responses')
        require(all(sum(r['prompt_id']==pid for r in rs)==3 for pid in pids),'Incomplete engine coverage')
    if m['track']=='pm':
        cases=rows('cases/cases.jsonl');sources=rows('evidence/sources.jsonl');sids={s['source_id'] for s in sources}
        require(len(cases)==12 and len({c['case_id'] for c in cases})==12,'Expected 12 unique cases')
        require(len(sids)==len(sources),'Duplicate source ID')
        require(all(s in sids for c in cases for s in c['allowed_source_ids']),'Case points to missing evidence')
        require(all((ROOT/s['text_path']).is_file() for s in sources),'Missing source text')
        print('Cases:',len(cases),'Evidence sources:',len(sources))
    print('Pack:',m['pack_name'],'Version:',m['version'])
    print('Prompts:',len(ps),'Responses:',len(rs),'Citation entries:',len(cs))
    print('All declared files, checksums and core input relationships are valid.')
    print('This checks the input pack only. It does not score your solution or verify claims in engine answers.')
except Exception as e:
    print('PACK CHECK FAILED:',str(e),file=sys.stderr);sys.exit(1)
