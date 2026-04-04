from datetime import date
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, PasswordField, DecimalField, DateField, SelectField, HiddenField, SubmitField
from wtforms.validators import DataRequired, NumberRange, EqualTo, Length, Email, Optional

ROLES_USUARIO = [
    ("Gerente", "Gerente"),
    ("Operador", "Operador"),
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

class RegistroUsuarioForm(FlaskForm):
    nombre = StringField(
        "Nombre",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(min=3, max=120, message="El nombre debe tener entre 3 y 120 caracteres"),
        ],
    )
    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingrese un correo válido"),
            Length(max=120, message="El correo no puede exceder 120 caracteres"),
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


class UsuarioCrearForm(FlaskForm):
    nombre = StringField(
        "Nombre",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(min=3, max=120, message="El nombre debe tener entre 3 y 120 caracteres"),
        ],
    )
    usuario = StringField(
        "Usuario",
        validators=[
            DataRequired(message="El usuario es obligatorio"),
            Length(min=3, max=60, message="El usuario debe tener entre 3 y 60 caracteres"),
        ],
    )
    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingrese un correo válido"),
            Length(max=120, message="El correo no puede exceder 120 caracteres"),
        ],
    )
    rol = SelectField(
        "Rol",
        choices=ROLES_USUARIO,
        validators=[DataRequired(message="El rol es obligatorio")],
    )
    contrasenaTemporal = PasswordField(
        "Contraseña Temporal",
        validators=[
            DataRequired(message="La contraseña temporal es obligatoria"),
            Length(min=6, max=128, message="La contraseña debe tener entre 6 y 128 caracteres"),
        ],
    )
    estado = SelectField(
        "Estado",
        choices=ESTADOS_USUARIO,
        validators=[DataRequired(message="El estado es obligatorio")],
    )


class UsuarioActualizarForm(FlaskForm):
    nombre = StringField(
        "Nombre",
        validators=[
            DataRequired(message="El nombre es obligatorio"),
            Length(min=3, max=120, message="El nombre debe tener entre 3 y 120 caracteres"),
        ],
    )
    usuario = StringField(
        "Usuario",
        validators=[
            DataRequired(message="El usuario es obligatorio"),
            Length(min=3, max=60, message="El usuario debe tener entre 3 y 60 caracteres"),
        ],
    )
    correo = StringField(
        "Correo Electrónico",
        validators=[
            DataRequired(message="El correo es obligatorio"),
            Email(message="Ingrese un correo válido"),
            Length(max=120, message="El correo no puede exceder 120 caracteres"),
        ],
    )
    rol = SelectField(
        "Rol",
        choices=ROLES_USUARIO,
        validators=[DataRequired(message="El rol es obligatorio")],
    )
    contrasenaTemporal = PasswordField(
        "Contraseña Temporal",
        validators=[
            Optional(),
            Length(min=6, max=128, message="La contraseña debe tener entre 6 y 128 caracteres"),
        ],
    )
    estado = SelectField(
        "Estado",
        choices=ESTADOS_USUARIO,
        validators=[DataRequired(message="El estado es obligatorio")],
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