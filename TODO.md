# TODO: Agregar detalles de subtotal, IVA y total a detalle_orden.html

## Completed Tasks
- [x] Modify `order_detail` route in `app/routes.py` to calculate and pass `subtotal` and `iva` to the template
- [x] Update `app/templates/ordenes/detalle_orden.html` to display subtotal, IVA (16%), and total instead of just the total amount

## Summary of Changes
- Added IVA calculation (16% of subtotal) in the `order_detail` route
- Passed `subtotal` and `iva` variables to the `detalle_orden.html` template
- Replaced the single "Monto Total" display with a breakdown showing:
  - Subtotal: Bs. [amount]
  - IVA (16%): Bs. [amount]
  - Total: Bs. [amount] (highlighted in green)

## Next Steps
- Test the order detail page to verify the amounts display correctly
- Ensure the calculations match those in `imprimir_nota.html` for consistency
