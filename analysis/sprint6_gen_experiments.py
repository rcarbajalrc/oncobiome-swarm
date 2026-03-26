"""
OncoBiome Sprint 6 — Integrador zAvatar → experiments.yaml
Genera configuración de experimentos para cada perfil TCGA-PAAD
"""

import json
import yaml_simple as yaml

# Cargar avatares
with open("data/avatars/zavatar_profiles.json") as f:
    avatars = json.load(f)

# Generar bloques de experimento para cada avatar
experiments_sprint6 = {}

avatar_map = {
    "TCGA_PAAD_MEDIAN":   "zavatar_median_llm",
    "COLD_TUMOR_PROFILE": "zavatar_cold_llm",
    "HOT_TUMOR_PROFILE":  "zavatar_hot_llm",
}

for avatar_id, exp_name in avatar_map.items():
    avatar = avatars[avatar_id]
    p = avatar["params"]
    experiments_sprint6[exp_name] = {
        "description": f"Sprint 6 zAvatar — {avatar_id} (TCGA-PAAD personalizado)",
        "cycles": 52,
        "use_llm": True,
        "memory_mode": "in_memory",
        "env": {
            "IMMUNE_KILL_RATE":              str(p["immune_kill_rate"]),
            "NK_KILL_RATE":                  str(p["nk_kill_rate"]),
            "NK_IL6_SUPPRESSION_THRESHOLD":  str(p["nk_il6_suppression_threshold"]),
            "DC_MATURATION_IFNG_THRESHOLD":  str(p["dc_maturation_ifng_threshold"]),
            "M2_POLARISATION_IL6_THRESHOLD": str(p["m2_polarisation_il6_threshold"]),
            "CYTOKINE_DECAY":                str(p["cytokine_decay"]),
            "TUMOR_INITIAL_ENERGY":          str(p["tumor_initial_energy"]),
            "IMMUNE_EXHAUSTION_AGE":         str(p["immune_exhaustion_age"]),
            "DC_MATURATION_CYCLES":          str(p["dc_maturation_cycles"]),
            "CAP_AGENTS":                    "80",
        }
    }

print("Experimentos Sprint 6 generados:")
for name, exp in experiments_sprint6.items():
    print(f"\n  [{name}]")
    for k, v in exp["env"].items():
        print(f"    {k}: {v}")
