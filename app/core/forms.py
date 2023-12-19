from django import forms

from .models import ReportsModel


class ReportEditForm(forms.ModelForm):
    class Meta:
        model = ReportsModel
        fields = ['is_solved',]
