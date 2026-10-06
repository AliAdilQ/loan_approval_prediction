"""Generate fictional applications with stochastic outcomes, never personal data."""
import numpy as np
import pandas as pd

from .schema import RANDOM_SEED, TARGET


def generate_dataset(records=800):
    rng = np.random.default_rng(RANDOM_SEED)
    income = np.clip(rng.lognormal(8.25, .53, records), 700, 24000).round(2)
    co_income = np.where(rng.random(records) < .52, rng.uniform(600, 5200, records), 0).round(2)
    amount = rng.uniform(18000, 320000, records).round(2)
    term = rng.choice([60, 120, 180, 240, 300, 360], records, p=[.04, .08, .16, .16, .12, .44])
    credit = rng.choice([0, 1], records, p=[.27, .73])
    education = rng.choice(["Graduate", "Not Graduate"], records, p=[.72, .28])
    employed = rng.choice(["Yes", "No"], records, p=[.24, .76])
    dependents = rng.choice(["0", "1", "2", "3+"], records, p=[.43, .26, .20, .11])
    # Synthetic labels use a noisy latent score and Bernoulli sampling.
    # These generation assumptions are not underwriting rules or inference logic.
    installment = amount * (.006 / (1 - (1.006) ** (-term)))
    burden = installment / (income + co_income)
    score = 1.4 + 4.5 * (credit - .5) - 7 * burden + .35 * (education == "Graduate") - .25 * (employed == "Yes") - .15 * (dependents == "3+")
    probability = 1 / (1 + np.exp(-score))
    frame = pd.DataFrame({
        "applicant_income": income, "coapplicant_income": co_income,
        "loan_amount": amount, "loan_amount_term": term, "credit_history": credit,
        "gender": rng.choice(["Male", "Female"], records),
        "married": rng.choice(["Yes", "No"], records, p=[.65, .35]),
        "dependents": dependents, "education": education, "self_employed": employed,
        "property_area": rng.choice(["Urban", "Semiurban", "Rural"], records),
        TARGET: np.where(rng.random(records) < probability, "Approved", "Rejected"),
    })
    # Realistic missing predictor values; targets always remain present.
    for column in ["coapplicant_income", "credit_history", "education", "self_employed"]:
        frame.loc[rng.choice(records, int(records * .025), replace=False), column] = np.nan
    return frame
