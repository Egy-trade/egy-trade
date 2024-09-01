""" Initialize Model """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class SaleOrder(models.Model):
    """
        Inherit Sale Order:
         -
    """
    _inherit = 'sale.order'

    lighting_designer_id = fields.Many2one(
        'res.users'
    )
    technical_sales_id = fields.Many2one(
        'res.users'
    )
    technical_office_id = fields.Many2one(
        'res.users'
    )
    terms_conditions_id = fields.Many2one(
        'terms.conditions'
    )
    amount_total = fields.Monetary(
        tracking=False
    )
    total = fields.Monetary(
        compute='_compute_total',
        tracking=True
    )

    @api.depends('amount_tax', 'order_line', 'amount_undiscounted', 'discount_amount')
    def _compute_total(self):
        """ Compute total value """
        for rec in self:
            if rec.order_line:
                tax_amount = 0
                for line in rec.order_line:
                    taxes = line.tax_id.compute_all(line.price_subtotal, rec.currency_id, 1,
                                                     product=line.product_id, partner=rec.partner_id)
                    price_tax = sum(t.get('amount', 0.0) for t in taxes.get('taxes', []))
                    tax_amount += price_tax
                rec.total = rec.amount_undiscounted - rec.discount_amount + tax_amount
            else:
                rec.total = 0

    def create_quotation_template(self):
        """ Create Quotation Template """
        self.ensure_one()
        return {
            'res_model': 'create.quotation.template',
            'name': _('Create Quotation Template'),
            'view_mode': 'form',
            'context': {
                'default_sale_id': self.id,
            },
            'target': 'new',
            'type': 'ir.actions.act_window',
        }

    @api.onchange('terms_conditions_id')
    def _onchange_terms_conditions_id(self):
        """ terms_conditions_id """
        for rec in self:
            if rec.terms_conditions_id:
                rec.write({
                    'note': rec.terms_conditions_id.name
                })
