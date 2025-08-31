# Optimización de impresión de códigos de barras

## Objetivo
Optimizar el espacio en página A4 para imprimir códigos de barras en 4 columnas y 11 filas por página

## Plan de trabajo
1. [x] Analizar el archivo actual `imprimir_codigos.html`
2. [x] Analizar el código relacionado en `routes.py` y `codigos_barra.html`
3. [x] Crear plan de optimización
4. [ ] Modificar CSS para usar 11 filas fijas por página
5. [ ] Crear contenedores separados para cada página (cada 44 productos)
6. [ ] Ajustar márgenes y espaciado para optimizar espacio A4
7. [ ] Asegurar saltos de página adecuados entre páginas
8. [ ] Verificar que la funcionalidad se mantenga

## Archivos a modificar
- `app/templates/inventario/imprimir_codigos.html` (principal)
