# -*- coding: utf-8 -*-

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _compound_discount(first_discount, second_discount):
    """Return the effective percentage for two sequential discounts."""
    return 100.0 * (
        1.0
        - (1.0 - (first_discount or 0.0) / 100.0)
        * (1.0 - (second_discount or 0.0) / 100.0)
    )


class KsGlobalDiscountSales(models.Model):
    _inherit = "sale.order"

    ks_global_discount_type = fields.Selection([('percent', 'Percentage'), ('amount', 'Amount')],
                                               string='Universal Discount Type',
                                               readonly=True,
                                               states={'draft': [('readonly', False)]},
                                               default='percent')
    ks_global_discount_rate = fields.Float('Universal Discount',
                                           readonly=True,
                                           states={'draft': [('readonly', False)]})
    ks_amount_discount = fields.Monetary(string='Universal Discount', readonly=True,
                                         # compute='_amount_all',
                                         store=True,
                                         track_visibility='always')
    ks_enable_discount = fields.Boolean(compute='ks_verify_discount')
    # apply_discount_on_tax_amount = fields.Boolean()

    discount_amount = fields.Float(
        compute='_compute_discount_amount'
    )

    @api.depends('amount_undiscounted', 'amount_untaxed')
    def _compute_discount_amount(self):
        """ Compute discount_amount value """
        for rec in self:
            rec.discount_amount = rec.amount_undiscounted - rec.amount_untaxed

    @api.depends('company_id.ks_enable_discount')
    def ks_verify_discount(self):
        for rec in self:
            rec.ks_enable_discount = rec.company_id.ks_enable_discount

    @api.onchange('ks_global_discount_rate', 'ks_global_discount_type')
    def _onchange_ks_global_discount_rate(self):
        """Apply the global discount to virtual lines without database writes."""
        warning = False
        for rec in self:
            discount_rate = 0.0
            if rec.ks_global_discount_type == 'percent':
                discount_rate = rec.ks_global_discount_rate
            elif rec.ks_global_discount_rate:
                eligible_amount = sum(
                    line.price_unit
                    * line.product_uom_qty
                    * (1.0 - (line.discount_2 or 0.0) / 100.0)
                    for line in rec.order_line
                    if not line.display_type
                )
                if eligible_amount > 0.0:
                    discount_rate = rec.ks_global_discount_rate / eligible_amount * 100.0
                else:
                    warning = {
                        'title': _('Universal Discount Not Applied'),
                        'message': _(
                            'A fixed discount requires at least one line with a positive amount after the first discount.'
                        ),
                    }

            for line in rec.order_line.filtered(lambda item: not item.display_type):
                line.discount_3 = discount_rate

        if warning:
            return {'warning': warning}


    # @api.depends('order_line.price_total', 'ks_global_discount_rate', 'ks_global_discount_type')
    # def _amount_all(self):
    #     for rec in self:
    #         if not ('ks_global_tax_rate' in rec):
    #             rec.ks_calculate_discount()

    # @api.multi
    def _prepare_invoice(self):
        self.ensure_one()
        res = super()._prepare_invoice()
        res['ks_global_discount_rate'] = self.ks_global_discount_rate
        res['ks_global_discount_type'] = self.ks_global_discount_type
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
        for order in self:
            if order.ks_global_discount_rate < 0:
                raise ValidationError(_('Universal Discount cannot be negative.'))
            if order.ks_global_discount_type == 'percent' and order.ks_global_discount_rate > 100:
                raise ValidationError(_('Universal Discount percentage cannot exceed 100.'))
            if order.ks_global_discount_type == 'amount':
                eligible_amount = sum(
                    line.price_unit
                    * line.product_uom_qty
                    * (1.0 - (line.discount_2 or 0.0) / 100.0)
                    for line in order.order_line
                    if not line.display_type
                )
                if order.ks_global_discount_rate > eligible_amount:
                    raise ValidationError(
                        _('Universal Discount amount cannot exceed the eligible line amount.')
                    )


class SaleOrderLine(models.Model):
    """
        Inherit Sale Order Line:
         -
    """
    _inherit = 'sale.order.line'

    discount_2 = fields.Float(string='Discount 1')
    discount_3 = fields.Float(string='Discount 2')
    discount = fields.Float(
        string='Discount (%)',
        compute='_compute_compound_discount',
        store=True,
        readonly=True,
    )
    tx_amount = fields.Monetary(
        string='Tax Amount',
        compute='_compute_tax_amount',
        currency_field='currency_id',
        store=True,
    )

    @api.depends('discount_2', 'discount_3')
    def _compute_compound_discount(self):
        for line in self:
            line.discount = _compound_discount(line.discount_2, line.discount_3)

    @api.depends('price_tax')
    def _compute_tax_amount(self):
        for line in self:
            line.tx_amount = line.price_tax

    @api.constrains('discount_2', 'discount_3')
    def _check_discount_percentages(self):
        for line in self:
            if not 0.0 <= line.discount_2 <= 100.0:
                raise ValidationError(_('Discount 1 must be between 0 and 100.'))
            if not 0.0 <= line.discount_3 <= 100.0:
                raise ValidationError(_('Discount 2 must be between 0 and 100.'))


    def _prepare_invoice_line(self, **optional_values):
        result = super(SaleOrderLine, self)._prepare_invoice_line(**optional_values)
        result['discount_1'] = self.discount_2
        result['discount_2'] = self.discount_3
        return result
