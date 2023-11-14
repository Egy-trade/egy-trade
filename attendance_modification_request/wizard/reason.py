from odoo import fields, models, api


class CancelAttendanceWizard(models.TransientModel):
    _name = "cancellation.reason"
    _description = "Reason For Cancelling the request"

    reason = fields.Text("Reason")

    def action_reject(self):
        return
