"""
URL configuration for jobtracker_server project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('analysis.urls')),  # job-search stats/insights
    path('api/assistant/', include('assistant.urls')),  # resume profile, cover letters, interview answers
    path('api/auth/', include('accounts.urls')),  # signup/login/logout
    path('api/', include('tracker.urls')),  # applications/profile/settings CRUD — the real data store
]
