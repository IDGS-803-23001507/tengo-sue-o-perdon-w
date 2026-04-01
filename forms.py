from flask_wtf import FlaskForm
from wtforms import StringField, TextAreaField
from wtforms.validators import DataRequired, Length, Email, Optional

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
    direccion = TextAreaField('Dirección', validators=[
        Optional(),
        Length(max=255, message='La dirección no puede exceder 255 caracteres')
    ])