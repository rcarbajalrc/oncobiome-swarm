"""
OncoBiome Sprint 6 — zAvatar TCGA-PAAD
Descarga datos TME via cBioPortal API (PanCancer Atlas 2018)
Estudio: paad_tcga_pan_can_atlas_2018 — 184 muestras PDAC
"""

import urllib.request
import json
import math
import os

CBIOPORTAL_API = "https://www.cbioportal.org/api"

# Genes clave TME → parámetros OncoBiome
TME_GENES = {
    "IFNG":  "immune_kill_rate / dc_maturation_threshold",
    "VEGFA": "cytokine_decay / m2_threshold",
    "IL6":   "m2_polarisation_il6_threshold",
    "CD8A":  "immune_kill_rate (CD8+)",
    "NCAM1": "nk_kill_rate (NK marker)",
    "ITGAE": "dc_maturation_cycles (DC marker)",
    "CD274": "immune_exhaustion_age (PD-L1)",
    "HAVCR2":"immune_exhaustion_age (TIM-3)",
    "KRAS":  "tumor driver",
    "PDCD1": "PD-1 exhaustion marker",
}

def api_get(endpoint, params=None):
    url = f"{CBIOPORTAL_API}{endpoint}"
    if params:
        qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k,v in params.items())
        url += "?" + qs
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except Exception as e:
        return None

import urllib.parse

def api_post(endpoint, data):
    url = f"{CBIOPORTAL_API}{endpoint}"
    payload = json.dumps(data).encode()
    req = urllib.request.Request(
        url, data=payload,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST"
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())

print("=" * 65)
print("  OncoBiome Sprint 6 — zAvatar TCGA-PAAD")
print("=" * 65)

# ── 1. Buscar estudios PAAD disponibles ───────────────────────
print("\n[1] Buscando estudios PAAD en cBioPortal...")
studies = api_get("/studies", {"keyword": "paad", "pageSize": "20"})
if studies:
    for s in studies:
        print(f"    {s['studyId']:45s} n={s['allSampleCount']:4d}  {s['name'][:40]}")
else:
    print("    Error consultando estudios")

# ── 2. Usar PanCancer Atlas (mayor n) ─────────────────────────
STUDY_ID = "paad_tcga_pan_can_atlas_2018"
print(f"\n[2] Usando estudio: {STUDY_ID}")
study = api_get(f"/studies/{STUDY_ID}")
if study:
    print(f"    Nombre: {study['name']}")
    print(f"    Total muestras: {study['allSampleCount']}")
    print(f"    mRNA RNA-seq: {study.get('mrnaRnaSeqV2SampleCount', 'N/A')}")
else:
    print("    Error — intentando con paad_tcga...")
    STUDY_ID = "paad_tcga"
    study = api_get(f"/studies/{STUDY_ID}")
    print(f"    Fallback: {study['name']} n={study['allSampleCount']}")

# ── 3. Perfiles moleculares ────────────────────────────────────
print("\n[3] Perfiles moleculares disponibles...")
profiles = api_get(f"/studies/{STUDY_ID}/molecular-profiles")
mrna_zscore_profile = None
mrna_profile = None
for p in profiles:
    pid = p["molecularProfileId"]
    alt = p["molecularAlterationType"]
    print(f"    {pid:55s} {alt}")
    if "zscores" in pid.lower() and "rna" in pid.lower():
        mrna_zscore_profile = pid
    elif alt == "MRNA_EXPRESSION" and mrna_profile is None:
        mrna_profile = pid

target_profile = mrna_zscore_profile or mrna_profile
print(f"\n    Perfil seleccionado: {target_profile}")

# ── 4. Obtener muestras ────────────────────────────────────────
print("\n[4] Obteniendo muestras...")
samples = api_get(f"/studies/{STUDY_ID}/samples",
                  {"pageSize": "300", "pageNumber": "0"})
if not samples:
    print("    Error obteniendo muestras")
    exit(1)

sample_ids = [s["sampleId"] for s in samples]
print(f"    Muestras disponibles: {len(sample_ids)}")

# ── 5. Obtener entrezIds para los genes TME ───────────────────
print(f"\n[5] Buscando genes TME ({len(TME_GENES)} genes)...")
gene_ids = {}
for gene in TME_GENES:
    result = api_get(f"/genes/{gene}")
    if result and "entrezGeneId" in result:
        gene_ids[gene] = result["entrezGeneId"]
        print(f"    {gene:10s} → entrezId={result['entrezGeneId']}")
    else:
        print(f"    {gene:10s} → no encontrado")

# ── 6. Descargar expresión génica ────────────────────────────
print(f"\n[6] Descargando expresión de {len(gene_ids)} genes en {len(sample_ids)} muestras...")
try:
    expr_data = api_post(
        f"/molecular-profiles/{target_profile}/molecular-data/fetch",
        {
            "sampleIds": sample_ids,
            "entrezGeneIds": list(gene_ids.values())
        }
    )
    print(f"    Entradas recibidas: {len(expr_data)}")
except Exception as e:
    print(f"    Error: {e}")
    expr_data = []

# ── 7. Organizar por gen ──────────────────────────────────────
print("\n[7] Estadísticas de expresión por gen:")
print(f"    {'Gen':10s} {'n':>5} {'media':>8} {'SD':>8} {'min':>8} {'max':>8}  Parámetro OncoBiome")
print("    " + "-" * 80)

gene_expr = {}
entrez_to_gene = {v: k for k, v in gene_ids.items()}

for entry in expr_data:
    entrez = entry.get("entrezGeneId")
    gene = entrez_to_gene.get(entrez, str(entrez))
    val = entry.get("value")
    if val is not None:
        try:
            fval = float(val)
            if not math.isnan(fval) and not math.isinf(fval):
                if gene not in gene_expr:
                    gene_expr[gene] = []
                gene_expr[gene].append(fval)
        except:
            pass

for gene, desc in TME_GENES.items():
    if gene in gene_expr and gene_expr[gene]:
        vals = gene_expr[gene]
        n = len(vals)
        m = sum(vals)/n
        sd = math.sqrt(sum((v-m)**2 for v in vals)/n)
        print(f"    {gene:10s} {n:>5} {m:>8.2f} {sd:>8.2f} {min(vals):>8.2f} {max(vals):>8.2f}  {desc}")
    else:
        print(f"    {gene:10s}   N/A  (sin datos)")

# ── 8. Guardar datos ──────────────────────────────────────────
os.makedirs("data/tcga_paad", exist_ok=True)
output = {
    "study_id": STUDY_ID,
    "n_samples": len(sample_ids),
    "molecular_profile": target_profile,
    "gene_expression": {g: v for g, v in gene_expr.items()},
    "gene_metadata": TME_GENES
}
with open("data/tcga_paad/tme_expression.json", "w") as f:
    json.dump(output, f, indent=2)
print(f"\n    Guardado: data/tcga_paad/tme_expression.json")
print("\n✓ Sprint 6 Step 1 completado")
