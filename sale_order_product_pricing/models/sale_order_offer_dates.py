# -*- coding: utf-8 -*-
"""System-managed offer and expiration dates for quotations."""

from datetime import timedelta

from odoo import _, api, fields, models
from odoo.exceptions import UserError, ValidationError

from .sale_order import _is_pricing_internal


_OFFER_DATE_INTERNAL_TOKEN = object()


def _is_offer_date_internal(env):
    """Allow only this module's own date refresh to avoid recursion."""
    return env.context.get(
        "_offer_date_internal_token"
    ) is _OFFER_DATE_INTERNAL_TOKEN


class ResCompany(models.Model):
    _inherit = "res.company"

    quotation_expiry_days_default = fields.Integer(
        string="Default Days of Expiry",
        default=14,
        help=(
            "Default number of days between Offer Date and Expiration Date "
            "for newly created quotations."
        ),
    )

    @api.constrains("quotation_expiry_days_default")
    def _check_quotation_expiry_days_default(self):
        for company in self:
            if company.quotation_expiry_days_default < 0:
                raise ValidationError(_("Default Days of Expiry cannot be negative."))


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    quotation_expiry_days_default = fields.Integer(
        related="company_id.quotation_expiry_days_default",
        readonly=False,
    )


class SaleOrder(models.Model):
    _inherit = "sale.order"

    offer_date = fields.Date(
        string="Offer Date",
        readonly=True,
        copy=False,
        help=(
            "Commercial offer date recorded when the draft is created. Changing "
            "Days of Expiry recalculates the expiration date without refreshing the page."
        ),
    )
    offer_expiry_days = fields.Integer(
        string="Days of Expiry",
        # Keep schema initialization independent from the new company column.
        # ``create`` below still applies the selected company's configured
        # default to every newly created quotation.
        default=14,
        copy=True,
        help=(
            "Expiration Date is automatically calculated as Offer Date plus "
            "this number of days."
        ),
    )

    @api.constrains("offer_expiry_days")
    def _check_offer_expiry_days(self):
        for order in self:
            if order.offer_expiry_days < 0:

                raise ValidationError(_("Days of Expiry cannot be negative."))

    @api.model
    def default_get(self, fields_list):
        values = super().default_get(fields_list)
        if (
            "offer_expiry_days" in fields_list
            and "default_offer_expiry_days" not in self.env.context
        ):
            values["offer_expiry_days"] = (
                self.env.company.quotation_expiry_days_default
            )
        return values
    def _offer_date_values(self):
        """Return the current business date and derived expiration."""
        self.ensure_one()
        offer_date = fields.Date.context_today(self)
        return {
            "offer_date": offer_date,
            "validity_date": offer_date + timedelta(days=self.offer_expiry_days),
        }

    @api.model_create_multi
    def create(self, vals_list):
        prepared_vals = []
        for incoming in vals_list:
            vals = dict(incoming)
            company = (
                self.env["res.company"].browse(vals.get("company_id"))
                if vals.get("company_id")
                else self.env.company
            )
            days = vals.get(
                "offer_expiry_days",
                company.quotation_expiry_days_default,
            )
            if days < 0:
                raise ValidationError(_("Days of Expiry cannot be negative."))
            vals["offer_expiry_days"] = days
            if (
                vals.get("state", "draft") == "draft"
                and vals.get("active", True)
            ):
                offer_date = fields.Date.context_today(
                    self.with_company(company).with_context(tz="Africa/Cairo")
                )
                vals.update({
                    "offer_date": offer_date,
                    "validity_date": offer_date + timedelta(days=days),
                })
            prepared_vals.append(vals)
        return super().create(prepared_vals)

    def write(self, vals):
        # Preview/apply audit writes are technical pricing operations, not a
        # user save of the commercial quotation.
        if _is_offer_date_internal(self.env) or _is_pricing_internal(self.env):
            return super().write(vals)

        vals = dict(vals)
        if vals.get("offer_expiry_days", 0) < 0:
            raise ValidationError(_("Days of Expiry cannot be negative."))

        date_fields = {
            "offer_date", "offer_expiry_days", "date_order", "validity_date",
        }
        if date_fields.intersection(vals) and self.filtered(
            lambda order: not getattr(order, "active", True)
        ):
            raise UserError(_(
                "Offer and expiration dates cannot be changed on archived "
                "quotation history."
            ))

        result = super().write(vals)

        # Changing Days of Expiry recalculates only the expiration date.
        # Viewing or saving unrelated fields never mutates the offer date or
        # the standard Odoo ``date_order``.
        if "offer_expiry_days" in vals:
            for order in self.filtered(
                lambda item: item.state == "draft" and getattr(item, "active", True)
            ):
                order.with_context(
                    _offer_date_internal_token=_OFFER_DATE_INTERNAL_TOKEN
                ).write({
                    "validity_date": order.offer_date + timedelta(
                        days=order.offer_expiry_days
                    ),
                })
        return result
