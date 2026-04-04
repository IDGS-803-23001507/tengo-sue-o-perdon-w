from datetime import date
from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField, DecimalField, DateField, SelectField, HiddenField, SubmitField
from wtforms.validators import DataRequired, NumberRange, Length, Email, Optional

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
    