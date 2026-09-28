from rest_framework import serializers


class VersionRequiredMixin:
    """PATCH with partial=True skips required fields: refuse a missing ``version`` as 400, never a 500
    (review 2026-09-28, BIZ-13)."""

    def validate(self, attrs):
        if "version" not in attrs:
            raise serializers.ValidationError({"version": ["هذا الحقل مطلوب."]})
        return super().validate(attrs)


class ReasonSerializer(serializers.Serializer):
    """Body of reversal/cancel actions that only need a reason."""

    reason = serializers.CharField(max_length=300)
