"""
conftest.py — raíz del proyecto.
Garantiza que el directorio raíz del proyecto esté al inicio de sys.path
antes que cualquier paquete del sistema con el mismo nombre (ej: 'config').
Necesario en Ubuntu/GitHub Actions donde dependencias transitivas pueden
sombrear módulos locales.
"""
import sys
import os

# Insertar la raíz del proyecto al inicio de sys.path
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
