from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


def _compound_discount(first_discount, second_discount):
    """Return the effective percentage for two sequential discounts."""
    return 100.0 * (
        1.0
        - (1.0 - (first_discount or 0.0) / 100.0)
        * (1.0 - (second_discount or 0.0) / 100.0)
    )


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
    amount_undiscounted = fields.Float('Amount Before Discount', compute='_compute_amount_undiscounted', digits=0)
    discount_amount = fields.Float(
        compute='_compute_discount_amount'
    )

    @api.depends('invoice_line_ids.price_unit', 'invoice_line_ids.quantity')
    def _compute_amount_undiscounted(self):
        for move in self:
            move.amount_undiscounted = sum(
                line.price_unit * line.quantity
                for line in move.invoice_line_ids
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
            rec.ks_sales_discount_account_id = rec.company_id.ks_sales_discount_account.id
            rec.ks_purchase_discount_account_id = rec.company_id.ks_purchase_discount_account.id

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
                    * line.quantity
                    * (1.0 - (line.discount_1 or 0.0) / 100.0)
                    for line in rec.invoice_line_ids
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

            for line in rec.invoice_line_ids.filtered(lambda item: not item.display_type):
                line.discount_2 = discount_rate

        if warning:
            return {'warning': warning}

    @api.constrains('ks_global_discount_rate', 'ks_global_discount_type')
    def _check_global_discount_value(self):
        for move in self:
            if move.ks_global_discount_rate < 0:
                raise ValidationError(_('Universal Discount cannot be negative.'))
            if move.ks_global_discount_type == 'percent' and move.ks_global_discount_rate > 100:
                raise ValidationError(_('Universal Discount percentage cannot exceed 100.'))
            if move.ks_global_discount_type == 'amount':
                eligible_amount = sum(
                    line.price_unit
                    * line.quantity
                    * (1.0 - (line.discount_1 or 0.0) / 100.0)
                    for line in move.invoice_line_ids
                    if not line.display_type
                )
                if move.ks_global_discount_rate > eligible_amount:
                    raise ValidationError(
                        _('Universal Discount amount cannot exceed the eligible line amount.')
                    )


class AccountMoveLine(models.Model):
    """
        Inherit Account Move Line:
         -
    """
    _inherit = 'account.move.line'

    discount_1 = fields.Float()
    discount_2 = fields.Float()
    discount = fields.Float(
        compute='_compute_discount',
        store=True,
    )

    @api.depends('discount_1', 'discount_2')
    def _compute_discount(self):
        """Compute the effective percentage without nested writes."""
        for line in self:
            line.discount = _compound_discount(line.discount_1, line.discount_2)

    @api.constrains('discount_1', 'discount_2')
    def _check_discount_percentages(self):
        for line in self:
            if not 0.0 <= line.discount_1 <= 100.0:
                raise ValidationError(_('Discount 1 must be between 0 and 100.'))
            if not 0.0 <= line.discount_2 <= 100.0:
                raise ValidationError(_('Discount 2 must be between 0 and 100.'))
