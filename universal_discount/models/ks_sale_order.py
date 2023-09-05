# -*- coding: utf-8 -*-

from odoo import models, fields, api
from odoo.exceptions import UserError, ValidationError


class KsGlobalDiscountSales(models.Model):
    _inherit = "sale.order"

    ks_global_discount_type = fields.Selection([('percent', 'Percentage'), ('amount', 'Amount')],
                                               string='Universal Discount Type',
                                               readonly=True,
                                               states={'draft': [('readonly', False)], 'sent': [('readonly', False)]},
                                               default='percent')
    ks_global_discount_rate = fields.Float('Universal Discount',
                                           readonly=True,
                                           states={'draft': [('readonly', False)], 'sent': [('readonly', False)]})
    ks_amount_discount = fields.Monetary(string='Universal Discount', readonly=True,
                                         # compute='_amount_all',
                                         store=True,
                                         track_visibility='always')
    ks_enable_discount = fields.Boolean(compute='ks_verify_discount')
    # apply_discount_on_tax_amount = fields.Boolean()

    @api.depends('company_id.ks_enable_discount')
    def ks_verify_discount(self):
        for rec in self:
            rec.ks_enable_discount = rec.company_id.ks_enable_discount

    @api.onchange('ks_global_discount_rate', 'ks_global_discount_type')
    def _onchange_ks_global_discount_rate(self):
        """ ks_global_discount_rate """
        for rec in self:
            if rec.ks_global_discount_type == 'percent':
                rec.order_line.write({
                    'discount_3': rec.ks_global_discount_rate
                })
            else:
                if rec.order_line:
                    amount_total = 0
                    discount_amount = 0
                    for line in rec.order_line:
                        amount_total += line.price_unit * line.product_uom_qty
                        discount_amount += line.price_unit * line.product_uom_qty * line.discount_2 / 100

                    if amount_total:
                        discount_rate = (rec.ks_global_discount_rate / (amount_total-discount_amount)) * 100
                        rec.order_line.write({
                            'discount_3': discount_rate
                        })


    # @api.depends('order_line.price_total', 'ks_global_discount_rate', 'ks_global_discount_type')
    # def _amount_all(self):
    #     for rec in self:
    #         if not ('ks_global_tax_rate' in rec):
    #             rec.ks_calculate_discount()

    # @api.multi
    def _prepare_invoice(self):
        res = super(KsGlobalDiscountSales, self)._prepare_invoice()
        for rec in self:
            res['ks_global_discount_rate'] = rec.ks_global_discount_rate
            res['ks_global_discount_type'] = rec.ks_global_discount_type
        return res

    # @api.multi
    # def ks_calculate_discount(self):
    #     for rec in self:
    #         if rec.ks_global_discount_type == "amount":
    #             rec.ks_amount_discount = rec.ks_global_discount_rate if rec.amount_untaxed > 0 else 0
    #
    #         elif rec.ks_global_discount_type == "percent":
    #             if rec.ks_global_discount_rate != 0.0:
    #                 rec.ks_amount_discount = (rec.amount_untaxed + rec.amount_tax) * rec.ks_global_discount_rate / 100
    #             else:
    #                 rec.ks_amount_discount = 0
    #         elif not rec.ks_global_discount_type:
    #             rec.ks_amount_discount = 0
    #             rec.ks_global_discount_rate = 0
    #         rec.amount_total = rec.amount_untaxed + rec.amount_tax - rec.ks_amount_discount

    @api.constrains('ks_global_discount_rate', 'ks_global_discount_type')
    def ks_check_discount_value(self):
        if self.ks_global_discount_type == "percent":
            if self.ks_global_discount_rate > 100 or self.ks_global_discount_rate < 0:
                raise ValidationError('You cannot enter percentage value greater than 100.')
        else:
            if self.ks_global_discount_rate < 0 or self.ks_global_discount_rate > self.amount_untaxed:
                raise ValidationError(
                    'You cannot enter discount amount greater than actual cost or value lower than 0.')


class SaleOrderLine(models.Model):
    """
        Inherit Sale Order Line:
         -
    """
    _inherit = 'sale.order.line'

    discount_2 = fields.Float(
        'Discount 1'
    )
    discount_3 = fields.Float(
        'Discount 2'
    )

    @api.depends('product_uom_qty', 'discount', 'price_unit',
                 'tax_id', 'discount_2', 'discount_3')
    def _compute_amount(self):
        """
        Compute the amounts of the SO line.
        """
        for line in self:
            price_subtotal = (line.price_unit * line.product_uom_qty)
            second_price_subtotal = 0
            if line.discount_2:
                price_subtotal = (line.price_unit * line.product_uom_qty) - ((line.price_unit * line.product_uom_qty) * line.discount_2 / 100)
                discount_2_amount = (line.price_unit * line.product_uom_qty) * line.discount_2 / 100
                second_price_subtotal = price_subtotal
            if line.discount_3 and second_price_subtotal:
                discount_3_amount = second_price_subtotal * line.discount_3 / 100
                price_subtotal -= discount_3_amount
            elif line.discount_3:
                discount_3_amount = price_subtotal * line.discount_3 / 100
                price_subtotal -= discount_3_amount
            amount_untaxed = price_subtotal
            all_amount = line.price_unit * line.product_uom_qty
            discount_amount = all_amount - price_subtotal
            if all_amount > 0:
                line.discount = (discount_amount / all_amount) * 100
            tax_amt = 0
            taxes = line.tax_id.compute_all(
                line.price_unit,
                line.currency_id,
                line.product_uom_qty,
                line.product_id,
                line.order_id.partner_id)["taxes"]
            if taxes:
                for rec in taxes:
                    tax_amt += rec.get("amount")

            line.update({
                'price_subtotal': amount_untaxed,
                'price_tax': tax_amt,
                'price_total': amount_untaxed + tax_amt,
            })

    def _prepare_invoice_line(self, **optional_values):
        result = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        result['discount_1'] = self.discount_2
        result['discount_2'] = self.discount_3
        return result


class KsSaleAdvancePaymentInv(models.TransientModel):
    _inherit = "sale.advance.payment.inv"

    def _create_invoice(self, order, so_line, amount):
        invoice = super(KsSaleAdvancePaymentInv, self)._create_invoice(order, so_line, amount)
        if invoice:
            invoice['ks_global_discount_rate'] = order.ks_global_discount_rate
            invoice['ks_global_discount_type'] = order.ks_global_discount_type
        return invoice
