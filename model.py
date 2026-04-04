from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from sqlalchemy import Enum
from sqlalchemy.dialects.mysql import LONGTEXT
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

class Usuario(db.Model):
    __tablename__ = "usuarios"

    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(120), nullable=False)
    correo = db.Column(db.String(120), unique=True, nullable=False, index=True)
    contrasenaHash = db.Column("password_hash", db.String(255), nullable=False)
    rol = db.Column(db.String(20), nullable=False)
    estado = db.Column(db.String(20), nullable=False, default="Activo")
    intentosFallidos = db.Column("intentos_fallidos", db.Integer, nullable=False, default=0)
    cuentaBloqueada = db.Column("cuenta_bloqueada", db.Boolean, nullable=False, default=False)
    bloqueoHasta = db.Column("bloqueo_hasta", db.DateTime(timezone=True), nullable=True)
    creadoEn = db.Column("creado_en", db.DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

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

    def registrarIntentoFallido(self, maxIntentos: int = 4, minutosBloqueo: int = 15) -> None:
        self.intentosFallidos += 1

        if self.intentosFallidos >= maxIntentos:
            self.cuentaBloqueada = True
            # Bloqueo temporal para frenar ataques de fuerza bruta sin deshabilitar la cuenta de forma permanente.
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
    
#Tablas Feacture/Productos 

class UnidadMedida(db.Model):
    __tablename__ = 'Unidad_medida'
    id_unidad = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(10), nullable=False)
    abreviacion = db.Column(db.String(4), unique=True)

class MateriaPrima(db.Model):
    __tablename__ = 'Materia_prima' 

    id_materia = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.Text, nullable=True)
    unidad_medida = db.Column(db.Integer, db.ForeignKey('Unidad_medida.id_unidad'), nullable=False) 
    stock_minimo = db.Column(db.Numeric(10, 2), default=0.00)
    stock_actual = db.Column(db.Numeric(10, 2), default=0.00)
    estatus = db.Column(db.Boolean, default=True)
    
    unidad = db.relationship('UnidadMedida', backref='materias_primas')
    detalles_compra = db.relationship('DetalleCompra', backref='materia_prima', lazy=True)

    def actualizar_stock(self, cantidad, costo_unitario):

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
    descripcion = db.Column(db.Text, nullable=False)
    imagen = db.Column(LONGTEXT, nullable=True)
    estatus = db.Column(db.Boolean, default=True)
    
class Proveedores(db.Model):
    __tablename__ = 'Proveedor'

    id  = db.Column('id_proveedor', db.Integer, primary_key=True, autoincrement=True)
    rfc = db.Column('RFC',    db.String(13),  unique=True, nullable=False)
    nombre = db.Column(          db.String(100), nullable=False)
    email = db.Column('correo', db.String(50),  nullable=True)
    telefono = db.Column(          db.String(15),  nullable=True)
    colonia = db.Column( db.String(25),  nullable=True)
    calle = db.Column( db.String(25),  nullable=True)
    num_exterior = db.Column( db.String(5),  nullable=True)
    estado = db.Column('estatus',db.Boolean,     default=True)

    compras = db.relationship('Compra', backref='proveedor', lazy=True)


# Tabla de merma 
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