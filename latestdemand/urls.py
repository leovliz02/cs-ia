"""
URL configuration for latestdemand project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
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
from django.urls import path
from core import views

urlpatterns = [
    path("admin/", admin.site.urls),

    #logins
    path('api/login/', views.login_view, name='login'),
    path('login/', views.show_login_page, name='login_page'),

    #employee - render page
    path ('employee/demands/', views.employee_demands_view, name = 'employee_demands'),
    path('employee/personal/', views.employee_personal_details_view, name="employee_personal"),
    path('employee/commitments/', views.employee_commitments_view, name="employee_commitments"),

    #employee - personal page - APIs
    path('api/notifications/<int:notification_ID>/mark_read/', views.mark_notification_as_read, name='mark_notification_as_read'),
    path('api/notifications/<int:notification_ID>/delete/', views.delete_notification, name='api_delete_notification'),
    path('api/capacity/change_request/', views.capacity_change_request_view, name='capacity_change_request'),
    path('api/capacity/check_overlap/', views.check_capacity_overlap_api, name='check_capacity_overlap'),

    #employee - demands page - APIs
    path ('api/demands/create_edit_request/', views.create_edit_request_view, name = 'create_edit_request'),

    #logout
    path('logout/', views.logout_view, name='logout'),

    #manager
    path('manager/teams/', views.manager_teams_page, name='manager_teams_page'),
    path('manager/demands/', views.manager_demands_page, name ='manager_demands_page'),
    path('manager/approvals/', views.manager_approvals_page, name='manager_approvals_page'),

    # manager - team details page - APIs
    path("api/manager/teams/", views.manager_teams_api, name='api_teams'),
    path('api/manager/teams/<int:team_id>/', views.manager_team_detail_api, name='manager_teams_api_detail'),
    path('api/manager/unassigned_users/', views.manager_unassigned_users_api, name='api_unassigned_users'),
    path('api/manager/teams/efficiency-report/', views.manager_team_efficiency_report_api, name = 'efficiency_report'),
    path('api/manager/teams/<int:team_id>/add_user/', views.manager_add_user_to_team_api, name='add-user-to-team'),
    #api/get_teamspath('api/manager/teams/<int:team_id>/remove_user/', views.manager_remove_user_from_team_api, name='remove-user-from-team'),

    # manager - approvals page - APIs
    path('api/approvals/capacity/<int:request_id>/approve/', views.approve_capacity_request_api, name='approve_capacity_request_api'),
    path('api/approvals/capacity/<int:request_id>/reject/', views.reject_capacity_request_api, name='reject_capacity_request_api'),
    path('api/approvals/demand/<int:request_id>/approve/', views.approve_demand_edit_request_api, name='approve_demand_edit_request_api'),
    path('api/approvals/demand/<int:request_id>/reject/', views.reject_demand_edit_request_api, name='reject_demand_edit_request_api'),

    #manager - demands page - APIs
    path ('api/demands/', views.manage_demand_api, name = 'manage_demand_api'),
    path('api/demands/<int:demand_id>/', views.manage_demand_api, name='manage_demand_api'),
    path('api/demands/delete/<int:demand_id>/', views.delete_demand_api, name='delete_demand_api'), 
    path('api/get_teams_meeting_deadline/', views.get_teams_meeting_deadline_api, name='get_teams_meeting_deadline'),
]
