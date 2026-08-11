# -*- coding: utf-8 -*-
"""Role-specific quotation access without exposing commercial master data."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


_DIRECTORY_PROGRESS_FIELDS = {
    "partner_id", "project", "team_id", "user_id", "state", "order_line",
    "client_order_ref", "validity_date", "offer_date", "note",
}


class SaleOrder(models.Model):
    _inherit = "sale.order"

    lighting_designer_ids = fields.Many2many(
        "res.users",
        "sale_order_lighting_designer_rel",
        "order_id",
        "user_id",
        string="Lighting Designers",
        copy=False,
        help=(
            "Assigned Lighting Designers may use the Technical Quotations "
            "workspace, which contains only products, descriptions, quantities, "
            "project context, and revision status."
        ),
        groups=(
            "sale_order_product_pricing.quotation_manager_group,"
            "sales_team.group_sale_manager"
        ),
    )
    technical_drawing_ids = fields.One2many(
        "quotation.technical.drawing",
        "order_id",
        string="Technical Drawings",
        copy=False,
        groups=(
            "sale_order_product_pricing.quotation_manager_group,"
            "sales_team.group_sale_manager"
        ),
        help=(
            "Drawings intentionally released to the assigned Lighting Designers. "
            "Upload only technical files that contain no prices, costs, margins, "
            "vendor details, or client contacts."
        ),
    )
    standard_discount_override_reason = fields.Text(
        string="Standard Discount Override Reason",
        copy=False,
        help=(
            "Required before quotation or sales management applies a Standard "
            "Discount above the assigned user's personal cap. The reason is "
            "copied to the protected audit and then cleared."
        ),
        groups=(
            "sale_order_product_pricing.quotation_manager_group,"
            "sales_team.group_sale_manager"
        ),
    )
    allowed_salesperson_ids = fields.Many2many(
        "res.users",
        string="Allowed Salespeople",
        compute="_compute_allowed_salesperson_ids",
        compute_sudo=True,
        help=(
            "Active internal users who hold the Sales user permission. This "
            "technical list limits the Salesperson selector for draft quotations."
        ),
    )

    def _is_quotation_manager(self):
        group = self.env.ref(
            "sale_order_product_pricing.quotation_manager_group",
            raise_if_not_found=False,
        )
        return bool(group and group in self.env.user.groups_id)

    def _is_sales_or_quotation_manager(self):
        return (
            self.env.is_superuser()
            or self.env.user.has_group("sales_team.group_sale_manager")
            or self._is_quotation_manager()
        )

    def _validate_salesperson(self, user_id):
        salesperson = self.env["res.users"].browse(user_id).exists()
        if not salesperson or not salesperson.active or salesperson.share:
            raise ValidationError(_(
                "Salesperson must be an active internal Sales user."
            ))
        # ``has_group`` checks the environment user. Switch to the candidate
        # so RPC/import cannot assign an active employee who is not a Sales user.
        if not salesperson.with_user(salesperson).has_group(
                "sales_team.group_sale_salesman"):
            raise ValidationError(_(
                "Salesperson must be an active internal Sales user."
            ))

    @api.depends_context("uid", "allowed_company_ids")
    def _compute_allowed_salesperson_ids(self):
        candidates = self.env["res.users"].sudo().search([
            ("active", "=", True), ("share", "=", False),
        ])
        salespeople = candidates.filtered(
            lambda user: user.with_user(user).has_group(
                "sales_team.group_sale_salesman"
            )
        )
        for order in self:
            order.allowed_salesperson_ids = salespeople

    def _sync_technical_scopes(self):
        Scope = self.env["quotation.technical.scope"].sudo()
        for order in self:
            designers = order.sudo().lighting_designer_ids
            existing = Scope.search([("order_id", "=", order.id)])
            obsolete = existing.filtered(lambda scope: scope.designer_id not in designers)
            obsolete.unlink()
            for designer in designers:
                scope = existing.filtered(lambda item: item.designer_id == designer)[:1]
                values = {
                    "order_id": order.id,
                    "designer_id": designer.id,
                    "project_name": order.project or order.name,
                    "internal_reference": order.name,
                    "revision_status": dict(order._fields["state"].selection).get(order.state, order.state),
                }
                if scope:
                    scope.write(values)
                else:
                    Scope.create(values)
            order._sync_technical_scope_lines()

    def _sync_project_directory(self):
        Directory = self.env["quotation.project.directory"].sudo()
        for order in self:
            directory = Directory.search([("order_id", "=", order.id)], limit=1)
            values = {
                "order_id": order.id,
                "project_name": order.project or order.name,
                "internal_reference": order.name,
                "client_organization": order.partner_id.commercial_partner_id.name,
                "stage": dict(order._fields["state"].selection).get(order.state, order.state),
                "owner_team_name": order.team_id.name,
                "latest_activity": fields.Datetime.now(),
            }
            if directory:
                directory.write(values)
            else:
                Directory.create(values)

    def _sync_technical_scope_lines(self):
        ScopeLine = self.env["quotation.technical.scope.line"].sudo()
        for order in self:
            scopes = self.env["quotation.technical.scope"].sudo().search([
                ("order_id", "=", order.id),
            ])
            for scope in scopes:
                existing = {line.sale_line_id.id: line for line in scope.line_ids}
                sale_lines = order.order_line.filtered(lambda line: not line.display_type)
                stale = scope.line_ids.filtered(lambda line: line.sale_line_id not in sale_lines)
                stale.unlink()
                for sale_line in sale_lines:
                    values = {
                        "scope_id": scope.id,
                        "sale_line_id": sale_line.id,
                        "product_name": sale_line.product_id.display_name,
                        "description": sale_line.name,
                        "quantity": sale_line.product_uom_qty,
                        "uom_name": sale_line.product_uom.name,
                    }
                    if sale_line.id in existing:
                        existing[sale_line.id].write(values)
                    else:
                        ScopeLine.create(values)

    @api.model_create_multi
    def create(self, vals_list):
        prepared = []
        is_specialist = self.env.user.has_group(
            "sale_order_product_pricing.quotation_specialist_group"
        ) and not self._is_sales_or_quotation_manager()
        for incoming in vals_list:
            vals = dict(incoming)
            if is_specialist:
                if vals.get("quotation_specialist_id") not in (False, self.env.user.id):
                    raise AccessError(_(
                        "A Quotation Specialist may only create a quotation assigned to themselves."
                    ))
                vals.setdefault("quotation_specialist_id", self.env.user.id)
            if vals.get("user_id"):
                self._validate_salesperson(vals["user_id"])
            if vals.get("lighting_designer_ids") and not self._is_sales_or_quotation_manager():
                raise AccessError(_("Only quotation or sales management may assign Lighting Designers."))
            prepared.append(vals)
        orders = super().create(prepared)
        orders._sync_technical_scopes()
        orders._sync_project_directory()
        return orders

    def write(self, vals):
        vals = dict(vals)
        salesperson_changes = {}
        if "user_id" in vals:
            self._validate_salesperson(vals["user_id"])
            salesperson_changes = {order.id: order.user_id for order in self}
        if "lighting_designer_ids" in vals and not self._is_sales_or_quotation_manager():
            raise AccessError(_("Only quotation or sales management may assign Lighting Designers."))
        if "standard_discount_override_reason" in vals:
            if not self._is_sales_or_quotation_manager():
                raise AccessError(_(
                    "Only quotation or sales management may provide a discount override reason."
                ))
            if self.filtered(lambda order: order.state != "draft"):
                raise ValidationError(_(
                    "A Standard Discount override reason can only be prepared on a draft quotation."
                ))
        result = super().write(vals)
        if "lighting_designer_ids" in vals:
            self._sync_technical_scopes()
        if _DIRECTORY_PROGRESS_FIELDS.intersection(vals):
            self._sync_project_directory()
        if "user_id" in vals:
            for order in self:
                old_user = salesperson_changes[order.id]
                if old_user != order.user_id:
                    order._pricing_log(_(
                        "Salesperson assignment changed from %(old)s to %(new)s."
                    ) % {
                        "old": old_user.display_name or _("Unassigned"),
                        "new": order.user_id.display_name or _("Unassigned"),
                    })
        return result


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    def write(self, vals):
        orders = self.mapped("order_id")
        result = super().write(vals)
        orders._sync_technical_scope_lines()
        orders._sync_project_directory()
        return result

    @api.model_create_multi
    def create(self, vals_list):
        lines = super().create(vals_list)
        lines.mapped("order_id")._sync_technical_scope_lines()
        lines.mapped("order_id")._sync_project_directory()
        return lines

    def unlink(self):
        orders = self.mapped("order_id")
        result = super().unlink()
        orders._sync_technical_scope_lines()
        orders._sync_project_directory()
        return result


class ResPartner(models.Model):
    _inherit = "res.partner"

    def _quotation_specialist_contact_restricted(self):
        user = self.env.user
        quotation_manager = self.env.ref(
            "sale_order_product_pricing.quotation_manager_group",
            raise_if_not_found=False,
        )
        return (
            user.has_group("sale_order_product_pricing.quotation_specialist_group")
            and not user.has_group("sales_team.group_sale_manager")
            and not (quotation_manager and quotation_manager in user.groups_id)
        )

    @api.model_create_multi
    def create(self, vals_list):
        if self._quotation_specialist_contact_restricted():
            raise AccessError(_(
                "Quotation Specialists can select existing clients and contacts but cannot create client master data."
            ))
        return super().create(vals_list)

    def write(self, vals):
        if self._quotation_specialist_contact_restricted():
            raise AccessError(_(
                "Quotation Specialists can select existing clients and contacts but cannot edit client master data."
            ))
        return super().write(vals)

    def unlink(self):
        if self._quotation_specialist_contact_restricted():
            raise AccessError(_(
                "Quotation Specialists cannot delete client master data."
            ))
        return super().unlink()


class QuotationTechnicalScope(models.Model):
    _name = "quotation.technical.scope"
    _description = "Lighting Designer Technical Quotation Scope"
    _order = "id desc"
    _rec_name = "internal_reference"

    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", groups="base.group_no_one")
    designer_id = fields.Many2one("res.users", required=True, ondelete="cascade", groups="base.group_no_one")
    project_name = fields.Char(readonly=True)
    internal_reference = fields.Char(readonly=True)
    revision_status = fields.Char(readonly=True)
    line_ids = fields.One2many("quotation.technical.scope.line", "scope_id", readonly=True)

    _sql_constraints = [
        ("quotation_technical_scope_unique", "unique(order_id, designer_id)",
         "Each Lighting Designer may have only one technical scope per quotation."),
    ]


class QuotationTechnicalScopeLine(models.Model):
    _name = "quotation.technical.scope.line"
    _description = "Lighting Designer Technical Quotation Line"
    _order = "id"

    scope_id = fields.Many2one("quotation.technical.scope", required=True, ondelete="cascade", groups="base.group_no_one")
    sale_line_id = fields.Many2one("sale.order.line", required=True, ondelete="cascade", groups="base.group_no_one")
    product_name = fields.Char(readonly=True)
    description = fields.Text(readonly=True)
    quantity = fields.Float(readonly=True)
    uom_name = fields.Char(readonly=True)

    _sql_constraints = [
        ("quotation_technical_scope_line_unique", "unique(scope_id, sale_line_id)",
         "A technical quotation scope can contain each quotation line only once."),
    ]


class QuotationTechnicalDrawing(models.Model):
    _name = "quotation.technical.drawing"
    _description = "Lighting Designer Technical Drawing"
    _order = "create_date desc, id desc"

    order_id = fields.Many2one(
        "sale.order", required=True, ondelete="cascade", index=True,
        groups="base.group_no_one",
    )
    name = fields.Char(
        string="Drawing Title", required=True,
        help=(
            "Plain-language drawing title visible to assigned Lighting Designers. "
            "Do not include commercial or client-contact information."
        ),
    )
    file_data = fields.Binary(
        string="Drawing File", required=True, attachment=True,
        help=(
            "Technical drawing released to assigned Lighting Designers. Managers "
            "must confirm the file contains no commercial or contact data before upload."
        ),
    )
    file_name = fields.Char(string="Filename")
    uploaded_by_id = fields.Many2one(
        "res.users", string="Released By", readonly=True,
        default=lambda self: self.env.user, copy=False,
    )
    revision_status = fields.Selection(
        related="order_id.state", string="Revision Status", readonly=True,
    )


class QuotationProjectDirectory(models.Model):
    _name = "quotation.project.directory"
    _description = "General Employee Project Directory"
    _order = "latest_activity desc, id desc"
    _rec_name = "internal_reference"

    order_id = fields.Many2one("sale.order", required=True, ondelete="cascade", groups="base.group_no_one")
    project_name = fields.Char(readonly=True)
    internal_reference = fields.Char(readonly=True)
    client_organization = fields.Char(readonly=True)
    stage = fields.Char(readonly=True)
    owner_team_name = fields.Char(readonly=True)
    latest_activity = fields.Datetime(readonly=True)

    _sql_constraints = [
        ("quotation_project_directory_order_unique", "unique(order_id)",
         "A quotation may have only one employee directory entry."),
    ]
