"""Validated input contract and reusable form sections."""
from django import forms

from .models import LoanApplication

FORM_SECTIONS = [
    ("01", "Applicant details", "A little about the person applying.", ["applicant_name", "email", "gender", "married", "dependents", "education", "self_employed", "property_area"]),
    ("02", "Financial profile", "Use monthly income and loan amounts in US dollars.", ["applicant_income", "coapplicant_income", "loan_amount", "loan_amount_term", "credit_history"]),
]


class LoanPredictionForm(forms.ModelForm):
    class Meta:
        model = LoanApplication
        fields = [name for _, _, _, names in FORM_SECTIONS for name in names]
        labels = {"married": "Marital status", "self_employed": "Self-employed", "applicant_income": "Monthly applicant income ($)", "coapplicant_income": "Monthly co-applicant income ($)", "loan_amount": "Loan amount ($)", "loan_amount_term": "Loan term", "credit_history": "Credit history"}
        help_texts = {"applicant_income": "$100–$100,000 per month", "coapplicant_income": "Enter 0 if applying alone.", "loan_amount": "$1,000–$1,000,000", "credit_history": "Good: previous obligations met. Poor: adverse history."}
        widgets = {"applicant_name": forms.TextInput(attrs={"placeholder": "e.g. Alex Morgan", "autocomplete": "name"}), "email": forms.EmailInput(attrs={"placeholder": "alex@example.com", "autocomplete": "email"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs["class"] = "form-select" if isinstance(field.widget, forms.Select) else "form-control"
            field.widget.attrs["aria-describedby"] = f"{name}_help {name}_errors"
            if isinstance(field, forms.DecimalField):
                field.widget.attrs.update({"step": "0.01", "inputmode": "decimal"})
            if self.is_bound and name in self.errors:
                field.widget.attrs.update({"aria-invalid": "true", "class": field.widget.attrs["class"] + " is-invalid"})

    def clean_applicant_name(self):
        name = " ".join(self.cleaned_data["applicant_name"].split())
        if len(name) < 2:
            raise forms.ValidationError("Please enter a name with at least two characters.")
        return name

    @property
    def sections(self):
        return [{"number": number, "title": title, "description": description, "fields": [self[name] for name in names]} for number, title, description, names in FORM_SECTIONS]
