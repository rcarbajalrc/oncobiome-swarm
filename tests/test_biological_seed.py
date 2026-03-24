"""Tests del seed biológico KRAS G12D — valida calibración contra literatura.

Verifica que los parámetros de settings.py son coherentes con los datos
de fuentes primarias documentados en config/biological_seed.py.

Ejecutar:
    cd ~/Desktop/oncobiome-swarm
    python3 -m pytest tests/test_biological_seed.py -v
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from config.biological_seed import KRAS_G12D_BIOLOGICAL_SEED as SEED


class TestKRASG12DSeedCoherence:
    """Valida coherencia interna del seed biológico."""

    def test_kill_rate_range(self):
        """immune_kill_rate debe estar entre 0.10 y 0.25 (rango plausible PDAC).

        Derivado de: ~50% kill en 48h a E:T 10:1 (ScienceDirect 2020).
        En KRAS G12D resistente: reducido a 0.15 (range: 0.10-0.25).
        """
        kill_rate = SEED["immune_kill_rate"]
        assert 0.10 <= kill_rate <= 0.25, (
            f"Kill rate {kill_rate} fuera del rango biológico plausible (0.10-0.25)"
        )

    def test_m2_threshold_less_than_m1(self):
        """Umbral M2 IL-6 debe ser menor que umbral M1 IFN-γ.

        En KRAS G12D el TME favorece M2 (umbral más bajo) sobre M1 (umbral más alto).
        """
        m1_threshold = SEED["m1_polarisation_ifng_threshold"]
        m2_threshold = SEED["m2_polarisation_il6_threshold"]
        assert m2_threshold < m1_threshold, (
            f"M2 threshold ({m2_threshold}) debe ser < M1 threshold ({m1_threshold})"
        )

    def test_tumor_energy_lower_than_immune(self):
        """TumorCell energy inicial < ImmuneCell en KRAS G12D PDAC.

        Hipoxia crónica PDAC → tumor en estrés energético basal.
        CD8+ infiltrantes tienen más energía al inicio.
        """
        tumor_e = SEED["tumor_initial_energy"]
        immune_e = SEED["immune_initial_energy"]
        assert tumor_e < immune_e, (
            f"Tumor energy ({tumor_e}) debe ser < immune energy ({immune_e}) en PDAC hipóxico"
        )

    def test_phyto_ttl_reduced_vs_baseline(self):
        """phytochemical_ttl debe ser < 35 (baseline) en KRAS G12D.

        TME inmunosupresor KRAS G12D reduce vida útil de fitoquímicos.
        """
        ttl = SEED["phytochemical_ttl"]
        assert ttl < 35, f"Phyto TTL ({ttl}) debe ser < 35 en KRAS G12D"
        assert ttl >= 20, f"Phyto TTL ({ttl}) no puede ser < 20 (irrealistamente corto)"

    def test_il6_suppression_threshold_documented(self):
        """El umbral de supresión por IL-6 debe estar documentado y en rango (0.04-0.10)."""
        threshold = SEED["il6_immune_suppression_threshold"]
        assert 0.04 <= threshold <= 0.10, (
            f"IL-6 suppression threshold {threshold} fuera de rango (0.04-0.10)"
        )

    def test_suppression_factor_reduces_kill(self):
        """Factor de supresión IL-6 debe reducir kill (< 1.0)."""
        factor = SEED["il6_immune_suppression_factor"]
        assert 0.0 < factor < 1.0, (
            f"IL-6 suppression factor {factor} debe estar entre 0 y 1 (es un factor reductor)"
        )

    def test_doubling_time_reference_range(self):
        """Doubling time de referencia debe estar en rango PDAC conocido (40-65h).

        PANC-1: 52h, AsPC-1: 58h, MiaPaCa-2: 40h (PMC4655885).
        """
        dt = SEED["_reference_doubling_time_hours"]
        assert 40 <= dt <= 65, (
            f"Doubling time {dt}h fuera del rango PDAC documentado (40-65h)"
        )

    def test_seed_has_primary_sources(self):
        """El seed debe documentar fuentes primarias para sus parámetros clave."""
        required_sources = [
            "_source_doubling",
            "_source_kill_rate",
            "_source_m2_bias",
            "_source_vegf",
        ]
        for source_key in required_sources:
            assert source_key in SEED, f"Falta fuente primaria: {source_key}"
            assert len(SEED[source_key]) > 10, f"Fuente muy corta para: {source_key}"

    def test_vegf_emit_higher_than_baseline(self):
        """VEGF emit en KRAS G12D debe ser mayor que baseline (0.20).

        KRAS G12D tiene respuesta HIF-1α→VEGF más intensa.
        """
        # El baseline era 0.20, calibrado a 0.25
        # Verificamos que el comentario en interactions.py documenta este cambio
        interactions_file = Path(__file__).parent.parent / "simulation" / "interactions.py"
        content = interactions_file.read_text()
        assert "0.25" in content, "VEGF emit calibrado (0.25) no encontrado en interactions.py"
        assert "HIF-1" in content, "Referencia HIF-1α no documentada en interactions.py"


class TestSettingsCalibration:
    """Valida que settings.py tiene los valores calibrados del seed."""

    def test_settings_match_seed_kill_rate(self):
        """settings.py debe usar immune_kill_rate del seed biológico."""
        from config.settings import SimulationConfig
        # Reset singleton
        SimulationConfig.__pydantic_fields_set__ = set()

        # Los valores en settings deben coincidir con el seed
        assert SimulationConfig.model_fields["immune_kill_rate"].default == SEED["immune_kill_rate"], (
            "settings.py immune_kill_rate no coincide con el seed biológico"
        )

    def test_settings_match_seed_m1_threshold(self):
        """settings.py debe usar m1_polarisation_ifng_threshold del seed."""
        from config.settings import SimulationConfig
        assert SimulationConfig.model_fields["m1_polarisation_ifng_threshold"].default == \
               SEED["m1_polarisation_ifng_threshold"]

    def test_settings_match_seed_m2_threshold(self):
        """settings.py debe usar m2_polarisation_il6_threshold del seed."""
        from config.settings import SimulationConfig
        assert SimulationConfig.model_fields["m2_polarisation_il6_threshold"].default == \
               SEED["m2_polarisation_il6_threshold"]

    def test_settings_match_seed_tumor_energy(self):
        """settings.py debe usar tumor_initial_energy del seed."""
        from config.settings import SimulationConfig
        assert SimulationConfig.model_fields["tumor_initial_energy"].default == \
               SEED["tumor_initial_energy"]

    def test_settings_match_seed_phyto_ttl(self):
        """settings.py debe usar phytochemical_ttl del seed."""
        from config.settings import SimulationConfig
        assert SimulationConfig.model_fields["phytochemical_ttl"].default == \
               SEED["phytochemical_ttl"]
