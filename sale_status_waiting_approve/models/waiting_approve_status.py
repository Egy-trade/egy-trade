# -*- coding: utf-8 -*-

from odoo import models, _
from odoo.exceptions import UserError


class inherit_sale(models.Model):
    _inherit = "sale.order"

    # state = fields.Selection(selection_add=[('waiting_approve', 'Waiting Approve')])

    def action_approve(self):
        # This legacy module must never bypass the controlled quotation
        # lifecycle. Its old ``waiting_approve`` state is no longer part of the
        # current sale.order selection, so route only genuine second-step
        # approvals to the protected parent implementation.
        if self.filtered(lambda order: order.state != 'waiting'):
            raise UserError(_(
                'Use the current quotation approval and confirmation workflow.'
            ))
        return super().action_approve()






