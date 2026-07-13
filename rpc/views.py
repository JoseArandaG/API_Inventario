from django.conf import settings
from django.db import DatabaseError
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.exceptions import AuthenticationFailed

from core.db import call_dispatcher, get_sp
from core.jwt_auth import JWTAuthentication, generate_token


def _status_login_fallido(mensaje: str) -> int:
    """
    sp_usuario_login solo devuelve 'error' + un mensaje; no hay código.
    Mapeamos por texto. Es frágil a propósito: aislado aquí, si algún día
    cambias el wording del SP, este es el único sitio que se rompe.
    """
    m = (mensaje or '').lower()
    if 'bloqueado' in m:
        return 423                      # Locked: el front NO debe ofrecer reintentar
    if m.startswith('el usuario está'):  # inactivo | suspendido
        return 403
    return 401                          # credenciales incorrectas


class RPCView(APIView):
    authentication_classes = []
    permission_classes = []

    def post(self, request, sp_id):
        # 1. El SP existe en el registry
        try:
            sp = get_sp(sp_id)
        except (DatabaseError, ValueError):
            return Response({'error': 'Error consultando el registry.'}, status=500)
        if sp is None:
            return Response({'error': f"Procedimiento '{sp_id}' no registrado."}, status=404)
        if not sp['is_active']:
            return Response({'error': f"Procedimiento '{sp['name']}' está inactivo."}, status=403)

        # 2. JWT si no es público
        rol_db = 'anon'
        if not sp['is_public']:
            try:
                result = JWTAuthentication().authenticate(request)
            except AuthenticationFailed as e:
                return Response({'error': str(e.detail)}, status=401)
            if result is None:
                return Response({'error': 'Autenticación requerida.'}, status=401)
            request.user = result[0]
            rol_db = 'authenticated'

        # 3. Body válido
        if not isinstance(request.data, dict):
            return Response({'error': 'El body debe ser {"params": [...]}'}, status=400)
        params = request.data.get('params', [])
        if not isinstance(params, list):
            return Response({'error': "'params' debe ser una lista."}, status=400)

        # 4. Dispatcher
        try:
            resultado = call_dispatcher(sp['name'], params, rol=rol_db)
        except (DatabaseError, ValueError) as e:
            mensaje = str(e.__cause__) if getattr(e, '__cause__', None) else str(e)
            return Response({'error': mensaje}, status=400)

        # 5. Caso especial: login → emitir JWT
        if sp['name'] == settings.LOGIN_SP_NAME:
            return self._login_response(resultado)

        return Response(resultado)

    @staticmethod
    def _login_response(resultado):
        """
        Adaptado a sp_usuario_login (return_type = 'table').

        Éxito → {'data': [{'resultado':'exito', 'mensaje':'Inicio de sesión correcto.',
                           'id_usuario':1, 'nombre':'Ana', 'apellido':'Pérez',
                           'username':'ana.perez1', 'correo':'ana@demo.com',
                           'id_rol':1, 'nombre_rol':'administrador'}]}
        Error → {'data': [{'resultado':'error', 'mensaje':'...', ...todo lo demás None}]}
        """
        data = resultado.get('data') or []
        if not data:
            # No debería pasar: el SP siempre retorna una fila.
            return Response(
                {'resultado': 'error', 'mensaje': 'Respuesta vacía del servidor.'},
                status=401,
            )

        row = data[0]

        # ── Camino de error: solo resultado y mensaje traen valor ──
        if row.get('resultado') != 'exito':
            mensaje = row.get('mensaje') or 'Usuario o contraseña incorrectos.'
            return Response(
                {'resultado': 'error', 'mensaje': mensaje},
                status=_status_login_fallido(mensaje),
            )

        # ── Camino de éxito ──
        token = generate_token({
            'id_usuario': row['id_usuario'],
            'username':   row['username'],
            'id_rol':     row['id_rol'],       # ← autoriza con esto
            'nombre_rol': row['nombre_rol'],   # ← solo para mostrar en la UI
        })

        nombre_completo = ' '.join(
            p for p in (row.get('nombre'), row.get('apellido')) if p
        )

        return Response({
            'resultado': 'exito',
            'mensaje': row['mensaje'],
            'token': token,
            'usuario': {
                'id_usuario':      row['id_usuario'],
                'username':        row['username'],
                'nombre':          row['nombre'],
                'apellido':        row['apellido'],
                'nombre_completo': nombre_completo,
                'correo':          row['correo'],
                'id_rol':          row['id_rol'],
                'nombre_rol':      row['nombre_rol'],
            },
        })
