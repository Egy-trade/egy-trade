"""Service-purchase pricing hooks that preserve Odoo's standard workflow."""

from odoo import fields, models


class SaleOrderLine(models.Model):
    _inherit = 'sale.order.line'

    def _purchase_service_prepare_line_values(
            self, purchase_order, quantity=False):
        """Seed a service RFQ from an approved positive purchase estimate.

        Odoo remains responsible for vendor selection, taxes, descriptions,
        planning dates, draft-PO reuse, and duplicate prevention. A zero
        estimate deliberately leaves Odoo's vendor-price result unchanged.
        """
        self.ensure_one()
        values = super()._purchase_service_prepare_line_values(
            purchase_order, quantity=quantity,
        )
        purchase_estimate = self.purchase_price_estimate
        if purchase_estimate > 0:
            source_currency = (
                self.order_id.currency_estimate_id
                or self.order_id.currency_id
            )
            values['price_unit'] = source_currency._convert(
                purchase_estimate,
                purchase_order.currency_id,
                purchase_order.company_id,
                fields.Date.context_today(self),
            )
        return values
