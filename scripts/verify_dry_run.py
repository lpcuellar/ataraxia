"""Verifica ambos modos contra DB real en solo lectura; no registra datos de prueba."""
import os
os.environ['ATARAXIA_DRY_RUN']='1'
import sys
import json
import hashlib
import subprocess
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from src.db.models import get_connection
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'data'/'dry-run'
OUT.mkdir(exist_ok=True)
def fingerprint():
    conn=get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute('show transaction_read_only')
            assert cur.fetchone()[0]=='on'
            result={}
            for table in ('watchlist','candidate_queue','recommendations','portfolio_snapshots','universe_state','decisions'):
                cur.execute(f'SELECT row_to_json(t)::text FROM {table} t')
                rows=sorted(r[0] for r in cur.fetchall())
                result[table]={'count':len(rows),'sha256':hashlib.sha256('\n'.join(rows).encode()).hexdigest()}
            return result
    finally:
        conn.close()
def pending():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'data'/'pending_db_writes').glob('*.json')}
before=fingerprint(); queued=pending()
for mode in ('barrido','reporte'):
    with (OUT/f'{mode}.txt').open('w') as log:
        subprocess.run([sys.executable,'-u',str(ROOT/'scripts'/'run_cycle.py'),mode,'--dry-run'],cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=120)
after=fingerprint()
assert before==after, 'Estado DB cambio durante prueba (investigar concurrencia o escritura)'
assert queued==pending(), 'Escrituras pendientes cambiaron'
(OUT/'verification.json').write_text(json.dumps({'read_only':True,'unchanged':before==after,'tables':after,'pending_unchanged':True},indent=2))
print('PASS: barrido y reporte terminan; 6 tablas y pending_db_writes sin cambios; transaction_read_only=on')
