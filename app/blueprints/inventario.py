# ============================================================
# API de inventario y almacenes.
# Incluye CRUD de productos, categorias, almacenes, ajustes de
# stock atomico y exportacion/importacion en Excel.
# ============================================================
from datetime import datetime

from flask import Blueprint, request
from sqlalchemy import or_

from app.extensions import db
from app.models.inventario import Almacen, Categoria, MovimientoInventario, Producto
from app.services.auditoria_service import registrar
from app.utils.contexto import empresa_activa_id, parametros_paginacion
from app.utils.respuestas import error, exito
from app.utils.seguridad import requiere_sesion, solo_administrador, usuario_actual
from app.utils.validaciones import limpiar_texto, validar_monto

inventario_bp = Blueprint("inventario", __name__, url_prefix="/api/inventario")


# ------------------------------------------------------------
# Categorias
# ------------------------------------------------------------
@inventario_bp.route("/categorias", methods=["GET"])
@requiere_sesion
def listar_categorias():
    empresa_id = empresa_activa_id()
    categorias = Categoria.query.filter_by(empresa_id=empresa_id).order_by(Categoria.nombre).all()
    return exito([c.a_diccionario() for c in categorias], "Categorias")


@inventario_bp.route("/categorias", methods=["POST"])
@requiere_sesion
def crear_categoria():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 120)
    if not nombre:
        return error("El nombre de la categoria es obligatorio", 400)
    categoria = Categoria(
        empresa_id=empresa_activa_id(),
        nombre=nombre,
        descripcion=limpiar_texto(datos.get("descripcion"), 200),
    )
    db.session.add(categoria)
    db.session.commit()
    return exito(categoria.a_diccionario(), "Categoria creada", 201)


# ------------------------------------------------------------
# Almacenes
# ------------------------------------------------------------
@inventario_bp.route("/almacenes", methods=["GET"])
@requiere_sesion
def listar_almacenes():
    empresa_id = empresa_activa_id()
    almacenes = Almacen.query.filter_by(empresa_id=empresa_id).order_by(Almacen.nombre).all()
    return exito([a.a_diccionario() for a in almacenes], "Almacenes")


@inventario_bp.route("/almacenes", methods=["POST"])
@requiere_sesion
def crear_almacen():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 120)
    if not nombre:
        return error("El nombre del almacen es obligatorio", 400)
    almacen = Almacen(
        empresa_id=empresa_activa_id(),
        codigo=limpiar_texto(datos.get("codigo"), 20),
        nombre=nombre,
        direccion=limpiar_texto(datos.get("direccion"), 200),
    )
    db.session.add(almacen)
    db.session.commit()
    return exito(almacen.a_diccionario(), "Almacen creado", 201)


# ------------------------------------------------------------
# Productos
# ------------------------------------------------------------
@inventario_bp.route("/productos", methods=["GET"])
@requiere_sesion
def listar_productos():
    empresa_id = empresa_activa_id()
    busqueda = (request.args.get("buscar") or "").strip()
    solo_alerta = request.args.get("alerta") in ("1", "true", "si")
    pagina, por_pagina = parametros_paginacion()

    consulta = Producto.query.filter_by(empresa_id=empresa_id)
    if busqueda:
        patron = f"%{busqueda}%"
        consulta = consulta.filter(
            or_(
                Producto.nombre.ilike(patron),
                Producto.codigo.ilike(patron),
                Producto.codigo_barras.ilike(patron),
            )
        )
    if solo_alerta:
        consulta = consulta.filter(Producto.stock_actual <= Producto.stock_minimo)

    total = consulta.count()
    productos = (
        consulta.order_by(Producto.nombre)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )
    datos = []
    for producto in productos:
        item = producto.a_diccionario()
        item["alerta_stock"] = producto.alerta_stock
        item["categoria_nombre"] = producto.categoria.nombre if producto.categoria else ""
        datos.append(item)
    return exito({"items": datos, "total": total, "pagina": pagina, "por_pagina": por_pagina}, "Productos")


@inventario_bp.route("/productos/<int:producto_id>", methods=["GET"])
@requiere_sesion
def obtener_producto(producto_id: int):
    producto = Producto.query.get(producto_id)
    if producto is None:
        return error("Producto no encontrado", 404)
    return exito(producto.a_diccionario(), "Producto")


@inventario_bp.route("/productos", methods=["POST"])
@requiere_sesion
def crear_producto():
    datos = request.get_json(silent=True) or {}
    nombre = limpiar_texto(datos.get("nombre"), 150)
    if not nombre:
        return error("El nombre del producto es obligatorio", 400)
    codigo = limpiar_texto(datos.get("codigo"), 40)
    if not codigo:
        return error("El codigo del producto es obligatorio", 400)
    for campo in ("costo_divisa", "precio_divisa"):
        valido, mensaje = validar_monto(datos.get(campo, 0), campo.replace("_", " "))
        if not valido:
            return error(mensaje, 400)

    empresa_id = empresa_activa_id()
    if Producto.query.filter_by(empresa_id=empresa_id, codigo=codigo).first():
        return error("Ya existe un producto con ese codigo", 409)

    producto = Producto(
        empresa_id=empresa_id,
        categoria_id=datos.get("categoria_id") or None,
        codigo=codigo,
        codigo_barras=limpiar_texto(datos.get("codigo_barras"), 60),
        nombre=nombre,
        descripcion=limpiar_texto(datos.get("descripcion"), 255),
        unidad_medida=limpiar_texto(datos.get("unidad_medida"), 20) or "UND",
        costo_divisa=float(datos.get("costo_divisa") or 0),
        precio_divisa=float(datos.get("precio_divisa") or 0),
        iva_porcentaje=float(datos.get("iva_porcentaje") or 16.0),
        stock_actual=float(datos.get("stock_actual") or 0),
        stock_minimo=float(datos.get("stock_minimo") or 0),
        activo=bool(datos.get("activo", True)),
    )
    db.session.add(producto)
    db.session.commit()

    # Registramos el stock inicial como movimiento de entrada.
    if producto.stock_actual:
        db.session.add(
            MovimientoInventario(
                empresa_id=empresa_id,
                producto_id=producto.id,
                tipo="entrada",
                cantidad=producto.stock_actual,
                costo_unitario=producto.costo_divisa,
                stock_resultante=producto.stock_actual,
                motivo="Carga inicial de inventario",
                usuario=usuario_actual()["email"],
            )
        )
        db.session.commit()

    registrar("crear", "inventario", "productos", producto.id, nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(producto.a_diccionario(), "Producto creado", 201)


@inventario_bp.route("/productos/<int:producto_id>", methods=["PUT"])
@requiere_sesion
def actualizar_producto(producto_id: int):
    producto = Producto.query.get(producto_id)
    if producto is None:
        return error("Producto no encontrado", 404)
    datos = request.get_json(silent=True) or {}
    if "nombre" in datos:
        producto.nombre = limpiar_texto(datos["nombre"], 150) or producto.nombre
    if "codigo" in datos:
        producto.codigo = limpiar_texto(datos["codigo"], 40) or producto.codigo
    if "codigo_barras" in datos:
        producto.codigo_barras = limpiar_texto(datos["codigo_barras"], 60)
    if "descripcion" in datos:
        producto.descripcion = limpiar_texto(datos["descripcion"], 255)
    if "unidad_medida" in datos:
        producto.unidad_medida = limpiar_texto(datos["unidad_medida"], 20)
    if "categoria_id" in datos:
        producto.categoria_id = datos["categoria_id"] or None
    for campo in ("costo_divisa", "precio_divisa", "iva_porcentaje", "stock_minimo"):
        if campo in datos and datos[campo] is not None:
            setattr(producto, campo, float(datos[campo]))
    if "activo" in datos:
        producto.activo = bool(datos["activo"])

    db.session.commit()
    registrar("modificar", "inventario", "productos", producto.id, producto.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(producto.a_diccionario(), "Producto actualizado")


@inventario_bp.route("/productos/<int:producto_id>", methods=["DELETE"])
@solo_administrador
def eliminar_producto(producto_id: int):
    producto = Producto.query.get(producto_id)
    if producto is None:
        return error("Producto no encontrado", 404)
    # Lo desactivamos en vez de borrarlo para no romper el historico.
    producto.activo = False
    db.session.commit()
    registrar("eliminar", "inventario", "productos", producto.id, producto.nombre,
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(None, "Producto desactivado")


# ------------------------------------------------------------
# Movimientos y ajustes de stock
# ------------------------------------------------------------
@inventario_bp.route("/movimientos", methods=["GET"])
@requiere_sesion
def listar_movimientos():
    empresa_id = empresa_activa_id()
    producto_id = request.args.get("producto_id", type=int)
    consulta = MovimientoInventario.query.filter_by(empresa_id=empresa_id)
    if producto_id:
        consulta = consulta.filter_by(producto_id=producto_id)
    movimientos = consulta.order_by(MovimientoInventario.id.desc()).limit(200).all()
    datos = []
    for movimiento in movimientos:
        item = movimiento.a_diccionario()
        item["producto_nombre"] = movimiento.producto.nombre if movimiento.producto else ""
        datos.append(item)
    return exito(datos, "Movimientos de inventario")


@inventario_bp.route("/productos/<int:producto_id>/ajuste", methods=["POST"])
@requiere_sesion
def ajustar_stock(producto_id: int):
    """Registra una entrada, salida o ajuste de stock.

    Usamos una transaccion atomica y verificamos el stock con
    bloqueo para evitar que quede en negativo por ventas simultaneas.
    """
    datos = request.get_json(silent=True) or {}
    tipo = (datos.get("tipo") or "ajuste").lower()
    if tipo not in ("entrada", "salida", "ajuste"):
        return error("Tipo de movimiento no valido", 400)
    valido, mensaje = validar_monto(datos.get("cantidad"), "cantidad", permitir_negativo=True)
    if not valido:
        return error(mensaje, 400)
    cantidad = float(datos["cantidad"])
    if cantidad <= 0:
        return error("La cantidad debe ser mayor que cero", 400)

    try:
        # Bloqueamos la fila para que nadie mas la modifique a la vez.
        producto = Producto.query.filter_by(id=producto_id).with_for_update().first()
        if producto is None:
            return error("Producto no encontrado", 404)

        if tipo == "entrada":
            stock_nuevo = producto.stock_actual + cantidad
            variacion = cantidad
        elif tipo == "salida":
            if producto.stock_actual < cantidad:
                db.session.rollback()
                return error(
                    f"Stock insuficiente. Disponible: {producto.stock_actual:.2f}", 409
                )
            stock_nuevo = producto.stock_actual - cantidad
            variacion = -cantidad
        else:  # ajuste: la cantidad es el stock final
            variacion = cantidad - producto.stock_actual
            stock_nuevo = cantidad

        producto.stock_actual = stock_nuevo
        movimiento = MovimientoInventario(
            empresa_id=producto.empresa_id,
            producto_id=producto.id,
            tipo=tipo,
            cantidad=abs(variacion),
            costo_unitario=producto.costo_divisa,
            stock_resultante=stock_nuevo,
            motivo=limpiar_texto(datos.get("motivo"), 150) or "Ajuste manual",
            usuario=usuario_actual()["email"],
        )
        db.session.add(movimiento)
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return error("No se pudo aplicar el ajuste de inventario", 500)

    registrar("modificar", "inventario", "productos", producto.id, f"Ajuste {tipo} {cantidad}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito({"stock_actual": stock_nuevo, "movimiento_id": movimiento.id}, "Stock actualizado")


# ------------------------------------------------------------
# Excel: exportar / importar
# ------------------------------------------------------------
@inventario_bp.route("/exportar", methods=["GET"])
@requiere_sesion
def exportar_excel():
    """Genera un Excel con todo el inventario."""
    from app.services import export_service

    empresa_id = empresa_activa_id()
    productos = Producto.query.filter_by(empresa_id=empresa_id).order_by(Producto.nombre).all()
    filas = [
        {
            "Codigo": p.codigo,
            "Codigo de barras": p.codigo_barras,
            "Nombre": p.nombre,
            "Categoria": p.categoria.nombre if p.categoria else "",
            "Unidad": p.unidad_medida,
            "Costo USD": p.costo_divisa,
            "Precio USD": p.precio_divisa,
            "IVA %": p.iva_porcentaje,
            "Stock": p.stock_actual,
            "Stock minimo": p.stock_minimo,
            "Activo": "Si" if p.activo else "No",
        }
        for p in productos
    ]
    ruta = export_service.exportar_excel(filas, "Inventario", "inventario")
    return exito({"archivo": ruta}, "Inventario exportado")


@inventario_bp.route("/importar", methods=["POST"])
@requiere_sesion
def importar_excel():
    """Importa productos desde un archivo Excel.

    Se esperan columnas: Codigo, Nombre, Costo USD, Precio USD,
    Stock, Stock minimo (las demas son opcionales).
    """
    import pandas as pd

    archivo = request.files.get("archivo")
    if archivo is None:
        return error("Debe adjuntar un archivo Excel", 400)
    try:
        marco = pd.read_excel(archivo)
    except Exception:
        return error("No se pudo leer el archivo. Verifique que sea un Excel valido", 400)

    columnas = {c.strip().lower(): c for c in marco.columns}
    if "codigo" not in columnas or "nombre" not in columnas:
        return error("El Excel debe tener al menos las columnas 'Codigo' y 'Nombre'", 400)

    empresa_id = empresa_activa_id()
    creados, actualizados, errores = 0, 0, 0
    for _, fila in marco.iterrows():
        try:
            codigo = str(fila[columnas["codigo"]]).strip()
            nombre = limpiar_texto(fila[columnas["nombre"]], 150)
            if not codigo or not nombre or codigo.lower() == "nan":
                errores += 1
                continue

            def _valor(campo, defecto=0):
                clave = columnas.get(campo)
                if clave is None:
                    return defecto
                valor = fila[clave]
                try:
                    return float(valor)
                except (TypeError, ValueError):
                    return defecto

            producto = Producto.query.filter_by(empresa_id=empresa_id, codigo=codigo).first()
            if producto is None:
                producto = Producto(empresa_id=empresa_id, codigo=codigo, nombre=nombre)
                db.session.add(producto)
                creados += 1
            else:
                actualizados += 1
            producto.nombre = nombre
            producto.costo_divisa = _valor("costo usd", producto.costo_divisa or 0)
            producto.precio_divisa = _valor("precio usd", producto.precio_divisa or 0)
            producto.stock_actual = _valor("stock", producto.stock_actual or 0)
            producto.stock_minimo = _valor("stock minimo", producto.stock_minimo or 0)
            db.session.commit()
        except Exception:
            db.session.rollback()
            errores += 1

    registrar("importar", "inventario", "productos", None,
              f"Creados {creados}, actualizados {actualizados}, errores {errores}",
              usuario=usuario_actual()["email"], ip=request.remote_addr)
    return exito(
        {"creados": creados, "actualizados": actualizados, "errores": errores},
        "Importacion finalizada",
    )
