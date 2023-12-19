from django.contrib import admin
from core.models import *


class MachineTypesModelAdmin(admin.ModelAdmin):
    list_display = ['machine_type']
    search_fields = ['machine_type']


class MachineModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in MachineModel._meta.fields]
    list_filter = [field.name for field in MachineModel._meta.fields ]


class RoleModelAdmin(admin.ModelAdmin):
    list_display = ['role_name']
    list_filter = ['role_name']


class WorkingAreaModelAdmin(admin.ModelAdmin):
    list_display = ['area_name']
    search_fields = ['area_name']


class PositionsModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in PositionsModel._meta.fields]
    list_filter = [field.name for field in PositionsModel._meta.fields ]
    search_fields = [field.name for field in PositionsModel._meta.fields]


class CustomUserModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in CustomUserModel._meta.fields]
    list_filter = [field.name for field in CustomUserModel._meta.fields ]
    search_fields = [field.name for field in CustomUserModel._meta.fields]


class ShiftModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in ShiftModel._meta.fields]
    list_filter = [field.name for field in ShiftModel._meta.fields ]
    date_hierarchy = 'start_time'


class OrdersModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in OrdersModel._meta.fields]
    list_filter = ['user', 'machine', 'related_to_shift', 'hold_ended' ,'ended_early']
    date_hierarchy = 'start_time'


class ReportsModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in ReportsModel._meta.fields]
    list_filter = [field.name for field in ReportsModel._meta.fields ]
    search_fields = [field.name for field in ReportsModel._meta.fields]
    date_hierarchy = 'start_time'
    readonly_fields = ['start_time',]


class UserRequestsModelAdmin(admin.ModelAdmin):
    list_display = [field.name for field in UserRequestsModel._meta.fields]
    list_filter = [field.name for field in UserRequestsModel._meta.fields ]
    search_fields = [field.name for field in UserRequestsModel._meta.fields]
    date_hierarchy = 'start_time'
    readonly_fields = ['start_time',]


admin.site.register(UserRequestsModel, UserRequestsModelAdmin)
admin.site.register(MachineTypesModel, MachineTypesModelAdmin)
admin.site.register(ReportsModel, ReportsModelAdmin)
admin.site.register(OrdersModel, OrdersModelAdmin)
admin.site.register(ShiftModel, ShiftModelAdmin)
admin.site.register(CustomUserModel, CustomUserModelAdmin)
admin.site.register(PositionsModel, PositionsModelAdmin)
admin.site.register(RoleModel, RoleModelAdmin)
admin.site.register(MachineModel, MachineModelAdmin)
admin.site.register(WorkingAreaModel, WorkingAreaModelAdmin)
