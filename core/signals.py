from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

from .models import User, Manager, Employee

_DO_NOT_RECURSE_USER_SAVE = False
_DO_NOT_RECURSE_MANAGER_SAVE = False
_DO_NOT_RECURSE_EMPLOYEE_SAVE = False

@receiver(post_save, sender=User)
def create_or_update_profile_from_user(sender, instance, created, **kwargs):
    global _DO_NOT_RECURSE_USER_SAVE, _DO_NOT_RECURSE_EMPLOYEE_SAVE, _DO_NOT_RECURSE_MANAGER_SAVE
    if _DO_NOT_RECURSE_USER_SAVE:
        return

    _DO_NOT_RECURSE_USER_SAVE = True
    try:

        if not instance._state.adding and not created and not instance._state.db:
            return
        
        if instance.is_manager:
            if not hasattr(instance, 'manager_profile'):
                _DO_NOT_RECURSE_MANAGER_SAVE = True
                Manager.objects.create(user=instance)
                _DO_NOT_RECURSE_MANAGER_SAVE = False
                print(f"Signal: Created Manager profile for {instance.username} (is_manager=True).")
            

            if hasattr(instance, 'employee_profile'):
                _DO_NOT_RECURSE_EMPLOYEE_SAVE = True
                instance.employee_profile.delete()
                _DO_NOT_RECURSE_EMPLOYEE_SAVE = False
                print(f"Signal: Deleted Employee profile for {instance.username} (is_manager=True).")
        
        else:
            if not hasattr(instance, 'employee_profile'):
                _DO_NOT_RECURSE_EMPLOYEE_SAVE = True
                Employee.objects.create(user=instance)
                _DO_NOT_RECURSE_EMPLOYEE_SAVE = False
                print(f"Signal: Created Employee profile for {instance.username} (is_manager=False).")


    finally:
        _DO_NOT_RECURSE_USER_SAVE = False

@receiver(post_save, sender=Manager)
def sync_user_is_manager_on_manager_save(sender, instance, created, **kwargs):
    global _DO_NOT_RECURSE_USER_SAVE, _DO_NOT_RECURSE_MANAGER_SAVE
    if _DO_NOT_RECURSE_MANAGER_SAVE:
        return

    _DO_NOT_RECURSE_MANAGER_SAVE = True
    try:
        user = instance.user
        if not user.is_manager:
            _DO_NOT_RECURSE_USER_SAVE = True
            user.is_manager = True
            user.save(update_fields=['is_manager'])
            _DO_NOT_RECURSE_USER_SAVE = False
            print(f"Signal: User {user.username} is_manager set to True because Manager profile was saved/created.")
            
    finally:
        _DO_NOT_RECURSE_MANAGER_SAVE = False

@receiver(post_delete, sender=Manager)
def sync_user_is_manager_on_manager_delete(sender, instance, **kwargs):
    global _DO_NOT_RECURSE_USER_SAVE, _DO_NOT_RECURSE_MANAGER_SAVE
    if _DO_NOT_RECURSE_MANAGER_SAVE: 
        return

    user = instance.user
    if user: 
        if user.is_manager:
            _DO_NOT_RECURSE_USER_SAVE = True
            user.is_manager = False
            user.save(update_fields=['is_manager'])
            _DO_NOT_RECURSE_USER_SAVE = False
            print(f"Signal: User {user.username} is_manager set to False because Manager profile was deleted.")

@receiver(post_save, sender=Employee)
def sync_user_is_employee_on_employee_save(sender, instance, created, **kwargs):
    global _DO_NOT_RECURSE_USER_SAVE, _DO_NOT_RECURSE_EMPLOYEE_SAVE
    if _DO_NOT_RECURSE_EMPLOYEE_SAVE:
        return

    _DO_NOT_RECURSE_EMPLOYEE_SAVE = True
    try:
        user = instance.user
        if user.is_manager: 
            _DO_NOT_RECURSE_USER_SAVE = True
            user.is_manager = False 
            user.save(update_fields=['is_manager'])
            _DO_NOT_RECURSE_USER_SAVE = False
            print(f"Signal: User {user.username} is_manager set to False because Employee profile was saved/created.")
            
    finally:
        _DO_NOT_RECURSE_EMPLOYEE_SAVE = False

@receiver(post_delete, sender=Employee)
def sync_user_is_employee_on_employee_delete(sender, instance, **kwargs):
    global _DO_NOT_RECURSE_USER_SAVE, _DO_NOT_RECURSE_EMPLOYEE_SAVE
    if _DO_NOT_RECURSE_EMPLOYEE_SAVE: 
        return

    user = instance.user
    if user: 
        if not user.is_manager: 
            print(f"Signal: Employee profile for {user.username} deleted. User's role will be re-evaluated by User post_save.")