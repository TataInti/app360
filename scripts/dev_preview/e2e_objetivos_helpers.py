"""Selectores y lecturas de servidor para el E2E de objetivos comerciales.

La pantalla es una tabla de equipo. Cada vendedor son dos filas hermanas dentro de #listaVendedores:
la fila de resumen ([data-seller-row]; [data-seller-draft] si es borrador) con sus datos, y la fila
siguiente (tr.oc-details), su zona expandible con el encabezado «Agregar objetivo» ([data-add-line]) y una
tabla anidada cuyas filas son las líneas ([data-line-row], con [data-line-id]; «Editar» la pasa a campos
[data-meta]). Cada línea tiene su fila de aviso debajo ([data-line-error], oculta si no hay). La línea nueva
se carga en el panel lateral de alta ([data-goal-drawer]), con el formulario [data-goal-form] y los campos
[data-campo="nivel"] y [data-campo="valor"].
"""
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation


MEDIDAS = ("importe", "cajas", "kilos")


class ObjetivosDOM:
    """Centraliza las filas de vendedor, sus zonas de líneas, el alta y la fila Equipo."""

    def __init__(self, page):
        self.page = page

    def filas_vendedor(self):
        return self.page.locator("[data-seller-row]")

    def fila_equipo(self):
        return self.page.locator("[data-team-row]")

    def fila_vendedor(self, ref):
        ref = str(ref)
        if ref.startswith("id:"):
            vendedor_id = ref.partition(":")[2]
            fila = self.page.locator(
                f'[data-seller-row][data-vendedor-ref="{ref}"], '
                f'[data-seller-row][data-vendedor-id="{vendedor_id}"]'
            ).first
            if fila.count():
                return fila
        return self.filas_vendedor().filter(has_text=ref).first

    def borrador_vendedor(self, ref=None):
        borradores = self.page.locator("[data-seller-draft]")
        if ref is None:
            return borradores.first
        ref = str(ref)
        if ref.startswith("id:"):
            exacto = self.page.locator(f'[data-seller-draft][data-vendedor-ref="{ref}"]').first
            if exacto.count():
                return exacto
        return borradores.filter(has_text=ref).first

    def fila_o_borrador(self, ref):
        fila = self.fila_vendedor(ref)
        return fila if fila.count() else self.borrador_vendedor(ref)

    def zona_de(self, ref):
        """Zona expandible del vendedor: la fila que sigue a su fila de resumen.

        ref puede ser el nombre, la referencia («id:…», «nombre:…») o el locator de la fila de resumen.
        """
        resumen = ref if hasattr(ref, "locator") else self.fila_o_borrador(ref)
        return resumen.locator("xpath=following-sibling::tr[1]")

    def tarjeta_activa(self, ref):
        """Zona de líneas del vendedor: contiene «Agregar objetivo» y los formularios de línea."""
        return self.zona_de(ref)

    def expandir(self, ref):
        """Expande la zona de líneas del vendedor si está contraída, como lo haría una persona."""
        fila = self.fila_vendedor(ref)
        boton = fila.locator("button[aria-expanded]")
        if boton.count() and boton.get_attribute("aria-expanded") == "false":
            boton.click()
        return self.zona_de(fila)

    def lineas_de(self, ref):
        """Filas de línea del vendedor ([data-line-row]). ref: nombre, referencia o zona de líneas."""
        zona = ref if hasattr(ref, "locator") else self.zona_de(ref)
        return zona.locator("[data-line-row]")

    def linea(self, ref, line_id=None, index=0):
        if line_id is not None:
            exacta = self.page.locator(f'[data-line-id="{line_id}"]').first
            if exacta.count():
                return exacta
        return self.lineas_de(ref).nth(index)

    def panel(self):
        """Panel lateral de alta (dialog con data-goal-drawer)."""
        return self.page.locator("[data-goal-drawer]")

    def formulario_alta(self, ref=None):
        """Formulario del panel de alta. Hay uno solo; ref solo identifica la fila de origen."""
        return self.page.locator("[data-goal-form]")

    def campo_alta(self, nombre):
        """Campo del panel por data-campo: «nivel» o «valor» (TomSelect con su desplegable)."""
        return self.page.locator(f'[data-goal-form] [data-campo="{nombre}"]')

    def resumen_de(self, ref):
        """Fila de resumen del vendedor: meta, realizado, avance, cajas, kilos y estado."""
        return self.fila_o_borrador(ref)


def entero(valor):
    """Redondeo medio hacia arriba, como lo muestra la pantalla."""
    return int(Decimal(str(valor)).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def numero_visible(texto):
    """«$ 1.234.567», «20 %» o «23» → entero. «—» o vacío → None."""
    digitos = re.sub(r"[^0-9-]", "", texto or "")
    return int(digitos) if digitos not in ("", "-") else None


def partir_real_meta(texto):
    """«26 / 715» → (26, 715); «16 / —» → (16, None)."""
    real, _, meta = (texto or "").partition("/")
    return numero_visible(real), numero_visible(meta)


def totales_equipo(datos):
    """Fila Equipo calculada desde la API. Cada medida suma solo a los vendedores con meta en esa medida."""
    total = {"lineas": 0}
    for medida in MEDIDAS:
        total[medida] = {"meta": Decimal(0), "real": Decimal(0), "hay": False}
    for vendedor in datos.get("objetivos", []):
        total["lineas"] += int(vendedor.get("cantidad_lineas") or 0)
        for medida in MEDIDAS:
            meta = (vendedor.get("metas") or {}).get(medida)
            if meta is None:
                continue
            total[medida]["meta"] += Decimal(str(meta))
            total[medida]["real"] += Decimal(str((vendedor.get("realizados") or {}).get(medida) or 0))
            total[medida]["hay"] = True
    return total


def leer_objetivos(contexto, base_url, mes):
    """Lee objetivos usando el contexto autenticado y no sigue redirecciones."""
    respuesta = contexto.request.get(
        f"{base_url.rstrip('/')}/api/objetivos-comerciales?mes={mes}", max_redirects=0
    )
    if respuesta.status != 200:
        raise AssertionError(f"GET de objetivos respondió {respuesta.status}, esperado 200")
    datos = respuesta.json()
    if datos.get("mes") != mes or not isinstance(datos.get("objetivos"), list):
        raise AssertionError("GET de objetivos devolvió un período o una colección inesperados")
    return datos


def vendedor_en(datos, vendedor_id=None, nombre=None):
    for vendedor in datos.get("objetivos", []):
        if vendedor_id is not None and str(vendedor.get("vendedor_id")) == str(vendedor_id):
            return vendedor
        if nombre is not None and vendedor.get("nombre_visible") == nombre:
            return vendedor
    return None


def linea_en(datos, objetivo_id):
    if objetivo_id is None:
        return None, None
    for vendedor in datos.get("objetivos", []):
        for linea in vendedor.get("lineas", []):
            if str(linea.get("id")) == str(objetivo_id):
                return vendedor, linea
    return None, None


def cantidad_lineas(datos, vendedor_id=None, nombre=None):
    vendedor = vendedor_en(datos, vendedor_id=vendedor_id, nombre=nombre)
    if vendedor is None:
        return 0
    return len(vendedor.get("lineas", []))


def objetivo_devuelto(respuesta):
    try:
        objetivo = respuesta.json().get("objetivo")
    except Exception:  # La respuesta de error puede no tener el contrato de alta.
        return {}
    return objetivo if isinstance(objetivo, dict) else {}


def _numero(valor):
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


def comparar_linea_readback(datos, objetivo_id, metas_esperadas, cantidad_esperada, vendedor_id=None):
    vendedor, linea = linea_en(datos, objetivo_id)
    metas_leidas = linea.get("metas", {}) if linea else {}
    metas_ok = bool(linea) and all(
        _numero(metas_leidas.get(medida)) == _numero(metas_esperadas.get(medida))
        for medida in MEDIDAS
    )
    id_ok = linea is not None and str(linea.get("id")) == str(objetivo_id)
    vendedor_ok = vendedor is not None and (
        vendedor_id is None or str(vendedor.get("vendedor_id")) == str(vendedor_id)
    )
    lineas = vendedor.get("lineas", []) if vendedor else []
    cantidad_api = vendedor.get("cantidad_lineas") if vendedor else None
    cantidad_ok = (
        vendedor is not None
        and cantidad_api == cantidad_esperada
        and len(lineas) == cantidad_esperada
    )
    detalle = {
        "id_esperado": objetivo_id,
        "id_leido": linea.get("id") if linea else None,
        "vendedor_id_esperado": vendedor_id,
        "vendedor_id_leido": vendedor.get("vendedor_id") if vendedor else None,
        "metas_esperadas": metas_esperadas,
        "metas_leidas": metas_leidas,
        "lineas_esperadas": cantidad_esperada,
        "cantidad_lineas": cantidad_api,
        "lineas_en_json": len(lineas),
    }
    return id_ok and metas_ok and vendedor_ok and cantidad_ok, detalle


def comparar_borrado(datos_antes, datos_despues, vendedor_id, objetivo_id, cantidad_esperada):
    vendedor_antes = vendedor_en(datos_antes, vendedor_id=vendedor_id)
    vendedor_despues = vendedor_en(datos_despues, vendedor_id=vendedor_id)
    if vendedor_antes is None or vendedor_despues is None:
        return False, {"vendedor_id": vendedor_id, "vendedor_presente": False}

    lineas_antes = {str(item.get("id")): item for item in vendedor_antes.get("lineas", [])}
    lineas_despues = {str(item.get("id")): item for item in vendedor_despues.get("lineas", [])}
    borrada = str(objetivo_id) not in lineas_despues
    restantes_iguales = all(
        str(line_id) in lineas_despues
        and all(
            _numero(lineas_despues[str(line_id)].get("metas", {}).get(medida))
            == _numero(linea.get("metas", {}).get(medida))
            for medida in MEDIDAS
        )
        for line_id, linea in lineas_antes.items()
        if str(line_id) != str(objetivo_id)
    )
    lineas = vendedor_despues.get("lineas", [])
    cantidad_api = vendedor_despues.get("cantidad_lineas")
    cantidad_ok = (
        cantidad_api == cantidad_esperada and len(lineas) == cantidad_esperada
    )
    detalle = {
        "id_eliminado": objetivo_id,
        "id_ausente": borrada,
        "restantes_con_mismas_metas": restantes_iguales,
        "lineas_esperadas": cantidad_esperada,
        "cantidad_lineas": cantidad_api,
        "lineas_en_json": len(lineas),
    }
    return borrada and restantes_iguales and cantidad_ok, detalle


def leer_accesos(contexto, base_url):
    """Lee el estado de accesos del servidor, sin aceptar una redirección como dato."""
    respuesta = contexto.request.get(
        f"{base_url.rstrip('/')}/api/admin/accesos", max_redirects=0
    )
    if respuesta.status != 200:
        raise AssertionError(f"GET de accesos respondió {respuesta.status}, esperado 200")
    datos = respuesta.json()
    if not isinstance(datos, list) or any(
        "id" not in user or "permissions" not in user for user in datos
    ):
        raise AssertionError("GET de accesos devolvió una colección inesperada")
    return {str(user["id"]): user for user in datos}
