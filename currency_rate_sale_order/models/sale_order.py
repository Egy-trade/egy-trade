from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    currency_rate_now = fields.Char(compute='_compute_currency_rate_now')
    currency_rate_confirm = fields.Char()
    currency_state = fields.Selection([('match', 'Matching'), ('not_match', 'Not Matching')])
    currency_is_default = fields.Boolean(compute='_check_default_currency_func')

    @api.onchange('pricelist_id', 'currency_id')
    def _onchange_currency_rate_confirm(self):
        """Snapshot the rate used by the interactive quotation flow.

        This intentionally stays out of ``create`` so unrelated API and batch
        sale-order creation retains Odoo's standard performance profile.
        """
        for order in self:
            order.currency_rate_confirm = order.currency_rate_now

    def action_confirm(self):
        # API-created orders may not have run browser onchange. Ensure the
        # snapshot exists before the quotation becomes a confirmed order.
        for order in self.filtered(lambda item: not item.currency_rate_confirm):
            order.currency_rate_confirm = order.currency_rate_now
        return super().action_confirm()

    def _compute_currency_rate_now(self):
        for rec in self:
            rate = rec.currency_id.rate_ids.filtered(
                lambda l: l.name == max([x.name for x in rec.currency_id.rate_ids]))
            rec.currency_rate_now = rate.inverse_company_rate if rate else 0
            if rec.currency_rate_now and rec.currency_rate_confirm:
                if float(rec.currency_rate_now) == float(rec.currency_rate_confirm):
                    rec.currency_state = 'match'
                else:
                    rec.currency_state = 'not_match'

    def action_update_prices(self):
        res = super(SaleOrder, self).action_update_prices()
        self.currency_rate_confirm = self.currency_rate_now
        return res

    @api.depends('pricelist_id', 'currency_id')
    def _check_default_currency_func(self):
        for rec in self:
            if rec.env.company.currency_id.id == rec.currency_id.id:
                rec.currency_is_default = True
            else:
                rec.currency_is_default = False
