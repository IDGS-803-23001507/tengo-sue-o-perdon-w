from datetime import datetime, timedelta, timezone, date
from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy import CheckConstraint, Enum, UniqueConstraint, func
from sqlalchemy.dialects.mysql import LONGTEXT
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash
import enum

db = SQLAlchemy()

class TipoProducto(enum.Enum):
    ALIMENTO = 'ALIMENTO'
    BEBIDA = 'BEBIDA'
    COMBO = 'COMBO'


class Productoo(db.Model):
    __tablename__ = 'Productoo'
    idProducto = db.Column(db.Integer, primary_key=True, autoincrement=True)
    nombre = db.Column(db.String(50), nullable=False)
    descripcion = db.Column(db.String(200), nullable=False)
    foto = db.Column(db.Text) 
    precio = db.Column(db.Numeric(10, 2))
    tipo = db.Column(db.Enum(TipoProducto), nullable=False)
    estatus = db.Column(db.Boolean, default=True)

class Alimento(db.Model):
    __tablename__ = 'Alimento'
    idAlimento = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idProducto = db.Column(db.Integer, db.ForeignKey('Productoo.idProducto'), nullable=False)

class Bebida(db.Model):
    __tablename__ = 'Bebida'
    idBebida = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idProducto = db.Column(db.Integer, db.ForeignKey('Productoo.idProducto'), nullable=False)

class Combo(db.Model):
    __tablename__ = 'Combo'
    idCombo = db.Column( db.Integer, primary_key=True, autoincrement=True)
    idProducto = db.Column(db.Integer, db.ForeignKey('Productoo.idProducto'), nullable=False)
    producto = db.relationship("Productoo", backref="combo")
    detalles = db.relationship("DetalleCombo", backref="combo", cascade="all, delete-orphan")


class DetalleCombo(db.Model):
    __tablename__ = 'DetalleCombo'
    idDetalleCombo = db.Column(db.Integer, primary_key=True, autoincrement=True)
    idCombo = db.Column(db.Integer, db.ForeignKey('Combo.idCombo'), nullable=False)
    idProducto = db.Column(db.Integer, db.ForeignKey('Productoo.idProducto'), nullable=False)
    cantidad = db.Column(db.Integer, nullable=False, default=1)
    producto = db.relationship("Productoo")
    
class Pedidoo(db.Model):
    __tablename__ = "Pedidoo"
    idPedido = db.Column(db.Integer,primary_key=True, autoincrement=True)
    
    idCliente = db.Column(
        db.Integer,
        db.ForeignKey("clientes.id"),
        nullable=False
    )
    
    total = db.Column(db.Numeric(10, 2), nullable=False)
    notas = db.Column(db.String(300))
    fecha = db.Column(db.DateTime,default=datetime.utcnow)
    estado = db.Column(db.String(30),default="Pendiente")
    cliente = db.relationship("Cliente", backref="pedidos")
    
    
class DetallePedidoo(db.Model):
    __tablename__ = "DetallePedidoo"
    idDetallePedido = db.Column( db.Integer, primary_key=True, autoincrement=True)
    idPedido = db.Column(db.Integer, db.ForeignKey("Pedidoo.idPedido"), nullable=False)
    idProducto = db.Column(db.Integer, db.ForeignKey("Productoo.idProducto"), nullable=False)
    cantidad = db.Column( db.Integer, nullable=False)
    precio = db.Column( db.Numeric(10, 2), nullable=False)

class Sucursal(db.Model):
        __tablename__ = "Sucursal"
        idSucursal = db.Column(db.Integer, primary_key=True,autoincrement=True)
        nombre = db.Column(db.String(50),nullable=False)
        foto = db.Column(LONGTEXT)
        ciudad = db.Column(db.String(50),nullable=False)
        calle = db.Column(db.String(50),nullable=False)
        colonia = db.Column(db.String(50),nullable=False)
        numInt = db.Column(db.String(10),nullable=False)
        cp = db.Column(db.String(10),nullable=False)
        estatus = db.Column(db.Boolean,default=True)


        def to_dict(self):
            return {
                "idSucursal": self.idSucursal,
                "nombre": self.nombre,
                "foto": self.foto,
                "ciudad": self.ciudad,
                "calle": self.calle,
                "colonia": self.colonia,
                "numInt": self.numInt,
                "cp": self.cp,
                "estatus": self.estatus
            }


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
    verificado = db.Column(db.Boolean, default=False)
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
