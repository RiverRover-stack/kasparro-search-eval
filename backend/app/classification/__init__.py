import time  # noqa: F401  (tests monkeypatch backend.app.classification.time.sleep)
import urllib.request  # noqa: F401  (tests monkeypatch backend.app.classification.urllib.request.urlopen)

from .adapters import (
    ClassificationOutcome,
    Classifier,
    ControlledStubClassifier,
    ModelAttempt,
    ReplayClassifier,
)
from .contract import (
    CLASSIFICATION_CONTRACT_VERSION,
    ClassificationResult,
    EvidenceKind,
    SupportingExcerpt,
    normalize_inactive_evidence,
    visibility_score,
)
from .groq import GroqClassifier
from .ollama import OllamaClassifier
from .prompt import (
    PROMPT_VERSION,
    SYSTEM_INSTRUCTION,
    candidate_excerpts,
    strict_classification_schema,
)

__all__ = [
    "CLASSIFICATION_CONTRACT_VERSION",
    "PROMPT_VERSION",
    "SYSTEM_INSTRUCTION",
    "ClassificationOutcome",
    "ClassificationResult",
    "Classifier",
    "ControlledStubClassifier",
    "EvidenceKind",
    "GroqClassifier",
    "ModelAttempt",
    "OllamaClassifier",
    "ReplayClassifier",
    "SupportingExcerpt",
    "candidate_excerpts",
    "normalize_inactive_evidence",
    "strict_classification_schema",
    "time",
    "urllib",
    "visibility_score",
]
