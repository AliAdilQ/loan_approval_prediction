# Model artifact

`loan_model.joblib` holds a dictionary containing the complete fitted scikit-learn pipeline and its metadata. Its `preprocessing` step includes numeric median imputation and standardization, categorical most-frequent imputation, and one-hot encoding. The classifier and its preprocessing are serialized together to prevent mismatched artifacts.

`metrics.json` records the selected model, actual test metrics, confusion matrix, training-only cross-validation comparison, feature order, random seed, dataset checksum, and library versions. Its confusion matrix uses `[Rejected, Approved]` for rows (actual) and columns (predicted); precision, recall, and F1 use Approved as the positive class.

The shipped model remains fitted on the 640-record training split, so its reported test metrics correspond to the exact serialized classifier. Retraining uses `python train_model.py`. Restart the development server after retraining; changes in file modification time also invalidate the inference cache.

Load joblib artifacts only from trusted sources: serialized Python objects can execute code. Use the pinned requirements to avoid scikit-learn version mismatches. The binary is small enough to commit to this portfolio repository; the SQLite database is deliberately excluded and recreated with migrations and `seed_demo`.
