import json
from django.core.cache import cache
from django.db import connection, transaction

SP_REGISTRY_CACHE_TTL = 60  # segundos


def call_dispatcher(sp_nombre: str, params: list, rol: str | None = None) -> dict:
    """
    Llama a sp_dispatcher con SQL parametrizado (sin callproc, que psycopg3 no tiene).
    `rol`: 'anon' | 'authenticated' | None.
      - None  -> el dispatcher usa current_user ('django_app'): acceso interno.
      - 'anon'-> la BD rechaza cualquier SP con is_public = FALSE.
    """
    with transaction.atomic():
        with connection.cursor() as cursor:
            if rol is not None:
                # 'true' = local: la variable muere al cerrar la transacción.
                cursor.execute(
                    "SELECT set_config('request.jwt.claim.role', %s, true)", [rol]
                )
            cursor.execute(
                "SELECT public.sp_dispatcher(%s, %s::jsonb)",
                [sp_nombre, json.dumps(params)],
            )
            row = cursor.fetchone()

    if row is None or row[0] is None:
        raise ValueError(f"sp_dispatcher no retornó resultado para '{sp_nombre}'.")
    result = row[0]
    return json.loads(result) if isinstance(result, str) else result


def get_sp(sp_id: int) -> dict | None:
    """
    Consulta el registry a través del dispatcher (única función con GRANT).
    Cacheado en memoria: el registry casi nunca cambia y consultarlo en cada
    request duplica la latencia de red hacia la base de datos.
    """
    cache_key = f'sp_registry:{sp_id}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    data = call_dispatcher('sp_registry_obtener', [sp_id]).get('data', [])
    if not data:
        return None
    r = data[0]
    sp = {'name': r['name'], 'is_active': r['is_active'], 'is_public': r['is_public']}
    cache.set(cache_key, sp, SP_REGISTRY_CACHE_TTL)
    return sp