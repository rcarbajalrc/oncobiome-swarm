"""Gestión y difusión de campos de citoquinas.

La difusión se implementa con FFT puro numpy como alternativa a
scipy.ndimage.gaussian_filter, que es incompatible con numpy>=2.0.
Matemáticamente equivalente a un filtro gaussiano con condiciones
de contorno periódicas.
"""
from __future__ import annotations

import numpy as np

from models.cytokine_state import CytokineType


def _build_gaussian_kernel_fft(shape: tuple[int, int], sigma: float) -> np.ndarray:
    """Construye el kernel gaussiano en dominio de frecuencias."""
    rows, cols = shape
    kr = np.fft.fftfreq(rows)
    kc = np.fft.fftfreq(cols)
    kc_grid, kr_grid = np.meshgrid(kc, kr)
    kernel = np.exp(-2 * (np.pi ** 2) * (sigma ** 2) * (kr_grid ** 2 + kc_grid ** 2))
    return kernel


class CytokineFieldManager:
    """Mantiene los arrays 2D de concentración de citoquinas y aplica
    difusión + decay en cada paso de simulación.
    """

    def __init__(
        self,
        grid_size: int,
        decay: float = 0.05,
        sigma: float = 1.5,
    ) -> None:
        self.grid_size = grid_size
        self.decay = decay
        shape = (grid_size, grid_size)

        self.fields: dict[str, np.ndarray] = {
            ct.value: np.zeros(shape, dtype=np.float32)
            for ct in CytokineType
        }
        self._kernel_fft = _build_gaussian_kernel_fft(shape, sigma)

    def emit(self, cytokine: str, pos: tuple[float, float], amount: float) -> None:
        """Añade `amount` de citoquina en la posición del grid más cercana."""
        r, c = self._pos_to_rc(pos)
        self.fields[cytokine][r, c] += amount

    def sample(self, cytokine: str, pos: tuple[float, float]) -> float:
        """Retorna la concentración de la citoquina en la posición indicada."""
        r, c = self._pos_to_rc(pos)
        return float(self.fields[cytokine][r, c])

    def step(self) -> None:
        """Aplica un paso de difusión gaussiana + decay a todos los campos."""
        for key in self.fields:
            field = self.fields[key]
            # Difusión via FFT (equivalente a gaussian_filter con contorno periódico)
            fft_field = np.fft.fft2(field)
            diffused = np.real(np.fft.ifft2(fft_field * self._kernel_fft)).astype(np.float32)
            # Decay exponencial + clip para evitar valores negativos
            self.fields[key] = np.clip(diffused * (1.0 - self.decay), 0.0, None)

    def summary(self) -> dict[str, dict[str, float]]:
        """Estadísticas agregadas de cada campo, para el snapshot de Opus."""
        result = {}
        for key, field in self.fields.items():
            result[key] = {
                "mean": float(field.mean()),
                "max": float(field.max()),
                "total": float(field.sum()),
            }
        return result

    def _pos_to_rc(self, pos: tuple[float, float]) -> tuple[int, int]:
        r = int(np.clip(pos[1], 0, self.grid_size - 1))
        c = int(np.clip(pos[0], 0, self.grid_size - 1))
        return r, c
