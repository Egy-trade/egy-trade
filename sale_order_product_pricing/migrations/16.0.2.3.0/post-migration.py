# -*- coding: utf-8 -*-
"""Backfill the safe role projections without touching quotation values."""


def migrate(cr, version):
    if not version:
        return
    from odoo.api import Environment
    from odoo import SUPERUSER_ID

    env = Environment(cr, SUPERUSER_ID, {})
    orders = env["sale.order"].search([])
    orders._sync_project_directory()
    orders._sync_technical_scopes()
