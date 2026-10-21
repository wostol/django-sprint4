from django.urls import path, re_path

from . import views


def get_urlpatterns():
    return [
        path('', views.IndexView.as_view(), name='index'),

        path(
            'auth/registration/',
            views.RegisterView.as_view(),
            name='registration',
        ),

        path(
            'edit_profile/',
            views.ProfileEditView.as_view(),
            name='edit_profile',
        ),

        path(
            'profile/<str:username>/',
            views.ProfileView.as_view(),
            name='profile',
        ),

        # Основное имя
        re_path(
            r'^category/(?P<category_slug>[-a-zA-Z0-9_]*)/$',
            views.CategoryListView.as_view(),
            name='category',
        ),
        re_path(
            r'^category/(?P<category_slug>[-a-zA-Z0-9_]*)/$',
            views.CategoryListView.as_view(),
            name='category_posts',
        ),

        path(
            'posts/create/',
            views.PostCreateView.as_view(),
            name='create_post',
        ),

        path(
            'posts/<int:post_id>/',
            views.PostDetailView.as_view(),
            name='post_detail',
        ),

        path(
            'posts/<int:post_id>/edit/',
            views.PostUpdateView.as_view(),
            name='edit_post',
        ),

        path(
            'posts/<int:post_id>/delete/',
            views.PostDeleteView.as_view(),
            name='delete_post',
        ),

        path(
            'posts/<int:post_id>/comment/',
            views.add_comment,
            name='add_comment',
        ),

        path(
            'posts/<int:post_id>/edit_comment/<int:comment_id>/',
            views.CommentUpdateView.as_view(),
            name='edit_comment',
        ),

        path(
            'posts/<int:post_id>/delete_comment/<int:comment_id>/',
            views.CommentDeleteView.as_view(),
            name='delete_comment',
        ),
    ]
