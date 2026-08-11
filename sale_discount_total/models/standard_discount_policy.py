# -*- coding: utf-8 -*-
"""Company and user policy for the ordinary quotation-line discount.

The policy intentionally lives with the existing sales-discount configuration.
``sale_order_product_pricing`` consumes it when this module is installed, but
keeps a legacy fallback for databases which have not installed this add-on yet.
"""

from odoo import _, api, fields, models
from odoo.exceptions import AccessError, ValidationError


MAX_STANDARD_DISCOUNT = 30.0


class ResCompany(models.Model):
    _inherit = "res.company"

    standard_discount_enabled = fields.Boolean(
        string="Enable Standard Discount",
        default=True,
        help=(
            "Allow the ordinary Discount % field on verified pricelist lines. "
            "When disabled, nobody can apply a Standard Discount."
        ),
    )
    standard_discount_maximum = fields.Float(
        string="Maximum Standard Discount",
        default=MAX_STANDARD_DISCOUNT,
        help=(
            "Company hard ceiling for Standard Discount. It can never be more "
            "than 30%, including a manager override."
        ),
    )
    standard_discount_default_cap = fields.Float(
        string="Default Personal Discount Cap",
        default=MAX_STANDARD_DISCOUNT,
        help=(
            "Starting Standard Discount limit for a newly created internal user. "
            "Management may set a lower personal cap per user."
        ),
    )
    # Compatibility name for controls that were introduced alongside this
    # policy. The canonical UI/configuration field remains the clearer
    # ``standard_discount_maximum``.
    standard_discount_cap = fields.Float(
        related="standard_discount_maximum", readonly=False,
        string="Standard Discount Cap",
    )

    @api.constrains("standard_discount_maximum", "standard_discount_default_cap")
    def _check_standard_discount_limits(self):
        for company in self:
            for value, label in (
                (company.standard_discount_maximum, _("Maximum Standard Discount")),
                (company.standard_discount_default_cap, _("Default Personal Discount Cap")),
            ):
                if value < 0 or value > MAX_STANDARD_DISCOUNT:
                    raise ValidationError(_(
                        "%(label)s must be between 0%% and %(maximum)s%%."
                    ) % {"label": label, "maximum": MAX_STANDARD_DISCOUNT})
            if company.standard_discount_default_cap > company.standard_discount_maximum:
                raise ValidationError(_(
                    "Default Personal Discount Cap cannot exceed Maximum Standard Discount."
                ))


class ResUsers(models.Model):
    _inherit = "res.users"

    standard_discount_cap = fields.Float(
        string="Personal Standard Discount Cap",
        default=lambda self: self.env.company.standard_discount_default_cap,
        help=(
            "Maximum Standard Discount this user may apply without a manager "
            "override. The company maximum still applies."
        ),
    )

    def _can_manage_standard_discount_caps(self):
        user = self.env.user
        quotation_manager = self.env.ref(
            "sale_order_product_pricing.quotation_manager_group",
            raise_if_not_found=False,
        )
        return (
            self.env.is_superuser()
            or user.has_group("base.group_system")
            or user.has_group("sales_team.group_sale_manager")
            or (quotation_manager and quotation_manager in user.groups_id)
        )

    @api.constrains("standard_discount_cap")
    def _check_standard_discount_cap(self):
        for user in self:
            if user.standard_discount_cap < 0 or user.standard_discount_cap > MAX_STANDARD_DISCOUNT:
                raise ValidationError(_(
                    "Personal Standard Discount Cap must be between 0% and 30%."
                ))

    @api.model_create_multi
    def create(self, vals_list):
        if any("standard_discount_cap" in vals for vals in vals_list) and not self._can_manage_standard_discount_caps():
            raise AccessError(_(
                "Only authorized quotation or sales management may set a personal discount cap."
            ))
        return super().create(vals_list)

    def write(self, vals):
        if "standard_discount_cap" in vals and not self._can_manage_standard_discount_caps():
            raise AccessError(_(
                "Only authorized quotation or sales management may change a personal discount cap."
            ))
        return super().write(vals)


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    standard_discount_enabled = fields.Boolean(
        related="company_id.standard_discount_enabled", readonly=False,
    )
    standard_discount_maximum = fields.Float(
        related="company_id.standard_discount_maximum", readonly=False,
    )
    standard_discount_default_cap = fields.Float(
        related="company_id.standard_discount_default_cap", readonly=False,
    )
