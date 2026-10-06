#!/usr/bin/env python
"""Compare classifiers by training-only CV; report one untouched test split."""
import argparse
import hashlib
import json
import platform
from pathlib import Path

import joblib
import pandas as pd
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, precision_score, recall_score, make_scorer
from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.tree import DecisionTreeClassifier

from ml_workflow.dataset import generate_dataset
from ml_workflow.schema import CATEGORICAL_FEATURES, FEATURES, NUMERIC_FEATURES, RANDOM_SEED, TARGET

BASE_DIR = Path(__file__).resolve().parent


def build_pipeline(classifier):
    preprocessing = ColumnTransformer([
        ("numeric", Pipeline([("imputer", SimpleImputer(strategy="median")), ("scale", StandardScaler())]), NUMERIC_FEATURES),
        ("categorical", Pipeline([("imputer", SimpleImputer(strategy="most_frequent")), ("encode", OneHotEncoder(handle_unknown="ignore"))]), CATEGORICAL_FEATURES),
    ])
    return Pipeline([("preprocessing", preprocessing), ("classifier", classifier)])


def train(regenerate=False):
    dataset_path = BASE_DIR / "data" / "loan_data.csv"
    dataset_path.parent.mkdir(exist_ok=True)
    if regenerate or not dataset_path.exists():
        generate_dataset().to_csv(dataset_path, index=False)
    frame = pd.read_csv(dataset_path, dtype={column: str for column in CATEGORICAL_FEATURES})
    if not set(FEATURES + [TARGET]).issubset(frame.columns):
        raise ValueError("Dataset is missing required feature/target columns.")
    frame = frame.dropna(subset=[TARGET]).drop_duplicates().reset_index(drop=True)
    if not set(frame[TARGET]).issubset({"Approved", "Rejected"}) or frame[TARGET].nunique() != 2:
        raise ValueError("Loan_Status must contain Approved and Rejected labels.")
    for column in NUMERIC_FEATURES:
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    x_train, x_test, y_train, y_test = train_test_split(frame[FEATURES], frame[TARGET], test_size=.2, random_state=RANDOM_SEED, stratify=frame[TARGET])
    classifiers = {
        "Logistic Regression": LogisticRegression(max_iter=2000, random_state=RANDOM_SEED),
        "Random Forest": RandomForestClassifier(n_estimators=240, max_depth=7, min_samples_leaf=5, random_state=RANDOM_SEED, n_jobs=1),
        "Decision Tree": DecisionTreeClassifier(max_depth=5, min_samples_leaf=12, random_state=RANDOM_SEED),
    }
    cross_validation = StratifiedKFold(n_splits=5, shuffle=True, random_state=RANDOM_SEED)
    scorer = make_scorer(f1_score, pos_label="Approved")
    comparison = {}
    for name, classifier in classifiers.items():
        scores = cross_val_score(build_pipeline(classifier), x_train, y_train, cv=cross_validation, scoring=scorer, n_jobs=1)
        comparison[name] = {"cv_f1_mean": float(scores.mean()), "cv_f1_std": float(scores.std())}
        print(f"{name}: CV F1 = {scores.mean():.4f} (+/- {scores.std():.4f})")
    selected_name = max(comparison, key=lambda name: comparison[name]["cv_f1_mean"])
    pipeline = build_pipeline(classifiers[selected_name]).fit(x_train, y_train)
    predicted = pipeline.predict(x_test)
    metrics = {
        "accuracy": float(accuracy_score(y_test, predicted)),
        "precision": float(precision_score(y_test, predicted, pos_label="Approved", zero_division=0)),
        "recall": float(recall_score(y_test, predicted, pos_label="Approved", zero_division=0)),
        "f1": float(f1_score(y_test, predicted, pos_label="Approved", zero_division=0)),
        "confusion_matrix": confusion_matrix(y_test, predicted, labels=["Rejected", "Approved"]).tolist(),
    }
    metadata = {
        "schema_version": 1, "model_name": selected_name, "random_seed": RANDOM_SEED,
        "dataset_records": len(frame), "training_records": len(x_train), "test_records": len(x_test),
        "dataset_sha256": hashlib.sha256(dataset_path.read_bytes()).hexdigest(),
        "features": FEATURES, "metrics": metrics, "comparison": comparison,
        "confusion_matrix_labels": ["Rejected", "Approved"],
        "versions": {"python": platform.python_version(), "scikit_learn": sklearn.__version__, "pandas": pd.__version__, "joblib": joblib.__version__},
    }
    model_directory = BASE_DIR / "ml_models"
    model_directory.mkdir(exist_ok=True)
    joblib.dump({"pipeline": pipeline, "metadata": metadata}, model_directory / "loan_model.joblib", compress=3)
    (model_directory / "metrics.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print(f"\nSelected model: {selected_name}")
    for key in ["accuracy", "precision", "recall", "f1"]:
        print(f"{key.title()}: {metrics[key]:.4f}")
    print(f"Confusion matrix (rows=actual, columns=predicted; Rejected, Approved):\n{metrics['confusion_matrix']}")
    print("Saved fitted preprocessing + classifier together in ml_models/loan_model.joblib")
    return metadata


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--regenerate", action="store_true", help="Replace CSV with the deterministic 800-record sample dataset.")
    train(parser.parse_args().regenerate)
