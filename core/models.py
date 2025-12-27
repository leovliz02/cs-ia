from datetime import date, timedelta
from django.conf import settings
from django.utils import timezone
from django.db import models, transaction
from django.contrib.auth.models import AbstractUser, Group, Permission
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db.models import Sum
from core.services import get_team_total_capacity_for_date_helper, get_hours_allocated_for_date_helper, change_employee_capacity_for_range, simulate_demand_allocation




class DemandDailyAllocation(models.Model):
    demand = models.ForeignKey("Demand", on_delete=models.CASCADE, related_name='daily_allocations')
    team = models.ForeignKey("Team", on_delete=models.CASCADE, related_name='demand_allocations_by_team')
    date = models.DateField()
    hours_allocated = models.FloatField(default=0)

    class Meta:
        unique_together = ('demand', 'date')

    def __str__(self):
        return f"{self.demand.demand_name} - {self.date}: {self.hours_allocated} hours"

class User(AbstractUser):
    is_manager = models.BooleanField(default=False)
    groups = models.ManyToManyField(
        Group,
        related_name="core_custom_users_groups",
        blank=True,
        related_query_name="user",
    )

    user_permissions = models.ManyToManyField(
        Permission,
        related_name="core_custom_users_permissions",
        blank=True,
        help_text="Specific permissions for this user.",
        related_query_name="user",
    )

    def __str__ (self):
        return self.username or self.get_full_name() or self.email or f"User {self.pk}"

class Employee (models.Model):
    employee_ID = models.AutoField(primary_key=True)
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='employee_profile')
    team = models.ForeignKey ("Team", on_delete=models.SET_NULL, null=True, blank=True, related_name='members')
    standard_daily_capacity = models.FloatField (default=8.0)

    def __str__ (self):
        return self.user.get_full_name() or self.user.username or f"Employee {self.employee_ID}"

    @transaction.atomic
    def send_capacity_change_request(self, new_capacity_for_range, start_date, end_date):
        today = timezone.localdate()
        one_week_from_now = today + timedelta(days=7)

        if start_date > end_date:
            raise ValueError("Start date cannot be after end date.")

        delta_days = (end_date - start_date).days + 1
        if not (1 <= delta_days <= 24):
            raise ValueError(f"Capacity change request must be for between 1 and 24 days. You requested {delta_days} days.")

        if start_date < one_week_from_now:
            raise ValueError(f"Capacity change request must be for dates at least one week away from today.")

        if not self.team:
            raise ValueError("Employee must be assigned to a team to send capacity change requests involving team schedule validation.")
        

        current_date = start_date
        clash_details = False
        

        while current_date <= end_date:
            employee_current_effective_capacity = Capacity.get_effective_capacity(self, current_date)
            change_in_employee_capacity =  employee_current_effective_capacity - new_capacity_for_range 
            team_current_total_capacity = get_team_total_capacity_for_date_helper(self.team, current_date)
            team_scheduled_hours = get_hours_allocated_for_date_helper(self.team, current_date)
            team_potential_new_total_capacity = team_current_total_capacity + change_in_employee_capacity

            if team_potential_new_total_capacity < team_scheduled_hours:
                clash_details=True

            current_date += timedelta(days=1)

        if clash_details:
            if new_capacity_for_range > 8.0:
                clash_message = "Cannot fulfill - Consider requesting a capacity below 8 hours."
            else:
                if new_capacity_for_range < 0:
                    clash_message = "Cannot fulfill - Capacity must be positive."
                else:
                    clash_message = "Cannot fulfill - Would cause clash with scheduled demands."
                    raise ValueError(clash_message)

        request = CapacityChangeRequest.objects.create(
            employee=self,
            start_date=start_date,
            end_date=end_date,
            new_capacity=new_capacity_for_range,
            status='Pending'
        )
        print(f"Capacity change request for {self.user.get_full_name()} from {start_date} to {end_date} (new cap: {new_capacity_for_range} hrs) sent successfully. Request ID: {request.pk}")
    
    def send_demand_edit_request(self, demand, new_name, new_status):
        if not (new_name or new_status):
            raise ValueError("Either new_name or new_status must be provided for a demand edit request.")

        if new_status and new_status not in [choice[0] for choice in Demand.demand_completion_status_choices]:
            raise ValueError(f"Invalid new_status '{new_status}'. Must be one of {Demand.demand_completion_status_choices}.")

        DemandEditRequest.objects.create(
            employee=self,
            demand=demand,
            new_name=new_name if new_name is not None else demand.demand_name,
            new_status=new_status if new_status is not None else demand.demand_completion_status,
            status='pending'
        )
        print(f"Demand edit request for Demand ID {demand.demandID} sent by {self.user.get_full_name()}.")

class TeamDailySchedule(models.Model):
    team = models.ForeignKey("Team", on_delete=models.CASCADE, related_name='daily_schedules')
    date = models.DateField()
    hours_allocated = models.FloatField(default=0)
    @property
    def team_capacity(self):
        return (
            Capacity.objects
            .filter(employee__team=self.team, date=self.date)
            .aggregate(total=Sum("capacity_hours"))["total"]
            or 0.0
        )

    class Meta:
        unique_together = ('team', 'date')

    def __str__(self):
        return f"Team {self.team.team_name} on {self.date}: Cap {self.team_capacity}h, Alloc {self.hours_allocated}h"
    
class Team (models.Model):
    team_ID = models.AutoField(primary_key=True)
    manager = models.ForeignKey("Manager", on_delete=models.SET_NULL, null=True, related_name='teams_managed')
    team_name = models.CharField(max_length = 100)
    on_time_completions = models.IntegerField(default=0)
    overdue_demands = models.IntegerField(default=0)
    early_completion = models.IntegerField(default=0)

    def __str__ (self):
        return self.team_name
    
    @property
    def get_member_count (self):
        return Employee.objects.filter(
            team = self
        ).count

    @transaction.atomic
    def update_aggregated_capacity(self, target_date):
        total_employee_capacity = Capacity.objects.filter(
            employee__team=self,
            date=target_date
        ).aggregate(Sum('capacity_hours'))['capacity_hours__sum'] or 0.0

        daily_schedule, _ =TeamDailySchedule.objects.get_or_create(
            team=self,
            date=target_date,
            defaults={'hours_allocated': 0}
        )

        daily_schedule.save()
        print(
        f"Team '{self.team_name}' capacity for {target_date} "
        f"updated to {total_employee_capacity:.2f} hours."
    )
    def get_free_time_on (self,target_date):
        try:
            schedule = self.daily_schedules.get(date=target_date)
            team_capacity = schedule.team_capacity
            used_time = schedule.hours_allocated
        except TeamDailySchedule.DoesNotExist:
            team_capacity = self.get_member_count() * 8.0
            used_time = 0.0

        return max(team_capacity - used_time, 0)

    @transaction.atomic
    def update_team_daily_allocation_summary(self, target_date):
        total_allocated_hours = (
            DemandDailyAllocation.objects
            .filter(team=self, date=target_date)
            .aggregate(total=Sum("hours_allocated"))["total"]
            or 0.0
        )

        schedule, created = TeamDailySchedule.objects.get_or_create(
            team=self,
            date=target_date,
            defaults={"hours_allocated": 0.0},
        )

        schedule.hours_allocated = total_allocated_hours
        schedule.save()

        print(
            f"Team '{self.team_name}' daily allocation summary "
            f"for {target_date} updated to {total_allocated_hours:.2f} hours."
        )


class Manager(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='manager_profile')

    def __str__(self):
        return self.user.get_full_name() or self.user.username or f"Manager {self.pk}"

    @transaction.atomic
    def handle_capacity_request(self, request_id: int, approve: bool = True):
        try:
            req = CapacityChangeRequest.objects.select_related('employee__user').get(id=request_id)
        except CapacityChangeRequest.DoesNotExist:
            print(f"CapacityChangeRequest with ID {request_id} not found.")
            return False

        if approve:
            try:
                change_employee_capacity_for_range(
                    employee_id=req.employee.pk,
                    target_start_date=req.start_date,
                    target_end_date=req.end_date,
                    new_capacity_hours=req.new_capacity
                )
                req.status = 'Approved'
                Notifications.objects.create(
                    notification_message=f"Your capacity change request for {req.start_date} to {req.end_date} (new capacity: {req.new_capacity} hrs) has been APPROVED.",
                    employee=req.employee
                )
                print(f"Capacity change request {request_id} approved for {req.employee.user.get_full_name()}.")
            except Exception as e:
                req.status = 'Rejected'
                Notifications.objects.create(
                    notification_message=f"Your capacity change request for {req.start_date} to {req.end_date} (new capacity: {req.new_capacity} hrs) FAILED during approval process: {e}",
                    employee=req.employee
                )
                print(f"Error approving capacity change request {request_id}: {e}")
                req.save()
                raise
        else:
            req.status = 'Rejected'
            Notifications.objects.create(
                notification_message=f"Your capacity change request for {req.start_date} to {req.end_date} (new capacity: {req.new_capacity} hrs) has been DECLINED.",
                employee=req.employee
            )
            print(f"Capacity change request {request_id} declined for {req.employee.user.get_full_name()}.")

        req.save()
        req.delete()
        return True

    @transaction.atomic
    def handle_demand_edit_request(self, request_id, approve):
        try:
            req = DemandEditRequest.objects.select_related('demand', 'employee__user').get(id=request_id)
        except DemandEditRequest.DoesNotExist:
            print(f"DemandEditRequest with ID {request_id} not found.")
            return False

        demand = req.demand

        if approve:
            name_changed = False
            status_changed = False

            if req.new_name is not None and demand.demand_name != req.new_name:
                demand.demand_name = req.new_name
                name_changed = True

            if req.new_status is not None and demand.demand_completion_status != req.new_status:
                demand.update_demand_status(req.new_status)
                status_changed = True

            demand.save()

            if demand.team:
                for team_member in demand.team.members.all():
                    if name_changed:
                        Notifications.objects.create(
                            notification_message=f"Demand name for Demand ID {demand.demandID} is now '{demand.demand_name}'.",
                            employee=team_member
                        )
                    if status_changed:
                        Notifications.objects.create(
                            notification_message=f"Demand '{demand.demand_name}' is now '{demand.demand_completion_status}'.",
                            employee=team_member
                        )

            Notifications.objects.create(
                notification_message=f"Your request to edit Demand '{req.demand.demand_name}' (ID: {req.demand.demandID}) has been APPROVED.",
                employee=req.employee
            )
            print(f"Demand edit request {request_id} approved for {req.employee.user.get_full_name()}.")
            req.status = 'Approved'
        else:
            req.status = 'Rejected'
            Notifications.objects.create(
                notification_message=f"Your request to edit details of Demand '{req.demand.demand_name}' (ID: {req.demand.demandID}) has been DECLINED.",
                employee=req.employee
            )
            print(f"Demand edit request {request_id} declined for {req.employee.user.get_full_name()}.")

        req.save()
        req.delete()
        return True

class Demand (models.Model):
    demand_completion_status_choices = [
        ('Pending', 'Pending'),
        ('In Progress', 'In Progress'),
        ('Finished', 'Finished'),
    ]

    demandID = models.AutoField(primary_key = True)
    demand_name = models.CharField(max_length=100, null=True)
    team = models.ForeignKey (Team, on_delete=models.SET_NULL, null=True, related_name='demands')
    time_needed = models.FloatField(default=0)
    demand_completion_status = models.CharField(max_length=20, default='Pending', choices=demand_completion_status_choices)
    demand_assignment_status = models.BooleanField(default=False)
    start_date = models.DateField(null=True, blank=True)
    estimated_end_date = models.DateField(null=True, blank=True)
    actual_end_date = models.DateField(null=True, blank = True)

    def __str__ (self):
        return self.demand_name

    def clear_previous_allocations(self):
        self.daily_allocations.all().delete()
        print(f"Cleared all daily allocations for Demand ID {self.demandID}.")
        
    
    def set_assigned_team(self, team_id, hours_predicted, start_date):
        self.clear_previous_allocations()
        if hours_predicted <= 0:
            raise ValueError("Hours predicted must be greater than 0.")

        if not isinstance(start_date, date):
            raise TypeError("start_date must be a datetime.date object.")
        
        target_team = Team.objects.get(team_ID=team_id)

        simulated_end_date = simulate_demand_allocation(
            target_team, hours_predicted, start_date
        )
        if simulated_end_date is None:
            raise ValueError
        (f"Team '{target_team.team_name}' cannot meet the demand within 30 days.")

        remaining_hours = hours_predicted
        current_date = start_date
        daily_allocations = []

        MAX_DAYS = 30
        days_used = 0

        print(
            f"Allocating {hours_predicted:.2f}h for Demand '{self.demand_name}' "
            f"to Team '{target_team.team_name}' starting {start_date}"
        )

        while remaining_hours > 0 and days_used < MAX_DAYS:
            team_capacity = target_team.get_free_time_on(current_date)

            print(
                f"{current_date} | Capacity: {team_capacity:.2f}h | "
            )

            if team_capacity > 0:
                hours_today = min(remaining_hours, team_capacity)

                daily_allocations.append(
                    DemandDailyAllocation(
                        demand=self,
                        team=target_team,
                        date=current_date,
                        hours_allocated=hours_today
                    )
                )
                remaining_hours -= hours_today

                print(f"→ Allocated {hours_today:.2f}h")

            current_date += timedelta(days=1)
            days_used += 1

        if remaining_hours > 0:
            raise ValueError(
                "Demand allocation stalled — insufficient team capacity within 30 days."
            )

        with transaction.atomic():
            self.team = target_team
            self.time_needed = hours_predicted
            self.start_date = start_date
            self.estimated_end_date = simulated_end_date
            self.demand_assignment_status = True
            self.save()

            DemandDailyAllocation.objects.bulk_create(daily_allocations)

            for allocation in daily_allocations:
                target_team.update_team_daily_allocation_summary(allocation.date)

        notif_message = (
            f"Demand '{self.demand_name}' assigned to Team '{target_team.team_name}'. "
            f"Estimated completion: {self.estimated_end_date.strftime('%Y-%m-%d')}."
        )
        for employee in target_team.members.all():
            Notifications.objects.create(
                notification_message=notif_message,
                employee=employee
            )

        print(
            f"Demand '{self.demand_name}' successfully assigned "
            f"({hours_predicted:.2f}h over {len(daily_allocations)} days)."
        )


    @transaction.atomic
    def update_demand_status (self, new_status=None):
            date_today = timezone.localdate()
            if new_status not in [choice[0] for choice in self.demand_completion_status_choices] and new_status is not None:
                raise ValueError(f"Invalid demand status: '{new_status}'. Must be one of {[choice[0] for choice in self.demand_completion_status_choices]}.")

            if not self.team:
                print(f"Demand '{self.demand_name}' (ID: {self.demandID}) has no assigned team. Status update skipped.")
                return
            elif self.demand_completion_status =='Finished':
                return
            else:
                if self.demand_completion_status != 'Finished':
                    old_status = self.demand_completion_status

                    if new_status is not None:
                        print (f"Updating Demand '{self.demand_name}' (ID: {self.demandID}) status from '{old_status}' to '{new_status}'.")
                        self.demand_completion_status = new_status
                        if new_status == 'In Progress':
                            self.start_date = timezone.localdate()
                            print(f"Start date for Demand '{self.demand_name}' (ID: {self.demandID}) set to today: {self.start_date}.") 
                            print(f"Demand '{self.demand_name}' (ID: {self.demandID}) status updated to 'In Progress'.")
                        elif new_status == 'Finished':
                            self.clear_previous_allocations()
                            self.actual_end_date = date_today
                            print(f"Demand '{self.demand_name}' (ID: {self.demandID}) status updated to 'Finished'.")
                            if self.estimated_end_date:
                                delta_days = (date_today - self.estimated_end_date).days
                                if delta_days > 0:
                                    self.team.overdue_demands += 1
                                    self.team.save()
                                    message = f"Demand {self.demand_name} completed {delta_days} days overdue."
                                    print (message)
                                    for employee in self.team.members.all():
                                        Notifications.objects.create(notification_message=message, employee=employee)
                                elif delta_days < 0:
                                    self.team.early_completion += 1
                                    self.team.save()
                                    message = f"Demand {self.demand_name} completed {abs(delta_days)} days early."
                                    print (message)
                                    for employee in self.team.members.all():
                                        Notifications.objects.create(notification_message=message, employee=employee)
                                else:
                                    if delta_days == 0:
                                        self.team.on_time_completions += 1
                                        self.team.save()
                                        message = f"Demand {self.demand_name} completed on time."
                                        print (message)
                                        for employee in self.team.members.all():
                                            Notifications.objects.create(notification_message=message, employee=employee)

                    if date_today >= self.start_date and self.demand_completion_status!='In Progress' and new_status==None:
                                print (f"Auto-updating Demand '{self.demand_name}' (ID: {self.demandID}) status based on dates.")
                                self.demand_completion_status = 'In Progress'
                                message = (f"Demand '{self.demand_name}' (ID: {self.demandID}) status auto-updated to 'In Progress' on start date.")
                                print (message)
                                for employee in self.team.members.all():
                                    Notifications.objects.create(notification_message=message, employee=employee)
                
            
                self.save()
                print(f"Demand '{self.demand_name}' (ID: {self.demandID}) status updated to '{new_status}'.")

                message = f"Demand '{self.demand_name}' is now '{self.demand_completion_status}'."
                for employee in self.team.members.all():
                    Notifications.objects.create(notification_message=message, employee=employee)

class Notifications (models.Model):
    notification_ID = models.AutoField(primary_key=True)
    notification_message = models.CharField(max_length=10000)
    is_read = models.BooleanField(default=False)
    employee = models.ForeignKey ("Employee", on_delete=models.CASCADE, related_name='notifications')
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.employee.user.get_full_name() or self.employee.user.username}: {self.notification_message[:50]}..."

class CapacityChangeRequest (models.Model):
    employee = models.ForeignKey("Employee", on_delete=models.CASCADE, related_name='capacity_change_requests')
    new_capacity = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(15.0)]
    )
    start_date = models.DateField ()
    end_date = models.DateField ()
    STATUS_CHOICES = [
        ('Pending', 'Pending'),
        ('Approved', 'Approved'),
        ('Rejected', 'Rejected'),
    ]
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='Pending')

    def __str__(self):
        return f"Capacity Req for {self.employee.user.get_full_name()} ({self.start_date} to {self.end_date}): {self.new_capacity}h - {self.status}"

class DemandEditRequest(models.Model):
    demand = models.ForeignKey(Demand, on_delete=models.CASCADE, related_name='edit_requests')
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name='demand_edit_requests')

    new_name = models.CharField(max_length=255, null=True, blank=True)
    new_status = models.CharField(max_length=20, choices=Demand.demand_completion_status_choices, null=True, blank=True)
    STATUS_CHOICES = [
        ('Pending'),
        ('Approved'),
        ('Rejected'),
    ]

    def __str__(self):
        return f'Edit Req for Demand {self.demand.demandID} by {self.employee.user.get_full_name()}: Name="{self.new_name or "N/A"}", Status="{self.new_status or "N/A"}" - {self.status}'

class Capacity(models.Model):
    employee = models.ForeignKey('Employee', on_delete=models.CASCADE, related_name='daily_capacities')
    date = models.DateField()
    capacity_hours = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(15.0)],
        default=8.0
    )

    class Meta:
        unique_together = ('employee', 'date')
        ordering = ['date']

    def __str__(self):
        return f"{self.employee.user.get_full_name()} ({self.date}): {self.capacity_hours} hrs"

    @classmethod
    def get_effective_capacity(self, employee_obj, target_date):
        try:
            capacity_entry = self.objects.get(employee=employee_obj, date=target_date)
            return capacity_entry.capacity_hours
        except self.DoesNotExist:
            return employee_obj.standard_daily_capacity