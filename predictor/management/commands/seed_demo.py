"""Idempotent local-only administrator and fictional model-backed records."""
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from ml_workflow.schema import FEATURES
from predictor.models import LoanApplication
from predictor.services import PredictionUnavailable, predict_loan

NAMES = ["Alex Morgan", "Jordan Lee", "Priya Sharma", "Daniel Brooks", "Sofia Martinez", "Noah Wilson", "Amara Okafor", "Oliver Chen", "Maya Patel", "Ethan Davis", "Isabella Rossi", "Lucas Silva", "Aisha Khan", "Liam Thompson", "Emma Laurent", "James Park", "Zara Ahmed", "Benjamin Scott", "Chloe Martin", "Arjun Mehta"]


class Command(BaseCommand):
    help = "Create the development admin and 20 fictional loan applications; safe to repeat."

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Demo seeding is disabled when DEBUG=False. Create a production admin with createsuperuser.")
        created = 0
        for index, name in enumerate(NAMES):
            email = f"demo{index + 1:02d}@example.com"
            if LoanApplication.objects.filter(email=email).exists():
                continue
            values = {
                "applicant_name": name, "email": email, "gender": "Female" if index % 2 else "Male",
                "married": "Yes" if index % 3 else "No", "dependents": ["0", "1", "2", "3+"][index % 4],
                "education": "Not Graduate" if index % 4 == 1 else "Graduate", "self_employed": "Yes" if index % 3 == 1 else "No",
                "applicant_income": 1800 + index * 360, "coapplicant_income": 1400 if index % 3 else 0,
                "loan_amount": 65000 + index * 7800, "loan_amount_term": [180, 240, 360][index % 3],
                "credit_history": 0 if index % 3 == 0 else 1, "property_area": ["Urban", "Semiurban", "Rural"][index % 3],
            }
            try:
                outcome = predict_loan({feature: values[feature] for feature in FEATURES})
            except PredictionUnavailable as error:
                raise CommandError("Train the model with python train_model.py before seeding.") from error
            application = LoanApplication(**values, prediction=outcome["prediction"], prediction_probability=outcome["probability"], model_name=outcome["model_name"])
            application.full_clean()
            application.save()
            created += 1
        user_model = get_user_model()
        if not user_model.objects.filter(username="admin").exists():
            user_model.objects.create_superuser("admin", "admin@example.com", "Admin@12345")
            self.stdout.write(self.style.SUCCESS("Demo admin created (local development only)."))
        else:
            self.stdout.write("Admin already exists; credentials and permissions were preserved.")
        self.stdout.write(self.style.SUCCESS(f"{created} sample loan applications created." if created else "Demo data already exists."))
