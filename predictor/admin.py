from django import forms
from django.contrib import admin
from ml_workflow.schema import FEATURES
from .models import LoanApplication
from .services import PredictionUnavailable, predict_loan

admin.site.site_header = "Loan Approval Prediction Administration"
admin.site.site_title = "LoanPredict AI Admin"
admin.site.index_title = "Loan Prediction Management"


class AdminPredictionForm(forms.ModelForm):
    """Validate inference before any staff edits are persisted."""

    class Meta:
        model = LoanApplication
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        if all(feature in cleaned for feature in FEATURES):
            try:
                self.prediction_output = predict_loan(cleaned)
            except PredictionUnavailable as error:
                raise forms.ValidationError(str(error)) from error
        return cleaned


@admin.register(LoanApplication)
class LoanApplicationAdmin(admin.ModelAdmin):
    form = AdminPredictionForm
    list_display = ["applicant_name", "email", "applicant_income", "loan_amount", "prediction", "confidence", "property_area", "created_at"]
    search_fields = ["applicant_name", "email"]
    list_filter = ["prediction", "property_area", "created_at", "education", "self_employed"]
    ordering = ["-created_at"]
    readonly_fields = ["id", "prediction", "prediction_probability", "model_name", "created_at", "updated_at"]
    list_per_page = 20
    date_hierarchy = "created_at"
    fieldsets = [
        ("Applicant", {"fields": ("applicant_name", "email", "gender", "married", "dependents", "education", "self_employed", "property_area")}),
        ("Financial profile", {"fields": ("applicant_income", "coapplicant_income", "loan_amount", "loan_amount_term", "credit_history")}),
        ("Prediction snapshot", {"fields": ("prediction", "prediction_probability", "model_name", "id", "created_at", "updated_at")}),
    ]

    @admin.display(description="Confidence", ordering="prediction_probability")
    def confidence(self, obj):
        return f"{obj.confidence_percent:.1f}%"

    def save_model(self, request, obj, form, change):
        # Recompute predictions when staff changes the underlying financial profile.
        outcome = form.prediction_output
        obj.prediction = outcome["prediction"]
        obj.prediction_probability = outcome["probability"]
        obj.model_name = outcome["model_name"]
        super().save_model(request, obj, form, change)
