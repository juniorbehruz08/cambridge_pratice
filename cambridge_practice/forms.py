from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .models import Feedback


class RegisterForm(UserCreationForm):
    email = forms.EmailField(required=False)

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')


class FeedbackForm(forms.ModelForm):
    feedback_type = forms.ChoiceField(
        choices=Feedback.TYPE_CHOICES,
        widget=forms.RadioSelect,
        initial=Feedback.TYPE_SUGGESTION,
    )
    image = forms.ImageField(required=False)

    class Meta:
        model = Feedback
        fields = ('feedback_type', 'name', 'email', 'page_url', 'message', 'image')
        widgets = {
            'message': forms.Textarea(attrs={'rows': 7}),
        }

    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return image

        if image.size > 5 * 1024 * 1024:
            raise forms.ValidationError('Please upload an image smaller than 5 MB.')

        content_type = getattr(image, 'content_type', '')
        if content_type and not content_type.startswith('image/'):
            raise forms.ValidationError('Please upload an image file.')

        return image
