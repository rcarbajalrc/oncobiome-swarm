"""
Ejecuta los tests del ablation study.
Uso: python3 scripts/run_ablation_tests.py
"""
import subprocess, sys
result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/test_ablation_memory.py", "-v", "--tb=short"],
    cwd=str(__import__('pathlib').Path(__file__).parent.parent)
)
sys.exit(result.returncode)
