"""Load a trusted local pipeline and run actual classifier inference."""
import logging
from functools import lru_cache

import joblib
import numpy as np
import pandas as pd
from django.conf import settings

from ml_workflow.schema import FEATURES

logger = logging.getLogger(__name__)


class PredictionUnavailable(Exception):
    """Recoverable model failure that can be safely shown to visitors."""


@lru_cache(maxsize=2)
def _load_artifact(path, modified_ns):
    # joblib/pickle can execute code: load only the repository's trusted artifact.
    artifact = joblib.load(path)
    if artifact["metadata"]["schema_version"] != 1 or artifact["metadata"]["features"] != FEATURES:
        raise ValueError("Incompatible model feature schema.")
    return artifact


def predict_loan(values):
    """Return predicted class, its probability, and model provenance."""
    try:
        path = settings.MODEL_PATH
        artifact = _load_artifact(str(path), path.stat().st_mtime_ns)
        frame = pd.DataFrame([{feature: values[feature] for feature in FEATURES}], columns=FEATURES)
        pipeline = artifact["pipeline"]
        probabilities = pipeline.predict_proba(frame)[0]
        label = str(pipeline.predict(frame)[0])
        index = list(pipeline.classes_).index(label)
        confidence = float(probabilities[index])
        if label not in {"Approved", "Rejected"} or not np.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Invalid classifier output.")
        return {"prediction": label, "probability": confidence, "model_name": artifact["metadata"]["model_name"]}
    except Exception as error:
        logger.exception("Loan inference failed")
        raise PredictionUnavailable("Predictions are temporarily unavailable. Please try again later or contact the administrator.") from error
