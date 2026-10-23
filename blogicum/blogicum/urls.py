from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import urls as auth_urls
from django.urls import include, path

urlpatterns = [
    path('admin/', admin.site.urls),

    path('auth/', include('django.contrib.auth.urls')),
    path('auth/', include((auth_urls.urlpatterns, 'auth'), namespace='auth')),

    path('', include('blog.urls_plain')),
    path('', include('blog.urls')),

    path('', include('pages.urls_plain')),
    path('', include('pages.urls')),
]

if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )

handler404 = 'pages.views.page_not_found'
handler500 = 'pages.views.server_error'
handler403 = 'pages.views.csrf_failure'
