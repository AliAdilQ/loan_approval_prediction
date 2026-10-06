"""Shared training/inference feature contract. Currency values are USD."""
NUMERIC_FEATURES = ["applicant_income", "coapplicant_income", "loan_amount", "loan_amount_term", "credit_history"]
CATEGORICAL_FEATURES = ["gender", "married", "dependents", "education", "self_employed", "property_area"]
FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES
TARGET = "Loan_Status"
RANDOM_SEED = 42
