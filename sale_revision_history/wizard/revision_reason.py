# -*- coding: utf-8 -*-

from odoo import _, api, fields, models
from odoo.exceptions import UserError


class RevisionReason(models.TransientModel):
    _name = "revision.reason"
    _rec_name = "name"
    _description = "Quotation Revision Comment"

    name = fields.Text(string="Revision Comment", required=True)
    sale_id = fields.Many2one(
        "sale.order", string="Quotation", required=True, readonly=True,
    )

    is_restoration = fields.Boolean(
        string="Historical Restoration", readonly=True,
    )
    restore_source_id = fields.Many2one(
        "sale.order", string="Previously Sent Offer", copy=False,
        help="The sent version to copy into a new draft. It is never reopened or changed.",
    )
    restore_candidate_ids = fields.Many2many(
        "sale.order", compute="_compute_restore_candidates", string="Restore Candidates",
    )
    expected_current_revision_id = fields.Many2one(
        "sale.order", string="Expected Current Revision", readonly=True,
    )

    @api.depends("sale_id", "is_restoration")
    def _compute_restore_candidates(self):
        for wizard in self:
            if wizard.sale_id and wizard.is_restoration:
                current = wizard.sale_id._current_revision()
                wizard.restore_candidate_ids = current._restore_candidates(current)
            else:
                wizard.restore_candidate_ids = False

    def action_confirm(self):
        self.ensure_one()
        if self.is_restoration:
            if not self.restore_source_id:
                raise UserError(_("Select a previously sent quotation to restore."))
            if not (self.name or "").strip():
                raise UserError(_("A Restoration Reason is required."))
            return self.sale_id.action_restore_revision(
                self.restore_source_id,
                self.name,
                expected_current_id=self.expected_current_revision_id.id,
            )
        return self.sale_id.action_view_revision_wizard(self.name)
