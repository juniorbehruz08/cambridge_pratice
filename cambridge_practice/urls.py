from django.urls import path
from django.contrib.auth import views as auth_views

from . import views

app_name = 'cambridge_practice'

urlpatterns = [
    path('', views.home, name='home'),
    path('books/<int:number>/', views.book_detail, name='book_detail'),
    path(
        'books/<int:book_number>/tests/<int:test_number>/',
        views.test_detail,
        name='test_detail',
    ),
    path(
        'books/<int:book_number>/tests/<int:test_number>/<str:section>/start/',
        views.practice_start,
        name='practice_start',
    ),
    path(
        'books/<int:book_number>/tests/<int:test_number>/<str:section>/',
        views.practice_section,
        name='practice_section',
    ),
    path('practice/save/', views.save_practice_answers, name='save_practice_answers'),
    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='login.html',
            redirect_authenticated_user=True,
        ),
        name='login',
    ),
    path('register/', views.register, name='register'),
    path('logout/', views.sign_out, name='logout'),
]
