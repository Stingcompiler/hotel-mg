from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import get_object_or_404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import rules, services
from .models import User
from .permissions import IsManager
from .serializers import (
    ConfirmSerializer,
    ConfirmTokenSerializer,
    LoginUserSerializer,
    PasswordLoginSerializer,
    PinLoginSerializer,
    ResetPinSerializer,
    SessionSerializer,
    UserCreateSerializer,
    UserSerializer,
    UserUpdateSerializer,
)


def _session_response(result):
    services.raise_for_login(result)
    return Response(SessionSerializer({"token": result.token, "user": result.user}).data)


class LoginUsersView(APIView):
    """Active users for the login screen's picker (names and roles only)."""

    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(responses=LoginUserSerializer(many=True))
    def get(self, request):
        users = User.objects.filter(is_active=True).order_by("full_name")
        return Response(LoginUserSerializer(users, many=True).data)


class PinLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=PinLoginSerializer, responses=SessionSerializer)
    def post(self, request):
        data = PinLoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return _session_response(services.login_with_pin(**data.validated_data))


class PasswordLoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    @extend_schema(request=PasswordLoginSerializer, responses=SessionSerializer)
    def post(self, request):
        data = PasswordLoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return _session_response(services.login_with_password(**data.validated_data))


class ConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=ConfirmSerializer, responses=ConfirmTokenSerializer)
    def post(self, request):
        data = ConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        token = services.issue_confirm_token(request.user, data.validated_data["password"])
        expires_in = int(rules.CONFIRM_LIFETIME.total_seconds())
        return Response(ConfirmTokenSerializer({"confirm_token": token, "expires_in": expires_in}).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        services.logout(request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=UserSerializer)
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class UserListView(APIView):
    permission_classes = [IsManager]

    @extend_schema(responses=UserSerializer(many=True))
    def get(self, request):
        return Response(UserSerializer(User.objects.order_by("full_name"), many=True).data)

    @extend_schema(request=UserCreateSerializer, responses={201: UserSerializer})
    def post(self, request):
        services.require_confirmation(request)
        data = UserCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = services.create_user(request.user, **data.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserDetailView(APIView):
    permission_classes = [IsManager]

    @extend_schema(responses=UserSerializer)
    def get(self, request, pk):
        return Response(UserSerializer(get_object_or_404(User, pk=pk)).data)

    @extend_schema(request=UserUpdateSerializer, responses=UserSerializer)
    def patch(self, request, pk):
        services.require_confirmation(request)
        get_object_or_404(User, pk=pk)
        data = UserUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(UserSerializer(services.update_user(request.user, pk, **data.validated_data)).data)


class ResetPinView(APIView):
    permission_classes = [IsManager]

    @extend_schema(request=ResetPinSerializer, responses=UserSerializer)
    def post(self, request, pk):
        services.require_confirmation(request)
        get_object_or_404(User, pk=pk)
        data = ResetPinSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        return Response(UserSerializer(services.reset_pin(request.user, pk, data.validated_data["pin"])).data)


class UnlockView(APIView):
    """Manager lifts a PIN lockout (login design: «طلب المدير»)."""

    permission_classes = [IsManager]

    @extend_schema(request=None, responses=UserSerializer)
    def post(self, request, pk):
        get_object_or_404(User, pk=pk)
        return Response(UserSerializer(services.unlock_user(request.user, pk)).data)
