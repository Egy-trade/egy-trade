from ast import literal_eval

from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _compound_discount(first_discount, second_discount):
    """Return the effective percentage for two sequential discounts."""
    return 100.0 * (
        1.0
        - (1.0 - (first_discount or 0.0) / 100.0)
        * (1.0 - (second_discount or 0.0) / 100.0)
    )


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

    @api.depends('order_line.price_unit', 'order_line.product_qty')
    def _compute_amount_undiscounted(self):
        for order in self:
            order.amount_undiscounted = sum(
                line.price_unit * line.product_qty
                for line in order.order_line
                if not line.display_type
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

    def _prepare_invoice(self):
        self.ensure_one()
        ks_res = super()._prepare_invoice()
        ks_res['ks_global_discount_type'] = self.ks_global_discount_type
        ks_res['ks_global_discount_rate'] = self.ks_global_discount_rate
        return ks_res

    def action_view_invoice(self, invoices=False):
        self.ensure_one()
        ks_res = super().action_view_invoice(invoices=invoices)
        action_context = ks_res.get('context') or {}
        if isinstance(action_context, str):
            action_context = literal_eval(action_context)
        action_context = dict(action_context)
        action_context.update({
            'default_ks_global_discount_rate': self.ks_global_discount_rate,
            'default_ks_global_discount_type': self.ks_global_discount_type,
        })
        ks_res['context'] = action_context
        return ks_res

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
                    * line.product_qty
                    * (1.0 - (line.discount_1 or 0.0) / 100.0)
                    for line in order.order_line
                    if not line.display_type
                )
                if order.ks_global_discount_rate > eligible_amount:
                    raise ValidationError(
                        _('Universal Discount amount cannot exceed the eligible line amount.')
                    )

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
                    * line.product_qty
                    * (1.0 - (line.discount_1 or 0.0) / 100.0)
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
                line.discount_2 = discount_rate

        if warning:
            return {'warning': warning}


class purchase_order_line(models.Model):
    _inherit = 'purchase.order.line'

    discount = fields.Float(
        'Discount %',
        compute='_compute_discount',
        store=True,
    )
    discount_1 = fields.Float()
    discount_2 = fields.Float()

    @api.depends('discount_1', 'discount_2')
    def _compute_discount(self):
        """Compute the effective percentage without invoking other computes."""
        for line in self:
            line.discount = _compound_discount(line.discount_1, line.discount_2)

    @api.depends('product_qty', 'price_unit', 'taxes_id', 'discount')
    def _compute_amount(self):
        for line in self:
            discounted_price_unit = line.price_unit * (1.0 - line.discount / 100.0)
            taxes = line.taxes_id.compute_all(
                discounted_price_unit,
                line.order_id.currency_id,
                line.product_qty,
                product=line.product_id,
                partner=line.order_id.partner_id,
            )
            line.price_subtotal = taxes['total_excluded']
            line.price_tax = sum(tax.get('amount', 0.0) for tax in taxes['taxes'])
            line.price_total = taxes['total_included']

    @api.constrains('discount_1', 'discount_2')
    def _check_discount_percentages(self):
        for line in self:
            if not 0.0 <= line.discount_1 <= 100.0:
                raise ValidationError(_('Discount 1 must be between 0 and 100.'))
            if not 0.0 <= line.discount_2 <= 100.0:
                raise ValidationError(_('Discount 2 must be between 0 and 100.'))


    def _prepare_account_move_line(self, move=False):
        result = super()._prepare_account_move_line(move=move)
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
