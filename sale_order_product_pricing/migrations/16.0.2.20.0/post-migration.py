# -*- coding: utf-8 -*-
"""Map active quotation drafts from their actual configured line taxes.

Sent offers, sales orders, invoices and accounting documents are deliberately
left untouched.  Ambiguous active drafts remain available but are flagged for
commercial review rather than guessing a tax policy.
"""


def migrate(cr, version):
    if not version:
        return
    from odoo import SUPERUSER_ID
    from odoo.api import Environment
    from odoo.addons.sale_order_product_pricing.models.finance_controls import _FINANCE_INTERNAL_TOKEN

    env = Environment(cr, SUPERUSER_ID, {})
    draft_domain = [('state', '=', 'draft')]
    # ``active`` is added by the optional revision-history module.  Pricing
    # must remain independently upgradeable on databases that do not install
    # that extension.
    if 'active' in env['sale.order']._fields:
        draft_domain.append(('active', '=', True))
    drafts = env['sale.order'].with_context(active_test=False).search(draft_domain)
    for order in drafts:
        configured = order.company_id.quotation_vat_tax_id | order.company_id.quotation_retention_tax_id
        lines = order.order_line.filtered(lambda line: not line.display_type)
        actual = set(tuple(sorted(line.tax_id.ids)) for line in lines)
        if len(actual) != 1:
            order.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
                'tax_selection_review_required': True,
            })
            continue
        tax_ids = env['account.tax'].browse(next(iter(actual), ()))
        if tax_ids - configured:
            order.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
                'tax_selection_review_required': True,
            })
            continue
        has_vat = bool(
            order.company_id.quotation_vat_tax_id
            and order.company_id.quotation_vat_tax_id in tax_ids
        )
        order.with_context(_finance_internal_token=_FINANCE_INTERNAL_TOKEN).write({
            'apply_vat': has_vat,
            'apply_withholding': bool(order.company_id.quotation_retention_tax_id and order.company_id.quotation_retention_tax_id in tax_ids),
            # Tax-free legacy drafts need a human to confirm a genuine VAT
            # exemption and record its reason; migration must never infer one.
            'tax_selection_review_required': not has_vat,
        })
