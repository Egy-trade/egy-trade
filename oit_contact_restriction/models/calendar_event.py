""" Initialize Calendar Event """

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError, Warning


class CalendarEvent(models.Model):
    """
        Inherit Calendar Event:
         -
    """
    _inherit = 'calendar.event'

    @api.model
    def create(self, vals_list):
        """ Override create """
        # vals_list ={'field': value}  -> dectionary contains only new filled fields
        res = super(CalendarEvent, self).create(vals_list)
        if self.env.user.has_group('oit_contact_restriction.group_restrict_contact'):
            if res.partner_ids:
                for partner in res.partner_ids:
                    if partner not in self.env.user.owner_partner_ids and not partner.is_user:
                        raise ValidationError('You Can Select Only Owners Customer !')
        return res
