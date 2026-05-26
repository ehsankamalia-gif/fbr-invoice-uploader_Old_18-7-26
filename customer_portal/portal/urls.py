
from django.urls import path
from . import views

urlpatterns = [
    path('', views.login_view, name='login'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('loan/<int:loan_id>/', views.loan_detail_view, name='loan_detail'),
    path('payments/', views.payments_view, name='payments'),
    path('profile/', views.profile_view, name='profile'),
    path('running-ledger/', views.running_ledger_view, name='running_ledger'),
]
