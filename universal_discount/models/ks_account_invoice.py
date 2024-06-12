from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError


class KsGlobalDiscountInvoice(models.Model):
    # _inherit = "account.invoice"
    """ changing the model to account.move """
    _inherit = "account.move"

    ks_global_discount_type = fields.Selection([
        ('percent', 'Percentage'),
        ('amount', 'Amount')],
        string='Universal Discount Type',
        readonly=True,
        states={'draft': [('readonly', False)],
                'sent': [('readonly', False)]},
        default='percent')
    ks_global_discount_rate = fields.Float('Universal Discount',
                                           readonly=True,
                                           states={'draft': [('readonly', False)],
                                                   'sent': [('readonly', False)]})
    ks_amount_discount = fields.Monetary(string='Universal Discount',
                                         # readonly=True,
                                         # compute='_compute_amount',
                                         store=True, track_visibility='always')
    ks_enable_discount = fields.Boolean(compute='ks_verify_discount')
    ks_sales_discount_account_id = fields.Integer(
        compute='ks_verify_discount'
    )
    ks_purchase_discount_account_id = fields.Integer(
        compute='ks_verify_discount'
    )
    discount_after_tax = fields.Boolean()

    @api.depends('company_id.ks_enable_discount')
    def ks_verify_discount(self):
        for rec in self:
            rec.ks_enable_discount = rec.company_id.ks_enable_discount
            rec.ks_sales_discount_account_id = rec.company_id.ks_sales_discount_account.id
            rec.ks_purchase_discount_account_id = rec.company_id.ks_purchase_discount_account.id

    @api.onchange('ks_global_discount_rate', 'ks_global_discount_type')
    def _onchange_ks_global_discount_rate(self):
        """ ks_global_discount_rate """
        for rec in self:
            if rec.ks_global_discount_rate:
                rec.invoice_line_ids.write({
                    'discount_2': 0
                })
                if rec.ks_global_discount_type == 'percent':
                    for line in rec.invoice_line_ids:
                        line.update({
                            'discount_2': rec.ks_global_discount_rate
                        })
                        # line._compute_discount()
                else:
                    if rec.invoice_line_ids:
                        amount_total = 0
                        discount_amount = 0
                        for line in rec.invoice_line_ids:
                            amount_total += line.price_unit * line.quantity
                            discount_amount += line.price_unit * line.quantity * line.discount_1 / 100
                        if amount_total:
                            # discount_rate = (rec.ks_global_discount_rate / amount_total) * 100
                            discount_rate = (rec.ks_global_discount_rate / (amount_total - discount_amount)) * 100
                            for line in rec.invoice_line_ids:
                                line.update({
                                    'discount_2': discount_rate
                                })
                                # line._compute_discount()
            else:
                rec.invoice_line_ids.write({
                    'discount_2': 0
                })


class AccountMoveLine(models.Model):
    """
        Inherit Account Move Line:
         -
    """
    _inherit = 'account.move.line'

    discount_1 = fields.Float()
    discount_2 = fields.Float()
    discount = fields.Float(
        compute='_compute_discount'
    )

    @api.depends('discount_1', 'discount_2')
    def _compute_discount(self):
        """ Compute discount value """
        for line in self:
            price_subtotal = (line.price_unit * line.quantity)
            second_price_subtotal = 0
            if line.discount_1:
                price_subtotal = (line.price_unit * line.quantity) - ((line.price_unit * line.quantity) * line.discount_1 / 100)
                second_price_subtotal = price_subtotal
            if line.discount_2 and second_price_subtotal:
                discount_3_amount = second_price_subtotal * line.discount_2 / 100
                price_subtotal -= discount_3_amount
            elif line.discount_2:
                discount_3_amount = price_subtotal * line.discount_2 / 100
                price_subtotal -= discount_3_amount
            all_amount = line.price_unit * line.quantity
            discount_amount = all_amount - price_subtotal
            if all_amount > 0:
                line.discount = (discount_amount / all_amount) * 100
            else:
                line.discount = 0
