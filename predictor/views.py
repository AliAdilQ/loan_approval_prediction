"""Thin request handlers with session-private results and staff-only reporting."""
import json
from pathlib import Path

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db import DatabaseError
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from .forms import LoanPredictionForm
from .models import LoanApplication
from .services import PredictionUnavailable, logger, predict_loan


def statistics():
    counts = LoanApplication.objects.aggregate(total=Count("id"), approved=Count("id", filter=Q(prediction="Approved")), rejected=Count("id", filter=Q(prediction="Rejected")))
    counts["approval_rate"] = round(100 * counts["approved"] / counts["total"], 1) if counts["total"] else 0
    return counts


def home(request):
    return render(request, "home.html", {"stats": statistics()})


def about(request):
    try:
        metadata = json.loads((Path(settings.MODEL_PATH).parent / "metrics.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        metadata = None
    return render(request, "about.html", {"metadata": metadata, "accuracy": round(metadata["metrics"]["accuracy"] * 100, 1) if metadata else None})


@never_cache
@require_http_methods(["GET", "POST"])
def predict(request):
    form = LoanPredictionForm(request.POST if request.method == "POST" else None)
    status = 200
    if request.method == "POST" and form.is_valid():
        try:
            outcome = predict_loan(form.cleaned_data)
            application = form.save(commit=False)
            application.prediction = outcome["prediction"]
            application.prediction_probability = outcome["probability"]
            application.model_name = outcome["model_name"]
            application.save()
            request.session["application_ids"] = (request.session.get("application_ids", []) + [str(application.pk)])[-50:]
            return redirect("predictor:result", application_id=application.pk)
        except PredictionUnavailable as error:
            form.add_error(None, str(error))
            status = 503
        except DatabaseError:
            logger.exception("Unable to save application")
            form.add_error(None, "We could not save your application. Please try again in a moment.")
            status = 503
    return render(request, "predict.html", {"form": form}, status=status)


@never_cache
def result(request, application_id):
    if not request.user.is_staff and str(application_id) not in request.session.get("application_ids", []):
        raise Http404
    application = get_object_or_404(LoanApplication, pk=application_id)
    return render(request, "result.html", {"application": application})


@staff_member_required
@never_cache
def dashboard(request):
    applications = LoanApplication.objects.all()
    query = request.GET.get("q", "").strip()[:100]
    status = request.GET.get("status", "")
    if query:
        applications = applications.filter(Q(applicant_name__icontains=query) | Q(email__icontains=query))
    if status in {"Approved", "Rejected"}:
        applications = applications.filter(prediction=status)
    parameters = request.GET.copy()
    parameters.pop("page", None)
    return render(request, "dashboard.html", {"stats": statistics(), "page_obj": Paginator(applications, 10).get_page(request.GET.get("page")), "query": query, "status": status, "pagination_query": parameters.urlencode()})


def not_found(request, exception):
    return render(request, "error.html", {"error_code": "404", "error_title": "This page is out of reach.", "error_message": "The link may have expired, or this result belongs to another session."}, status=404)


def server_error(request):
    return render(request, "error.html", {"error_code": "500", "error_title": "Something interrupted your request.", "error_message": "Please try again in a moment."}, status=500)
