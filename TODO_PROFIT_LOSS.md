# TODO: Agregar Resumen Mensual de Ganancias y Pérdidas a Estadísticas

## Información Recopilada
- **Archivo actual de estadísticas**: `app/templates/estadisticas.html` muestra 3 gráficos: ventas mensuales, top productos, clientes frecuentes
- **Ruta de estadísticas**: `app/routes.py` en la función `estadisticas()` calcula datos actuales
- **Modelos relevantes**:
  - `Order`: ventas con `total_amount` y `date_created`
  - `Purchase`: costos con `total_cost` y `date_created`
  - `CostStructure`: gastos fijos (renta, servicios, impuestos) y porcentajes variables (comisión ventas, marketing)
- **Datos disponibles**: Ventas mensuales ya calculadas, necesito agregar costos y gastos

## Plan Detallado

### 1. Actualizar `app/routes.py` - Función `estadisticas()`
- [x] Agregar consulta para costos mensuales desde `Purchase.total_cost`
- [x] Calcular gastos mensuales:
  - Gastos fijos: distribuir `CostStructure` (renta + servicios + impuestos) / 12
  - Gastos variables: comisión de ventas y marketing basados en ventas mensuales
- [x] Calcular ganancias/pérdidas mensuales: ventas - costos - gastos
- [x] Preparar datos para gráfico de ganancias/pérdidas
- [x] Agregar resumen numérico (total ganancias, total pérdidas, promedio mensual)

### 2. Actualizar `app/templates/estadisticas.html`
- [x] Agregar nueva sección para gráfico de ganancias/pérdidas mensuales
- [x] Agregar sección de resumen con valores numéricos
- [x] Incluir JavaScript para el nuevo gráfico usando Chart.js
- [x] Mantener diseño consistente con las otras secciones

## Archivos a Editar
- [x] `app/routes.py`: Modificar función `estadisticas()` para calcular datos de P&L
- [x] `app/templates/estadisticas.html`: Agregar gráfico y resumen de ganancias/pérdidas

## Pasos de Seguimiento
- [ ] Probar cálculos de ganancias/pérdidas con datos de prueba
- [ ] Verificar que el gráfico se renderice correctamente
- [ ] Validar que los valores del resumen sean precisos
- [ ] Revisar responsive design en diferentes tamaños de pantalla
