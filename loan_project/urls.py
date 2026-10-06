from django.contrib import admin
from django.urls import include, path

urlpatterns = [path("admin/", admin.site.urls), path("", include("predictor.urls"))]
handler404 = "predictor.views.not_found"
handler500 = "predictor.views.server_error"
