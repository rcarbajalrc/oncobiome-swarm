#!/usr/bin/env python3
"""
Escáner de secretos — verifica que no haya API keys ni tokens en el código fuente.

Uso:
    python scripts/scan_secrets.py

Sale con código 0 si todo está limpio, 1 si encuentra secretos.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT = Path(__file__).parent.parent

# Patrones que indican secretos reales
SECRET_PATTERNS = [
    (r'sk-ant-api\d{2}-[A-Za-z0-9_-]{20,}', 'Anthropic API key'),
    (r'm0-[A-Za-z0-9]{20,}',                  'mem0 API key'),
    (r'sk-[A-Za-z0-9]{40,}',                   'OpenAI-style API key'),
    (r'ghp_[A-Za-z0-9]{36}',                   'GitHub personal token'),
    (r'Bearer [A-Za-z0-9._-]{40,}',            'Bearer token'),
]

# Directorios y archivos a excluir del escaneo
SKIP_DIRS = {
    '.git', '__pycache__', 'node_modules',
    'logs', 'state', 'runs', 'results',
    '.venv', 'venv', 'env',
}
SKIP_FILES = {
    '.env',             # contiene keys reales — no se sube a GitHub
    'scan_secrets.py',  # este mismo script
}
SCAN_EXTENSIONS = {'.py', '.yaml', '.yml', '.md', '.txt', '.json', '.example'}

findings: list[tuple[str, int, str, str]] = []


def scan_file(path: Path) -> None:
    if path.name in SKIP_FILES:
        return
    if path.suffix not in SCAN_EXTENSIONS:
        return
    try:
        content = path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return
    for lineno, line in enumerate(content.splitlines(), 1):
        for pattern, label in SECRET_PATTERNS:
            if re.search(pattern, line):
                findings.append((str(path.relative_to(PROJECT)), lineno, label, line.strip()[:80]))


def scan_dir(root: Path) -> None:
    for item in root.iterdir():
        if item.name.startswith('.') and item.name not in {'.env.example', '.gitignore'}:
            continue
        if item.is_dir():
            if item.name in SKIP_DIRS:
                continue
            scan_dir(item)
        elif item.is_file():
            scan_file(item)


if __name__ == '__main__':
    scan_dir(PROJECT)

    if not findings:
        print('✓ Sin secretos detectados en el código fuente.')
        print(f'  Escaneado: {PROJECT}')
        print('  Excluidos: .env (no se publica), logs/, state/, runs/')
        sys.exit(0)
    else:
        print(f'⚠ SECRETOS ENCONTRADOS ({len(findings)} hallazgos):')
        print()
        for fpath, lineno, label, snippet in findings:
            print(f'  [{label}] {fpath}:{lineno}')
            print(f'    {snippet}')
        print()
        print('Acción requerida: eliminar o mover los secretos antes de git push.')
        sys.exit(1)
