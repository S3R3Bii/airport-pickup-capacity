"""Recompute all deterministic validation/held outputs in an isolated source copy."""
import csv,gzip,io,json,shutil,subprocess,sys,tempfile
from pathlib import Path
from verify_freeze import verify as verify_freeze
from verify_results import verify as verify_results
def check():
    root=Path(__file__).resolve().parents[1];freeze=verify_freeze(root);checks=0;results=[]
    with tempfile.TemporaryDirectory(prefix='pickup-replay-') as folder:
        isolated=Path(folder)/'source';isolated.mkdir()
        for name in ['src','data','tests']:shutil.copytree(root/name,isolated/name,ignore=shutil.ignore_patterns('__pycache__'))
        for name in ['protocol.json','PROTOCOL.md','SOURCES.md','SOURCE_CORRECTION.md','SELECTION.json','FREEZE.json']:shutil.copy2(root/name,isolated/name)
        for phase in ['validation','held']:
            subprocess.run([sys.executable,'src/run_analysis.py',phase],cwd=isolated,check=True,capture_output=True)
            for suffix in ['-metrics.csv','-predictions.csv.gz']:
                def read(p):return list(csv.reader(io.StringIO(gzip.decompress(p.read_bytes()).decode()))) if str(p).endswith('.gz') else list(csv.reader(p.open(encoding='utf-8',newline='')))
                actual=read(isolated/'results'/(phase+suffix));expected=read(root/'results'/(phase+suffix));assert actual==expected;checks+=sum(map(len,expected))
            results.append(verify_results(isolated,phase))
        assert json.loads((isolated/'SELECTION.json').read_text(encoding='utf-8'))==json.loads((root/'SELECTION.json').read_text(encoding='utf-8'));checks+=1
        actual=list(csv.reader((isolated/'results/held-temporal-sensitivity.csv').open(encoding='utf-8',newline='')));expected=list(csv.reader((root/'results/held-temporal-sensitivity.csv').open(encoding='utf-8',newline='')));assert actual==expected;checks+=sum(map(len,expected))
    return dict(status='PASS',exact_csv_fields_and_selection_documents=checks,protected_dependencies=freeze['dependencies'],phases=results,timing='Original per-policy timing retained; variable replay timings excluded from deterministic equality.')
if __name__=='__main__':
    result=check();Path('REPRODUCTION_CHECK.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
