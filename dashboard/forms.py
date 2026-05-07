from django import forms
from django.contrib.auth.forms import AuthenticationForm
from users.models import current_academic_year, NotificationCampaign, Group


class LoginForm(AuthenticationForm):
    username = forms.CharField(
        label="Foydalanuvchi nomi",
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'username',
            'autofocus': True,
        })
    )
    password = forms.CharField(
        label="Parol",
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': '••••••••',
        })
    )


class ExcelImportForm(forms.Form):
    file = forms.FileField(
        label="Excel fayl (.xlsx)",
        widget=forms.FileInput(attrs={
            'class': 'form-control',
            'accept': '.xlsx',
        })
    )
    academic_year = forms.CharField(
        label="O'quv yili",
        max_length=9,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '2024-2025',
        })
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'academic_year' not in (self.initial or {}):
            self.fields['academic_year'].initial = current_academic_year()

    def clean_academic_year(self):
        value = self.cleaned_data['academic_year'].strip()
        parts = value.split('-')
        if len(parts) != 2:
            raise forms.ValidationError("Format: 2024-2025 bo'lishi kerak.")
        try:
            y1, y2 = int(parts[0]), int(parts[1])
            if y2 - y1 != 1:
                raise forms.ValidationError("Yillar ketma-ket bo'lishi kerak (masalan 2024-2025).")
        except ValueError:
            raise forms.ValidationError("Format: 2024-2025 bo'lishi kerak.")
        return value

    def clean_file(self):
        f = self.cleaned_data['file']
        if not f.name.endswith('.xlsx'):
            raise forms.ValidationError("Faqat .xlsx formatdagi fayllar qabul qilinadi.")
        return f


class ConfirmPaymentForm(forms.Form):
    confirmed_amount = forms.DecimalField(
        label="To'lagan summa (so'm)",
        required=False,
        min_value=0,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': "Masalan: 2500000",
            'step': '1000',
        })
    )
    note = forms.CharField(
        label="Izoh (ixtiyoriy)",
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': "Masalan: Naqd to'ladi, kvitansiya #123",
        })
    )


class NotificationCampaignForm(forms.ModelForm):
    class Meta:
        model = NotificationCampaign
        fields = [
            'groups', 'student_type_filter', 'target_debt_tier',
            'recipients', 'message_text',
            'start_date', 'end_date', 'send_time',
        ]
        widgets = {
            'groups': forms.CheckboxSelectMultiple(),
            'start_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control form-control-sm'}
            ),
            'end_date': forms.DateInput(
                attrs={'type': 'date', 'class': 'form-control form-control-sm'}
            ),
            'send_time': forms.TimeInput(
                attrs={'type': 'time', 'class': 'form-control form-control-sm'}
            ),
            'message_text': forms.Textarea(
                attrs={'class': 'form-control', 'rows': 5,
                       'placeholder': "Hurmatli talaba,\n\nXabarnoma matni..."}
            ),
            'student_type_filter': forms.Select(
                attrs={'class': 'form-select form-select-sm'}
            ),
            'target_debt_tier': forms.Select(
                attrs={'class': 'form-select form-select-sm'}
            ),
            'recipients': forms.Select(
                attrs={'class': 'form-select form-select-sm'}
            ),
        }

    def __init__(self, *args, accessible_groups=None, **kwargs):
        super().__init__(*args, **kwargs)
        if accessible_groups is not None:
            self.fields['groups'].queryset = accessible_groups
