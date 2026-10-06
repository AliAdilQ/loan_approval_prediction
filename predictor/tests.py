"""Integration tests use the real shipped model; failures are tested separately."""
import io
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .forms import LoanPredictionForm
from .models import LoanApplication
from .services import PredictionUnavailable, predict_loan

VALID_DATA = {
    "applicant_name": "Alex Morgan", "email": "alex@example.com", "gender": "Female",
    "married": "Yes", "dependents": "0", "education": "Graduate", "self_employed": "No",
    "applicant_income": "6500", "coapplicant_income": "1800", "loan_amount": "120000",
    "loan_amount_term": "360", "credit_history": "1", "property_area": "Urban",
}


class PageTests(TestCase):
    def test_home_loads_with_empty_statistics(self):
        response = self.client.get(reverse("predictor:home"))
        self.assertContains(response, "Loan Approval")
        self.assertEqual(response.context["stats"]["total"], 0)

    def test_prediction_form_loads(self):
        response = self.client.get(reverse("predictor:predict"))
        self.assertContains(response, "csrfmiddlewaretoken")
        self.assertContains(response, "Monthly applicant income")

    def test_about_loads_actual_report(self):
        self.assertContains(self.client.get(reverse("predictor:about")), "held-out synthetic applications")

    def test_dashboard_requires_staff(self):
        self.assertRedirects(self.client.get(reverse("predictor:dashboard")), "/admin/login/?next=/dashboard/")

    def test_invalid_uuid_is_not_found(self):
        self.assertEqual(self.client.get("/result/not-a-uuid/").status_code, 404)


class FormTests(TestCase):
    def test_valid_form(self):
        form = LoanPredictionForm(VALID_DATA)
        self.assertTrue(form.is_valid(), form.errors)

    def test_numeric_limits_and_nonfinite_values(self):
        for field, value in [("applicant_income", "-2"), ("loan_amount", "0"), ("coapplicant_income", "NaN"), ("applicant_income", "Infinity"), ("loan_amount", "1000001"), ("loan_amount", "abc")]:
            with self.subTest(field=field, value=value):
                form = LoanPredictionForm({**VALID_DATA, field: value})
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)

    def test_invalid_email_and_category(self):
        form = LoanPredictionForm({**VALID_DATA, "email": "bad", "property_area": "Moon", "loan_amount_term": "999"})
        self.assertFalse(form.is_valid())
        for field in ["email", "property_area", "loan_amount_term"]:
            self.assertIn(field, form.errors)

    def test_name_is_normalized(self):
        form = LoanPredictionForm({**VALID_DATA, "applicant_name": "  Alex   Morgan  "})
        self.assertTrue(form.is_valid())
        self.assertEqual(form.cleaned_data["applicant_name"], "Alex Morgan")


class PredictionTests(TestCase):
    def test_model_output_structure(self):
        form = LoanPredictionForm(VALID_DATA)
        self.assertTrue(form.is_valid())
        outcome = predict_loan(form.cleaned_data)
        self.assertEqual(set(outcome), {"prediction", "probability", "model_name"})
        self.assertIn(outcome["prediction"], ["Approved", "Rejected"])
        self.assertGreaterEqual(outcome["probability"], .5)
        self.assertLessEqual(outcome["probability"], 1)

    def test_model_responds_to_different_profiles(self):
        approved = predict_loan(VALID_DATA)
        rejected = predict_loan({**VALID_DATA, "credit_history": 0, "applicant_income": 1000, "coapplicant_income": 0, "loan_amount": 300000, "loan_amount_term": 60})
        self.assertEqual(approved["prediction"], "Approved")
        self.assertEqual(rejected["prediction"], "Rejected")

    def test_valid_post_saves_and_redirects(self):
        response = self.client.post(reverse("predictor:predict"), VALID_DATA)
        self.assertEqual(LoanApplication.objects.count(), 1)
        application = LoanApplication.objects.get()
        self.assertRedirects(response, reverse("predictor:result", args=[application.pk]))
        self.assertEqual(application.email, VALID_DATA["email"])
        self.assertGreater(application.prediction_probability, 0)
        self.assertTrue(application.model_name)
        self.assertContains(self.client.get(response.url), "Application saved successfully")

    def test_refresh_result_does_not_duplicate(self):
        response = self.client.post(reverse("predictor:predict"), VALID_DATA)
        self.client.get(response.url)
        self.client.get(response.url)
        self.assertEqual(LoanApplication.objects.count(), 1)

    def test_invalid_post_displays_errors_without_saving(self):
        response = self.client.post(reverse("predictor:predict"), {**VALID_DATA, "loan_amount": "-100"})
        self.assertContains(response, "Please review your application")
        self.assertEqual(LoanApplication.objects.count(), 0)

    def test_empty_post_displays_errors(self):
        self.assertContains(self.client.post(reverse("predictor:predict"), {}), "This field is required.")

    def test_private_result_is_inaccessible_to_other_sessions(self):
        response = self.client.post(reverse("predictor:predict"), VALID_DATA)
        self.assertEqual(Client().get(response.url).status_code, 404)
        self.assertIn("no-store", self.client.get(response.url)["Cache-Control"])

    def test_csrf_is_enforced(self):
        response = Client(enforce_csrf_checks=True).post(reverse("predictor:predict"), VALID_DATA)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(LoanApplication.objects.count(), 0)

    def test_missing_model_returns_friendly_error(self):
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR, prefix=".test-model-") as directory, override_settings(MODEL_PATH=Path(directory) / "missing.joblib"), self.assertLogs("predictor.services", level="ERROR"):
            response = self.client.post(reverse("predictor:predict"), VALID_DATA)
        self.assertContains(response, "Predictions are temporarily unavailable", status_code=503)
        self.assertNotContains(response, "Traceback", status_code=503)
        self.assertEqual(LoanApplication.objects.count(), 0)

    def test_corrupt_model_returns_friendly_error(self):
        with tempfile.TemporaryDirectory(dir=settings.BASE_DIR, prefix=".test-model-") as directory:
            model = Path(directory) / "broken.joblib"
            model.write_bytes(b"not a pickle")
            with override_settings(MODEL_PATH=model), self.assertLogs("predictor.services", level="ERROR"), self.assertRaises(PredictionUnavailable):
                predict_loan(VALID_DATA)

    def test_unexpected_inference_error_is_wrapped(self):
        with patch("predictor.services._load_artifact", side_effect=RuntimeError("private internal details")), self.assertLogs("predictor.services", level="ERROR"):
            response = self.client.post(reverse("predictor:predict"), VALID_DATA)
        self.assertContains(response, "temporarily unavailable", status_code=503)
        self.assertNotContains(response, "private internal details", status_code=503)


class DemoAndAdminTests(TestCase):
    @override_settings(DEBUG=True)
    def test_seed_is_idempotent_and_preserves_password(self):
        call_command("seed_demo", stdout=io.StringIO())
        admin = get_user_model().objects.get(username="admin")
        self.assertTrue(admin.check_password("Admin@12345"))
        self.assertEqual(LoanApplication.objects.count(), 20)
        self.assertEqual(set(LoanApplication.objects.values_list("prediction", flat=True)), {"Approved", "Rejected"})
        admin.set_password("Changed-password-123!")
        admin.save()
        call_command("seed_demo", stdout=io.StringIO())
        admin.refresh_from_db()
        self.assertTrue(admin.check_password("Changed-password-123!"))
        self.assertEqual(LoanApplication.objects.count(), 20)

    @override_settings(DEBUG=False)
    def test_seed_is_disabled_in_production(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(get_user_model().objects.count(), 0)

    @override_settings(DEBUG=True)
    def test_admin_login_search_filters_and_dashboard(self):
        call_command("seed_demo", stdout=io.StringIO())
        self.assertTrue(self.client.login(username="admin", password="Admin@12345"))
        self.assertContains(self.client.get(reverse("admin:index")), "Loan Prediction Management")
        url = reverse("admin:predictor_loanapplication_changelist")
        self.assertContains(self.client.get(url + "?q=Alex"), "Alex Morgan")
        response = self.client.get(url + "?prediction__exact=Rejected&property_area__exact=Urban")
        self.assertEqual(response.status_code, 200)
        for row in response.context["cl"].queryset:
            self.assertEqual(row.prediction, "Rejected")
            self.assertEqual(row.property_area, "Urban")
        response = self.client.get(reverse("predictor:dashboard") + "?q=Alex&status=Rejected")
        self.assertEqual(response.status_code, 200)
        for row in response.context["page_obj"]:
            self.assertEqual(row.prediction, "Rejected")

    @override_settings(DEBUG=True)
    def test_admin_edits_recompute_the_prediction(self):
        from .admin import AdminPredictionForm
        call_command("seed_demo", stdout=io.StringIO())
        application = LoanApplication.objects.first()
        form = AdminPredictionForm({**VALID_DATA, "prediction": "Approved", "prediction_probability": .8, "model_name": "test"}, instance=application)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.prediction_output["prediction"], predict_loan(VALID_DATA)["prediction"])

    @override_settings(DEBUG=False)
    def test_production_404_is_custom(self):
        response = self.client.get("/unknown-page/")
        self.assertContains(response, "This page is out of reach", status_code=404)

    @override_settings(DEBUG=True)
    def test_admin_edit_saves_recalculated_prediction(self):
        call_command("seed_demo", stdout=io.StringIO())
        self.client.login(username="admin", password="Admin@12345")
        application = LoanApplication.objects.first()
        values = {**VALID_DATA, "credit_history": "0", "applicant_income": "1000", "coapplicant_income": "0", "loan_amount": "300000", "loan_amount_term": "60"}
        response = self.client.post(reverse("admin:predictor_loanapplication_change", args=[application.pk]), {**values, "_save": "Save"})
        self.assertRedirects(response, reverse("admin:predictor_loanapplication_changelist"))
        application.refresh_from_db()
        self.assertEqual(application.prediction, "Rejected")
        self.assertAlmostEqual(application.prediction_probability, predict_loan(values)["probability"])
