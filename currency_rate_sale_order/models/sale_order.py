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

    @api.model
    def create(self, vals_list):
        currency_rate_ids = self.env['res.currency'].browse(
            int(vals_list.get('currency_id')) if vals_list.get('currency_id') else self.currency_id.id).rate_ids

        vals_list['currency_rate_confirm'] = currency_rate_ids.filtered(
            lambda l: l.name == max([x.name for x in currency_rate_ids])).inverse_company_rate

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
