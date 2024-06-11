# -*- coding: utf-8 -*-
from odoo import models, fields, api, exceptions, _
from datetime import date, datetime, time, timedelta
from odoo.fields import Date, Datetime
from odoo.tools import float_compare
import odoo.addons.decimal_precision as dp


class NewModule(models.TransientModel):
    _name = 'revision.reason'
    _rec_name = 'name'
    _description = 'Revision Reason'

    name = fields.Char("Reason Of Change", required=True)
    sale_id = fields.Many2one(comodel_name="sale.order", string="Sale Order", required=False, )

    def action_confirm(self):
        if self.sale_id:
            self.sale_id.action_view_revision_wizard(self.name)
