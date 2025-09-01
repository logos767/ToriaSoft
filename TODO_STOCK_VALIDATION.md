# TODO - Mejoras en Validación de Stock

## Estado Actual
- ✅ Validación del lado del servidor existe pero es básica
- ❌ Mensajes de error no incluyen stock disponible actual
- ❌ Falta validación del lado del cliente
- ❌ No hay indicadores visuales de stock bajo
- ❌ La validación por código de barras no considera stock disponible

## Plan de Mejoras

### 1. Mejoras en routes.py
- [x] Mejorar el mensaje de error para incluir stock disponible actual y cantidad solicitada
- [x] Agregar validación más detallada con información específica del producto
- [x] Mejorar el manejo de errores para casos edge (stock = 0, etc.)
- [x] Agregar logging detallado para debugging

### 2. Mejoras en nuevo.html
- [x] Agregar validación del lado del cliente para cantidades vs stock disponible
- [x] Mostrar indicadores visuales de stock (bajo: <5, suficiente: 5-20, agotado: 0)
- [x] Prevenir entrada de cantidades que excedan el stock disponible
- [x] Mejorar la experiencia de usuario con feedback visual en tiempo real
- [x] Asegurar que la validación funcione con escaneo de códigos de barras
- [x] Agregar mensajes de advertencia cuando el stock es bajo
- [x] Deshabilitar productos sin stock en el dropdown

### 3. Funcionalidades Adicionales
- [ ] Agregar función para verificar stock disponible en tiempo real vía AJAX
- [ ] Implementar bloqueo de productos sin stock
- [ ] Agregar notificaciones visuales de stock bajo durante la selección

## Archivos a Modificar
- `ToriaSoft/app/routes.py`: Mejorar mensajes de error y validación
- `ToriaSoft/app/templates/ordenes/nuevo.html`: Agregar validación del lado del cliente e indicadores visuales

## Seguimiento de Progreso
- [ ] Paso 1: Modificar routes.py para mejorar validación del servidor
- [ ] Paso 2: Actualizar nuevo.html con validación del cliente
- [ ] Paso 3: Agregar indicadores visuales de stock
- [ ] Paso 4: Probar funcionalidad completa
- [ ] Paso 5: Verificar que no se puedan crear órdenes con stock insuficiente
