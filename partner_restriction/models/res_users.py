from odoo import models, fields, api, SUPERUSER_ID

# -- List of predefined rules that must be managed
PREDEFINED_RULES = ['res.partner.rule.private.employee',
                    'res.partner.rule.private.group']


class PRTUsers(models.Model):
    _name = "res.users"
    _inherit = "res.users"

    partner_res_ids = fields.Many2many(
        'res.partner', string='Allowed partners', compute='partners_access_rules')

    def partners_access_rules(self):
        for rec in self:
            rec.partner_res_ids = False
            partners = self.env['res.partner'].search([])
            for partner in partners:
                if rec.id in partner.allowed_users_ids.ids:
                    rec.partner_res_ids = [(4, partner.id)]
