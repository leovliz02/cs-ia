# core/views.py
from datetime import datetime
from django.utils import timezone
import json
from django.http import HttpResponseNotAllowed, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.contrib.auth import authenticate, login, logout, get_user_model
from django.contrib.auth.decorators import login_required 
from django.db.models import Sum, Case, When, Value, IntegerField
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods, require_POST, require_GET
from .models import Demand
from functools import wraps
from core.services import get_teams_meeting_deadline_helper

from core.models import Capacity, CapacityChangeRequest, Demand, DemandDailyAllocation, DemandEditRequest, Manager, Employee, Notifications, Team

#logout view
def logout_view(request):
        logout(request)
        return redirect('login_page')

#decorator views to maintain data integrity and to establish access levels
def manager_required(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.groups.filter(name='Manager').exists():
                return JsonResponse({'success': False, 'message': 
                                     'User is not associated with'
                                     ' an manager profile.'}, 
                                     status=403)
            return view_func(request, *args, **kwargs)
        return wrapper

def employee_required(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.groups.filter(name='Employee').exists():
                return JsonResponse({'success': False, 'message': 
                                     'User is not associated with'
                                     ' an employee profile.'}, 
                                     status=403)
            return view_func(request, *args, **kwargs)
        return wrapper

#login details 
    #render page
def show_login_page (request):
    return render (request, 'registration/login.html')

#login api
def login_view(request):
        if request.method == "POST":
            try:
                data = json.loads(request.body)
                username = data.get("username")
                password = data.get("password")
                print(f"Attempting login for username: {username}") 
            except (json.JSONDecodeError, AttributeError):
                print("Invalid JSON received during login.") 
                return JsonResponse({"success": False, "error": "Invalid JSON"}, status=400)
            
            user = authenticate(request, username=username, password=password)

            if user is not None:
                login(request, user) 

                role = "manager" if hasattr(user, 'manager_profile') else "employee"
                
                return JsonResponse({"success": True, "role": role})
            else:
                return JsonResponse({"success": False, "error": "Invalid credentials"}, status=401)

        print("Received non-POST request for login_view.")
        return HttpResponseNotAllowed(['POST'])

# EMPLOYEE VIEWS
# demands view 
    #render demands_page.html
@login_required(login_url='login_page')
@employee_required
def employee_demands_view(request):    
        demands = Demand.objects.filter(team__members=request.user.employee_profile).order_by('start_date')

        demands_list_for_template_and_js = []
        for demand in demands:
            demands_list_for_template_and_js.append({
                'demandID': demand.demandID,
                'demand_name': demand.demand_name, 
                'start_date': demand.start_date.isoformat() if demand.start_date else None,
                'estimated_end_date': demand.estimated_end_date.isoformat() if demand.estimated_end_date else None,
                'actual_end_date': demand.actual_end_date.isoformat() if demand.actual_end_date else None,
                'time_needed': demand.time_needed, 
                'demand_completion_status': demand.demand_completion_status, 
            })

        demands_json = json.dumps(demands_list_for_template_and_js)

        context = {
            'demands_data_parsed': demands_list_for_template_and_js,
            'demands_json': demands_json,
            'message': 'No demands found for your team.' if not demands else None,
        }
        return render(request, 'employee/demands_page.html', context)

    #APIs - create edit request
def create_edit_request_view(request):
    if request.method != "POST":
        return JsonResponse({"success": False, "message": "Only POST requests are allowed."}, status=405)

    user = request.user

    try:
        data = json.loads(request.body)
        demandID = data.get('demandID')
        new_name = data.get('new_name')
        new_status = data.get('new_status')

        if not demandID:
            return JsonResponse({"success": False, "message": "Missing demand ID."}, status=400)

        if not (new_name or new_status):
            return JsonResponse({"success": False, "message": "Provide at least new_name or new_status."}, status=400)

        # Fetch the demand
        try:
            demand = Demand.objects.get(demandID=demandID)
        except Demand.DoesNotExist:
            return JsonResponse({"success": False, "message": "Demand not found."}, status=404)

        # Fetch employee profile
        if not hasattr(user, 'employee_profile'):
            return JsonResponse({"success": False, "message": "User is not an employee."}, status=403)

        employee = user.employee_profile

        # Create the edit request
        DemandEditRequest.objects.create(
            demand=demand,
            employee=employee,
            new_name=new_name,
            new_status=new_status
        )

        return JsonResponse({"success": True, "message": "Edit request submitted successfully."})

    except json.JSONDecodeError:
        return JsonResponse({"success": False, "message": "Invalid JSON."}, status=400)

    except Exception as e:
        return JsonResponse({"success": False, "message": f"Error: {str(e)}"}, status=500)

#personal.html

    #personal details view
@employee_required
def employee_personal_details_view (request):
        employee_profile = request.user.employee_profile
        employee_data = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'team_id': employee_profile.team.team_ID if employee_profile.team else 'N/A',
            'team_name': employee_profile.team.team_name if employee_profile.team else 'Not Assigned',
            'employee_capacity': employee_profile.standard_daily_capacity,
            'daily_overrides': [], 
        }


        notifications = Notifications.objects.filter(employee=employee_profile) \
    .order_by('is_read', '-timestamp')

        employee_data['notifications'] = notifications

        context = {
            'employee_data': employee_data,
            'employee_ID': employee_profile.employee_ID,
        }
        return render(request, 'employee/personal.html', context)


    #API to mark notifications as read
@employee_required
def mark_notification_as_read(request, notification_ID):
        if request.method == 'POST':
            try:
                notification = Notifications.objects.get(notification_ID=notification_ID, employee=request.user.employee_profile)
                notification.is_read = True
                notification.save()
                return JsonResponse({'success': True, 'message': 'Notification marked as read.'})
            except Notifications.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Notification not found or unauthorized.'}, status=404)
            except Exception as e:
                return JsonResponse({'success': False, 'message': f'Error marking as read: {str(e)}'}, status=500)
        return HttpResponseNotAllowed(['POST'])

    #API to delete notification object
@employee_required
def delete_notification(request, notification_ID):
        if request.method == 'POST':
            try:
                notification = Notifications.objects.get(notification_ID=notification_ID, employee=request.user.employee_profile)
                notification.delete()
                return JsonResponse({'success': True, 'message': 'Notification deleted.'})
            except Notifications.DoesNotExist:
                return JsonResponse({'success': False, 'message': 'Notification not found or unauthorized.'}, status=404)
            except Exception as e:
                return JsonResponse({'success': False, 'message': f'Error deleting notification: {str(e)}'}, status=500)
        return HttpResponseNotAllowed(['POST'])

    #API to validate capacity change request
@require_GET
def check_capacity_overlap_api(request):
    employee_id = request.GET.get('employee_id')
    start_date = request.GET.get('start_date')
    end_date = request.GET.get('end_date')

    from datetime import datetime
    from core.models import CapacityChangeRequest, Employee

    if not (employee_id and start_date and end_date):
        return JsonResponse({'error': 'Missing parameters'}, status=400)

    try:
        start_date = datetime.strptime(start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_date, '%Y-%m-%d').date()
        employee = Employee.objects.get(pk=employee_id)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=400)

    overlapping_requests = CapacityChangeRequest.objects.filter(
        employee=employee,
        start_date__lte=end_date,
        end_date__gte=start_date,
        status='Pending'
    )

    if overlapping_requests.exists():
        return JsonResponse({'overlap': True})
    else:
        return JsonResponse({'overlap': False})

@employee_required
def capacity_change_request_view(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            new_capacity = data.get("new_capacity")
            start_date_str = data.get("start_date")
            end_date_str = data.get("end_date")

            # if data is missing, error message is returned to the HTML which then returns this message through the alert.  
            if new_capacity is None or start_date_str is None or end_date_str is None:
                return JsonResponse({"success": False, "message": "Missing data in request."}, status=400)

            # converts date from string back to date objects
            start_date = parse_date(start_date_str)
            end_date = parse_date(end_date_str)

            if start_date is None or end_date is None:
                return JsonResponse({"success": False, "message": "Invalid date format. Use YYYY-MM-DD."}, status=400)

            # Convert new_capacity to float
            new_capacity = float(new_capacity)

            # Get the Employee instance for the logged-in user
            employee = request.user.employee_profile

            try:
                # Call the method to save the capacity change request
                employee.send_capacity_change_request(new_capacity, start_date, end_date)
            except ValueError as e:
                return JsonResponse({"success": False, "message": str(e)}, status=200)
            

            return JsonResponse({"success": True})

        except Exception as e:
            return JsonResponse({"message":str(e)})

    else:
        return JsonResponse({"success": False, "message": "Only POST requests are allowed."}, status=405)


# time_commitments.html -> render
@employee_required
def employee_commitments_view(request):
    employee_profile = request.user.employee_profile
    today = timezone.now().date()

    if not employee_profile.team:
        # VALIDATION: if employee is not assigned to a team, cannot display team commitments
        return render(request, 'employee/time_commitments.html', {'message': 'You are not assigned to a team. Cannot display team commitments.'})

    team = employee_profile.team

    employee_effective_capacity = employee_profile.standard_daily_capacity

    try:
        capacity_override = Capacity.objects.filter(employee=employee_profile, date=today).first()
        if capacity_override:
            employee_effective_capacity = capacity_override.capacity_hours
    except NameError:
        # backup - using standard daily capacity instead of capacity if the capacity is not found
        print("Warning: Capacity model not found or imported. Using employee's standard_daily_capacity.")
    except Exception as e:
        print(f"Error fetching employee specific capacity for {today}: {e}. Using standard_daily_capacity.")

    demand_allocations_raw = DemandDailyAllocation.objects.filter(
        team=team, 
        date=today 
    ).values('demand__demand_name').annotate(
        total_allocated_hours= Sum('hours_allocated') 
    ).order_by('demand__demand_name') 

    demand_allocations_list = []
    for allocation in demand_allocations_raw:
        demand_allocations_list.append({
            'label': allocation['demand__demand_name'],
            'time': float(allocation['total_allocated_hours']) 
        })

    print (demand_allocations_list)

    context = {
        'team_bau_time': employee_effective_capacity, 
        'demand_allocations_json': json.dumps(demand_allocations_list),
    }

    # Add messages for specific scenarios
    if not demand_allocations_list and employee_effective_capacity == 0:
        context['message'] = "No demands allocated for your team today and your daily capacity is not set."
    elif not demand_allocations_list:
        context['message'] = f"No demands allocated for your team today. You have {employee_effective_capacity} hours of available capacity."

    return render(request, 'employee/time_commitments.html', context)

#manager views

# team_details.html -> render
@manager_required
def manager_teams_page(request):
    #available_users = User.objects.filter(is_manager=False, team__isnull=True)
    available_users = User.objects.all()
    team = Team.objects.all()
    
    context = {
        "available_users" : available_users,
    }
    return render(request, 'manager/team_details.html', context)

# team details page -> APIs

    #to display all team details 

User = get_user_model()

@manager_required
@require_http_methods(["GET", "POST", "PUT"])
def manager_teams_api(request, team_id=None):
    if request.method == "GET":
        teams = Team.objects.all().order_by('team_name')
        teams_data = []
        for team in teams:
            members_data = []
            for member in team.members.all():
                members_data.append({
                    'id': member.user.id,
                    'username': member.user.username,
                    'first_name': member.user.first_name,
                    'last_name': member.user.last_name,
                })
            teams_data.append({
                'id': team.team_ID,
                'name': team.team_name,
                'members': members_data
            })
        return JsonResponse(teams_data, safe = False)
    elif request.method == "POST":
        if Team.objects.count() >= 12:
            return JsonResponse(
            {"error": "Maximum of 12 teams allowed."},
            status=400
            )
        try:
            data = json.loads(request.body)
            team_name = data.get("name")
            if not team_name:
                return JsonResponse({"error": "team_name is required"}, status=400)
            
            team = Team.objects.create(team_name=team_name)
            return JsonResponse({
                "id": team.team_ID,
                "name": team.team_name,
                "members": []
            }, status=201)
        except json.JSONDecodeError:
            return JsonResponse({"error": "Invalid JSON"}, status=400)
        
    elif request.method == "PUT":
        data = json.loads(request.body)
        team_name = data.get("team_name")
        if not team_name:
            return JsonResponse({"error": "Team name is required"}, status=400)
        try:
            team = Team.objects.get(team_ID=team_id)
        except Team.DoesNotExist:
            return JsonResponse({"error": "Team not found"}, status=404)
        if team.team_name != team_name:
            team.team_name = team_name
            team.save()
        return JsonResponse({"id": team.team_ID, "name": team.team_name})   
    
@manager_required
def manager_team_detail_api(request, team_id):
    print("HIT manager_team_detail_api")
    team = get_object_or_404(Team, team_ID=team_id)

    if request.method == "GET":
        members_data = []
        for member in team.members.all():
            members_data.append({
                'id': member.employee_ID,
                'username': member.user.username,
                'first_name': member.user.first_name,
                'last_name': member.user.last_name,
            })
        team_data = {
            'id': team.team_ID,
            'name': team.team_name,
            'member_count': team.members.count(),
            'members': members_data
        }
        return JsonResponse(team_data)

    elif request.method == "PUT":
        try:
            data = json.loads(request.body)
            team_name = data.get('name')

            if not team_name:
                return JsonResponse({'success': False, 'message': 'Team name is required.'}, status=400)

            team.team_name = team_name
            team.save()
            return JsonResponse({'success': True, 'message': 'Team updated successfully.'})
        except Exception as e:
            return JsonResponse({'success': False, 'message': str(e)}, status=500)

    elif request.method == "DELETE":
        team_name = team.team_name
        team.delete()
        return JsonResponse({'success': True, 'message': f'Team "{team_name}" deleted successfully.'})

@manager_required
def manager_unassigned_users_api(request):
    if request.method == "GET":
        employees = Employee.objects.all()
        employee_data=[]
        for employee in employees:
            if(employee.team is None):
                employee_data.append({
                    'id': employee.user.id,
                    'emp_id': employee.employee_ID,
                    'first_name': employee.user.first_name,
                    'last_name': employee.user.last_name,
                    'username': employee.user.username
                })
    return JsonResponse({'unassigned_users': employee_data})

@manager_required
@require_POST
def manager_add_user_to_team_api(request, team_id):
    team = get_object_or_404(Team, team_ID=team_id)
    try:
        data = json.loads(request.body)
        emp_id = data.get('emp_id')
        print(emp_id)
        if not emp_id:
            return JsonResponse({'success': False, 'message': 'User ID is required.'}, status=400)
        
        if team.members.count() >= 6:
            return JsonResponse(
                {
                    'success': False,
                    'message': f'{team.team_name} already has 6 members.'
                },
                status=400
            )

        employee = get_object_or_404(Employee, employee_ID=emp_id)
        print(employee.team)

        if employee.team:
            return JsonResponse({'success': False, 'message': f'User {employee.user.username} already in team {employee.team.team_name}.'}, status=400)
        
        employee.team = team
        employee.save()

        return JsonResponse({'success': True, 'message': f'User {employee.user.username} added to {team.team_name}.'})
    except Exception as e:
        return JsonResponse({'success': False, 'message': str(e)}, status=500)
    
    #for the efficiency report

@manager_required
@require_http_methods(["GET"])
def manager_team_efficiency_report_api(request):
    teams = Team.objects.all()
    report_data = []

    for team in teams:
        overdue = team.overdue_demands
        early = team.early_completion
        on_time = team.on_time_completions
        print (overdue, early, on_time)
        
        total_completed_demands = overdue + early + on_time

        efficiency_rating = 0.0
        if total_completed_demands > 0:
            # Formula: (Early + On-Time - Overdue) / Total Completed
            # weightage for early is 1.2x, on-time 1x, overdue -0.5x
            efficiency_rating = (early * 1.2 + on_time * 1.0 + overdue * (-0.5)) / total_completed_demands
        
        report_data.append({
            'team_id': team.team_ID,
            'team_name': team.team_name,
            'overdue_completions': overdue,
            'early_completions': early,
            'on_time_completions': on_time,
            'total_completed_demands': total_completed_demands,
            'efficiency_rating': efficiency_rating
        })

        report_data = sorted(report_data, key=lambda x: x['efficiency_rating'], reverse=True)

    return JsonResponse({'teams': report_data}) 
    

def manager_demands_page(request):
    demands = Demand.objects.all().select_related('team').order_by('start_date')
    for demand in demands:
        demand.update_demand_status()
    teams = Team.objects.all().order_by('team_name')

    selected_team_id = request.GET.get("team_ID", "")
    selected_assignment_status = request.GET.get('assignment_status')

    if selected_team_id:
        demands = demands.filter(team__team_ID=selected_team_id)

    demands = demands.annotate(
    is_finished=Case(
        When(demand_completion_status="Finished", then=Value(1)),
        default=Value(0),
        output_field=IntegerField()
    )
).order_by("is_finished", "start_date")

    if selected_assignment_status:
        if selected_assignment_status == 'assigned':
            demands = demands.exclude(team__isnull=True) 
        elif selected_assignment_status == 'unassigned':
            demands = demands.filter(team__isnull=True)  

    context = {
        'demands': demands,
        'teams': teams,
        'selected_team_id': selected_team_id,
        'selected_assignment_status': selected_assignment_status,
    }
    return render(request, 'manager/all_demands.html', context)

# demands page -> APIs
    #create/edit demand
@manager_required
@require_http_methods(["POST", "PUT", "GET"])
def manage_demand_api(request, demand_id=None):
    print("Received request:", request.method, request.body)
    team_id = request.GET.get("team_id")

    if request.method == "GET":
        demand = get_object_or_404(Demand, demandID=demand_id)
        demand.update_demand_status()
        return JsonResponse({
            "demand_name": demand.demand_name,
            "start_date": demand.start_date.isoformat() if demand.start_date else None,
            "time_needed": demand.time_needed,
            "team_id": demand.team_id if demand.team else None,
            "predicted_end_date": demand.estimated_end_date.isoformat() if demand.estimated_end_date else None,
            "actual_end_date": demand.actual_end_date.isoformat() if demand.actual_end_date else None,
            "demand_completion_status": demand.demand_completion_status
        })

    try:
        data = json.loads(request.body)
        name = data.get("demand_name")
        start_date = datetime.strptime(data.get("start_date"), "%Y-%m-%d").date()
        hours = float(data.get("time_needed"))
        team_id = int(data.get("team_ID")) if data.get("team_ID") else None
        status = data.get("demand_completion_status")

        print("RAW BODY:", request.body)
        data = json.loads(request.body)
        print("PARSED DATA:", data)

        print('input validation completed')

        if request.method == "POST":
            print('preparing to insert demand')
            demand = Demand.objects.create(
                demand_name=name,
                start_date=start_date,
                time_needed=hours,
            )
            demand.update_demand_status(new_status=status if status else None)
            print('successfully created',demand)
            return JsonResponse(
                {
                    "message": f"Demand '{demand.demand_name}' created successfully.",
                    "demand_id": demand.demandID,
                    "predicted_end_date": demand.estimated_end_date.isoformat()
                    if demand.estimated_end_date else None
                },
                status=201
            )
        elif request.method == "PUT":
            print('preparing to update demand')
            demand = get_object_or_404(Demand, demandID=demand_id)
            demand.demand_name = name

            demand.update_demand_status(new_status=status if status else None)

            print('going to compute end date')
            if team_id: 
                demand.set_assigned_team(team_id=team_id, hours_predicted=hours, start_date=start_date)
            elif data.get("start_date") or hours:
                    demand.start_date = data["start_date"]
                    demand.time_needed = hours

            print('going to save demand')
            demand.save()
            return JsonResponse({"message": f"Demand '{demand.demand_name}' saved successfully."})
    

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)
    

    # to get list of teams that meet deadline

@require_http_methods(["POST"])
def get_teams_meeting_deadline_api(request):
    data = json.loads(request.body)
    print ("hi", data)
    predicted_end = datetime.strptime(data.get("predicted_end"), "%Y-%m-%d").date()
    print ("hello", predicted_end)
    start_date = datetime.strptime(data.get("start_date"), "%Y-%m-%d").date()
    print ("hey", start_date)
    time_required = float(data.get('time_required'))
    print ("yo", time_required)

    if not all([predicted_end, start_date, time_required]):
        print ("missing data")
        return JsonResponse({'error': 'Missing data for deadline check'}, status=400)
    
    available_teams = get_teams_meeting_deadline_helper(predicted_end, start_date, time_required)
    if available_teams:
        return JsonResponse({
            "deadline_met": True,
            "teams": [
                {
                    "team_ID": team.team_ID,
                    "team_name": team.team_name
                }
                for team in available_teams
            ]
        })

    return JsonResponse({
        "deadline_met": False,
        "teams": list(
            Team.objects.values("team_ID", "team_name")
        )
    })


    

    # delete demands api
@manager_required
@require_http_methods(['POST'])
@manager_required
def delete_demand_api(request, demand_id):
    if request.method == 'POST':
        try:
            demand = Demand.objects.get(demandID=demand_id)
            demand.clear_previous_allocations()
            demand.delete()
            return JsonResponse({'success': True, 'message': 'Demand deleted successfully.'})
        except Demand.DoesNotExist:
            return JsonResponse({'success': False, 'message': 'Demand not found.'}, status=404)
        except Exception as e:
            return JsonResponse({'success': False, 'message': f'Error deleting demand: {str(e)}'}, status=500)
    return HttpResponseNotAllowed(['POST'])

# approvals page -> render
@manager_required
def manager_approvals_page(request):
    pending_capacity_requests = CapacityChangeRequest.objects.select_related('employee__user')
    pending_demand_edit_requests = DemandEditRequest.objects.select_related('demand')

    approvals_data = []

    for req in pending_capacity_requests:
        if req.start_date == req.end_date:
            approvals_data.append({
                'id': req.id,
                'type': 'capacity_change',
                'description': f"{req.employee.user.first_name} requests capacity change to {req.new_capacity} hours per day on {req.start_date}. ",
                'request_id': req.id, 
            })
        else: 
            approvals_data.append({
                'id': req.id,
                'type': 'capacity_change',
                'description': f"{req.employee.user.first_name} requests capacity change to {req.new_capacity} hours per day from {req.start_date} to {req.end_date}. ",
                'request_id': req.id, 
            })

    for req in pending_demand_edit_requests:
        approvals_data.append({
            'id': req.id,
            'type': 'demand_edit',
            'description': f"{req.demand.demand_name} with status {req.new_status} to be updated to {req.new_name} with status {req.new_status}.",
            'request_id': req.id,
        })
    
    context = {
        'approvals_json': json.dumps(approvals_data)
    }
    return render(request, 'manager/approvals_page.html', context)

# approvals page -> APIs

@manager_required
@require_POST
def approve_capacity_request_api(request, request_id):
    manager_profile = get_object_or_404(Manager, user=request.user)
    if manager_profile.handle_capacity_request(request_id, approve=True):
        return JsonResponse({'success': True, 'message': 'Capacity request approved.'})
    else:
        return JsonResponse({'success': False, 'message': 'Failed to approve capacity request or request not found.'}, status=400)

@manager_required
@require_POST
def reject_capacity_request_api(request, request_id):
    manager_profile = get_object_or_404(Manager, user=request.user)
    if manager_profile.handle_capacity_request(request_id, approve=False):
        return JsonResponse({'success': True, 'message': 'Capacity request rejected.'})
    else:
        return JsonResponse({'success': False, 'message': 'Failed to reject capacity request or request not found.'}, status=400)

@manager_required
@require_POST
def approve_demand_edit_request_api(request, request_id):
    manager_profile = get_object_or_404(Manager, user=request.user)
    if manager_profile.handle_demand_edit_request(request_id, approve=True):
        return JsonResponse({'success': True, 'message': 'Demand edit request approved.'})
    else:
        return JsonResponse({'success': False, 'message': 'Failed to approve demand edit request or request not found.'}, status=400)

@manager_required
def reject_demand_edit_request_api(request, request_id):
    manager_profile = get_object_or_404(Manager, user=request.user)
    if manager_profile.handle_demand_edit_request(request_id, approve=False):
        return JsonResponse({'success': True, 'message': 'Demand edit request rejected.'})
    else:
        return JsonResponse({'success': False, 'message': 'Failed to reject demand edit request or request not found.'}, status=400)
