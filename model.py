from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from sqlalchemy import CheckConstraint, Enum, UniqueConstraint, func
from sqlalchemy.dialects.mysql import LONGTEXT
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def _normalizar_unidad_texto(texto: str | None) -> str:
    return (texto or "").strip().lower().replace(".", "").replace(" ", "")


def _factor_y_tipo_unidad(unidad) -> tuple[Decimal, str]:
    abbr = _normalizar_unidad_texto(getattr(unidad, "abreviacion", ""))
    nombre = _normalizar_unidad_texto(getattr(unidad, "nombre", ""))
    clave = abbr or nombre

    mapa = {
        "kg": (Decimal("1000"), "solido"),
        "kgr": (Decimal("1000"), "solido"),
        "kilogramo": (Decimal("1000"), "solido"),
        "kilogramos": (Decimal("1000"), "solido"),
        "g": (Decimal("1"), "solido"),
        "gr": (Decimal("1"), "solido"),
        "grs": (Decimal("1"), "solido"),
        "gramo": (Decimal("1"), "solido"),
        "gramos": (Decimal("1"), "solido"),
        "oz": (Decimal("28.35"), "solido"),
        "l": (Decimal("1000"), "liquido"),
        "lt": (Decimal("1000"), "liquido"),
        "litro": (Decimal("1000"), "liquido"),
        "litros": (Decimal("1000"), "liquido"),
        "ml": (Decimal("1"), "liquido"),
        "mililitro": (Decimal("1"), "liquido"),
        "mililitros": (Decimal("1"), "liquido"),
        "pz": (Decimal("1"), "conteo"),
        "pieza": (Decimal("1"), "conteo"),
        "piezas": (Decimal("1"), "conteo"),
        "u": (Decimal("1"), "conteo"),
        "ud": (Decimal("1"), "conteo"),
        "unidad": (Decimal("1"), "conteo"),
        "unidades": (Decimal("1"), "conteo"),
    }

    if clave in mapa:
        return mapa[clave]

    factor_db = Decimal(str(getattr(unidad, "factor", 1) or 1))
    tipo_db = str(getattr(unidad, "tipo", "")).strip().lower()
    return factor_db, tipo_db

def convertir(cantidad, unidad_origen, unidad_destino):
    factor_origen, tipo_origen = _factor_y_tipo_unidad(unidad_origen)
    factor_destino, tipo_destino = _factor_y_tipo_unidad(unidad_destino)

    if tipo_origen != tipo_destino:
        raise ValueError("Unidades incompatibles")

    cantidad = Decimal(str(cantidad))

    cantidad_base = cantidad * factor_origen
    return cantidad_base / factor_destino

class Rol(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(20), nullable=False, unique=True, index=True)


class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    correo = db.Column(db.String(120), unique=True, nullable=False, index=True)
    contrasenaHash = db.Column("password_hash", db.String(255), nullable=False)
    rolId = db.Column("rol_id", db.Integer, db.ForeignKey("roles.id"), nullable=False, index=True)
    estado = db.Column(db.String(20), nullable=False, default="Activo")
    intentosFallidos = db.Column("intentos_fallidos", db.Integer, nullable=False, default=0)
    cuentaBloqueada = db.Column("cuenta_bloqueada", db.Boolean, nullable=False, default=False)
    bloqueoHasta = db.Column("bloqueo_hasta", db.DateTime(timezone=True), nullable=True)
    creadoEn = db.Column("creado_en", db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    rolRef = db.relationship("Rol", backref=db.backref("usuarios", lazy=True))

    @property
    def rol(self) -> str:
        return self.rolRef.nombre if self.rolRef else ""

    def establecerContrasena(self, contrasena: str) -> None:
        self.contrasenaHash = generate_password_hash(contrasena)

    def validarContrasena(self, contrasena: str) -> bool:
        return check_password_hash(self.contrasenaHash, contrasena)

    def estaBloqueada(self) -> bool:
        if not self.cuentaBloqueada:
            return False

        ahora = datetime.now(timezone.utc)
        bloqueoHastaNormalizado = self.bloqueoHasta
        if bloqueoHastaNormalizado and bloqueoHastaNormalizado.tzinfo is None:
            bloqueoHastaNormalizado = bloqueoHastaNormalizado.replace(tzinfo=timezone.utc)

        if bloqueoHastaNormalizado and ahora >= bloqueoHastaNormalizado:
            self.cuentaBloqueada = False
            self.intentosFallidos = 0
            self.bloqueoHasta = None
            return False

        return True

    def registrarIntentoFallido(self, maxIntentos: int = 3, minutosBloqueo: int = 15) -> None:
        self.intentosFallidos += 1

        if self.intentosFallidos >= maxIntentos:
            self.cuentaBloqueada = True
            self.bloqueoHasta = datetime.now(timezone.utc) + timedelta(minutes=minutosBloqueo)

    def resetearSeguridad(self) -> None:
        self.intentosFallidos = 0
        self.cuentaBloqueada = False
        self.bloqueoHasta = None


class RegistroSesion(db.Model):
    __tablename__ = "registros_sesion"

    id = db.Column(db.Integer, primary_key=True)
    usuarioId = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    tokenSesion = db.Column(db.String(128), nullable=False, index=True)
    direccionIp = db.Column(db.String(64), nullable=True)
    agenteUsuario = db.Column(db.String(255), nullable=True)
    fechaInicio = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    fechaFin = db.Column(db.DateTime(timezone=True), nullable=True)
    activa = db.Column(db.Boolean, nullable=False, default=True)
    

class UnidadMedida(db.Model):
    __tablename__ = 'Unidad_medida'
    id_unidad = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(10), nullable=False)
    abreviacion = db.Column(db.String(4), unique=True)
    tipo = db.Column(Enum("liquido", "solido", "conteo", name="tipo_unidad"), nullable=False)
    factor = db.Column(db.Numeric(10, 4), nullable=False)

    
class MateriaPrima(db.Model):
    __tablename__ = 'Materia_prima' 

    id_materia = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    unidad_medida = db.Column(db.Integer, db.ForeignKey('Unidad_medida.id_unidad'), nullable=False) 
    stock_minimo = db.Column(db.Numeric(10, 2), default=0.00)
    stock_actual = db.Column(db.Numeric(10, 2), default=0.00)
    estatus = db.Column(db.Boolean, default=True)
    costo_promedio = db.Column(db.Numeric(10, 2), default=0)

    
    unidad = db.relationship('UnidadMedida', backref='materias_primas')
    detalles_compra = db.relationship('DetalleCompra', backref='materia_prima', lazy=True)

    def actualizar_costo_promedio(self, nuevo_costo, cantidad):
        nuevo_costo_dec = Decimal(str(nuevo_costo))
        cantidad_dec = Decimal(str(cantidad))

        if self.stock_actual and self.stock_actual > 0:
            stock_actual_dec = Decimal(str(self.stock_actual))
            costo_actual_dec = Decimal(str(self.costo_promedio or 0))
            costo_anterior = costo_actual_dec * stock_actual_dec
            costo_nuevo = nuevo_costo_dec * cantidad_dec
            total_costo = costo_anterior + costo_nuevo
            total_stock = stock_actual_dec + cantidad_dec
            if total_stock > 0:
                self.costo_promedio = float(total_costo / total_stock)
        else:
            self.costo_promedio = float(nuevo_costo_dec)


    def actualizar_stock(self, cantidad):

        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a 0")

        cantidad_dec     = Decimal(str(cantidad))
        stock_actual_dec = Decimal(str(self.stock_actual or 0))

        self.stock_actual = stock_actual_dec + cantidad_dec

    def revertir_stock(self, cantidad):
        
        if cantidad <= 0:
            raise ValueError("La cantidad debe ser mayor a 0")

        cantidad_dec     = Decimal(str(cantidad))
        stock_actual_dec = Decimal(str(self.stock_actual or 0))

        nuevo_stock = stock_actual_dec - cantidad_dec

        self.stock_actual = max(nuevo_stock, Decimal('0'))

class Producto(db.Model):
    __tablename__ = 'Producto'

    id_producto = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(50), nullable=False)
    categoria = db.Column(Enum('bebidas', 'alimentos', name='categoria_enum'), nullable=False)
    precio_venta = db.Column(db.Numeric(10, 2))
    stock = db.Column(db.Integer, nullable=False, default=0)
    stockMinimo = db.Column("stock_minimo", db.Integer, nullable=False, default=0)
    descripcion = db.Column(db.Text, nullable=False)
    imagen = db.Column(LONGTEXT, nullable=True)
    estatus = db.Column(db.Boolean, default=True)
    
    def costo_unitario(self):
   
        if not self.recetas:
            return Decimal('0')
        total = Decimal('0')
        for receta in self.recetas:
            if receta.materiaPrima:
                cantidad = Decimal(str(receta.cantidad))
                costo = Decimal(str(receta.materiaPrima.costo_promedio or 0))
                total += cantidad * costo
        return total
    
    def margen_ganancia(self):
        costo = self.costo_unitario()
        if self.precio_venta:
            return Decimal(str(self.precio_venta)) - costo
        return Decimal('0')

    def margen_porcentaje(self):
        costo = self.costo_unitario()
        if self.precio_venta and self.precio_venta > 0:
            return ((Decimal(str(self.precio_venta)) - costo) / Decimal(str(self.precio_venta))) * 100
        return Decimal('0')

    def to_dict_rentabilidad(self):
        return {
            'id': self.id_producto,
            'nombre': self.nombre,
            'precio': float(self.precio_venta) if self.precio_venta else 0,
            'costo': float(self.costo_unitario()),
            'margen': float(self.margen_ganancia()),
            'porcentaje': float(self.margen_porcentaje())
        }

    
class Proveedores(db.Model):
    __tablename__ = 'Proveedor'

    id  = db.Column('id_proveedor', db.Integer, primary_key=True, autoincrement=True)
    rfc = db.Column('RFC',    db.String(13),  unique=True, nullable=False)
    nombre = db.Column(          db.String(100), nullable=False)
    email = db.Column('correo', db.String(50),  nullable=True)
    telefono = db.Column(          db.String(15),  nullable=True)
    colonia = db.Column(db.String(100), nullable=True)
    calle = db.Column(db.String(100), nullable=True)
    num_exterior = db.Column(db.String(10), nullable=True)
    estado = db.Column('estatus',db.Boolean,     default=True)

    compras = db.relationship('Compra', backref='proveedor', lazy=True)


class Merma(db.Model):
    id_merma = db.Column(db.Integer, primary_key=True)
    cantidad = db.Column(db.Numeric(10, 2), nullable = False)
    fecha = db.Column( db.Date , default=date.today, nullable = False)
    motivo = db.Column(Enum(
                            "Error en preparación",
                            "Derrame o caída",
                            "Insumo en mal estado",
                            "Producto caducado",
                            "Sobrante de producción diaria",
                            "Falla de refrigeración/almacenaje",
                            "Muestra o degustación",
                            "Pérdida no identificada",
                            "Devolución por cliente", 
      name='merma_enum'  
    ), nullable = False)
    
    materia_id = db.Column(db.Integer, db.ForeignKey('Materia_prima.id_materia'), nullable=False)
    materia = db.relationship('MateriaPrima', backref='mermas')
    
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    usuario = db.relationship('Usuario', backref='mermas_registradas')
    

class Compra(db.Model):
    __tablename__ = 'compra'

    id_compra = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_proveedor = db.Column(db.Integer, db.ForeignKey('Proveedor.id_proveedor'), nullable=False)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    detalles = db.relationship('DetalleCompra',
        backref='compra', lazy=True, cascade='all, delete-orphan'
    )
    
    @property
    def precio_total(self):

        return sum((detalle.cantidad * detalle.costo_unitario)
            for detalle in self.detalles
        )
    
    
class DetalleCompra(db.Model):
    __tablename__ = 'detalle_compra'

    id_detalle_compra = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_compra = db.Column(db.Integer, db.ForeignKey('compra.id_compra'), nullable=False)
    id_materia = db.Column(db.Integer, db.ForeignKey('Materia_prima.id_materia'), nullable=False)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    unidad = db.Column(db.Integer, db.ForeignKey('Unidad_medida.id_unidad'), nullable=False)
    costo_unitario = db.Column(db.Numeric(10, 2), nullable=False)

    unidad_medida = db.relationship('UnidadMedida', backref='detalles_compra')
    
    @property
    def subtotal(self):    
        return self.cantidad * self.costo_unitario
    

class Cliente(db.Model):
    __tablename__ = "clientes"

    id = db.Column(db.Integer, primary_key=True)
    usuarioId = db.Column(db.Integer, db.ForeignKey("usuarios.id"), unique=True, nullable=False)
    
    nombre = db.Column(db.String(120), nullable=False)
    apellidoPaterno = db.Column(db.String(50), nullable=False)
    apellidoMaterno = db.Column(db.String(50), nullable=True)
    telefono = db.Column(db.String(15), nullable=True)
    alias = db.Column(db.String(50), nullable=True)
    estado = db.Column(db.Boolean, default=True)  # Usa Boolean si solo almacenas activo/inactivo
    creadoEn = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    usuario = db.relationship("Usuario", backref=db.backref("cliente", uselist=False), lazy="joined")
    
class Empleado(db.Model):
    __tablename__ = "empleados"

    id = db.Column(db.Integer, primary_key=True)
    usuarioId = db.Column(db.Integer, db.ForeignKey("usuarios.id"), unique=True, nullable=False)
    username = db.Column(db.String(60), unique=True, nullable=False)

    nombre = db.Column(db.String(60), nullable=False)
    fechaIngreso = db.Column(db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    estado = db.Column(db.Boolean, default=True)
    usuario = db.relationship("Usuario", backref=db.backref("empleado", uselist=False), lazy="joined")

class Venta(db.Model):
    __tablename__ = "ventas"

    id_venta = db.Column(db.Integer, primary_key=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    id_cliente = db.Column(db.Integer, db.ForeignKey("clientes.id"), nullable=True)
    
    total = db.Column(db.Numeric(10, 2), nullable=False, default=0)
    utilidadBruta = db.Column("utilidad_bruta", db.Numeric(10, 2), nullable=False, default=0)
    estatus = db.Column(db.Boolean, nullable=False, default=False)
    estado = db.Column(db.String(20), default='entregado')
    fecha = db.Column("creado_en", db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    tipo_venta = db.Column(Enum('fisica','en_linea', name="tipo_venta"), nullable=False)  
    metodo_pago = db.Column(db.String(30), nullable=True)
    codigo_recogida = db.Column(db.String(10), nullable=True)
    
    cliente = db.relationship("Cliente", backref="ventas")
    usuario = db.relationship("Usuario", backref="ventas_realizadas")


'''Tabla Detalles de Venta'''
class DetalleVenta(db.Model):
    __tablename__ = "detalle_venta"

    id_detalle = db.Column(db.Integer, primary_key=True)
    id_venta = db.Column(db.Integer, db.ForeignKey("ventas.id_venta"), nullable=False, index=True)
    id_producto = db.Column(db.Integer, db.ForeignKey("Producto.id_producto"), nullable=False, index=True)
    
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False, default = 0)
    tipo_descuento = db.Column(Enum('monto','porcentaje', name="tipo_descuento"), default = 'monto')  
    descuento = db.Column(db.Numeric(10, 2), default=0.00)

    venta = db.relationship("Venta", backref="detalles")
    producto = db.relationship("Producto")

'''Tabla Pedidos'''
class Pedido(db.Model):
    __tablename__ = "pedidos"

    id_pedido = db.Column(db.Integer, primary_key=True)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    
    hora_solicitud = db.Column(db.DateTime, nullable=False, server_default=func.now())
    hora_recogida = db.Column(db.DateTime, nullable=False)
    notas = db.Column(db.String(200))

    estado = db.Column(db.String(20), default="pendiente")
    id_venta = db.Column(db.Integer, db.ForeignKey("ventas.id_venta"), nullable=True)


class SolicitudProduccion(db.Model):
    __tablename__ = "Solicitud_produccion"

    id_solicitud = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_usuario = db.Column(db.Integer, db.ForeignKey("usuarios.id"), nullable=False, index=True)
    fecha = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    estado = db.Column(
        Enum("pendiente", "en_proceso", "finalizado", "cancelado", name="estado_solicitud_enum"),
        nullable=False,
        default="pendiente",
    )

    usuario = db.relationship("Usuario", backref=db.backref("solicitudes_produccion", lazy=True))
    detalles = db.relationship(
        "DetalleProduccion",
        backref="solicitud",
        lazy=True,
        cascade="all, delete-orphan",
    )


class DetalleProduccion(db.Model):
    __tablename__ = "Detalle_produccion"

    id_detalle = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_solicitud = db.Column(db.Integer, db.ForeignKey("Solicitud_produccion.id_solicitud"), nullable=False, index=True)
    id_producto = db.Column(db.Integer, db.ForeignKey("Producto.id_producto"), nullable=False, index=True)
    cantidad = db.Column(db.Integer, nullable=False)

    producto = db.relationship("Producto", backref=db.backref("detalles_produccion", lazy=True))


class Receta(db.Model):
    __tablename__ = "Recetas"
    __table_args__ = (
        UniqueConstraint("id_producto", "id_materia", name="uq_receta_producto_materia"),
        CheckConstraint("cantidad > 0", name="chk_receta_cantidad_mayor_cero"),
    )

    id_receta = db.Column(db.Integer, primary_key=True, autoincrement=True)
    id_producto = db.Column(db.Integer, db.ForeignKey("Producto.id_producto"), nullable=False, index=True)
    id_materia = db.Column(db.Integer, db.ForeignKey("Materia_prima.id_materia"), nullable=False, index=True)
    cantidad = db.Column(db.Numeric(10, 2), nullable=False)
    estado = db.Column(db.Boolean, nullable=False, default=True, index=True)

    producto = db.relationship("Producto", backref=db.backref("recetas", lazy=True))
    materiaPrima = db.relationship("MateriaPrima", backref=db.backref("recetas", lazy=True))

    @property
    def nombre_materia(self) -> str:
        return self.materiaPrima.nombre if self.materiaPrima else ""

    @property
    def unidad_materia(self) -> str:
        if not self.materiaPrima or not self.materiaPrima.unidad:
            return ""
        return self.materiaPrima.unidad.abreviacion or self.materiaPrima.unidad.nombre

    @classmethod
    def validar_insumos_no_vacios(cls, insumos: list[dict]) -> None:
        if not insumos:
            raise ValueError("No se puede registrar una receta sin insumos.")

    @classmethod
    def validar_insumos_en_inventario(cls, insumos: list[dict]) -> None:
        ids_materia = [int(insumo.get("id_materia", 0)) for insumo in insumos]
        if any(id_materia <= 0 for id_materia in ids_materia):
            raise ValueError("Todos los insumos deben tener un id_materia válido.")

        materias = MateriaPrima.query.filter(
            MateriaPrima.id_materia.in_(ids_materia),
            MateriaPrima.estatus.is_(True),
        ).all()

        ids_disponibles = {m.id_materia for m in materias}
        ids_faltantes = [id_materia for id_materia in ids_materia if id_materia not in ids_disponibles]

        if ids_faltantes:
            raise ValueError("Hay insumos que no existen en inventario o están inactivos.")

    @classmethod
    def validar_activa_para_produccion(cls, id_producto: int) -> None:
        existe_activa = cls.query.filter_by(id_producto=id_producto, estado=True).first()
        if not existe_activa:
            raise ValueError("La receta del producto está inactiva o no existe.")

    @classmethod
    def producto_tiene_produccion_finalizada(cls, id_producto: int) -> bool:
        return (
            db.session.query(DetalleProduccion.id_detalle)
            .join(SolicitudProduccion, DetalleProduccion.id_solicitud == SolicitudProduccion.id_solicitud)
            .filter(
                DetalleProduccion.id_producto == id_producto,
                SolicitudProduccion.estado == "finalizado",
            )
            .first()
            is not None
        )

    @classmethod
    def reemplazar_receta_producto(cls, id_producto: int, insumos: list[dict]) -> list["Receta"]:
        cls.validar_insumos_no_vacios(insumos)
        cls.validar_insumos_en_inventario(insumos)

        producto = Producto.query.get(id_producto)
        if not producto:
            raise ValueError("El producto indicado no existe.")

        recetas_activas = cls.query.filter_by(id_producto=id_producto, estado=True).all()
        mapa_activas = {receta.id_materia: receta for receta in recetas_activas}

        mapa_entrada: dict[int, Decimal] = {}
        for insumo in insumos:
            id_materia = int(insumo.get("id_materia", 0))
            cantidad = Decimal(str(insumo.get("cantidad", 0)))

            if cantidad <= 0:
                raise ValueError("La cantidad de cada insumo debe ser mayor a cero.")

            if id_materia in mapa_entrada:
                raise ValueError("No se puede repetir el mismo insumo en la receta del producto.")

            mapa_entrada[id_materia] = cantidad

        if cls.producto_tiene_produccion_finalizada(id_producto):
            snapshot_actual = {receta.id_materia: Decimal(str(receta.cantidad)) for receta in recetas_activas}
            if snapshot_actual != mapa_entrada:
                raise ValueError(
                    "No se puede modificar la receta porque el producto ya tiene producciones finalizadas. "
                    "Esto protege la persistencia histórica."
                )

        nuevas_recetas: list[Receta] = []
        for id_materia, cantidad in mapa_entrada.items():
            receta_existente = cls.query.filter_by(id_producto=id_producto, id_materia=id_materia).first()
            if receta_existente:
                receta_existente.cantidad = cantidad
                receta_existente.estado = True
                nuevas_recetas.append(receta_existente)
            else:
                nueva = cls(
                    id_producto=id_producto,
                    id_materia=id_materia,
                    cantidad=cantidad,
                    estado=True,
                )
                db.session.add(nueva)
                nuevas_recetas.append(nueva)

        for id_materia, receta_activa in mapa_activas.items():
            if id_materia not in mapa_entrada:
                receta_activa.estado = False

        return nuevas_recetas