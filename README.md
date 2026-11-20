# Sistema de Facturación – Repuestos y Rectificaciones Pacífico E.I.R.L.

Aplicación de escritorio (Tkinter) en Python con arquitectura en capas (DAO) sobre MySQL 8.0+.

## Puesta en marcha

1. `pip install -r requirements.txt`
2. `python main.py`

No hace falta crear la base de datos a mano. Flujo de arranque:

| Situación | Qué hace |
|---|---|
| No existe `config.json` o la conexión falla | Muestra la pantalla de configuración (host, puerto, usuario, contraseña). Al guardar se conecta **sin base de datos**, ejecuta `sql/script_facturacion_servicios.sql` completo, guarda `config.json` (con el nombre de la BD creada) y abre la ventana principal. |
| `config.json` válido y conexión correcta | Abre directo la ventana principal. Si detecta tablas/catálogos faltantes, reaplica el script (es idempotente). |

El usuario de MySQL necesita permiso `CREATE` (y `TRIGGER`/`CREATE ROUTINE`) para la primera instalación.

## Script SQL (`sql/script_facturacion_servicios.sql`)

* Idempotente: `CREATE ... IF NOT EXISTS`, **sin `DROP TABLE`**, `INSERT IGNORE` en catálogos. Se puede ejecutar también desde Workbench.
* Catálogos precargados: monedas (Soles/Dólares), formas de pago (Contado/Crédito), 12 detracciones del Anexo 3 SUNAT y ubigeo de Arequipa (8 provincias, 109 distritos).
* Los `id_distrito` son identificadores internos (el esquema los limita a ≤ 999); no son el ubigeo INEI.
* No incluye empresa, clientes, servicios ni facturas de prueba.

## Uso

1. **Empresa emisora**: registre razón social, RUC, dirección, teléfono, cuenta corriente y ubicación (Departamento → Provincia → Distrito). Se carga sola en cada factura.
2. **Clientes** y **Servicios/Productos**: CRUD desde el menú *Maestros* o las pestañas.
3. **Nueva factura**: elija cliente, moneda, forma de pago y detracción (combos cargados desde MySQL), agregue servicios y registre. Cabecera + detalle se guardan en una sola transacción; luego se ofrece exportar a PDF. También puede exportar desde **Facturas registradas**.

## Estructura

```
main.py                 Arranque: config.json, prueba de conexión, setup o ventana principal
sql/                    Script SQL (BD, tablas, triggers, catálogos)
core/                   config, setup_db (ejecuta el script), database, modelos, validadores, utilidades
dao/                    Acceso a datos (cliente, servicio, empresa, catálogo, factura, reporte)
ui/config_ventana.py    Pantalla inicial de configuración de BD
ui/tkinter_app.py       Ventana principal
ui/widgets.py           ComboID (texto ↔ ID) y SelectorUbigeo en cascada
ui/pdf_exporter.py      Factura en PDF (reportlab)
ui/consola.py           Interfaz de consola original (opcional)
```

## Generar el .exe (Windows)

Ejecute `build_exe.bat`. El script SQL va empaquetado (`--add-data "sql;sql"`); `config.json` se crea junto al .exe en el primer arranque.

## Notas

* `config.json` guarda la contraseña en texto plano (junto al ejecutable); protéjalo.
* La detracción se calcula sobre el total con IGV (lo hace `recalcular_factura`); la tasa vigente y el umbral (S/ 700) conviene verificarlos en SUNAT.
* Las tasas de detracción se cargan con `INSERT IGNORE`: si su BD ya tenía filas con otro porcentaje (p. ej. id 2 «Otros servicios empresariales» al 10 %), no se modifican.
