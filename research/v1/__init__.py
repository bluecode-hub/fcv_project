"""TASC-v1 (Phase 4): training-free, evidence-gated, illumination-aware enhancement.
Independent of the frozen ``tasc/`` package (TASC-v0), which is only imported for shared read-only helpers."""
from .config import V1Config, CANDIDATES  # noqa: F401
from .method import TASCv1  # noqa: F401
