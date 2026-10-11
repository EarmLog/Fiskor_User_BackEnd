# Fiskor ERP — Backend

API REST del sistema **Fiskor**, un ERP orientado a la realidad fiscal y cambiaria
de Venezuela (IVA 16 %, IGTF 3 %, doble moneda Bs/USD y tasa BCV con respaldo
inteligente).

- **Framework:** Flask (patrón application factory + blueprints)
- **Base de datos:** SQLite en modo WAL
- **Autenticación:** Supabase (PostgreSQL) con caché local para trabajo sin conexión
- **Servidor de producción:** Waitress

## Requisitos

- Python 3.10 o superior

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # complete las credenciales reales
```

## Ejecución

```bash
python run.py             # desarrollo en http://0.0.0.0:5050
FISKOR_ENTORNO=produccion python run.py   # producción con Waitress
```

## Variables de entorno

Todas se documentan en `.env.example`. Las más relevantes:

| Variable | Descripción |
| --- | --- |
| `FISKOR_JWT_SECRET` | Clave para firmar los tokens de sesión |
| `SUPABASE_*` | Conexión a Supabase para el inicio de sesión de usuarios |
| `TASA_API_URL` | API de la tasa BCV/USD (con respaldo local si falla) |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | Administrador inicial sembrado al arrancar |
| `FISKOR_IVA` / `FISKOR_IGTF` | Alícuotas (16 % y 3 % por defecto) |

> El archivo `.env` **no** se versiona. Nunca suba credenciales al repositorio.

## Estructura

```
app/
  blueprints/   endpoints por módulo (auth, ventas, compras, inventario, ...)
  models/       modelos SQLAlchemy
  services/     lógica de negocio (tasa BCV, fiscal, exportación, Supabase)
  utils/        validaciones, respuestas, fechas y contexto
  __init__.py   fábrica de la aplicación
run.py          punto de entrada
```

## Módulos principales

`auth` · `usuarios` · `empresa` · `tasas` · `inventario` · `clientes` ·
`proveedores` · `ventas` (incluye cuentas por cobrar) · `compras` (cuentas por
pagar) · `tesoreria` · `nomina` · `fiscal` · `reportes` · `auditoria`.

## Licencia

Consulte el archivo [LICENSE](LICENSE).
