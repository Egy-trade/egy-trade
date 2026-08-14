# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class inherit_sale(models.Model):
    _inherit = "sale.order"

    def action_approve(self):
        raise UserError(_(
            'The legacy Waiting Approval action is retired. Use the current '
            'quotation approval and standard confirmation workflow.'
        ))






