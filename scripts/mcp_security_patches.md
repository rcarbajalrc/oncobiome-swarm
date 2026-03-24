# ─── SECURITY FIXES aplicados a mcp_server.py ───────────────────────────────
#
# FIX 1 — Path traversal (HIGH): usar .resolve() para resolver symlinks
#   Antes: str(target).startswith(str(SIM_DIR))  ← bypasseable con symlinks
#   Después: target.resolve(), SIM_DIR.resolve() comparados correctamente
#
# FIX 2 — Shell injection (MEDIUM): _run_custom() usa shell=True
#   Riesgo: 'ls; rm -rf ~' ejecutaría ambos comandos
#   Mitigación: añadir advertencia en SECURITY.md. Para uso local de
#   investigación, el riesgo es aceptable pero documentado.
#
# FIX 3 — JSON parse size (LOW): limitar tamaño antes de json.loads()
#   Añadir: if len(raw) > 100_000: return None
#
# Las funciones corregidas son:
#
# def _list_files(subdir: str) -> str:
#     target = (SIM_DIR / subdir).resolve()           # ← .resolve() añadido
#     sim_dir_resolved = SIM_DIR.resolve()            # ← .resolve() añadido
#     if not str(target).startswith(str(sim_dir_resolved)):  # ← comparación con resolved
#         return "Error: acceso fuera del directorio del proyecto."
#
# def _read_file(path: str) -> str:
#     target = (SIM_DIR / path).resolve()             # ← .resolve() añadido
#     sim_dir_resolved = SIM_DIR.resolve()            # ← .resolve() añadido
#     if not str(target).startswith(str(sim_dir_resolved)):
#         return "Error: acceso fuera del directorio del proyecto."
#     if len(content) > 100_000:                      # ← límite de tamaño añadido
#         content = content[:8000] + "\n[... truncado ...]"
#
# def _write_file(path: str, content: str) -> str:
#     target = (SIM_DIR / path).resolve()             # ← .resolve() añadido
#     sim_dir_resolved = SIM_DIR.resolve()            # ← .resolve() añadido
#     if not str(target).startswith(str(sim_dir_resolved)):
#         return "Error: acceso fuera del directorio del proyecto."
#
# NOTA: estos fixes deben aplicarse manualmente en mcp_server.py si se
# regenera el archivo completo. Ver scripts/security_audit.py para validación.
