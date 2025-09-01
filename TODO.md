# TODO: Modificar impresión de códigos de barra para nombres largos y agregar bordes

## Tareas Pendientes
- [x] Modificar la función `generate_barcode_pdf_reportlab` en `app/routes.py` para permitir dos líneas en el nombre del producto
- [x] Ajustar la posición del código de barras hacia abajo para hacer espacio para la segunda línea
- [x] Agregar borde a cada etiqueta para delimitarlas
- [x] Cambiar el borde a líneas segmentadas (dashed) cada 2mm para delimitar el recorte
- [ ] Probar la generación del PDF para confirmar que los nombres largos se dividan en dos líneas, el código de barras esté posicionado correctamente y los bordes segmentados se dibujen (requiere ejecutar la aplicación)

## Información Recopilada
- La función `generate_barcode_pdf_reportlab` en `app/routes.py` genera el PDF con códigos de barra usando ReportLab.
- El nombre del producto se dibuja en una sola línea actualmente.
- El código de barras se posiciona en la parte inferior de la etiqueta.

## Plan de Edición
- Dividir el nombre del producto en dos líneas si supera una longitud máxima (ej. 30 caracteres).
- Dibujar la primera línea en la posición original y la segunda línea debajo.
- Mover el código de barras y su texto hacia abajo para crear espacio.
- Dibujar un borde rectangular alrededor de cada etiqueta.

## Archivos Dependientes
- Ninguno, ya que esta es la única función que genera el PDF de códigos de barra.
