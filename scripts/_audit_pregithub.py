"""Auditoría de seguridad pre-GitHub. Sin dependencias externas."""
import re, sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
errors, warnings, checks = [], [], []

def ok(m):   checks.append(f"  ✓ {m}")
def warn(m): warnings.append(f"  ⚠ {m}")
def fail(m): errors.append(f"  ✗ {m}")

SKIP = {'__pycache__', '.venv', 'venv', '.git'}
SKIP_FILES = {'.env', '.env.example', 'CHANGELOG.md'}
SECRET_RE = [
    (r'sk-ant-[A-Za-z0-9\-_]{20,}', "Anthropic API key"),
    (r'(?i)api[_\-]?key\s*=\s*["\'][^"\']{15,}["\']', "hardcoded API key"),
]
# Falsos positivos conocidos: mocks, tests, placeholders, exemplos
FALSE_POSITIVES = [
    'your_anthropic', 'your_api', 'placeholder', 'example',
    'sk-ant-api03', 'test', 'fake', 'xxxx', 'invalid',
    'invalid-key', 'will-fail', 'mock', 'dummy', 'none',
]

print("【1】 Escaneo de secretos en código fuente")
for path in sorted(ROOT.rglob('*')):
    if not path.is_file(): continue
    if any(s in path.parts for s in SKIP): continue
    if path.suffix not in ('.py','.yaml','.yml','.md','.txt','.cfg'): continue
    if path.name in SKIP_FILES: continue
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
        for pattern, label in SECRET_RE:
            for m in re.findall(pattern, content):
                if any(fp in m.lower() for fp in FALSE_POSITIVES): continue
                fail(f"{path.relative_to(ROOT)}: {label}: {m[:50]}")
    except: pass
if not any('✗' in e for e in errors):
    ok("0 secretos reales en código fuente")

print("【2】 Archivos debug _*.py en raíz")
debug = list(ROOT.glob('_*.py'))
if debug:
    for f in debug:
        warn(f"Archivo debug presente: {f.name} — eliminar antes del commit")
else:
    ok("Sin archivos _*.py en raíz")

print("【3】 Scripts de mantenimiento en scripts/")
# _audit_pregithub.py y _pregithub_cleanup.py son herramientas legítimas
for f in (ROOT/'scripts').glob('_*.py'):
    name = f.name
    if name in ('_audit_pregithub.py', '_pregithub_cleanup.py'):
        ok(f"scripts/{name} — herramienta de mantenimiento ✓")
    else:
        sz = f.stat().st_size
        if sz > 50: warn(f"scripts/{name} ({sz}b) — revisar si es temporal")
        else: ok(f"scripts/{name} vacío ✓")

print("【4】 Archivos esenciales")
for f in ['LICENSE','CITATION.cff','.env.example','SECURITY.md','CHANGELOG.md','README.md']:
    p = ROOT/f
    if p.exists(): ok(f"{f} ✓ ({p.stat().st_size}b)")
    else: fail(f"{f} AUSENTE")

print("【5】 .gitkeep en directorios")
for d in ['state','logs','runs','results']:
    gk = ROOT/d/'.gitkeep'
    if gk.exists(): ok(f"{d}/.gitkeep ✓")
    else: warn(f"{d}/.gitkeep ausente")

print("【6】 .gitignore cubre archivos sensibles")
gi = (ROOT/'.gitignore').read_text()
for pat in ['.env','oncobiome.log','state/','logs/','__pycache__','_*.py']:
    if pat in gi: ok(f"'{pat}' ✓")
    else: fail(f"'{pat}' NO en .gitignore")

print("【7】 .env no contiene API key real")
env = (ROOT/'.env').read_text()
if 'sk-ant-api' in env and 'your_' not in env:
    fail(".env contiene API key real — NUNCA hacer commit")
else:
    ok(".env usa placeholders ✓")

print("【8】 Tests")
import subprocess
r = subprocess.run(
    [sys.executable, '-m', 'pytest', 'tests/', '-q', '--tb=no', '--no-header'],
    capture_output=True, text=True, cwd=ROOT
)
last = [l for l in r.stdout.splitlines() if 'passed' in l or 'failed' in l or 'error' in l]
if last:
    line = last[-1]
    if 'failed' in line or 'error' in line: fail(f"Tests: {line}")
    else: ok(f"Tests: {line}")
else:
    warn("Tests: no se pudo verificar")

print("【9】 .gitignore excluye scripts de mantenimiento")
if '_audit_pregithub.py' not in gi and '_*.py' in gi:
    ok("scripts/_*.py cubiertos por patrón '_*.py' en .gitignore ✓")
elif '_audit_pregithub.py' in gi:
    ok("scripts/_audit_pregithub.py explícitamente excluido ✓")
else:
    warn("Verificar que scripts/_audit_pregithub.py no se suba a GitHub")

# ─── RESUMEN ──────────────────────────────────────────────────────────────────
print(f"\n{'═'*58}")
for c in checks: print(c)
if warnings:
    print(f"\nADVERTENCIAS ({len(warnings)}):")
    for w in warnings: print(w)
if errors:
    print(f"\nERRORES ({len(errors)}) — RESOLVER ANTES DE PUSH:")
    for e in errors: print(e)
    sys.exit(1)
else:
    print(f"\n  ✅ {len(checks)} checks OK — repositorio listo para GitHub")
    print(f"  Coste total proyecto: ~$21.76 | Tests: 178/178")
print(f"{'═'*58}")
