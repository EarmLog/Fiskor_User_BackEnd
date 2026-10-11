# ============================================================
# Punto de entrada del backend de Fiskor ERP.
# Uso:  python run.py  (desarrollo)
#       waitress-serve --port 5050 app.crear_aplicacion:crear_aplicacion
# ============================================================
import os

from waitress import serve

from app import crear_aplicacion

if __name__ == "__main__":
    # Creamos la aplicacion completa (fabrica + datos iniciales).
    aplicacion = crear_aplicacion()

    if os.getenv("FISKOR_ENTORNO", "desarrollo").lower() == "produccion":
        # Servidor de produccion robusto: soporta varios usuarios.
        print(" * Fiskor ERP corriendo en produccion sobre Waitress :5050")
        serve(aplicacion, host="0.0.0.0", port=5050, threads=8)
    else:
        # Modo desarrollo con recarga automatica.
        aplicacion.run(host="0.0.0.0", port=5050, debug=True, use_reloader=False)