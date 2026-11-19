"""Selectores y lecturas de servidor para el E2E de objetivos comerciales."""
from decimal import Decimal, InvalidOperation


MEDIDAS = ("importe", "cajas", "kilos")


class ObjetivosDOM:
    """Centraliza las raíces de vendedor, línea, alta y resumen de la pantalla."""

    def __init__(self, page):
        self.page = page

    def filas_vendedor(self):
        filas = self.page.locator("[data-seller-row]")
        return filas if filas.count() else self.page.locator("article.oc-seller-card")

    def fila_vendedor(self, ref):
        ref = str(ref)
        filas = self.page.locator("[data-seller-row]")
        if ref.startswith("id:"):
            vendedor_id = ref.partition(":")[2]
            fila = self.page.locator(
                f'[data-seller-row][data-vendedor-ref="{ref}"], '
                f'[data-seller-row][data-vendedor-id="{vendedor_id}"], '
                f'article.oc-seller-card[data-vendedor-ref="{ref}"]'
            ).first
            if fila.count():
                return fila
        if filas.count():
            return filas.filter(has_text=ref).first
        return self.page.locator("article.oc-seller-card").filter(
            has=self.page.locator("h2", has_text=ref)
        ).first

    def borrador_vendedor(self, ref=None):
        borradores = self.page.locator("[data-seller-draft]")
        if not borradores.count():
            borradores = self.page.locator("article.oc-seller-draft")
        if ref is None:
            return borradores.first
        ref = str(ref)
        if ref.startswith("id:"):
            exacto = self.page.locator(
                f'[data-seller-draft][data-vendedor-ref="{ref}"], '
                f'article.oc-seller-draft[data-vendedor-ref="{ref}"]'
            ).first
            if exacto.count():
                return exacto
        return borradores.filter(has_text=ref).first

    def tarjeta_activa(self, ref):
        borrador = self.borrador_vendedor(ref)
        return borrador if borrador.count() else self.fila_vendedor(ref)

    def _raiz_vendedor(self, ref):
        if hasattr(ref, "locator"):
            return ref
        return self.tarjeta_activa(ref)

    def lineas_de(self, ref):
        raiz = self._raiz_vendedor(ref)
        filas = raiz.locator("[data-line-row]")
        if filas.count():
            return filas
        contenedor = raiz.locator("[data-lines]")
        if contenedor.count():
            return contenedor.locator("form.oc-line")
        return raiz.locator("form.oc-line")

    def linea(self, ref, line_id=None, index=0):
        if line_id is not None:
            exacta = self.page.locator(f'[data-line-id="{line_id}"]').first
            if exacta.count():
                return exacta
        return self.lineas_de(ref).nth(index)

    def formulario_alta(self, ref=None):
        panel = self.page.locator("[data-goal-drawer]:visible")
        if panel.count():
            formularios = panel.locator("[data-goal-form], form.oc-line")
            if formularios.count():
                return formularios.last
        raiz = self.borrador_vendedor(ref) if ref is None else self.tarjeta_activa(ref)
        return self.lineas_de(raiz).last

    def resumen_de(self, ref):
        raiz = self.fila_vendedor(ref)
        if not raiz.count():
            raiz = self.borrador_vendedor(ref)
        return raiz.locator("[data-summary]").first


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
