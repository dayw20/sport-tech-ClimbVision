from django.contrib import admin
from .models import Job

@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = ("id", "status", "created_at", "updated_at")
    search_fields = ("id",)
    list_filter = ("status",)
