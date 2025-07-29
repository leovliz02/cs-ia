from django.contrib import admin
from core.models import CapacityChangeRequest, DemandEditRequest, Employee, Manager, Team, Demand, DemandDailyAllocation, Capacity, TeamDailySchedule, Notifications, User

admin.site.register(Demand)
admin.site.register(Manager)
admin.site.register(Employee)
admin.site.register(CapacityChangeRequest)
admin.site.register(DemandEditRequest)
admin.site.register(TeamDailySchedule) 
admin.site.register(DemandDailyAllocation)
admin.site.register(Capacity)
admin.site.register(Team)
admin.site.register(Notifications)
admin.site.register(User)