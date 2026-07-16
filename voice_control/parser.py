import re

# fn_normalizar (SQL) no maneja plurales: "paquetes" != "paquete" tras normalizar.
# Se mapea siempre a la forma singular para que coincida con unidades_articulo.palabra_clave.
UNIDADES_SINGULAR = {
    'cajas': 'caja', 'caja': 'caja',
    'packs': 'pack', 'pack': 'pack',
    'paquetes': 'paquete', 'paquete': 'paquete',
    'pallets': 'pallet', 'pallet': 'pallet',
    'bolsas': 'bolsa', 'bolsa': 'bolsa',
    'unidades': 'unidad', 'unidad': 'unidad',
}

# El reconocimiento de voz a veces transcribe números como palabras ("dos") en vez de dígitos.
NUM_UNIDADES = {
    'cero': 0, 'un': 1, 'uno': 1, 'una': 1, 'dos': 2, 'tres': 3, 'cuatro': 4, 'cinco': 5,
    'seis': 6, 'siete': 7, 'ocho': 8, 'nueve': 9, 'diez': 10, 'once': 11, 'doce': 12,
    'trece': 13, 'catorce': 14, 'quince': 15, 'dieciseis': 16, 'dieciséis': 16,
    'diecisiete': 17, 'dieciocho': 18, 'diecinueve': 19, 'veinte': 20,
    'veintiuno': 21, 'veintiun': 21, 'veintiún': 21, 'veintidos': 22, 'veintidós': 22,
    'veintitres': 23, 'veintitrés': 23, 'veinticuatro': 24, 'veinticinco': 25,
    'veintiseis': 26, 'veintiséis': 26, 'veintisiete': 27, 'veintiocho': 28, 'veintinueve': 29,
}
NUM_DECENAS = {
    'treinta': 30, 'cuarenta': 40, 'cincuenta': 50, 'sesenta': 60,
    'setenta': 70, 'ochenta': 80, 'noventa': 90,
}
NUM_CENTENAS = {
    'cien': 100, 'ciento': 100, 'doscientos': 200, 'trescientos': 300,
    'cuatrocientos': 400, 'quinientos': 500, 'seiscientos': 600,
    'setecientos': 700, 'ochocientos': 800, 'novecientos': 900,
}


def _limpia(palabra):
    return re.sub(r"[.,;:!?]+$", "", palabra.lower())


def _consumir_numero(palabras, inicio):
    """Lee un número en palabras desde `inicio`. Devuelve (valor, palabras_consumidas) o (None, 0)."""
    i = inicio
    n = len(palabras)
    valor = 0
    consumidos = 0

    tok = _limpia(palabras[i]) if i < n else None
    if tok in NUM_CENTENAS:
        valor += NUM_CENTENAS[tok]
        consumidos += 1
        i += 1
        tok = _limpia(palabras[i]) if i < n else None

    if tok in NUM_DECENAS:
        valor += NUM_DECENAS[tok]
        consumidos += 1
        i += 1
        if i < n and _limpia(palabras[i]) == 'y' and i + 1 < n and _limpia(palabras[i + 1]) in NUM_UNIDADES:
            valor += NUM_UNIDADES[_limpia(palabras[i + 1])]
            consumidos += 2
    elif tok in NUM_UNIDADES:
        valor += NUM_UNIDADES[tok]
        consumidos += 1

    return (valor, consumidos) if consumidos else (None, 0)


def _numero_inicial_a_digitos(texto):
    """Si el texto empieza con un número en palabras, lo reemplaza por dígitos."""
    palabras = texto.split(' ')
    valor, consumidos = _consumir_numero(palabras, 0)
    if valor is None:
        return texto
    return ' '.join([str(valor)] + palabras[consumidos:])


def _numero_final_a_digitos(texto):
    """Si el texto termina en un número en palabras, lo reemplaza por dígitos."""
    palabras = texto.split(' ')
    n = len(palabras)
    for inicio in range(max(0, n - 4), n):
        valor, consumidos = _consumir_numero(palabras, inicio)
        if valor is not None and inicio + consumidos == n:
            return ' '.join(palabras[:inicio] + [str(valor)])
    return texto


def parsear_comando_voz(texto, mapa_unidades=None):
    """
    Analiza una cadena de texto y extrae:
    - tipo_movimiento ('ENTRADA', 'SALIDA', 'AJUSTE')
    - cantidad_detectada (int)
    - unidad_detectada (str o None)
    - nombre_busqueda (str)

    `mapa_unidades`: dict {palabra_hablada: palabra_clave_canonica}. Si no se pasa,
    se usa solo el set genérico base (UNIDADES_SINGULAR). views.py normalmente pasa
    una versión ampliada con las palabras reales de unidades_articulo (ver core.db /
    _mapa_unidades), para no tener que tocar este archivo cada vez que se registra
    una unidad nueva en Supabase.
    """
    mapa_unidades = mapa_unidades or UNIDADES_SINGULAR
    regex_accion = r"^(agrega|agregar|añadir|añade|suma|sumar|quita|quitar|resta|restar|elimina|eliminar|ajusta|ajustar|cambia|cambiar|establece|establecer)\s+"
    texto_limpio = re.sub(regex_accion, "", texto, flags=re.IGNORECASE).strip()
    palabras_accion = re.match(regex_accion, texto, re.IGNORECASE)

    if not palabras_accion:
        return None

    accion_verbal = palabras_accion.group(1).lower()

    if accion_verbal in ['agrega', 'agregar', 'añadir', 'añade', 'suma', 'sumar']:
        tipo_movimiento = 'ENTRADA'
    elif accion_verbal in ['quita', 'quitar', 'resta', 'restar', 'elimina', 'eliminar']:
        tipo_movimiento = 'SALIDA'
    else:
        tipo_movimiento = 'AJUSTE'

    cantidad_detectada = 1
    unidad_detectada = None
    nombre_busqueda = ""

    if tipo_movimiento in ['ENTRADA', 'SALIDA']:
        texto_cantidad = _numero_inicial_a_digitos(texto_limpio)
        patron_unidad = '|'.join(
            re.escape(p) for p in sorted(mapa_unidades.keys(), key=len, reverse=True)
        )
        match_cant = re.match(
            rf"^(\d+)\s+(?:({patron_unidad})\s+(?:de\s+|del\s+|de\s+los\s+)?)?(.+)",
            texto_cantidad,
            re.IGNORECASE
        )
        if match_cant:
            cantidad_detectada = int(match_cant.group(1))
            unidad_detectada = mapa_unidades.get(match_cant.group(2).lower()) if match_cant.group(2) else None
            nombre_busqueda = re.sub(r"[.,;:!?]+$", "", match_cant.group(3).strip()).strip()
    else:
        texto_ajuste = _numero_final_a_digitos(texto_limpio)
        match_ajuste = re.match(r"^(.+?)\s+a\s+(\d+)[.,;:!?]*\s*$", texto_ajuste, re.IGNORECASE)
        if match_ajuste:
            nombre_busqueda = match_ajuste.group(1).strip()
            cantidad_detectada = int(match_ajuste.group(2))

    return {
        'tipo_movimiento': tipo_movimiento,
        'cantidad_detectada': cantidad_detectada,
        'unidad_detectada': unidad_detectada,
        'nombre_busqueda': nombre_busqueda
    }