
from django import forms
from django.contrib.auth.hashers import check_password
from .models import Customer, CustomerPortalAuth


class LoginForm(forms.Form):
    phone_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 bg-gray-50 hover:bg-white',
            'placeholder': 'Enter your phone number',
            'id': 'phone_number'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'w-full px-4 py-3 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 bg-gray-50 hover:bg-white',
            'placeholder': 'Enter your password',
            'id': 'password'
        })
    )
    
    def clean(self):
        cleaned_data = super().clean()
        phone_number = cleaned_data.get('phone_number')
        password = cleaned_data.get('password')
        
        if phone_number and password:
            try:
                auth = CustomerPortalAuth.objects.get(
                    phone_number=phone_number,
                    is_active=True
                )
                
                if not check_password(password, auth.password_hash):
                    raise forms.ValidationError('Invalid password')
                
                cleaned_data['customer'] = auth.customer
                cleaned_data['auth'] = auth
                
            except CustomerPortalAuth.DoesNotExist:
                raise forms.ValidationError('Invalid phone number or password')
        
        return cleaned_data
