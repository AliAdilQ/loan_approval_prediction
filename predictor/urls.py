from django.urls import path
from . import views

app_name = "predictor"
urlpatterns = [
    path("", views.home, name="home"), path("predict/", views.predict, name="predict"),
    path("result/<uuid:application_id>/", views.result, name="result"),
    path("about/", views.about, name="about"), path("dashboard/", views.dashboard, name="dashboard"),
]
