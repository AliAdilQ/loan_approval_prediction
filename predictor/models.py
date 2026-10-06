"""Stored applications and immutable prediction snapshots."""
import uuid
from decimal import Decimal

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

YES_NO = [("Yes", "Yes"), ("No", "No")]
TERMS = [(months, f"{months} months ({months // 12} years)") for months in [60, 120, 180, 240, 300, 360]]


class LoanApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    applicant_name = models.CharField(max_length=100)
    email = models.EmailField()
    gender = models.CharField(max_length=6, choices=[("Male", "Male"), ("Female", "Female")])
    married = models.CharField(max_length=3, choices=YES_NO)
    dependents = models.CharField(max_length=2, choices=[(value, value) for value in ["0", "1", "2", "3+"]])
    education = models.CharField(max_length=12, choices=[("Graduate", "Graduate"), ("Not Graduate", "Not Graduate")])
    self_employed = models.CharField(max_length=3, choices=YES_NO)
    applicant_income = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("100")), MaxValueValidator(Decimal("100000"))])
    coapplicant_income = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0), MaxValueValidator(Decimal("100000"))])
    loan_amount = models.DecimalField(max_digits=11, decimal_places=2, validators=[MinValueValidator(Decimal("1000")), MaxValueValidator(Decimal("1000000"))])
    loan_amount_term = models.PositiveSmallIntegerField(choices=TERMS)
    credit_history = models.PositiveSmallIntegerField(choices=[(1, "Good"), (0, "Poor")])
    property_area = models.CharField(max_length=9, choices=[(value, value) for value in ["Urban", "Semiurban", "Rural"]])
    prediction = models.CharField(max_length=8, choices=[("Approved", "Approved"), ("Rejected", "Rejected")])
    prediction_probability = models.FloatField(validators=[MinValueValidator(0), MaxValueValidator(1)])
    model_name = models.CharField(max_length=50)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["prediction", "created_at"], name="prediction_date_idx")]

    def __str__(self):
        return f"{self.applicant_name} — {self.prediction}"

    @property
    def confidence_percent(self):
        return round(self.prediction_probability * 100, 1)
