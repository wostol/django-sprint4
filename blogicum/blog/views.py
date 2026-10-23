from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.views.generic import (
    CreateView,
    DeleteView,
    DetailView,
    ListView,
    UpdateView,
)

from .forms import (
    CommentForm,
    CustomUserCreationForm,
    PostForm,
    UserEditForm,
)
from .models import Category, Comment, Post

User = get_user_model()


def reverse_name(name, **kwargs):
    """Разворачивает URL по имени, перебирая пространство имён."""
    candidates = (
        name,
        f'blog:{name}',
        f'pages:{name}',
        f'auth:{name}',
    )
    last_exc = NoReverseMatch(f'URL name not found: {name}')
    for candidate in candidates:
        try:
            return reverse(candidate, kwargs=kwargs if kwargs else None)
        except NoReverseMatch as exc:
            last_exc = exc
    raise last_exc


def base_posts():
    """Базовый queryset постов с предзагрузкой связей и счётчиком комментариев."""
    return Post.objects.select_related(
        'author', 'category', 'location',
    ).annotate(
        comment_count=Count('comments', distinct=True),
    )


def get_published_posts(queryset):
    """Фильтрует queryset по условиям публикации поста, категории и локации."""
    return queryset.filter(
        is_published=True,
        pub_date__lte=timezone.now(),
    ).filter(
        Q(category__isnull=True) | Q(category__is_published=True),
    ).filter(
        Q(location__isnull=True) | Q(location__is_published=True),
    ).order_by('-pub_date')


def public_posts():
    return get_published_posts(base_posts())


def is_publicly_visible(post):
    if not post.is_published or post.pub_date > timezone.now():
        return False
    if post.category_id and not post.category.is_published:
        return False
    if post.location_id and not post.location.is_published:
        return False
    return True


def can_view_post(post, user):
    """Публика видит опубликованные посты; отложенные и скрытые — автор и суперпользователь."""
    if is_publicly_visible(post):
        return True
    return user.is_authenticated and (user == post.author or user.is_superuser)


class AddPostsToContextMixin:
    """Дублирует post_list в posts для совместимости со старыми шаблонами."""

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'post_list' in context:
            context['posts'] = context['post_list']
        return context


class IndexView(AddPostsToContextMixin, ListView):
    template_name = 'blog/index.html'
    context_object_name = 'post_list'
    paginate_by = 10

    def get_queryset(self):
        return public_posts()


class CategoryListView(AddPostsToContextMixin, ListView):
    template_name = 'blog/category.html'
    context_object_name = 'post_list'
    paginate_by = 10

    def get_queryset(self):
        slug = self.kwargs['category_slug']
        if not slug:
            self.category = None
            return public_posts().none()

        category = Category.objects.filter(slug=slug).first()

        if category is None:
            if not Category.objects.exists():
                self.category = Category(
                    title='Без категории',
                    slug='no-category',
                    is_published=True,
                )
                return public_posts().none()
            raise Http404

        if not category.is_published:
            raise Http404

        self.category = category
        return public_posts().filter(category=category)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['category'] = self.category
        return context


class ProfileView(AddPostsToContextMixin, ListView):
    template_name = 'blog/profile.html'
    context_object_name = 'post_list'
    paginate_by = 10

    def get_queryset(self):
        self.profile = get_object_or_404(
            User, username=self.kwargs['username'],
        )
        all_author_posts = base_posts().filter(author=self.profile)
        if self.request.user == self.profile or self.request.user.is_superuser:
            return all_author_posts.order_by('-pub_date')
        return public_posts().filter(author=self.profile)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self.profile
        return context


class PostDetailView(DetailView):
    template_name = 'blog/detail.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def get_object(self, queryset=None):
        post = get_object_or_404(Post, pk=self.kwargs[self.pk_url_kwarg])
        if not can_view_post(post, self.request.user):
            raise Http404
        return post

    def post(self, request, *args, **kwargs):
        return add_comment(request, self.kwargs[self.pk_url_kwarg])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.comments.select_related(
            'author',
        ).order_by('created_at')
        context['form'] = CommentForm()
        return context


class RegisterView(CreateView):
    form_class = CustomUserCreationForm
    template_name = 'registration/registration_form.html'

    def get_success_url(self):
        return reverse_name('login')


class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = 'blog/user.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_name('profile', username=self.request.user.username)


class PostCreateView(LoginRequiredMixin, CreateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'

    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_name('profile', username=self.request.user.username)


class PostUpdateView(LoginRequiredMixin, UpdateView):
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        post = get_object_or_404(Post, pk=self.kwargs[self.pk_url_kwarg])
        if not request.user.is_authenticated:
            return self.handle_no_permission()
        if post.author != request.user:
            return HttpResponseRedirect(
                reverse_name('post_detail', post_id=post.pk)
            )
        self.object = post
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.object

    def get_success_url(self):
        return reverse_name('post_detail', post_id=self.object.pk)


class PostDeleteView(LoginRequiredMixin, DeleteView):
    model = Post
    template_name = 'blog/create.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def get_queryset(self):
        return Post.objects.filter(author=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = PostForm(instance=self.object)
        return context

    def get_success_url(self):
        return reverse_name('profile', username=self.object.author.username)


@login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    if not can_view_post(post, request.user):
        raise Http404

    if request.method == 'POST':
        form = CommentForm(request.POST)
        if form.is_valid():
            comment = form.save(commit=False)
            comment.post = post
            comment.author = request.user
            comment.save()
            return HttpResponseRedirect(
                reverse_name('post_detail', post_id=post.pk)
            )
        context = {
            'post': post,
            'comments': post.comments.select_related('author').order_by('created_at'),
            'form': form,
        }
        return render(request, 'blog/detail.html', context)

    return HttpResponseRedirect(reverse_name('post_detail', post_id=post.pk))


class CommentAccessMixin(LoginRequiredMixin):
    model = Comment
    pk_url_kwarg = 'comment_id'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()

        comment = get_object_or_404(
            Comment,
            pk=self.kwargs[self.pk_url_kwarg],
            post_id=self.kwargs['post_id'],
        )
        if comment.author != request.user:
            raise Http404

        self.object = comment
        return super().dispatch(request, *args, **kwargs)

    def get_object(self, queryset=None):
        return self.object


class CommentUpdateView(CommentAccessMixin, UpdateView):
    template_name = 'blog/comment.html'
    context_object_name = 'comment'
    fields = ['text']

    def get_success_url(self):
        return reverse_name('post_detail', post_id=self.object.post_id)


class CommentDeleteView(CommentAccessMixin, DeleteView):
    model = Comment
    template_name = 'blog/comment.html'
    context_object_name = 'comment'
    pk_url_kwarg = 'comment_id'

    def get_success_url(self):
        return reverse_name('post_detail', post_id=self.object.post_id)
