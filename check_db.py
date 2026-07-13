"""
check_db.py — Diagnóstico de conexión y permisos, SIN Django.

Uso:  python check_db.py
Lee las mismas variables de .env que usa settings.py.

Los chequeos 4 y 5 DEBEN fallar con 'permission denied'. Eso es señal
de que el candado de la base está bien puesto: django_app solo puede
ejecutar sp_dispatcher, nada más.
"""
import json
import os
import sys

import psycopg
from dotenv import load_dotenv

load_dotenv(override=True)

OK, FAIL, WARN = "\033[92m✅\033[0m", "\033[91m❌\033[0m", "\033[93m⚠️ \033[0m"

CONN = {
    "dbname":   os.getenv("DB_NAME", "postgres"),
    "user":     os.getenv("DB_USER", "django_app"),
    "password": os.getenv("DB_PASSWORD", ""),
    "host":     os.getenv("DB_HOST", "localhost"),
    "port":     os.getenv("DB_PORT", "5432"),
    "sslmode":  "require",
}

LOGIN_SP = os.getenv("LOGIN_SP_NAME", "sp_login")
USER_TEST = os.getenv("TEST_USERNAME", "maria.gestora1")
PASS_TEST = os.getenv("TEST_PASSWORD", "ClaveGestor123")


def main():
    print(f"\n→ Conectando a {CONN['host']}:{CONN['port']} como '{CONN['user']}'\n")

    # ── 1. ¿Hay cable? ────────────────────────────────────────────────
    try:
        conn = psycopg.connect(**CONN, connect_timeout=10)
    except Exception as e:
        print(f"{FAIL} 1. Conexión")
        print(f"      {type(e).__name__}: {e}")
        print("\n   Pistas:")
        print("   • 'Network is unreachable' → Supabase directo es IPv6-only.")
        print("     Usa el pooler: aws-0-<region>.pooler.supabase.com:6543")
        print("   • 'password authentication failed' → revisa DB_PASSWORD y que")
        print("     hayas cambiado 'CAMBIAR_ESTA_CONTRASENA' en el CREATE ROLE.")
        sys.exit(1)

    print(f"{OK} 1. Conexión TCP + SSL establecida")

    with conn:
        # ── 2. Identidad y versión ────────────────────────────────────
        with conn.cursor() as cur:
            cur.execute("SELECT current_user, current_database(), version()")
            user, db, ver = cur.fetchone()
            print(f"{OK} 2. current_user = '{user}' | db = '{db}'")
            print(f"      {ver.split(',')[0]}")
            if user == "postgres":
                print(f"{WARN}   Estás conectado como superusuario. Los chequeos 4 y 5")
                print("      pasarán aunque los permisos estén mal. Usa django_app.")

        # ── 3. El dispatcher responde ─────────────────────────────────
        with conn.cursor() as cur:
            try:
                cur.execute(
                    "SELECT public.sp_dispatcher(%s, %s::jsonb)",
                    ["sp_registry_obtener", json.dumps([1])],
                )
                cur.fetchone()
                print(f"{OK} 3. EXECUTE sobre sp_dispatcher concedido")
            except Exception as e:
                print(f"{FAIL} 3. No puedo ejecutar sp_dispatcher: {e}")
                print("      Falta: GRANT EXECUTE ON FUNCTION")
                print("             public.sp_dispatcher(TEXT, JSONB) TO django_app;")
                sys.exit(1)

    # Cada chequeo negativo va en su propia conexión: un error aborta
    # la transacción y deja la sesión inutilizable.

    # ── 4. NO debe poder leer tablas ──────────────────────────────────
    _debe_fallar(
        "4. Lectura directa de tablas bloqueada",
        "SELECT * FROM public.usuarios LIMIT 1",
        [],
        "django_app puede leer usuarios directamente. Revisa "
        "REVOKE ALL ON ALL TABLES ... FROM django_app y el RLS.",
    )

    # ── 5. NO debe poder saltarse el dispatcher ───────────────────────
    _debe_fallar(
        "5. Llamada directa a un SP bloqueada",
        f"SELECT * FROM public.{LOGIN_SP}(%s, %s)",
        [USER_TEST, PASS_TEST],
        "django_app puede llamar SPs sin pasar por el registry. Revisa "
        "REVOKE EXECUTE ON ALL FUNCTIONS IN SCHEMA public FROM PUBLIC.",
    )

    # ── 6. Login vía dispatcher con rol 'anon' ────────────────────────
    with psycopg.connect(**CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('request.jwt.claim.role','anon',true)")
            cur.execute(
                "SELECT public.sp_dispatcher(%s, %s::jsonb)",
                [LOGIN_SP, json.dumps([USER_TEST, PASS_TEST])],
            )
            res = cur.fetchone()[0]
            res = json.loads(res) if isinstance(res, str) else res
            fila = (res.get("data") or [{}])[0]

            if fila.get("resultado") == "exito":
                print(f"{OK} 6. Login vía dispatcher (rol anon) → id_usuario="
                      f"{fila['id_usuario']}, rol='{fila['nombre_rol']}'")
            else:
                print(f"{WARN}6. El dispatcher respondió, pero el login falló:")
                print(f"      \"{fila.get('mensaje', res)}\"")
                print(f"      Crea el usuario en el SQL Editor:")
                print(f"      SELECT * FROM sp_usuario_crear("
                      f"'Ana','Pérez','{PASS_TEST}','ana@demo.com',1);")
                print("      Si dice 'bloqueado': UPDATE usuarios SET "
                      "bloque_usuario=FALSE, intentos_fallidos=0 WHERE ...;")

    # ── 7. Un SP privado con rol 'anon' DEBE ser rechazado ────────────
    with psycopg.connect(**CONN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('request.jwt.claim.role','anon',true)")
            try:
                cur.execute(
                    "SELECT public.sp_dispatcher(%s, %s::jsonb)",
                    ["sp_categoria_listar", json.dumps([False])],
                )
                cur.fetchone()
                print(f"{FAIL} 7. 'anon' ejecutó un SP privado. El chequeo de "
                      "is_public del dispatcher no está funcionando.")
            except psycopg.errors.RaiseException as e:
                if "Acceso denegado" in str(e):
                    print(f"{OK} 7. 'anon' rechazado en SP privado (is_public OK)")
                else:
                    print(f"{WARN}7. Rechazado, pero con otro error: {e}")

    print("\n→ Diagnóstico terminado.\n")


def _debe_fallar(titulo, sql, params, mensaje_si_pasa):
    """Ejecuta sql esperando 'permission denied'. Que falle es el éxito."""
    try:
        with psycopg.connect(**CONN) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cur.fetchone()
        print(f"{FAIL} {titulo}")
        print(f"      {mensaje_si_pasa}")
    except psycopg.errors.InsufficientPrivilege:
        print(f"{OK} {titulo} (permission denied, como debe ser)")
    except psycopg.errors.UndefinedTable:
        print(f"{WARN}{titulo}: la tabla no existe. ¿Corriste el script maestro?")
    except psycopg.errors.UndefinedFunction:
        print(f"{WARN}{titulo}: la función no existe. Revisa LOGIN_SP_NAME.")
    except Exception as e:
        print(f"{WARN}{titulo}: falló con otro error → {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()