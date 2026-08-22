from odoo import api, fields, models


class SaleOrder(models.Model):
    _inherit = 'sale.order'

    currency_rate_now = fields.Char(compute='_compute_currency_rate_now')
    currency_rate_confirm = fields.Char()
    currency_state = fields.Selection([('match', 'Matching'), ('not_match', 'Not Matching')])
    currency_is_default = fields.Boolean(compute='_check_default_currency_func')

    # def action_confirm(self):
    #     res = super(SaleOrder, self).action_confirm()
    #     self.currency_rate_confirm = self.currency_id.rate_ids.filtered(
    #         lambda l: l.name == max([x.name for x in self.currency_id.rate_ids])).inverse_company_rate
    #     return res

    @api.model_create_multi
    def create(self, vals_list):
        """Snapshot each order's creation-time currency rate.

        Grouped implementation: the latest inverse rate is resolved once per
        DISTINCT currency across the whole input list (the ORM cache serves
        repeated currencies), instead of once per record. Handles both single
        dicts and lists and falls back to the company currency when no
        explicit currency is given. The company currency converts to itself,
        so its snapshot is the deterministic 1.0 without any rate lookup.
        """
        company_currency_id = self.env.company.currency_id.id
        latest_inverse_rate = {}
        for vals in vals_list:
            currency_id = vals.get('currency_id') or company_currency_id
            if currency_id not in latest_inverse_rate:
                if currency_id == company_currency_id:
                    latest_inverse_rate[currency_id] = 1.0
                else:
                    rates = self.env['res.currency'].browse(currency_id).rate_ids
                    latest_inverse_rate[currency_id] = (
                        rates.filtered(
                            lambda l: l.name == max([x.name for x in rates])
                        ).inverse_company_rate
                        if rates else False
                    )
        for vals in vals_list:
            vals['currency_rate_confirm'] = (
                latest_inverse_rate[vals.get('currency_id') or company_currency_id])

        return super(SaleOrder, self).create(vals_list)

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
                print('true')
                rec.currency_is_default = True
            else:
                rec.currency_is_default = False
