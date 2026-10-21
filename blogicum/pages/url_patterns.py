from django.urls import path

from . import views


def get_urlpatterns():
    return [
        path('about/', views.AboutView.as_view(), name='about'),
        path('rules/', views.RulesView.as_view(), name='rules'),
    ]
