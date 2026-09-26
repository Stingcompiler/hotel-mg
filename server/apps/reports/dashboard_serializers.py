"""Response shape of ``GET reports/owner-dashboard`` (typed for the generated client). Money in minor units."""

from rest_framework import serializers

Text, Int, Day = serializers.CharField, serializers.IntegerField, serializers.DateField


class PeriodSerializer(serializers.Serializer):
    key = serializers.ChoiceField(choices=["month", "previous", "90days"])
    label = Text()
    date_from = Day()
    date_to = Day()


class OccupancyTodaySerializer(serializers.Serializer):
    value = Int(help_text="Percent tonight.")
    occupied = Int()
    rooms = Int()
    period_average = Int()


class RevenueKpiSerializer(serializers.Serializer):
    value = Int()
    change_percent = Int(allow_null=True, help_text="Against the month before the period; null without data.")


class CollectedKpiSerializer(serializers.Serializer):
    value = Int()
    of_revenue_percent = Int()


class LargestDebtSerializer(serializers.Serializer):
    room = Text()
    amount = Int()


class DebtsKpiSerializer(serializers.Serializer):
    value = Int()
    count = Int()
    largest = LargestDebtSerializer(allow_null=True)


class NeglectedKpiSerializer(serializers.Serializer):
    value = Int()
    latest_shift_user = Text(allow_null=True)
    latest_at = serializers.DateTimeField(allow_null=True)


class KpisSerializer(serializers.Serializer):
    occupancy_today = OccupancyTodaySerializer()
    revenue = RevenueKpiSerializer()
    collected = CollectedKpiSerializer()
    debts = DebtsKpiSerializer()
    neglected_alerts = NeglectedKpiSerializer()


class OccupancyPointSerializer(serializers.Serializer):
    date = Day()
    occupied = Int()
    rooms = Int()
    percent = Int()


class PeakSerializer(serializers.Serializer):
    date = Day()
    percent = Int()


class OccupancySerializer(serializers.Serializer):
    series = OccupancyPointSerializer(many=True, help_text="Last 30 nights, oldest first.")
    average = Int()
    peak = PeakSerializer()


class WeekSerializer(serializers.Serializer):
    label = Text()
    date_from = Day()
    date_to = Day()
    revenue = Int()
    collected = Int()


class AttentionSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=["overdue", "neglected", "debt", "shift", "maint"])
    label = Text()
    report = Text(help_text="Report name the row links to.")
    text = Text()


class StaffResponseSerializer(serializers.Serializer):
    name = Text()
    total = Int()
    handled = Int()
    handled_percent = Int()
    neglected = Int()
    average_delay_minutes = Int(allow_null=True)


class OwnerDashboardSerializer(serializers.Serializer):
    period = PeriodSerializer()
    rooms = Int()
    kpis = KpisSerializer()
    occupancy = OccupancySerializer()
    weeks = WeekSerializer(many=True)
    attention = AttentionSerializer(many=True)
    staff = StaffResponseSerializer(many=True)
    overdue_stays = Int()
