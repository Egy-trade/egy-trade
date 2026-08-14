# -*- coding: utf-8 -*-
"""Retire legacy sale.order approval states without deleting any quotations."""


def migrate(cr, version):
    if not version:
        return

    from odoo import SUPERUSER_ID
    from odoo.api import Environment

    env = Environment(cr, SUPERUSER_ID, {})
    cr.execute(
        "SELECT id, state FROM sale_order "
        "WHERE state IN ('approve', 'waiting', 'waiting_approve')"
    )
    retired = cr.fetchall()
    if not retired:
        return

    ids = [row[0] for row in retired]
    old_state_by_id = dict(retired)
    cr.execute("UPDATE sale_order SET state = 'draft' WHERE id = ANY(%s)", [ids])
    orders = env['sale.order'].browse(ids)
    orders.invalidate_cache(['state'])
    for order in orders:
        order.message_post(
            body=(
                'Phase 1 workflow migration: legacy quotation state "%(state)s" '
                'was mapped to Draft. Approval evidence is now separate from '
                'the Sales Order state.'
            ) % {'state': old_state_by_id[order.id]},
            subtype_xmlid='mail.mt_note',
        )
