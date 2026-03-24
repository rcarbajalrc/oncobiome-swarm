from enum import Enum


class CytokineType(str, Enum):
    IL6 = "IL-6"
    VEGF = "VEGF"
    IFNG = "IFN-γ"
