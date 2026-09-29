from rest_framework import serializers

from . import rules
from .models import Role, User


def _validate_pin(value):
    if not rules.is_valid_pin(value):
        raise serializers.ValidationError("رمز الدخول يجب أن يكون من 4 إلى 6 أرقام.")
    return value


class LoginUserSerializer(serializers.ModelSerializer):
    """Shown on the login screen's user picker: names only."""

    class Meta:
        model = User
        fields = ["id", "full_name", "role"]


class UserSerializer(serializers.ModelSerializer):
    has_recovery_code = serializers.SerializerMethodField(help_text="The owner has a one-time recovery code.")
    recovery_code = serializers.SerializerMethodField(
        help_text="Only in the answer that created it (the owner's password was set): write it down, it is not stored."
    )

    def get_has_recovery_code(self, obj) -> bool:
        return bool(obj.recovery_code_hash)

    def get_recovery_code(self, obj) -> str | None:
        return getattr(obj, "new_recovery_code", None)

    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "full_name",
            "role",
            "is_active",
            "last_login",
            "locked_until",
            "default_password",
            "default_pin",
            "email",
            "has_recovery_code",
            "recovery_code",
            "version",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class PinLoginSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()
    pin = serializers.CharField(max_length=6)


class PasswordLoginSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    password = serializers.CharField(max_length=128, style={"input_type": "password"})


class SessionSerializer(serializers.Serializer):
    token = serializers.CharField()
    user = UserSerializer()


class ConfirmSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=128, style={"input_type": "password"})


class ConfirmTokenSerializer(serializers.Serializer):
    confirm_token = serializers.CharField()
    expires_in = serializers.IntegerField(help_text="Seconds.")


class UserCreateSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    full_name = serializers.CharField(max_length=120)
    role = serializers.ChoiceField(choices=Role.choices)
    pin = serializers.CharField(max_length=6, validators=[_validate_pin])
    password = serializers.CharField(min_length=8, max_length=128, required=False, allow_blank=False)
    email = serializers.EmailField(required=False, allow_blank=True, default="", help_text="For «نسيت كلمة المرور؟».")

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("اسم المستخدم مستخدم من قبل.")
        return value

    def validate(self, attrs):
        if rules.is_manager(attrs["role"]) and not attrs.get("password"):
            raise serializers.ValidationError({"password": "كلمة المرور مطلوبة للمدير والمالك."})
        return attrs


class UserUpdateSerializer(serializers.Serializer):
    version = serializers.IntegerField(min_value=1)
    username = serializers.CharField(max_length=64, required=False, help_text="The owner or a manager renames a login.")
    full_name = serializers.CharField(max_length=120, required=False)
    role = serializers.ChoiceField(choices=Role.choices, required=False)
    is_active = serializers.BooleanField(required=False)
    password = serializers.CharField(min_length=8, max_length=128, required=False, allow_blank=False)
    email = serializers.EmailField(required=False, allow_blank=True, help_text="Empty removes it.")


class RecoverPasswordSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    email = serializers.CharField(
        max_length=254, required=False, allow_blank=True, default="", help_text="Staff accounts."
    )
    recovery_code = serializers.CharField(
        max_length=40, required=False, allow_blank=True, default="", help_text="The owner's one-time recovery code."
    )
    password = serializers.CharField(
        min_length=8, max_length=128, style={"input_type": "password"}, help_text="The new password."
    )


class RecoveryCodeSerializer(serializers.Serializer):
    recovery_code = serializers.CharField(allow_null=True, help_text="A new one for the owner; null for staff.")


class ResetPinSerializer(serializers.Serializer):
    pin = serializers.CharField(max_length=6, validators=[_validate_pin])
