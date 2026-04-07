from datetime import date, datetime
from flask_wtf import FlaskForm
from wtforms import StringField, DateTimeLocalField, IntegerField, RadioField, TextAreaField, PasswordField, DecimalField, DateField, SelectField, HiddenField, SubmitField
from wtforms.validators import DataRequired, ValidationError, NumberRange, EqualTo, Length, Email, Optional

ROLES_USUARIO = [
    ("Admin General (TI)", "Admin General (TI)"),
    ("Gerente de Tienda", "Gerente de Tienda"),
    ("Cajero", "Cajero"),
    ("Barista", "Barista"),
    ("Cliente", "Cliente"),
]

ESTADOS_USUARIO = [
    ("Activo", "Activo"),
    ("Inactivo", "Inactivo"),
]


class LoginForm(FlaskForm):
    correo = StringField(
        "Correo o Usuario",
        validators=[
            DataRequired(message="El correo o usuario es obligatorio"),
            Length(max=120, message="El identificador no puede exceder 120 caracteres"),
        ],
    )
    contrasena = PasswordField(
        "Contraseña",
        validators=[
            DataRequired(message="La contraseña es obligatoria"),
            Length(min=6, max=128, message="La contraseña debe tener entre 6 y 128 caracteres"),
        ],
    )

class RecuperarContrasenaForm(FlaskForm):
    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingrese un correo válido"),
            Length(max=120, message="El correo no puede exceder 120 caracteres"),
        ],
    )


class ResetearContrasenaForm(FlaskForm):
    contrasena = PasswordField(
        "Nueva Contraseña",
        validators=[
            DataRequired(message="La nueva contraseña es obligatoria"),
            Length(min=8, max=128, message="La contraseña debe tener entre 8 y 128 caracteres"),
        ],
    )
    confirmarContrasena = PasswordField(
        "Confirmar Contraseña",
        validators=[
            DataRequired(message="Debes confirmar la contraseña"),
            EqualTo("contrasena", message="Las contraseñas no coinciden"),
        ],
    )

class ProveedorForm(FlaskForm):
    nombre = StringField('Nombre / Razón Social', validators=[
        DataRequired(message='El nombre es obligatorio'),
        Length(min=3, max=150, message='El nombre debe tener entre 3 y 150 caracteres')
    ])
    rfc = StringField('RFC', validators=[
        DataRequired(message='El RFC es obligatorio'),
        Length(min=12, max=13, message='El RFC debe tener 12 o 13 caracteres')
    ])
    telefono = StringField('Teléfono', validators=[
        Optional(),
        Length(max=20, message='El teléfono no puede exceder 20 caracteres')
    ])
    email = StringField('Correo Electrónico', validators=[
        Optional(),
        Email(message='Ingrese un correo válido'),
        Length(max=100, message='El email no puede exceder 100 caracteres')
    ])
    
    colonia = StringField('Colonia', validators=[
        Optional(),
        Length(max=100, message='El email no puede exceder 100 caracteres')
    ])
    
    calle = StringField('Calle', validators=[
        Optional(),
        Length(max=100, message='El email no puede exceder 100 caracteres')
    ])
    
    num_exterior = StringField('Numero Exterior', validators=[
        Optional(),
        Length(max=5, message='El email no puede exceder 6 caracteres')
    ])
    
    
class DesactivarForm(FlaskForm):
    id = HiddenField()
    submit = SubmitField('Sí, Desactivar')
    
class MermaForm(FlaskForm):
    
    cantidad = DecimalField('Cantidad',
        validators=[
            DataRequired(message="La cantidad es obligatoria"),
            NumberRange(min=0, message="La cantidad debe ser mayor a 0")
        ], places=2)
    
    fecha = DateField('Fecha', default= date.today,
        validators=[
            DataRequired(message="La fecha es obligatoria")], format='%Y-%m-%d')
    
    motivo = SelectField('Motivo',
        choices=[
            ("Error en preparación", "Error en preparación"),
            ("Derrame o caída", "Derrame o caída"),
            ("Insumo en mal estado", "Insumo en mal estado"),
            ("Producto caducado", "Producto caducado"),
            ("Sobrante de producción diaria", "Sobrante de producción diaria"),
            ("Falla de refrigeración/almacenaje", "Falla de refrigeración/almacenaje"),
            ("Muestra o degustación", "Muestra o degustación"),
            ("Pérdida no identificada", "Pérdida no identificada"),
            ("Devolución por cliente", "Devolución por cliente")
        ], validators=[DataRequired(message="Selecciona un motivo")])
    
    materia_id = SelectField('Materia Prima', coerce=int,
        validators=[DataRequired(message="Selecciona una materia prima")]
    )
    
class CompraForm(FlaskForm):

    id_proveedor = SelectField('Proveedor', coerce=int,
        validators=[DataRequired(message='Debe seleccionar un proveedor')]
    )

    fecha = DateField('Fecha de Compra',
        format='%Y-%m-%d', validators=[DataRequired(message='La fecha es obligatoria')]
    )

    def set_proveedores(self, proveedores):
        self.id_proveedor.choices = [(p.id, p.nombre) for p in proveedores]


class FiltroComprasForm(FlaskForm):

    fecha_inicio = DateField('Fecha Inicio',
        format='%Y-%m-%d', validators=[Optional()]
    )

    fecha_fin = DateField('Fecha Fin', format='%Y-%m-%d',
        validators=[Optional()]
    )

    id_proveedor = SelectField('Proveedor',
        coerce=int, validators=[Optional()]
    )

    def set_proveedores(self, proveedores):     
        self.id_proveedor.choices = [(0, 'Todos')] + [
            (p.id, p.nombre) for p in proveedores
        ]

    def validate(self, extra_validators=None):
        if not super().validate(extra_validators):
            return False

        if self.fecha_inicio.data and self.fecha_fin.data:
            if self.fecha_inicio.data > self.fecha_fin.data:
                self.fecha_fin.errors.append(
                    "La fecha fin debe ser mayor o igual a la fecha inicio"
                )
                return False

        return True
    
class PedidoForm(FlaskForm):
    
    nombre = StringField('Nombre', 
            validators=[DataRequired(), Length(max=120)])
    
    telefono = StringField('Teléfono', 
            validators=[Length(max=15)])

    hora_recogida = DateTimeLocalField('Hora de recogida', format='%Y-%m-%dT%H:%M',
            validators=[DataRequired()])

    notas = TextAreaField('Notas', 
            validators=[Length(max=200)])

    submit = SubmitField('Crear Pedido')

    def validate_hora_recogida(self, field):
        ahora = datetime.now()
        diferencia = (field.data - ahora).total_seconds() / 60

        if field.data.date() != ahora.date():
            raise ValidationError("El pedido debe ser para hoy.")

        if diferencia < 10:
            raise ValidationError("Debe pedir con al menos 10 minutos de anticipación.")

        if diferencia > 60:
            raise ValidationError("No puedes pedir con más de 1 hora de anticipación.")

class VentaForm(FlaskForm):
 
    producto = SelectField("Producto", 
                coerce=int, validators=[Optional()])

    cantidad = IntegerField("Cantidad", 
                default=1, validators=[DataRequired()])

    tipo_venta = RadioField("Tipo", choices=[
        ("fisica", "Física"),
        ("en_linea", "En línea")
    ], validators=[Optional()])


    metodo_pago = SelectField("Método de pago", choices=[
        ("efectivo", "Efectivo"),
        ("tarjeta", "Tarjeta"),
        ("transferencia", "Transferencia")
    ], validators=[Optional()])

  
    hora_recogida = DateTimeLocalField(
        "Hora recogida",
        format='%Y-%m-%dT%H:%M',
        validators=[Optional()]
    )

    notas = StringField("Notas", validators=[Optional()])

    agregar = SubmitField("Agregar producto")
    terminar = SubmitField("Finalizar venta")


class PagoForm(FlaskForm):
    
    metodo_pago = SelectField("Método de Pago", choices=[
        ('efectivo', 'Efectivo'),
        ('tarjeta', 'Tarjeta'),
        ('transferencia', 'Transferencia')
    ], validators=[DataRequired()])
    
    submit = SubmitField("Registrar Pago")
    
class ClienteForm(FlaskForm):
    
    nombre = StringField(
        "Nombre",
        validators=[DataRequired(), Length(max=120)]
    )

    apellidoPaterno = StringField(
        "Apellido Paterno",
        validators=[DataRequired(), Length(max=50)]
    )

    apellidoMaterno = StringField(
        "Apellido Materno",
        validators=[Optional(), Length(max=50)]
    )

    telefono = StringField(
        "Teléfono",
        validators=[Optional(), Length(max=15)]
    )

    alias = StringField(
        "Alias",
        validators=[Optional(), Length(max=50)]
    )

    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(),
            Email(),
            Length(max=120)
        ]
    )

    usuario = StringField(
        "Usuario",
        validators=[ Optional(), 
            Length(max=60)
        ]
    )

    contrasena = PasswordField(
        "Contraseña",
        validators=[
            DataRequired(),
            Length(min=6, max=128)
        ]
    )
    
    submit = SubmitField("Registrar")


class ClientePerfilForm(FlaskForm):
    nombre = StringField(
        "Nombre",
        validators=[DataRequired(message="El nombre es obligatorio"), Length(max=120)],
    )

    apellidoPaterno = StringField(
        "Apellido Paterno",
        validators=[DataRequired(message="El apellido paterno es obligatorio"), Length(max=50)],
    )

    apellidoMaterno = StringField(
        "Apellido Materno",
        validators=[Optional(), Length(max=50)],
    )

    telefono = StringField(
        "Teléfono",
        validators=[Optional(), Length(max=15)],
    )

    alias = StringField(
        "Alias",
        validators=[Optional(), Length(max=50)],
    )

    submit = SubmitField("Guardar cambios")
    
class CrearEmpleadoForm(FlaskForm):

    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingrese un correo válido"),
            Length(max=120),
        ],
    )

    username = StringField(
        "Usuario",
        validators=[
            DataRequired(message="El usuario es obligatorio"),
            Length(min=3, max=60),
        ],
    )

    nombre = StringField(
        "Nombre",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(max=60),
        ],
    )

    rol = SelectField(
        "Rol",
        choices=ROLES_USUARIO,
        validators=[DataRequired("Rol requerido")],
    )

    contrasenaTemporal = PasswordField(
        "Contraseña",
        validators=[
            DataRequired("Contraseña requerida"),
            Length(min=6, max=128),
        ],
    )

    submit = SubmitField("Registrar Empleado")
    
class EmpleadoActualizarForm(FlaskForm):

    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingrese un correo válido"),
            Length(max=120),
        ],
    )

    username = StringField(
        "Usuario",
        validators=[
            DataRequired(message="El usuario es obligatorio"),
            Length(min=3, max=60),
        ],
    )

    nombre = StringField(
        "Nombre",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(max=60),
        ],
    )

    rol = SelectField(
        "Rol",
        choices=ROLES_USUARIO,
        validators=[DataRequired()],
    )

    contrasenaTemporal = PasswordField(
        "Contraseña",
        validators=[
            Optional(),
            Length(min=6, max=128),
        ],
    )

    submit = SubmitField("Registrar Empleado")


class AgregarDetalleSolicitudForm(FlaskForm):
    id_producto = SelectField(
        "Producto",
        coerce=int,
        validators=[DataRequired(message="Selecciona un producto")],
    )

    cantidad = IntegerField(
        "Cantidad",
        default=1,
        validators=[
            DataRequired(message="La cantidad es obligatoria"),
            NumberRange(min=1, message="La cantidad debe ser mayor a 0"),
        ],
    )

    submit = SubmitField("Agregar a la solicitud")

    def set_productos(self, productos):
        self.id_producto.choices = [
            (p.id_producto, f"{p.nombre} {'(Inactivo)' if not p.estatus else ''}".strip())
            for p in productos
        ]


class RegistroProduccionForm(FlaskForm):
    id_producto = SelectField(
        "Producto",
        coerce=int,
        validators=[DataRequired(message="Selecciona un producto")],
    )

    cantidad = IntegerField(
        "Cantidad",
        default=1,
        validators=[
            DataRequired(message="La cantidad es obligatoria"),
            NumberRange(min=1, message="La cantidad debe ser mayor a 0"),
        ],
    )

    submit = SubmitField("Registrar Producción")

    def set_productos(self, productos):
        self.id_producto.choices = [
            (p.id_producto, p.nombre)
            for p in productos
            if p.estatus
        ]


class ProductoTerminadoForm(FlaskForm):
    nombre = StringField(
        "Nombre del Producto",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(max=50, message="El nombre no puede exceder 50 caracteres"),
        ],
    )

    categoria = SelectField(
        "Categoría",
        choices=[
            ("bebidas", "Bebidas"),
            ("alimentos", "Alimentos"),
        ],
        validators=[DataRequired(message="Selecciona una categoría")],
    )

    precio_venta = DecimalField(
        "Precio de Venta",
        validators=[
            DataRequired(message="El precio es obligatorio"),
            NumberRange(min=0.01, message="El precio debe ser mayor a 0"),
        ],
        places=2,
    )

    tipo_preparacion = SelectField(
        "Tipo de preparación",
        choices=[
            ("materia_prima", "Preparación al momento (descuenta materia prima en venta)"),
            ("stock", "Producto con stock (descuenta stock en venta)"),
        ],
        validators=[DataRequired(message="Selecciona el tipo de preparación")],
    )

    descripcion = TextAreaField(
        "Descripción",
        validators=[Optional(), Length(max=500)],
    )

    imageBase64 = HiddenField(
        "Imagen base64",
        validators=[Optional(), Length(max=2000000)],
    )

    submit = SubmitField("Guardar Producto")


class ProductoTerminadoEditarForm(ProductoTerminadoForm):
    estatus = SelectField(
        "Estatus",
        choices=[
            ("1", "Activo (Visible en el menú)"),
            ("0", "Inactivo (Fuera de temporada/No disponible)"),
        ],
        validators=[DataRequired(message="Selecciona un estatus")],
    )

    submit = SubmitField("Actualizar Producto")


class RecetaForm(FlaskForm):
    id_producto = SelectField(
        "Producto",
        coerce=int,
        validators=[DataRequired(message="Selecciona un producto")],
    )

    id_materia = SelectField(
        "Insumo",
        coerce=int,
        validators=[DataRequired(message="Selecciona un insumo")],
    )

    cantidad = DecimalField(
        "Cantidad",
        places=2,
        validators=[
            DataRequired(message="La cantidad es obligatoria"),
            NumberRange(min=0.01, message="La cantidad debe ser mayor a 0"),
        ],
    )

    estado = SelectField(
        "Estado",
        choices=[("1", "Activa"), ("0", "Inactiva")],
        validators=[DataRequired(message="Selecciona el estado")],
    )

    submit = SubmitField("Guardar Receta")

    def set_productos(self, productos):
        self.id_producto.choices = [(p.id_producto, p.nombre) for p in productos]

    def set_materias(self, materias):
        opciones = []
        for materia in materias:
            unidad = ""
            if getattr(materia, "unidad", None):
                unidad = materia.unidad.abreviacion or materia.unidad.nombre or ""

            etiqueta = f"{materia.nombre} ({unidad})" if unidad else materia.nombre
            opciones.append((materia.id_materia, etiqueta))

        self.id_materia.choices = opciones


class RecetaLoteForm(FlaskForm):
    id_producto = SelectField(
        "Producto",
        coerce=int,
        validators=[DataRequired(message="Selecciona un producto")],
    )

    estado = SelectField(
        "Estado",
        choices=[("1", "Activa"), ("0", "Inactiva")],
        validators=[DataRequired(message="Selecciona el estado")],
    )

    insumos_json = HiddenField(
        "Insumos",
        validators=[DataRequired(message="Agrega al menos un insumo a la receta")],
        render_kw={"id": "insumos_json"},
    )

    submit = SubmitField("Guardar Receta")

    def set_productos(self, productos):
        self.id_producto.choices = [
            (p.id_producto, f"{p.nombre} {'(Inactivo)' if not p.estatus else ''}".strip())
            for p in productos
        ]


class MateriaPrimaForm(FlaskForm):
    
    nombre_insumo = StringField(
        "Nombre de la materia prima",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(max=50, message="El nombre no puede exceder 50 caracteres"),
        ],
    )

    descripcion = TextAreaField(
        "Descripción",
        validators=[Optional(), Length(max=500, message="La descripción no puede exceder 500 caracteres")],
    )

    unidad_medida = SelectField(
        "Unidad de Medida",
        coerce=int,
        validators=[DataRequired(message="Selecciona una unidad de medida")],
    )

    stock_minimo = DecimalField(
        "Alerta de Stock Mínimo",
        places=2,
        validators=[
            DataRequired(message="El stock mínimo es obligatorio"),
            NumberRange(min=0, message="El stock mínimo no puede ser negativo"),
        ],
    )

    submit = SubmitField("Guardar Insumo")

    def set_unidades(self, unidades):
        self.unidad_medida.choices = [
            (u.id_unidad, f"{u.nombre} ({u.abreviacion})" if u.abreviacion else u.nombre)
            for u in unidades
        ]
        
class FechasReporteForm(FlaskForm):
    fecha_inicio = DateField('Fecha Inicio', format='%Y-%m-%d', validators=[
        DataRequired(message='La fecha de inicio es obligatoria')
    ])
    fecha_fin = DateField('Fecha Fin', format='%Y-%m-%d', validators=[
        DataRequired(message='La fecha de fin es obligatoria')
    ])