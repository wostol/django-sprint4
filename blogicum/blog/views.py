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


# ---------------------------------------------
# Кастомные страницы ошибок
# ---------------------------------------------


# ---------------------------------------------
# Вспомогательные функции
# ---------------------------------------------

def reverse_name(name, **kwargs):
    """
    Ищет имя маршрута в нескольких вариантах:
    - name
    - blog:name
    - pages:name
    - auth:name

    Это удобно, если шаблоны используют разные варианты имён.
    """
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
    """
    Базовый queryset для постов: связанные объекты + счётчик комментариев.

    Имя аннотации — comment_count, именно его использует готовый
    includes/post_card.html: {{ post.comment_count }}
    """
    return Post.objects.select_related(
        'author',
        'category',
        'location',
    ).annotate(
        comment_count=Count('comments', distinct=True),
    )


def get_published_posts(queryset):
    """
    Возвращает только опубликованные посты:
    - is_published == True;
    - pub_date не позже текущего времени;
    - категория опубликована, если она указана;
    - местоположение опубликовано, если оно указано.
    """
    return queryset.filter(
        is_published=True,
        pub_date__lte=timezone.now(),
    ).filter(
        Q(category__isnull=True) | Q(category__is_published=True),
    ).filter(
        Q(location__isnull=True) | Q(location__is_published=True),
    ).order_by('-pub_date')


def public_posts():
    """
    Опубликованные посты для анонимных пользователей и других пользователей.
    """
    return get_published_posts(base_posts())


def is_publicly_visible(post):
    """
    Проверка, виден ли пост всем посетителям.
    """
    if not post.is_published or post.pub_date > timezone.now():
        return False

    if post.category_id and not post.category.is_published:
        return False

    if post.location_id and not post.location.is_published:
        return False

    return True


def can_view_post(post, user):
    """
    Может ли пользователь посмотреть пост.

    Если пост опубликован и дата наступила — видят все.
    Если пост отложенный или снят с публикации — его видит автор и суперпользователь.
    """
    if is_publicly_visible(post):
        return True

    return user.is_authenticated and (
        user == post.author or user.is_superuser
    )


class AddPostsToContextMixin:
    """
    Добавляет в контекст переменную posts,
    если старые шаблоны используют именно её.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if 'post_list' in context:
            context['posts'] = context['post_list']
        return context


# ---------------------------------------------
# Главная, категория, профиль
# ---------------------------------------------

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

        # Пустой слаг — страница открывается, но постов нет.
        if not slug:
            self.category = None
            return public_posts().none()

        # Ищем реальную категорию в базе.
        # Используем filter(...).first(), чтобы не задействовать менеджер-заглушку.
        category = Category.objects.filter(slug=slug).first()

        if category is None:
            # Если в базе вообще нет ни одной категории,
            # показываем пустую страницу категории.
            if not Category.objects.exists():
                self.category = Category(
                    title='Без категории',
                    slug='no-category',
                    is_published=True,
                )
                return public_posts().none()

            # Если категории есть, но такой slug не найден — обычный 404.
            raise Http404

        # Категория снята с публикации — страница недоступна.
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
            User,
            username=self.kwargs['username'],
        )

        all_author_posts = base_posts().filter(author=self.profile)

        # Владелец профиля видит все свои посты:
        # обычные, отложенные и снятые с публикации.
        if self.request.user == self.profile or self.request.user.is_superuser:
            return all_author_posts.order_by('-pub_date')

        # Остальные посетители видят только опубликованные посты.
        return public_posts().filter(author=self.profile)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['profile'] = self.profile
        return context


# ---------------------------------------------
# Страница поста + комментарии
# ---------------------------------------------

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
        # Если форма комментария отправлена прямо на страницу поста,
        # передаём запрос в add_comment.
        return add_comment(request, self.kwargs[self.pk_url_kwarg])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['comments'] = self.object.comments.select_related(
            'author',
        ).order_by('created_at')
        context['form'] = CommentForm()
        return context

# ---------------------------------------------
# Регистрация и редактирование профиля
# ---------------------------------------------


class RegisterView(CreateView):
    form_class = CustomUserCreationForm

    # Если у вас шаблон называется иначе, поменяйте только эту строку.
    template_name = 'registration/registration_form.html'

    def get_success_url(self):
        return reverse_name('login')


class ProfileEditView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = UserEditForm
    template_name = 'blog/user.html'   # было 'blog/edit_profile.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_name('profile', username=self.request.user.username)


# ---------------------------------------------
# Создание, редактирование, удаление постов
# ---------------------------------------------

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

        # По заданию: если редактирует не автор,
        # редиректим на страницу просмотра поста.
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


# ---------------------------------------------
# Комментарии
# ---------------------------------------------

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

        # Если форма невалидна, снова показываем страницу поста.
        context = {
            'post': post,
            'comments': post.comments.select_related('author').order_by('created_at'),
            'form': form,
        }
        return render(request, 'blog/detail.html', context)

    # GET-запрос сюда обычно не нужен, форма уже есть на странице поста.
    return HttpResponseRedirect(
        reverse_name('post_detail', post_id=post.pk)
    )


class CommentAccessMixin(LoginRequiredMixin):
    """Одинаковые права доступа для редактирования и удаления комментария."""
    model = Comment
    pk_url_kwarg = 'comment_id'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return self.handle_no_permission()   # теперь метод существует

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

    # form_class НЕ задаём.
    # form в контекст НЕ передаём.

    def get_success_url(self):
        return reverse_name('post_detail', post_id=self.object.post_id)
