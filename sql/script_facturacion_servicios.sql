-- ============================================================
-- BASE DE DATOS: Facturacion por servicios
-- Repuestos y Rectificaciones Pacifico E.I.R.L.
-- Compatible con MySQL 8.0+ (InnoDB).
--
-- Script IDEMPOTENTE: se puede ejecutar varias veces sin perder datos.
--   * CREATE ... IF NOT EXISTS  (no hay DROP TABLE)
--   * INSERT IGNORE en los catalogos maestros
--   * procedimiento y triggers se recrean (no almacenan datos)
-- La aplicacion lo ejecuta sola en el primer arranque (pantalla de
-- configuracion). Tambien se puede ejecutar completo desde Workbench.
-- ============================================================

CREATE DATABASE IF NOT EXISTS facturacion_servicios
  CHARACTER SET utf8mb4 COLLATE utf8mb4_spanish_ci;
USE facturacion_servicios;

-- 1. Ubicacion geografica
CREATE TABLE IF NOT EXISTS departamento (
    id_departamento TINYINT UNSIGNED NOT NULL,
    nombre VARCHAR(50) NULL,
    PRIMARY KEY (id_departamento),
    CONSTRAINT chk_departamento_id CHECK (id_departamento <= 999)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS provincia (
    id_provincia SMALLINT UNSIGNED NOT NULL,
    nombre VARCHAR(50) NOT NULL,
    id_departamento TINYINT UNSIGNED NOT NULL,
    PRIMARY KEY (id_provincia),
    CONSTRAINT chk_provincia_id CHECK (id_provincia <= 999),
    CONSTRAINT fk_provincia_departamento FOREIGN KEY (id_departamento)
      REFERENCES departamento(id_departamento)
      ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS distrito (
    id_distrito SMALLINT UNSIGNED NOT NULL,
    nombre VARCHAR(30) NOT NULL,
    id_provincia SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (id_distrito),
    CONSTRAINT chk_distrito_id CHECK (id_distrito <= 999),
    CONSTRAINT fk_distrito_provincia FOREIGN KEY (id_provincia)
      REFERENCES provincia(id_provincia)
      ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 2. Empresa emisora y clientes. RUC y telefonos se guardan como texto
-- para conservar ceros iniciales y validar su longitud.
CREATE TABLE IF NOT EXISTS empresa (
    ruc_empresa CHAR(11) NOT NULL,
    razon_social_empresa VARCHAR(50) NOT NULL,
    direccion_empresa VARCHAR(50) NOT NULL,
    telefono_empresa CHAR(9) NOT NULL,
    cuenta_corriente BIGINT UNSIGNED NOT NULL,
    id_distrito SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (ruc_empresa),
    CONSTRAINT chk_empresa_ruc CHECK (ruc_empresa REGEXP '^[0-9]{11}$'),
    CONSTRAINT chk_empresa_telefono CHECK (telefono_empresa REGEXP '^[0-9]{9}$'),
    CONSTRAINT chk_empresa_cuenta CHECK (cuenta_corriente <= 99999999999),
    CONSTRAINT fk_empresa_distrito FOREIGN KEY (id_distrito)
      REFERENCES distrito(id_distrito)
      ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS cliente (
    ruc_cliente CHAR(11) NOT NULL,
    nombre_cliente VARCHAR(50) NOT NULL,
    direccion_cliente VARCHAR(50) NOT NULL,
    id_distrito SMALLINT UNSIGNED NOT NULL,
    PRIMARY KEY (ruc_cliente),
    CONSTRAINT chk_cliente_ruc CHECK (ruc_cliente REGEXP '^[0-9]{11}$'),
    CONSTRAINT fk_cliente_distrito FOREIGN KEY (id_distrito)
      REFERENCES distrito(id_distrito)
      ON UPDATE CASCADE ON DELETE RESTRICT
) ENGINE=InnoDB;

-- 3. Catalogos
CREATE TABLE IF NOT EXISTS servicio (
    codigo_servicio TINYINT UNSIGNED NOT NULL,
    descripcion_servicio VARCHAR(100) NOT NULL,
    valor_unitario_servicio DECIMAL(8,2) NOT NULL,
    PRIMARY KEY (codigo_servicio),
    CONSTRAINT chk_servicio_codigo CHECK (codigo_servicio <= 999),
    CONSTRAINT chk_servicio_valor CHECK (valor_unitario_servicio > 0)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS detraccion (
    id_detraccion SMALLINT UNSIGNED NOT NULL,
    detraccion_porcentaje DECIMAL(3,2) NOT NULL,
    servicio_detraccion VARCHAR(50) NOT NULL,
    PRIMARY KEY (id_detraccion),
    CONSTRAINT chk_detraccion_id CHECK (id_detraccion <= 999),
    CONSTRAINT chk_detraccion_porcentaje CHECK
      (detraccion_porcentaje >= 0.00 AND detraccion_porcentaje <= 1.00)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS moneda (
    id_moneda TINYINT UNSIGNED NOT NULL,
    descripcion VARCHAR(20) NOT NULL,
    PRIMARY KEY (id_moneda),
    CONSTRAINT chk_moneda_id CHECK (id_moneda <= 999),
    UNIQUE KEY uq_moneda_descripcion (descripcion)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS forma_pago (
    id_forma_pago TINYINT UNSIGNED NOT NULL,
    descripcion VARCHAR(20) NOT NULL,
    PRIMARY KEY (id_forma_pago),
    CONSTRAINT chk_forma_pago_id CHECK (id_forma_pago <= 999),
    UNIQUE KEY uq_forma_pago_descripcion (descripcion)
) ENGINE=InnoDB;

-- 4. Cabecera de factura
-- Los importes de cabecera se actualizan automaticamente mediante triggers
-- al insertar, modificar o borrar detalles. No se usa columna generada porque
-- subtotal depende de SUM() de varias filas de detalle.
CREATE TABLE IF NOT EXISTS factura (
    numero_factura CHAR(13) NOT NULL,
    igv_porcentaje DECIMAL(3,2) NOT NULL DEFAULT 0.18,
    fecha_emision DATE NOT NULL,
    fecha_vencimiento DATE NULL,
    subtotal DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    igv_calculado DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    total DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    id_detraccion SMALLINT UNSIGNED NULL,
    monto_detraccion DECIMAL(8,2) NOT NULL DEFAULT 0.00,
    id_moneda TINYINT UNSIGNED NOT NULL,
    id_forma_pago TINYINT UNSIGNED NOT NULL,
    ruc_empresa CHAR(11) NOT NULL,
    ruc_cliente CHAR(11) NOT NULL,
    PRIMARY KEY (numero_factura),
    CONSTRAINT chk_factura_formato CHECK (numero_factura REGEXP '^[A-Z0-9]{4}-[0-9]{8}$'),
    CONSTRAINT chk_factura_igv CHECK (igv_porcentaje >= 0.00 AND igv_porcentaje <= 1.00),
    CONSTRAINT fk_factura_detraccion FOREIGN KEY (id_detraccion)
      REFERENCES detraccion(id_detraccion)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_moneda FOREIGN KEY (id_moneda)
      REFERENCES moneda(id_moneda)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_forma_pago FOREIGN KEY (id_forma_pago)
      REFERENCES forma_pago(id_forma_pago)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_empresa FOREIGN KEY (ruc_empresa)
      REFERENCES empresa(ruc_empresa)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_factura_cliente FOREIGN KEY (ruc_cliente)
      REFERENCES cliente(ruc_cliente)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    INDEX idx_factura_fecha (fecha_emision),
    INDEX idx_factura_cliente (ruc_cliente)
) ENGINE=InnoDB;

-- 5. Detalle de factura
-- Se incluye precio_unitario_aplicado para conservar el precio usado al facturar.
-- valor_venta es una columna generada: cantidad * precio unitario aplicado.
CREATE TABLE IF NOT EXISTS detalle_factura (
    codigo_servicio TINYINT UNSIGNED NOT NULL,
    numero_factura CHAR(13) NOT NULL,
    cantidad TINYINT UNSIGNED NOT NULL,
    precio_unitario_aplicado DECIMAL(8,2) NOT NULL,
    valor_venta DECIMAL(8,2)
      GENERATED ALWAYS AS (ROUND(cantidad * precio_unitario_aplicado, 2)) STORED,
    PRIMARY KEY (codigo_servicio, numero_factura),
    CONSTRAINT chk_detalle_cantidad CHECK (cantidad > 0),
    CONSTRAINT chk_detalle_precio CHECK (precio_unitario_aplicado > 0),
    CONSTRAINT fk_detalle_servicio FOREIGN KEY (codigo_servicio)
      REFERENCES servicio(codigo_servicio)
      ON UPDATE CASCADE ON DELETE RESTRICT,
    CONSTRAINT fk_detalle_factura FOREIGN KEY (numero_factura)
      REFERENCES factura(numero_factura)
      ON UPDATE CASCADE ON DELETE CASCADE,
    INDEX idx_detalle_factura (numero_factura)
) ENGINE=InnoDB;

-- 6. Procedimiento y triggers de recalculo (se recrean: no contienen datos)
DROP PROCEDURE IF EXISTS recalcular_factura;
DROP TRIGGER IF EXISTS trg_detalle_ai;
DROP TRIGGER IF EXISTS trg_detalle_au;
DROP TRIGGER IF EXISTS trg_detalle_ad;

DELIMITER $$

CREATE PROCEDURE recalcular_factura(IN p_numero_factura CHAR(13))
BEGIN
    UPDATE factura f
    SET f.subtotal = (
          SELECT COALESCE(SUM(df.valor_venta), 0.00)
          FROM detalle_factura df
          WHERE df.numero_factura = p_numero_factura
        )
    WHERE f.numero_factura = p_numero_factura;

    UPDATE factura f
    SET f.igv_calculado = ROUND(f.subtotal * f.igv_porcentaje, 2),
        f.total = ROUND(f.subtotal + ROUND(f.subtotal * f.igv_porcentaje, 2), 2),
        f.monto_detraccion = CASE
          WHEN f.id_detraccion IS NULL THEN 0.00
          ELSE ROUND(
            (f.subtotal + ROUND(f.subtotal * f.igv_porcentaje, 2)) *
            (SELECT d.detraccion_porcentaje
             FROM detraccion d WHERE d.id_detraccion = f.id_detraccion), 2)
        END
    WHERE f.numero_factura = p_numero_factura;
END$$

CREATE TRIGGER trg_detalle_ai AFTER INSERT ON detalle_factura
FOR EACH ROW
BEGIN
    CALL recalcular_factura(NEW.numero_factura);
END$$

CREATE TRIGGER trg_detalle_au AFTER UPDATE ON detalle_factura
FOR EACH ROW
BEGIN
    CALL recalcular_factura(NEW.numero_factura);
    IF OLD.numero_factura <> NEW.numero_factura THEN
        CALL recalcular_factura(OLD.numero_factura);
    END IF;
END$$

CREATE TRIGGER trg_detalle_ad AFTER DELETE ON detalle_factura
FOR EACH ROW
BEGIN
    CALL recalcular_factura(OLD.numero_factura);
END$$

DELIMITER ;

-- ============================================================
-- DATOS MAESTROS (catalogos). INSERT IGNORE: no duplica ni pisa
-- filas existentes. No se cargan empresa, clientes, servicios ni
-- facturas de prueba: la empresa se registra desde la aplicacion.
-- ============================================================

-- Monedas
INSERT IGNORE INTO moneda (id_moneda, descripcion) VALUES
(1, 'Soles (PEN)'),
(2, 'Dólares (USD)');

-- Formas de pago
INSERT IGNORE INTO forma_pago (id_forma_pago, descripcion) VALUES
(1, 'Contado'),
(2, 'Crédito');

-- Detracciones: Anexo 3 de la R.S. 183-2004/SUNAT (servicios sujetos al SPOT).
-- La detraccion aplica sobre el importe total (con IGV) y, por regla general,
-- en operaciones mayores a S/ 700. Verifique tasas vigentes en SUNAT.
INSERT IGNORE INTO detraccion (id_detraccion, detraccion_porcentaje, servicio_detraccion) VALUES
(1,  0.12, 'Mantenimiento y reparacion de bienes muebles'),
(2,  0.12, 'Otros servicios empresariales'),
(3,  0.00, 'No aplica detraccion'),
(4,  0.12, 'Intermediacion laboral y tercerizacion'),
(5,  0.10, 'Arrendamiento de bienes'),
(6,  0.10, 'Movimiento de carga'),
(7,  0.10, 'Comision mercantil'),
(8,  0.10, 'Fabricacion de bienes por encargo'),
(9,  0.10, 'Servicio de transporte de personas'),
(10, 0.04, 'Contratos de construccion'),
(11, 0.04, 'Transporte de bienes por via terrestre'),
(12, 0.12, 'Demas servicios gravados con el IGV');

-- Ubigeo: departamento de Arequipa, sus 8 provincias y los 109 distritos.
-- Los id_distrito son identificadores internos (el esquema los limita a <= 999),
-- NO son el codigo ubigeo del INEI.
INSERT IGNORE INTO departamento (id_departamento, nombre) VALUES
(4, 'Arequipa');

INSERT IGNORE INTO provincia (id_provincia, nombre, id_departamento) VALUES
(401, 'Arequipa', 4),
(402, 'Camaná', 4),
(403, 'Caravelí', 4),
(404, 'Castilla', 4),
(405, 'Caylloma', 4),
(406, 'Condesuyos', 4),
(407, 'Islay', 4),
(408, 'La Unión', 4);

INSERT IGNORE INTO distrito (id_distrito, nombre, id_provincia) VALUES
(401, 'Paucarpata', 401),
(402, 'Cerro Colorado', 401),
(403, 'Yura', 401),
(404, 'Cercado', 401),
(405, 'Alto Selva Alegre', 401),
(406, 'Cayma', 401),
(407, 'Characato', 401),
(408, 'Chiguata', 401),
(409, 'Jacobo Hunter', 401),
(410, 'José Luis Bustamante y Rivero', 401),
(411, 'La Joya', 401),
(412, 'Mariano Melgar', 401),
(413, 'Miraflores', 401),
(414, 'Mollebaya', 401),
(415, 'Pocsi', 401),
(416, 'Polobaya', 401),
(417, 'Quequeña', 401),
(418, 'Sabandía', 401),
(419, 'Sachaca', 401),
(420, 'San Juan de Siguas', 401),
(421, 'San Juan de Tarucani', 401),
(422, 'Santa Isabel de Siguas', 401),
(423, 'Santa Rita de Siguas', 401),
(424, 'Socabaya', 401),
(425, 'Tiabaya', 401),
(426, 'Uchumayo', 401),
(427, 'Vítor', 401),
(428, 'Yanahuara', 401),
(429, 'Yarabamba', 401),
(601, 'Camaná', 402),
(602, 'José María Quimper', 402),
(603, 'Mariano Nicolás Valcárcel', 402),
(604, 'Mariscal Cáceres', 402),
(605, 'Nicolás de Piérola', 402),
(606, 'Ocoña', 402),
(607, 'Quilca', 402),
(608, 'Samuel Pastor', 402),
(611, 'Caravelí', 403),
(612, 'Acarí', 403),
(613, 'Atico', 403),
(614, 'Atiquipa', 403),
(615, 'Bella Unión', 403),
(616, 'Cahuacho', 403),
(617, 'Chala', 403),
(618, 'Chaparra', 403),
(619, 'Huanuhuanu', 403),
(620, 'Jaquí', 403),
(621, 'Lomas', 403),
(622, 'Quicacha', 403),
(623, 'Yauca', 403),
(631, 'Aplao', 404),
(632, 'Andagua', 404),
(633, 'Ayo', 404),
(634, 'Chachas', 404),
(635, 'Chilcaymarca', 404),
(636, 'Choco', 404),
(637, 'Huancarqui', 404),
(638, 'Machaguay', 404),
(639, 'Orcopampa', 404),
(640, 'Pampacolca', 404),
(641, 'Tipán', 404),
(642, 'Uñón', 404),
(643, 'Uraca', 404),
(644, 'Viraco', 404),
(651, 'Chivay', 405),
(652, 'Achoma', 405),
(653, 'Cabanaconde', 405),
(654, 'Callalli', 405),
(655, 'Caylloma', 405),
(656, 'Coporaque', 405),
(657, 'Huambo', 405),
(658, 'Huanca', 405),
(659, 'Ichupampa', 405),
(660, 'Lari', 405),
(661, 'Lluta', 405),
(662, 'Maca', 405),
(663, 'Madrigal', 405),
(664, 'San Antonio de Chuca', 405),
(665, 'Sibayo', 405),
(666, 'Tapay', 405),
(667, 'Tisco', 405),
(668, 'Tuti', 405),
(669, 'Yanque', 405),
(670, 'Majes', 405),
(681, 'Chuquibamba', 406),
(682, 'Andaray', 406),
(683, 'Cayarani', 406),
(684, 'Chichas', 406),
(685, 'Iray', 406),
(686, 'Río Grande', 406),
(687, 'Salamanca', 406),
(688, 'Yanaquihua', 406),
(691, 'Mollendo', 407),
(692, 'Cocachacra', 407),
(693, 'Dean Valdivia', 407),
(694, 'Islay', 407),
(695, 'Mejía', 407),
(696, 'Punta de Bombón', 407),
(701, 'Cotahuasi', 408),
(702, 'Alca', 408),
(703, 'Charcana', 408),
(704, 'Huaynacotas', 408),
(705, 'Pampamarca', 408),
(706, 'Puyca', 408),
(707, 'Quechualla', 408),
(708, 'Sayla', 408),
(709, 'Tauria', 408),
(710, 'Tomepampa', 408),
(711, 'Toro', 408);

-- FIN DEL SCRIPT
