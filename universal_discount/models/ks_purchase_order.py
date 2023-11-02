from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError
import json


class KSGlobalDiscountPurchases(models.Model):
    _inherit = "purchase.order"

    ks_global_discount_type = fields.Selection([('percent', 'Percentage'), ('amount', 'Amount')],
                                               string='Universal Discount Type', readonly=True,
                                               states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
                                               default='percent')
    ks_global_discount_rate = fields.Float('Universal Discount', readonly=True,
                                           states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
    ks_amount_discount = fields.Monetary(string='Universal Discount', readonly=True,
                                         # compute='_amount_all',
                                         track_visibility='always', store=True)
    ks_enable_discount = fields.Boolean(compute='ks_verify_discount')
    amount_undiscounted = fields.Float('Amount Before Discount', compute='_compute_amount_undiscounted', digits=0)
    discount_amount = fields.Float(
        compute='_compute_discount_amount'
    )

    def _compute_amount_undiscounted(self):
        for order in self:
            total = 0.0
            for line in order.order_line:
                total += (line.price_subtotal * 100)/(100-line.discount) if line.discount != 100 else (line.price_unit * line.product_qty)
            order.amount_undiscounted = total

    @api.depends('amount_undiscounted', 'amount_untaxed')
    def _compute_discount_amount(self):
        """ Compute discount_amount value """
        for rec in self:
            rec.discount_amount = rec.amount_undiscounted - rec.amount_untaxed

    @api.depends('company_id.ks_enable_discount')
    def ks_verify_discount(self):
        for rec in self:
            rec.ks_enable_discount = rec.company_id.ks_enable_discount

    def _prepare_invoice(self):
        ks_res = super(KSGlobalDiscountPurchases, self)._prepare_invoice()
        ks_res['ks_global_discount_type'] = self.ks_global_discount_type
        ks_res['ks_global_discount_rate'] = self.ks_global_discount_rate
        return ks_res

    def action_view_invoice(self, invoices=False):
        ks_res = super(KSGlobalDiscountPurchases, self).action_view_invoice()
        for rec in self:
            hh = ks_res['context']
            jj = str(hh).replace("'", '"')
            dic = json.loads(jj)
            dic['default_ks_global_discount_rate'] = rec.ks_global_discount_rate
            dic['default_ks_global_discount_type'] = rec.ks_global_discount_type
            context_str = json.dumps(dic)
            ks_res['context'] = context_str
            # ks_res['context']['default_ks_global_discount_rate'] = rec.ks_global_discount_rate
            # ks_res['context']['default_ks_global_discount_type'] = rec.ks_global_discount_type
        return ks_res

    @api.constrains('ks_global_discount_rate')
    def ks_check_discount_value(self):
        if self.ks_global_discount_type == "percent":
            if self.ks_global_discount_rate > 100 or self.ks_global_discount_rate < 0:
                raise ValidationError('You cannot enter percentage value greater than 100.')
        else:
            if self.ks_global_discount_rate < 0 or self.ks_global_discount_rate > self.amount_untaxed:
                raise ValidationError(
                    'You cannot enter discount amount greater than actual cost or value lower than 0.')

    @api.onchange('ks_global_discount_rate', 'ks_global_discount_type')
    def _onchange_ks_global_discount_rate(self):
        """ ks_global_discount_rate """
        for rec in self:
            if rec.ks_global_discount_rate:
                rec.order_line.write({
                    'discount_2': 0
                })
                if rec.ks_global_discount_type == 'percent':
                    rec.order_line.write({
                        'discount_2': rec.ks_global_discount_rate
                    })
                else:
                    if rec.order_line:
                        amount_total = 0
                        discount_amount = 0
                        for line in rec.order_line:
                            amount_total += line.price_unit * line.product_qty
                            discount_amount += line.price_unit * line.product_qty * line.discount_1 / 100
                        if amount_total:
                            discount_rate = (rec.ks_global_discount_rate / (amount_total - discount_amount)) * 100
                            rec.order_line.write({
                                'discount_2': discount_rate
                            })
            else:
                rec.order_line.write({
                    'discount_2': 0
                })


class purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    discount = fields.Float(
        'Discount %',
        compute='_compute_discount'
    )
    discount_1 = fields.Float()
    discount_2 = fields.Float()

    @api.depends('discount_1', 'discount_2')
    def _compute_discount(self):
        """ Compute discount value """
        for line in self:
            price_subtotal = (line.price_unit * line.product_qty)
            second_price_subtotal = 0
            if line.discount_1:
                price_subtotal = (line.price_unit * line.product_qty) - ((line.price_unit * line.product_qty) * line.discount_1 / 100)
                second_price_subtotal = price_subtotal
            if line.discount_2 and second_price_subtotal:
                discount_3_amount = second_price_subtotal * line.discount_2 / 100
                price_subtotal -= discount_3_amount
            elif line.discount_2:
                discount_3_amount = price_subtotal * line.discount_2 / 100
                price_subtotal -= discount_3_amount
            all_amount = line.price_unit * line.product_qty
            discount_amount = all_amount - price_subtotal
            if all_amount > 0:
                line.discount = (discount_amount / all_amount) * 100
            else:
                line.discount = 0
            line._compute_amount()


    def _prepare_account_move_line(self, move=False):
        result = super(purchase_order_line, self)._prepare_account_move_line()
        if result:
            result.update({
                'discount_1': self.discount_1,
                'discount_2': self.discount_2,
            })
        return result

    def _convert_to_tax_base_line_dict(self):
        self.ensure_one()
        return self.env['account.tax']._convert_to_tax_base_line_dict(
            self,
            partner=self.order_id.partner_id,
            currency=self.order_id.currency_id,
            product=self.product_id,
            taxes=self.taxes_id,
            price_unit=self.price_unit,
            quantity=self.product_qty,
            price_subtotal=self.price_subtotal,
            discount=self.discount
        )