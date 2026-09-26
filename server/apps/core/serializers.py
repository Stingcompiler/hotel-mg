from rest_framework import serializers


class ReasonSerializer(serializers.Serializer):
    """Body of reversal/cancel actions that only need a reason."""

    reason = serializers.CharField(max_length=300)
