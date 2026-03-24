"""Seed biológico calibrado para KRAS G12D PDAC/CRC.

FUENTES PRIMARIAS (verificadas marzo 2026):
─────────────────────────────────────────────────────────────────────────────
TUMOR CELL KINETICS (PANC-1/AsPC-1 KRAS G12D):
  - PANC-1 doubling time: 52h (Wikipedia/ATCC; PMC4655885)
  - AsPC-1 doubling time: 58h (PMC4655885)
  - MiaPaCa-2 doubling time: 40h (PMC4655885)
  - Usamos 52h (PANC-1) como referencia KRAS G12D moderado
  - 1 ciclo de simulación = 52h = 2.17 días biológicos (PANC-1 doubling time)
  - Proliferación energética por ciclo: consume 0.30 energía (validado en runs)

PROLIFERACIÓN BLOQUEADA POR IL-6 VÍA KRAS:
  - KRAS G12D activa IL-6/JAK-STAT3 que suprime CD8+ citotoxicidad (Frontiers/Medicine 2024)
  - Kill probability reducida 40% cuando IL-6 local > 0.06 (ya implementado)
  - Umbral de IL-6 para VEGF: reducido de 0.05 a 0.04 (mayor sensibilidad KRAS G12D)

CD8+ T CELL CYTOTOXICITY:
  - ~50% kill en 48h co-cultura (ScienceDirect 2020, E:T ratio 10:1)
  - En solid tumors KRAS G12D: frecuente fallo en conjugación 1:1 (Nature Comm 2021)
  - Additive cytotoxicity: 3 serial hits con <50min intervalo para muerte efectiva
  - Kill rate por ciclo calibrado: 0.15 (reducido de 0.20 — KRAS G12D más resistente)
  - IL-6 immunosuppression: reduce kill_prob en 40% cuando IL-6 > 0.06

MACROPHAGE POLARIZATION:
  - KRAS G12D induce infiltración temprana de TAMs hacia M2 (Frontiers/Medicine 2024)
  - M1 threshold IFN-γ: aumentado de 0.15 a 0.18 (más difícil polarizar M1 en KRAS G12D)
  - M2 threshold IL-6: reducido de 0.08 a 0.06 (más fácil polarizar M2 — sesgo pro-tumoral)

HIPOXIA Y VEGF:
  - HIF-1α → VEGF en hipoxia es mecanismo canónico en KRAS G12D (verificado)
  - Umbral hipoxia: energy < 0.30 (sin cambio — bien calibrado)
  - VEGF emit: 0.25 (aumentado de 0.20 — KRAS G12D tiene mayor señal angiogénica)

FITOQUÍMICOS:
  - TTL reducido de 35 a 28 ciclos (vida media más corta en TME inmunosupresor KRAS G12D)
  - Phyto damage rate: 0.06 (reducido de 0.08 — menor eficacia en KRAS G12D resistente)

ENERGÉTICA:
  - tumor_initial_energy: 0.75 (reducido de 0.80 — KRAS G12D en hipoxia crónica)
  - immune_initial_energy: 0.85 (reducido de 0.90 — CD8+ agotados por TME inmunosupresor)
  - macrophage_initial_energy: 0.80 (reducido de 0.85 — TME pro-M2)
─────────────────────────────────────────────────────────────────────────────
"""

# Constantes biológicas derivadas de literatura
# Usado por config/settings.py y como referencia para tests

KRAS_G12D_BIOLOGICAL_SEED = {
    # ── Cinética tumoral ──────────────────────────────────────────────────
    # PANC-1 doubling time 52h
    # 1 ciclo simulación = 52h = 2.17 días biológicos
    # → un tumor que dobla en 52h necesita 1 ciclo de duplicación
    "tumor_doubling_cycles": 1,             # 1 ciclo = 1 doubling time (52h)
    "tumor_doubling_time_hours": 52,        # PANC-1 (ATCC CRL-1469; PMC4655885)
    "cycle_biological_days": 2.167,         # 52h / 24h = 2.167 días/ciclo
    "tumor_initial_energy": 0.75,           # hipoxia crónica KRAS G12D
    "proliferation_energy_cost": 0.30,      # validado en runs anteriores

    # ── Inmunidad CD8+ ────────────────────────────────────────────────────
    # ~50% kill en 48h → per-cycle probability calibrado:
    # 48h ≈ 0.92 ciclos → kill_prob ≈ 0.50 / ciclo en condiciones ideales
    # KRAS G12D más resistente: reducimos a 0.15 (resistencia inmune documentada)
    "immune_kill_rate": 0.15,               # reducido de 0.20 (KRAS G12D resistencia)
    "immune_initial_energy": 0.85,          # agotamiento precoz por TME inmunosupresor
    "immune_exhaustion_age": 15,            # ciclos antes del agotamiento funcional
    "immune_exhaustion_kills": 2,           # muertes antes del agotamiento

    # ── Macrófagos ────────────────────────────────────────────────────────
    # KRAS G12D induce sesgo M2 temprano (Frontiers/Medicine 2024)
    "macrophage_m1_kill_rate": 0.08,        # reducido de 0.10
    "macrophage_initial_energy": 0.80,      # reducido de 0.85
    "m1_polarisation_ifng_threshold": 0.18, # más difícil M1 en TME KRAS G12D
    "m2_polarisation_il6_threshold": 0.06,  # más fácil M2 (umbral reducido)

    # ── Citoquinas ────────────────────────────────────────────────────────
    # IL-6 clave en KRAS G12D → JAK-STAT3 → inmuno-supresión
    "cytokine_decay": 0.04,                 # decaimiento más lento (TME denso PDAC)
    "cytokine_diffusion_sigma": 1.8,        # difusión más amplia
    "cytokine_emit_amount": 0.30,           # sin cambio

    # ── Angiogénesis VEGF ────────────────────────────────────────────────
    # KRAS G12D tiene mayor señal HIF-1α → VEGF
    "hypoxia_threshold": 0.30,              # energy < 0.30 → VEGF
    "vegf_emit_amount": 0.25,               # aumentado de 0.20

    # ── Fitoquímicos ─────────────────────────────────────────────────────
    "phytochemical_ttl": 28,                # reducido de 35 (menor eficacia en KRAS G12D)
    "phyto_damage_rate": 0.06,              # reducido de 0.08

    # ── IL-6 immunosuppression (implementado en interactions.py) ─────────
    "il6_immune_suppression_threshold": 0.06,  # IL-6 > 0.06 → kill_prob * 0.60
    "il6_immune_suppression_factor": 0.60,

    # ── Referencia celular (PANC-1 KRAS G12D) ────────────────────────────
    "_reference_cell_line": "PANC-1",
    "_reference_mutation": "KRAS_G12D",
    "_reference_doubling_time_hours": 52,
    "_source_doubling": "ATCC CRL-1469; PMC4655885 (Gómez-Lechón et al. 2015)",
    "_source_kill_rate": "ScienceDirect 2020 (50% kill/48h E:T 10:1); Nature Comm 2021",
    "_source_m2_bias": "Frontiers/Medicine 2024 (KRAS G12D early TAM M2 infiltration)",
    "_source_vegf": "Canonical HIF-1alpha→VEGF in hypoxic KRAS G12D tumors",
}
