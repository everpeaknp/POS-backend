"""Tenant admin forms."""

from django import forms

from core_backend.platform_constants import AVAILABLE_MODULES
from tenants.models import Tenant


class TenantAdminForm(forms.ModelForm):
    active_module_choices = forms.MultipleChoiceField(
        choices=AVAILABLE_MODULES,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label='Active modules',
        help_text='Modules visible in the customer app sidebar for this organization.',
    )

    class Meta:
        model = Tenant
        fields = '__all__'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['active_module_choices'].initial = self.instance.active_modules or []
        self.fields['active_modules'].widget = forms.HiddenInput()
        self.fields['active_modules'].required = False

    def clean(self):
        cleaned = super().clean()
        modules = cleaned.get('active_module_choices') or []
        cleaned['active_modules'] = list(modules)
        return cleaned

    def save(self, commit=True):
        self.instance.active_modules = self.cleaned_data.get('active_module_choices') or []
        return super().save(commit=commit)
