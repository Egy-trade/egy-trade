""" Initialize Create Quotation Template """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class CreateQuotationTemplate(models.TransientModel):
    """
        Initialize Create Quotation Template:
         -
    """
    _name = 'create.quotation.template'
    _description = 'Create Quotation Template'

    sale_id = fields.Many2one(
        'sale.order',
        string='Sale Order'
    )
    name = fields.Char()

    def create_quotation_template(self):
        """ Create Quotation Template """
        for rec in self:
            template = self.env['sale.order.template'].create({
                'name': rec.name
            })
            if rec.sale_id.order_line:
                for line in rec.sale_id.order_line:
                    self.env['sale.order.template.line'].create({
                        'name': line.name,
                        'product_uom_qty': line.product_uom_qty,
                        'product_id': line.product_id.id,
                        'product_uom_id': line.product_uom.id,
                        'sale_order_template_id': template.id,
                    })
            rec.sale_id.sale_order_template_id = template.id