import jwt
from datetime import datetime, timezone, timedelta
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class AuthUser:
    is_authenticated = True

    def __init__(self, payload):
        self.id_usuario = payload['id_usuario']
        self.username = payload['username']
        self.rol = payload.get('rol', '')


def generate_token(data: dict) -> str:
    payload = {
        **data,
        'iat': datetime.now(tz=timezone.utc),
        'exp': datetime.now(tz=timezone.utc) + timedelta(hours=settings.JWT_EXPIRY_HOURS),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm='HS256')


class JWTAuthentication(BaseAuthentication):
    def authenticate(self, request):
        auth_header = request.headers.get('Authorization', '')
        if not auth_header.startswith('Bearer '):
            return None
        token = auth_header[7:]
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token expirado.')
        except jwt.PyJWTError:
            raise AuthenticationFailed('Token inválido.')
        try:
            return (AuthUser(payload), token)
        except KeyError:
            raise AuthenticationFailed('Token con estructura inválida.')