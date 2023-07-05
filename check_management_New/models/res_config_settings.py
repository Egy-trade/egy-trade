from odoo import models, fields,api


class ResConfigSettings(models.TransientModel):
    _inherit = 'res.config.settings'

    description_check_received = fields.Char(string="Description Check Received", config_parameter='check_notification.description_check_received')
    description_check_issued = fields.Char(string="Description Check Issued",config_parameter='check_notification.description_check_issued')
    reminder_ids = fields.Many2many(related='company_id.reminder_ids', string="Reminders" ,readonly=False)


class NotificationReminder(models.Model):
    _inherit = 'res.company'

    reminder_ids = fields.Many2many(comodel_name='calendar.alarm', string="Reminders")

