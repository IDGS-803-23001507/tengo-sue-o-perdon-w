from datetime import date, datetime
from decimal import Decimal
from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed
from wtforms import StringField, FieldList, FormField, BooleanField, SelectMultipleField,  DateTimeLocalField, IntegerField, RadioField, TextAreaField, PasswordField, DecimalField, DateField, SelectField, HiddenField, SubmitField
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
    
class ProductooForm(FlaskForm):

    nombre = StringField(
        "Nombre",
        validators=[
            DataRequired(),
            Length(min=2, max=50)
        ]
    )

    descripcion = TextAreaField(
        "Descripción",
        validators=[
            DataRequired(),
            Length(min=5, max=200)
        ]
    )

    foto = FileField(
        "Foto",
        validators=[
            FileAllowed(
                ['jpg', 'jpeg', 'png', 'webp'],
                'Solo imágenes válidas'
            )
        ]
    )

    precio = DecimalField(
        "Precio",
        places=2,
        validators=[
            DataRequired(),
            NumberRange(min=1)
        ]
    )

    submit = SubmitField("Guardar")


class AlimentoForm(ProductooForm):

    submit = SubmitField("Guardar Alimento")


class BebidaForm(ProductooForm):

    submit = SubmitField("Guardar Bebida")


class ComboForm(ProductooForm):

    submit = SubmitField("Guardar Combo")


class DetalleComboForm(FlaskForm):

    idProducto = SelectField(
        "Producto",
        coerce=int,
        validators=[DataRequired()]
    )

    cantidad = IntegerField(
        "Cantidad",
        default=1,
        validators=[
            DataRequired(),
            NumberRange(min=1)
        ]
    )
    
    
class SucursalForm(FlaskForm):
    nombre = StringField("Nombre", validators=[DataRequired(), Length(max=50)])
    foto = FileField("Foto", validators=[ Optional(), FileAllowed(['jpg', 'jpeg', 'png', 'webp'], 'Solo imágenes')])
    ciudad = StringField("Ciudad", validators=[DataRequired(), Length(max=50)])
    calle = StringField("Calle",validators=[DataRequired(), Length(max=50)])
    colonia = StringField("Colonia",validators=[DataRequired(), Length(max=50)])
    numInt = StringField("Numero Interior", validators=[DataRequired(), Length(max=6)])
    cp = StringField("Codigo Postal", validators=[ DataRequired(), Length(max=10)])
    
class DesactivarForm(FlaskForm):
    id = HiddenField()
    submit = SubmitField('Sí, Desactivar')
        
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
            Optional(),
            NumberRange(min=0, message="El precio no puede ser negativo"),
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

    target_food_cost = DecimalField(
        "Food Cost Objetivo",
        places=2,
        default=Decimal('0.30'),
        validators=[
            Optional(),
            NumberRange(min=0.01, max=0.99, message="El Food Cost debe estar entre 0.01 y 0.99"),
        ],
    )

    submit = SubmitField("Guardar Producto")


class ProductoTerminadoEditarForm(ProductoTerminadoForm):
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

    submit = SubmitField("Guardar Receta")

    def set_productos(self, productos):
        self.id_producto.choices = [(p.id_producto, p.nombre) for p in productos]

    def set_materias(self, materias):
        opciones = []
        for materia in materias:
            unidad = ""
            if getattr(materia, "unidad", None):
                unidad = materia.unidad.abreviacion or materia.unidad.nombre or ""

            tamanio = getattr(materia, "tamanio", None) or ""
            etiqueta = materia.nombre
            if tamanio:
                etiqueta += f" — {tamanio}"
            if unidad:
                etiqueta += f" ({unidad})"
            opciones.append((materia.id_materia, etiqueta))

        self.id_materia.choices = opciones


class RecetaLoteForm(FlaskForm):
    id_producto = SelectField(
        "Producto",
        coerce=int,
        validators=[DataRequired(message="Selecciona un producto")],
    )

    insumos_json = HiddenField(
        "Insumos",
        validators=[DataRequired(message="Agrega al menos un insumo a la receta")],
        render_kw={"id": "insumos_json"},
    )

    nombre_variante = StringField(
        "Variante / Tamaño",
        validators=[Optional(), Length(max=50, message="Máximo 50 caracteres")],
        render_kw={"placeholder": "Ej. Chico, Mediano, Grande, 12oz... (opcional)"},
    )

    precio_variante = DecimalField(
        "Precio de esta variante",
        places=2,
        validators=[Optional(), NumberRange(min=0)],
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
            Length(max=30, message="El nombre no puede exceder 30 caracteres"),
        ],
    )

    tamanio = StringField(
        "Presentación / Tamaño",
        validators=[
            Optional(),
            Length(max=20, message="El tamaño no puede exceder 20 caracteres"),
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
    
class DetallePedidoProveedorForm(FlaskForm):
    id_materia = SelectField("Materia Prima", coerce=int, validators=[DataRequired()])
    cantidad_solicitada = DecimalField("Cantidad", validators=[DataRequired(), NumberRange(min=0.01)])
    costo_unitario_est = DecimalField("Costo Estimado", validators=[Optional()])

class PedidoProveedorForm(FlaskForm):
    id_proveedor = SelectField("Proveedor", coerce=int, validators=[DataRequired()])
    notas = TextAreaField("Notas")
    detalles = FieldList(FormField(DetallePedidoProveedorForm), min_entries=1)