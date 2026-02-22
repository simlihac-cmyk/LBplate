from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm

from .models import DiscussionMessage, FreeBoardComment, FreeBoardPost


class SignUpForm(UserCreationForm):
    email = forms.EmailField(label='이메일', max_length=254)

    class Meta(UserCreationForm.Meta):
        model = get_user_model()
        fields = ('username', 'email', 'password1', 'password2')

    def clean_email(self):
        email = (self.cleaned_data.get('email') or '').strip().lower()
        if not email:
            raise forms.ValidationError('이메일을 입력해주세요.')

        user_model = get_user_model()
        if user_model.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('이미 사용 중인 이메일입니다.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']
        if commit:
            user.save()
        return user


class FreeBoardPostForm(forms.ModelForm):
    class Meta:
        model = FreeBoardPost
        fields = ('title', 'content')
        widgets = {
            'title': forms.TextInput(attrs={'maxlength': 120, 'placeholder': '제목을 입력하세요'}),
            'content': forms.Textarea(attrs={'rows': 12, 'placeholder': '자유롭게 이야기를 남겨주세요'}),
        }

    def clean_title(self):
        title = (self.cleaned_data.get('title') or '').strip()
        if len(title) < 2:
            raise forms.ValidationError('제목은 2자 이상 입력해주세요.')
        return title


class FreeBoardCommentForm(forms.ModelForm):
    class Meta:
        model = FreeBoardComment
        fields = ('content',)
        widgets = {
            'content': forms.Textarea(attrs={'rows': 3, 'placeholder': '댓글을 입력하세요'}),
        }

    def clean_content(self):
        content = (self.cleaned_data.get('content') or '').strip()
        if len(content) < 1:
            raise forms.ValidationError('댓글 내용을 입력해주세요.')
        if len(content) > 2000:
            raise forms.ValidationError('댓글은 2000자 이하로 입력해주세요.')
        return content


class DiscussionMessageForm(forms.ModelForm):
    class Meta:
        model = DiscussionMessage
        fields = ('content',)
        widgets = {
            'content': forms.Textarea(attrs={'rows': 4, 'placeholder': '주제에 대한 의견을 남겨주세요'}),
        }

    def clean_content(self):
        content = (self.cleaned_data.get('content') or '').strip()
        if len(content) < 2:
            raise forms.ValidationError('메시지는 2자 이상 입력해주세요.')
        if len(content) > 3000:
            raise forms.ValidationError('메시지는 3000자 이하로 입력해주세요.')
        return content
