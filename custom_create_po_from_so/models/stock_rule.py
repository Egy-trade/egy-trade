"""Purchase procurement extensions that preserve Odoo's stock workflow."""

from odoo import api, fields, models


def _purchase_estimate_price(values, purchase_order):
    """Return the approved sale estimate converted to the PO currency."""
    sale_line = purchase_order.env['sale.order.line'].browse(
        values.get('sale_line_id')
    ).exists()
    if not sale_line or not hasattr(sale_line, 'purchase_price_estimate'):
        return False
    if sale_line.purchase_price_estimate <= 0:
        return False
    source_currency = (
        sale_line.order_id.currency_estimate_id
        if hasattr(sale_line.order_id, 'currency_estimate_id')
        else sale_line.order_id.currency_id
    )
    return source_currency._convert(
        sale_line.purchase_price_estimate,
        purchase_order.currency_id,
        purchase_order.company_id,
        fields.Date.context_today(sale_line),
    )


class StockRule(models.Model):
    _inherit = 'stock.rule'

    @api.model
    def _run_buy(self, procurements):
        """Use Odoo's supported RFQ reuse, merge, and cancellation behavior."""
        return super()._run_buy(procurements)

    def _update_purchase_order_line(
            self, product_id, product_qty, product_uom, company_id, values,
            line):
        result = super()._update_purchase_order_line(
            product_id, product_qty, product_uom, company_id, values, line,
        )
        estimate_price = _purchase_estimate_price(values, line.order_id)
        if estimate_price is not False:
            result['price_unit'] = estimate_price
        return result


class PurchaseOrderLine(models.Model):
    _inherit = 'purchase.order.line'

    @api.model
    def _prepare_purchase_order_line_from_procurement(
            self, product_id, product_qty, product_uom, company_id, values, po):
        result = super()._prepare_purchase_order_line_from_procurement(
            product_id, product_qty, product_uom, company_id, values, po,
        )
        estimate_price = _purchase_estimate_price(values, po)
        if estimate_price is not False:
            result['price_unit'] = estimate_price
        return result
