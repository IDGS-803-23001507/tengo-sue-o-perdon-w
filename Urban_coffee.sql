Drop Database if Exists Urban_Coffee;

Create Database Urban_Coffee;
use Urban_Coffee;

insert into unidad_medida(nombre, abreviacion, tipo, factor) values("Gramos","g", "solido", 1);
insert into unidad_medida(nombre, abreviacion, tipo, factor) values("KiloGramos","kl", "solido", 1000);
insert into unidad_medida(nombre, abreviacion, tipo, factor) values("Onza","Oz", "solido", 28.35);

select * from usuarios;

-- esta era la base de datos que tenia, es lo mismo solo modifique algunas cosas
-- perooo igual todos modificaron su parte, recuerda que la base de datos chida es la que
-- se esta haciendo en el models, esta solo es una base :D

Create table Rol(
id_rol int auto_increment not null,
nombre varchar(20) unique,
constraint pk_rol primary key (id_rol)
);

Create table Usuario(
id_usuario int auto_increment not null,
id_rol int not null,
nombre varchar(50) not null,
ap_paterno varchar(50),
ap_materno varchar(50), 
telefono varchar(15) not null,
correo varchar(50) not null unique,
contrasena varchar(255) not null,
estatus boolean default true,
constraint pk_id_usuario primary key (id_usuario),
constraint fk_usuario_rol foreign key (id_rol) references Rol(id_rol)
);

Create table Sesion(
token varchar(254) not null,
id_usuario int not null,
fecha_inicio datetime,
fecha_expiracion datetime,
ultimo_acceso datetime,
constraint pk_sesion primary key (token),
constraint fk_sesion_usuario foreign key (id_usuario) references Usuario(id_usuario)
);
 
Create table Proveedor(
id_proveedor int not null auto_increment, 
RFC varchar(13) not null unique,
nombre varchar(100) not null,
correo varchar(50), 
telefono varchar(15),
direccion text,
estatus boolean default true,
constraint pk_proveedor primary key (id_proveedor)
);

Create table Unidad_medida(
id_unidad int auto_increment not null,
nombre varchar(10) not null,
abreviacion varchar(4) unique,
constraint pk_unidad primary key(id_unidad)
);

Create table Materia_prima(
id_materia int not null auto_increment,
nombre varchar(50) not null,
descripcion text, 
unidad_medida int not null, -- duda sobre la tabla 
stock_minimo decimal(10, 2) default 0,
stock_actual decimal(10, 2) default 0,
constraint pk_materia primary key (id_materia),
constraint fk_materia_unidad foreign key (unidad_medida) 
references Unidad_medida(id_unidad)
);

Create table Compra(
id_compra int not null auto_increment,
id_proveedor int not null,
fecha datetime not null,
constraint pk_compra primary key (id_compra),
constraint fk_compra_proveedor foreign key (id_proveedor) references Proveedor(id_proveedor)
);

Create table detalle_compra(
id_detalle_compra int not null auto_increment,
id_compra int not null,
id_materia int not null,
cantidad numeric(10, 2) not null,
unidad int not null,
costo_unitario numeric(10, 2) not null,
constraint pk_detalle_compra primary key (id_detalle_compra),
constraint fk_detalle_compra_unidad foreign key (unidad) references Unidad_medida(id_unidad),
constraint fk_detalle_compra_compra foreign key (id_compra) references Compra(id_compra),
constraint fk_detalle_compra_materia foreign key (id_materia) references Materia_prima(id_materia)
);

Create table Producto (
id_producto int not null auto_increment,
nombre varchar(50) not null,
categoria enum('Bebidas','Alimentos'),
precio_venta numeric(10, 2),
estatus boolean default true,
constraint pk_producto primary key (id_producto)
);

Create table Recetas(
id_receta int not null auto_increment,
id_producto int not null,
id_materia int not null,
cantidad numeric(10, 2) not null,
constraint pk_receta primary key (id_receta),
constraint fk_recetas_producto foreign key (id_producto) references Producto(id_producto),
constraint fk_recetas_materia foreign key (id_materia) references Materia_prima(id_materia),
unique(id_producto, id_materia)
);

create table Solicitud_produccion(
id_solicitud int not null auto_increment,
id_usuario int not null,
fecha datetime not null,
estado enum('pendiente','en_proceso','finalizado','cancelado'),
constraint pk_solicitud primary key (id_solicitud),
constraint fk_solicitud_usuario foreign key (id_usuario) references Usuario(id_usuario)
);

CREATE TABLE Detalle_produccion(
id_detalle INT AUTO_INCREMENT NOT NULL,
id_solicitud INT NOT NULL,
id_producto INT NOT NULL,
cantidad INT NOT NULL,
constraint pk_detalle_produccion primary key(id_detalle),

constraint fk_detalle_produccion_solicitud 
foreign key (id_solicitud) references Solicitud_produccion(id_solicitud),

constraint fk_detalle_produccion_producto
foreign key (id_producto) references Producto(id_producto)
);

create table Ventas(
id_venta int not null auto_increment,
fecha datetime not null,
id_usuario int not null,
metodo_pago varchar(30) not null,
total decimal(10,2) not null,
constraint pk_ventas primary key (id_venta),
constraint fk_ventas_usuario foreign key(id_usuario) references Usuario(id_usuario)
);

create table Detalle_venta(
id_detalle_venta int auto_increment not null,
id_venta int not null,
id_producto int not null,
cantidad int not null,
subtotal numeric(10,2) not null,
constraint pk_detalle_venta primary key (id_detalle_venta),
constraint fk_detalle_venta_venta foreign key(id_venta) references Ventas(id_venta),
constraint fk_detalle_venta_producto foreign key(id_producto) references Producto(id_producto),
UNIQUE(id_venta, id_producto)
);

create table Merma(
id_merma int not null auto_increment,
id_materia int not null,
cantidad numeric(10,2) not null,
fecha datetime not null,
motivo varchar(200),
id_usuario int,
constraint pk_merma primary key (id_merma),
constraint fk_merma_materia foreign key(id_materia) references Materia_prima(id_materia),
constraint fk_merma_usuario foreign key(id_usuario) references Usuario(id_usuario)
);

-- preguntar sobre creacion de tabla de utilidades

create user 'admin'@'localhost' identified by 'admin123';
create user 'operador'@'localhost' identified by 'operador123';
create user 'consulta'@'localhost' identified by 'consulta123';

grant rol_administrador to 'admin'@'localhost';
grant rol_operador to 'operador'@'localhost';
grant rol_consulta to 'consulta'@'localhost';

CREATE ROLE rol_backup;

grant select, lock tables, show view, event, trigger
on Urban_Coffee.*
to rol_backup;

create user 'respaldos'@'localhost'
identified by 'respaldos123';

grant rol_backup to 'backup_uc'@'localhost';

SELECT mp.nombre, mp.stock_actual, r.cantidad FROM Recetas r JOIN Materia_prima mp 
ON r.id_materia = mp.id_materia WHERE r.id_producto = 1;

CREATE INDEX idx_detalle_venta_producto
ON Detalle_venta(id_producto);

CREATE INDEX idx_detalle_venta_venta
ON Detalle_venta(id_venta);

SELECT id_producto, nombre, stock FROM Producto
WHERE estatus = true AND stock > 0;


CREATE INDEX idx_recetas_producto
 ON Recetas(id_producto);


CREATE INDEX idx_producto_estatus_stock
 ON Producto(estatus, stock);

CREATE INDEX idx_compra_proveedor_fecha
ON Compra(id_proveedor, fecha);



CREATE INDEX idx_detalle_produccion_producto
 ON Detalle_produccion(id_producto);

 CREATE INDEX idx_recetas_materia
 ON Recetas(id_materia);

SELECT id_compra, fecha, precio_total FROM Compra
WHERE id_proveedor = 3 ORDER BY fecha DESC;

SELECT p.nombre, SUM(dv.cantidad) AS total_vendido
FROM Detalle_venta dv JOIN Producto p ON dv.id_producto = p.id_producto
GROUP BY p.id_producto ORDER BY total_vendido DESC;

SELECT mp.nombre, SUM(r.cantidad * dp.cantidad) AS consumo_total
FROM Detalle_produccion dp JOIN Recetas r ON dp.id_producto = r.id_producto
JOIN Materia_prima mp ON r.id_materia = mp.id_materia GROUP BY mp.id_materia;