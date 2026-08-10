# -*- coding: utf-8 -*-
"""Quotation pricing presentation counters and post-send write protection."""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, UserError

from .sale_order import _is_pricing_downpayment, _is_pricing_internal


_ORDER_PRICING_FIELDS = {
    "order_line",
    "pricelist_id",
    "currency_id",
    "product_pricing",
    "currency_estimate_id",
    "change_currency_rate_type",
    "change_currency_rate",
    "global_factor",
    "ks_enable_discount",
    "ks_global_discount_type",
    "ks_global_discount_rate",
}
_ORDER_STATE_LOCKED_FIELDS = _ORDER_PRICING_FIELDS | {
    "partner_id",
    "partner_invoice_id",
    "partner_shipping_id",
    "date_order",
    "validity_date",
    "payment_term_id",
    "fiscal_position_id",
    "incoterm",
    "incoterm_id",
    "client_order_ref",
    "note",
}
_LINE_PRICING_FIELDS = {
    "product_id",
    "product_uom",
    "product_uom_qty",
    "tax_id",
    "is_downpayment",
    "name",
    "price_unit",
    "discount",
    "discount_2",
    "discount_3",
    "price_origin",
    "price_reference",
    "price_currency_id",
    "pricing_warning",
    "pricing_reprice_pending",
    "purchase_price_estimate",
    "factor",
    "line_factor",
    "estimate_unit_price",
    "currency_estimate_id",
    "currency_rate_estimate",
}


class SaleOrder(models.Model):
    _inherit = "sale.order"

    quotation_specialist_id = fields.Many2one(
        "res.users",
        string="Quotation Specialist",
        copy=True,
        tracking=True,
        default=lambda self: (
            self.env.user if self.env.user.has_group(
                "sale_order_product_pricing.quotation_specialist_group"
            ) else False
        ),
        groups=(
            "sale_order_product_pricing.quotation_specialist_group,"
            "sales_team.group_sale_manager"
        ),
    )
    can_edit_quotation_price = fields.Boolean(
        compute="_compute_can_edit_quotation_price"
    )
    can_assign_salesperson = fields.Boolean(compute="_compute_can_assign_salesperson")
    can_assign_quotation_specialist = fields.Boolean(
        compute="_compute_can_assign_quotation_specialist"
    )
    product_pricing_line_count = fields.Integer(
        string="Product Pricing", compute="_compute_price_origin_counts",
        groups="sale_order_product_pricing.product_pricing_group"
    )
    odoo_pricelist_line_count = fields.Integer(
        string="Odoo Price List", compute="_compute_price_origin_counts",
        groups="sale_order_product_pricing.product_pricing_group"
    )
    edited_price_line_count = fields.Integer(
        string="Edited", compute="_compute_price_origin_counts",
        groups="sale_order_product_pricing.product_pricing_group"
    )

    def _is_quotation_specialist(self):
        return self.env.is_superuser() or self.env.user.has_group(
            "sale_order_product_pricing.quotation_specialist_group"
        ) or self.env.user.has_group("sales_team.group_sale_manager")

    @api.depends_context("uid")
    def _compute_can_edit_quotation_price(self):
        can_edit = self.env.user.has_group(
            "sale_order_product_pricing.product_pricing_group"
        ) or self.env.user.has_group("sales_team.group_sale_manager")
        for order in self:
            order.can_edit_quotation_price = can_edit

    @api.depends_context("uid")
    def _compute_can_assign_salesperson(self):
        can_assign = self._is_quotation_specialist()
        for order in self:
            order.can_assign_salesperson = can_assign

    @api.depends_context("uid")
    def _compute_can_assign_quotation_specialist(self):
        can_assign = self.env.is_superuser() or self.env.user.has_group(
            "sales_team.group_sale_manager"
        )
        for order in self:
            order.can_assign_quotation_specialist = can_assign

    def _ensure_price_editor_access(self):
        if not self.env.is_superuser() and not self.env.user.has_group(
                "sale_order_product_pricing.product_pricing_group") and not self.env.user.has_group(
                "sales_team.group_sale_manager"):
            raise AccessError(_("Price Editor access is required for this change."))

    @api.depends("order_line.price_origin")
    def _compute_price_origin_counts(self):
        for order in self:
            origins = order.order_line.filtered(
                lambda line: not line.display_type and not line.is_downpayment
            ).mapped("price_origin")
            order.product_pricing_line_count = origins.count("product_pricing")
            order.odoo_pricelist_line_count = origins.count("pricelist")
            order.edited_price_line_count = origins.count("edited")

    def _ensure_pricing_editable(self):
        if self.filtered(lambda order: order.state != "draft"):
            raise UserError(_("Pricing is locked after a quotation has been sent or confirmed."))

    def _ensure_product_pricing_access(self):
        if not self.env.is_superuser() and not self.env.user.has_group(
                "sale_order_product_pricing.product_pricing_group"):
            raise AccessError(_("Product Pricing access is required for this action."))

    def write(self, vals):
        vals = dict(vals)
        if (
                "user_id" in vals
                and self.env.user.has_group(
                    "sale_order_product_pricing.quotation_specialist_group"
                )
                and not self.env.user.has_group("sales_team.group_sale_manager")
                and all(not order.quotation_specialist_id for order in self)):
            # Backfill legacy draft quotations before moving Salesperson ownership
            # away from the specialist who originally prepared them.
            vals.setdefault("quotation_specialist_id", self.env.user.id)
        if vals.get("state") == "draft" and not self.env.is_superuser() and self.filtered(
                lambda order: order.state != "draft"):
            raise UserError(_(
                "A sent, confirmed, cancelled, or superseded quotation cannot be reopened. "
                "Create a new draft revision instead."
            ))
        if _ORDER_STATE_LOCKED_FIELDS.intersection(vals):
            self._ensure_pricing_editable()
        editor_fields = (_ORDER_PRICING_FIELDS - {"order_line"}).intersection(vals)
        if editor_fields:
            self._ensure_price_editor_access()
        if "user_id" in vals:
            if not self._is_quotation_specialist():
                raise AccessError(_("Only Quotation Specialists can change the Salesperson."))
            if self.filtered(lambda order: order.state != "draft"):
                raise UserError(
                    _("The Salesperson can only be changed on a draft quotation or revision.")
                )
        if "quotation_specialist_id" in vals and not self.env.is_superuser() and not (
                self.env.user.has_group("sales_team.group_sale_manager")
                or vals["quotation_specialist_id"] == self.env.user.id):
            raise AccessError(_(
                "Only Sales Managers may assign another Quotation Specialist."
            ))
        if "quotation_specialist_id" in vals and self.filtered(
                lambda order: order.state != "draft"):
            raise UserError(_(
                "The Quotation Specialist can only be changed on a draft quotation or revision."
            ))
        return super().write(vals)

    def action_preview_product_pricing(self):
        self._ensure_product_pricing_access()
        self._ensure_pricing_editable()
        return super().action_preview_product_pricing()

    def action_apply_product_pricing(self):
        self._ensure_product_pricing_access()
        self._ensure_pricing_editable()
        return super().action_apply_product_pricing()

    def apply_estimate_product_price(self):
        self._ensure_product_pricing_access()
        self._ensure_pricing_editable()
        return super().apply_estimate_product_price()

    def get_product_pricing_preview(self):
        self._ensure_product_pricing_access()
        self._ensure_pricing_editable()
        return super().get_product_pricing_preview()


class SaleOrderLine(models.Model):
    _inherit = "sale.order.line"

    can_edit_quoted_price = fields.Boolean(compute="_compute_can_edit_quoted_price")
    price_origin_display = fields.Html(
        string="Price Origin", compute="_compute_price_origin_display", readonly=True,
        sanitize=False, groups="sale_order_product_pricing.product_pricing_group"
    )

    @api.depends_context("uid")
    def _compute_can_edit_quoted_price(self):
        can_edit = self.env.user.has_group(
            "sale_order_product_pricing.product_pricing_group"
        ) or self.env.user.has_group("sales_team.group_sale_manager")
        for line in self:
            line.can_edit_quoted_price = can_edit

    @api.depends("price_origin")
    def _compute_price_origin_display(self):
        origin_markup = {
            "product_pricing": '<span class="text-success"><i class="fa fa-calculator"></i> <i class="fa fa-check"></i> Product Pricing</span>',
            "pricelist": '<span class="text-warning"><i class="fa fa-tag"></i> Odoo Price List</span>',
            "edited": '<span><i class="fa fa-pencil"></i> Edited</span>',
        }
        for line in self:
            line.price_origin_display = origin_markup.get(
                line.price_origin, '<span class="text-muted">Unknown</span>'
            )

    def write(self, vals):
        if _LINE_PRICING_FIELDS.intersection(vals):
            locked_lines = self.filtered(
                lambda line: line.order_id.state != "draft"
            )
            if locked_lines:
                raise UserError(
                    _("Pricing is locked after the related quotation has been sent or confirmed.")
                )
        if {"discount", "discount_2", "discount_3"}.intersection(vals):
            if not _is_pricing_internal(self.env):
                self.order_id._ensure_price_editor_access()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        genuine_downpayment = _is_pricing_downpayment(self.env)
        protected_values = [
            values for values in vals_list
            if not (values.get("is_downpayment") and genuine_downpayment)
        ]
        order_ids = {
            values.get("order_id") for values in protected_values if values.get("order_id")
        }
        locked_orders = self.env["sale.order"].browse(list(order_ids)).filtered(
            lambda order: order.state != "draft"
        )
        if locked_orders:
            raise UserError(_("Quotation lines cannot be added after the quotation has been sent or confirmed."))
        return super().create(vals_list)

    def unlink(self):
        if self.filtered(lambda line: line.order_id.state != "draft"):
            raise UserError(_("Quotation lines cannot be removed after the quotation has been sent or confirmed."))
        return super().unlink()
