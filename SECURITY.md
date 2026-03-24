# Security Policy — OncoBiome Swarm

## Supported Versions

| Version | Supported |
|---------|-----------|
| Sprint 4 (v0.4.x) | ✅ Active |
| Sprint 3 (v0.3.x) | ⚠ Security fixes only |
| Sprint 0–2 | ❌ Not supported |

---

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Report vulnerabilities privately by email:
- **Email:** robertocarbajal.rc@gmail.com
- **Subject:** `[SECURITY] OncoBiome Swarm — <brief description>`

You will receive a response within 72 hours. If the vulnerability is confirmed, a patch will be released within 14 days.

---

## Security Architecture

### API Key Protection
- `ANTHROPIC_API_KEY` is loaded exclusively from `.env` (excluded from git via `.gitignore`)
- `load_dotenv(override=False)` — environment variables set before process start are never overwritten
- No API keys are logged, printed, or included in any error messages
- `scripts/scan_secrets.py` — pre-push secret scanner (run before every commit)

### LLM Prompt Injection Defense
- Agent prompts are constructed from structured `LocalContext` objects, not raw user input
- No external data enters the LLM prompt pipeline without type validation (pydantic)
- Agent decisions are parsed via strict JSON schema — malformed responses trigger `BatchError → rule engine`
- `_MAX_RESPONSE_BYTES = 100_000` — prevents OOM from unexpectedly large LLM responses

### Data Privacy
- Simulation data (token_usage.json, decisions.csv, opus_history.json) excluded from git
- No patient data or PII is processed by this framework
- Biological parameters are calibrated from published literature only

### Process Isolation
- PID file locking (`state/sim.lock`, `fcntl.LOCK_EX | LOCK_NB`) prevents concurrent simulations
- Simulation state is written atomically with `fcntl.flock` — no partial state corruption
- Log rotation (`RotatingFileHandler`, maxBytes=5MB, backupCount=3) prevents disk exhaustion
- Process escalation: SIGTERM → 3s timeout → SIGKILL for clean shutdown

### Path Traversal Prevention
- `mcp_server.py` file operations use `.resolve()` against symlinks before any path check
- All file reads/writes are sandboxed to `SIM_DIR` with boundary enforcement

### Subprocess Safety
- No `shell=True` in any `subprocess` call
- All subprocess arguments are lists of strings, never f-string interpolated commands
- `PYTHON = sys.executable` — no hardcoded interpreter paths

### Dependency Security
- All production dependencies are version-pinned with `==` in `requirements.txt`
- No wildcard (`>=`, `~=`) versions in production
- Development dependencies isolated in `requirements-dev.txt`

---

## Known Limitations & Planned Improvements

### MCP Rate Limiting (Sprint 5)
The MCP server tools (`run_simulation`, `_write_file`) do not currently implement
rate limiting. A malicious actor with MCP access could loop API calls consuming
tokens and CPU. Planned fix: add per-tool call rate limiting (max 10 `run_simulation`
calls per hour) in Sprint 5.

### Dependency Hash Verification (Future)
`requirements.txt` uses exact version pinning (`==`) which prevents version drift but
does not verify file integrity. For stronger supply chain security, generate
requirements with SHA256 hashes:
```bash
pip install pip-tools
pip-compile --generate-hashes requirements.in
```
This is recommended for production deployments but not required for research use.

### SSL in Ollama Integration
Ollama connections verify SSL by default. To disable for local development only:
```
OLLAMA_VERIFY_SSL=false
```
Never disable in production or network-accessible deployments.

---

## Pre-Push Security Checklist

Before every `git push`:

```bash
# 1. Scan for secrets
python scripts/scan_secrets.py

# 2. Run full audit
python scripts/_audit_pregithub.py

# 3. Verify .env is not tracked
git status | grep -v "^?" | grep ".env"  # should return nothing

# 4. Run full test suite
python -m pytest tests/ -q

# 5. Check no sensitive files staged
git diff --cached --name-only | grep -E "(\.env|token_usage|decisions\.csv|opus_history)"
```

---

## Known Security Considerations

1. **MCP server (`mcp_server.py`):** Exposes simulation control via Claude Desktop MCP protocol. Only bind to localhost; never expose to public network.
2. **Plotly Dash dashboard:** Runs on `localhost:8051` by default. Not authenticated — do not expose to public network.
3. **oncobiome.log:** May contain simulation metadata and cycle counts. Excluded from git but handle with care if sharing locally.
4. **simulation/_batch_fix.py:** Placeholder file kept for import compatibility. Contains no executable code. Will be removed in Sprint 5 cleanup.
