""" Initialize Mail Activity """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class MailActivity(models.Model):
    """
        Inherit Mail Activity:
         -
    """
    _inherit = 'mail.activity'

    def action_close_dialog(self):
        """ Override action_close_dialog """
        res = super(MailActivity, self).action_close_dialog()
        lead = self.env['crm.lead'].search([('id', '=', self.res_id)])
        for rec in self:
            if rec.activity_type_id.add_allowed_partner and rec.res_model_id.model == 'crm.lead':
                rec.user_id.allowed_partner_ids |= lead.partner_id
                lead.partner_id.allowed_users_ids |= rec.user_id
        return res


class MailActivityType(models.Model):
    """
        Inherit Mail Activity Type:
         -
    """
    _inherit = 'mail.activity.type'

    add_allowed_partner = fields.Boolean()

