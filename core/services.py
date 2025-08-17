from datetime import date, timedelta
from django.db import transaction

def get_team_total_capacity_for_date_helper(team_obj: 'Team', target_date: date):
    from core.models import TeamDailySchedule 
    try:
        schedule_entry = TeamDailySchedule.objects.get(team=team_obj, date=target_date)
        return schedule_entry.team_capacity
    except TeamDailySchedule.DoesNotExist:
        return 0.0

def get_hours_allocated_for_date_helper(team_obj, target_date):
    from core.models import TeamDailySchedule
    try:
        schedule_entry = TeamDailySchedule.objects.get(team=team_obj, date=target_date)
        return schedule_entry.hours_allocated
    except TeamDailySchedule.DoesNotExist:
        return 0.0

@transaction.atomic
def change_employee_capacity_for_range(employee_id, target_start_date, target_end_date, new_capacity_hours):
    from core.models import Employee, Capacity, CapacityChangeRequest
    if not isinstance(target_start_date, date) or not isinstance(target_end_date, date):
        raise TypeError("target_start_date and target_end_date must be datetime.date objects.")
    
    if target_start_date > target_end_date:
        raise ValueError("target_start_date cannot be after target_end_date.")

    if not isinstance(new_capacity_hours, (int, float)) or new_capacity_hours < 0:
        raise ValueError("new_capacity_hours must be a non-negative number.")

    
    try:
        employee = Employee.objects.select_related('team').get(pk=employee_id)
    except Employee.DoesNotExist:
        raise ValueError(f"Employee with ID {employee_id} not found.")
    
    dates_to_update_team_capacity = set()
    current_date = target_start_date
    
    capacities_to_bulk_upsert = [] 

    while current_date <= target_end_date:
        capacity_entry = Capacity.objects.filter(employee=employee, date=current_date).first()

        if capacity_entry:
            capacity_entry.capacity_hours = new_capacity_hours
        else:
            capacity_entry = Capacity(employee=employee, date=current_date, capacity_hours=new_capacity_hours)
        
        capacities_to_bulk_upsert.append(capacity_entry)
        dates_to_update_team_capacity.add(current_date)
        current_date += timedelta(days=1)
    
        new_capacities = [c for c in capacities_to_bulk_upsert if c.pk is None]
        existing_capacities = [c for c in capacities_to_bulk_upsert if c.pk is not None]

        if new_capacities:
            Capacity.objects.bulk_create(new_capacities, ignore_conflicts=True)

        if existing_capacities:
            Capacity.objects.bulk_update(existing_capacities, ['capacity_hours'])

    print(f"Employee '{employee.user.first_name}' (ID: {employee.employee_ID})'s capacity updated for "
          f"{target_start_date} to {target_end_date} to {new_capacity_hours:.2f} hours.")

    if employee.team:
        for d_date in dates_to_update_team_capacity:
            employee.team.update_aggregated_capacity(d_date)
    else:
        print(f"Note: Employee '{employee.user.first_name()}' is not assigned to a team. Team capacity will not be updated.")


def get_teams_meeting_deadline(desired_end_date, proposed_start_date, hours_predicted):
        from .models import Demand, Team

        dummy_demand = Demand.objects.create (
            demand_name = "sample demand",
            start_date = proposed_start_date,
            hours_needed = hours_predicted
        )

        if not isinstance(desired_end_date, date):
            raise TypeError("desired_end_date must be a datetime.date object.")
        if not isinstance(proposed_start_date, date):
            raise TypeError("proposed_start_date must be a datetime.date object.")
        if not isinstance(hours_predicted, (int, float)) or hours_predicted < 0:
            raise ValueError("hours_predicted must be a non-negative number.")

        if proposed_start_date > desired_end_date:
            raise ValueError("proposed_start_date cannot be after desired_end_date.")

        suitable_teams = []
        all_teams = Team.objects.all()

        for team in all_teams:
            simulated_end_date = dummy_demand.simulate_demand_allocation(
                team,
                hours_predicted,
                proposed_start_date
            )

            if simulated_end_date and simulated_end_date <= desired_end_date:
                suitable_teams.append(team, 0)
            elif simulated_end_date>desired_end_date:
                suitable_teams = None
                
        
        dummy_demand.delete()

        return suitable_teams