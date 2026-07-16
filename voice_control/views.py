from django.shortcuts import render

import json
from django.core.cache import cache
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.db import connection, DatabaseError
from core.db import call_dispatcher
from .parser import UNIDADES_SINGULAR, parsear_comando_voz  # 👈 Importamos tu lógica limpia

UNIDADES_MAPA_CACHE_KEY = 'voice_control:unidades_mapa'
UNIDADES_MAPA_CACHE_TTL = 300  # 5 minutos


def _mapa_unidades():
    """
    Palabras de unidad reconocidas por el parser: el set genérico base +
    las palabra_clave reales de unidades_articulo (para no editar código
    cada vez que se registra una unidad nueva en Supabase). Cacheado porque
    se consulta en cada frase de voz.
    """
    mapa = cache.get(UNIDADES_MAPA_CACHE_KEY)
    if mapa is not None:
        return mapa

    mapa = dict(UNIDADES_SINGULAR)
    with connection.cursor() as cursor:
        cursor.execute("SELECT DISTINCT palabra_clave FROM public.unidades_articulo WHERE activa = TRUE;")
        for (palabra,) in cursor.fetchall():
            base = palabra.strip().lower()
            if not base:
                continue
            mapa[base] = base
            mapa[base + 's'] = base
            mapa[base + 'es'] = base

    cache.set(UNIDADES_MAPA_CACHE_KEY, mapa, UNIDADES_MAPA_CACHE_TTL)
    return mapa

@csrf_exempt
def historial_voz_api(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    with connection.cursor() as cursor:
        cursor.execute("""
            SELECT m.id_movimiento, m.tipo_movimiento, a.nombre AS nombre_articulo,
                   m.cantidad, m.stock_antes, m.stock_despues, m.origen_captura, m.texto_voz
            FROM public.movimientos_inventario m
            JOIN public.articulos a ON a.id_articulo = m.id_articulo
            ORDER BY m.id_movimiento DESC
            LIMIT 50;
        """)
        columnas = [col[0] for col in cursor.description]
        movimientos = [dict(zip(columnas, fila)) for fila in cursor.fetchall()]

    return JsonResponse({'movimientos': movimientos})


@csrf_exempt
def procesar_voz_api(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=405)

    try:
        data = json.loads(request.body)
        texto_original = data.get('texto', '').strip()
        id_usuario = data.get('id_usuario')

        if not texto_original:
            return JsonResponse({'error': 'No se recibió texto'}, status=400)

        # Usar el parser exclusivo
        datos_comando = parsear_comando_voz(texto_original, mapa_unidades=_mapa_unidades())
        if not datos_comando or not datos_comando['nombre_busqueda']:
            return JsonResponse({'error': 'No se reconoció la acción o el formato de voz'}, status=400)

        tipo_movimiento = datos_comando['tipo_movimiento']
        cantidad_detectada = datos_comando['cantidad_detectada']
        unidad_detectada = datos_comando['unidad_detectada']
        nombre_busqueda = datos_comando['nombre_busqueda']

        # Búsqueda en la BD usando tu fn_normalizar.
        # fn_normalizar no maneja plurales, así que se toleran también las formas
        # "nombre/alias + s" y "+ es" (ej. alias "tomate" reconoce "tomates" hablado).
        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT a.id_articulo, a.nombre, a.stock_actual, a.precio_costo
                FROM public.articulos a
                LEFT JOIN public.alias_articulo aa ON a.id_articulo = aa.id_articulo
                WHERE public.fn_normalizar(a.nombre) = public.fn_normalizar(%s)
                   OR public.fn_normalizar(aa.alias) = public.fn_normalizar(%s)
                   OR public.fn_normalizar(a.nombre)  || 's'  = public.fn_normalizar(%s)
                   OR public.fn_normalizar(a.nombre)  || 'es' = public.fn_normalizar(%s)
                   OR public.fn_normalizar(aa.alias)  || 's'  = public.fn_normalizar(%s)
                   OR public.fn_normalizar(aa.alias)  || 'es' = public.fn_normalizar(%s)
                LIMIT 1;
            """, [nombre_busqueda] * 6)
            row = cursor.fetchone()

        if not row:
            return JsonResponse({'error': f"No se encontró el artículo: '{nombre_busqueda}'"}, status=404)

        id_articulo, nombre_real, stock_actual, precio_costo = row

        # Conversión de Unidades
        factor_conversion = 1
        if unidad_detectada:
            with connection.cursor() as cursor:
                cursor.execute("""
                    SELECT factor 
                    FROM public.unidades_articulo 
                    WHERE id_articulo = %s AND public.fn_normalizar(palabra_clave) = public.fn_normalizar(%s) AND activa = TRUE
                    LIMIT 1;
                """, [id_articulo, unidad_detectada])
                u_row = cursor.fetchone()
                if u_row:
                    factor_conversion = u_row[0]

        # Cantidad que recibe el SP: delta para ENTRADA/SALIDA, stock final para AJUSTE
        cantidad_unidades_reales = cantidad_detectada * factor_conversion
        motivo = 'Voz' if tipo_movimiento == 'AJUSTE' else None

        # sp_movimiento_registrar es el único camino permitido para tocar stock_actual
        # (un trigger bloquea el UPDATE directo); se llama vía sp_dispatcher, igual que rpc/views.py
        try:
            resultado = call_dispatcher('sp_movimiento_registrar', [
                tipo_movimiento,
                id_articulo,
                cantidad_unidades_reales,
                float(precio_costo) if precio_costo is not None else 0,
                None,  # referencia
                motivo,
                id_usuario,
                'VOZ',
                cantidad_detectada,
                unidad_detectada,
                texto_original,
            ], rol=None)
        except (DatabaseError, ValueError) as e:
            mensaje = str(e.__cause__) if getattr(e, '__cause__', None) else str(e)
            return JsonResponse({'error': mensaje}, status=400)

        data = resultado.get('data') or []
        if not data:
            return JsonResponse({'error': 'El procedimiento no devolvió resultado.'}, status=500)
        mov = data[0]

        return JsonResponse({
            'success': True,
            'detalle': {
                'articulo': mov['nombre_articulo'],
                'tipo': mov['tipo_movimiento'],
                'unidades_afectadas': mov['cantidad'],
                'stock_anterior': mov['stock_antes'],
                'stock_nuevo': mov['stock_despues'],
                'alerta': mov.get('alerta_stock'),
            }
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)