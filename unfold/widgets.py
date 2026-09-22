from django import forms

class UnfoldAdminCheckboxSelectMultipleWidget(forms.CheckboxSelectMultiple):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UnfoldAdminTextareaWidget(forms.Textarea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UnfoldAdminPasswordWidget(forms.PasswordInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UnfoldAdminSelectWidget(forms.Select):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

class UnfoldAdminTextInputWidget(forms.TextInput):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
