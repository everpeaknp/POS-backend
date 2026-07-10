"""Tenant admin forms."""

from django import forms

from billing.account_limits import normalize_active_modules_for_plan
from billing.plans import get_plan_type_to_code_map
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
        plan_type = cleaned.get('plan_type') or getattr(self.instance, 'plan_type', 'free')
        plan_code = get_plan_type_to_code_map().get(plan_type, 'free')
        normalized = normalize_active_modules_for_plan(plan_code, modules)
        cleaned['active_modules'] = normalized
        cleaned['active_module_choices'] = normalized
        return cleaned

    def save(self, commit=True):
        self.instance.active_modules = self.cleaned_data.get('active_module_choices') or []
        return super().save(commit=commit)
