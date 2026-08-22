# -*- coding: utf-8 -*-
from pathlib import Path

from odoo.tests import TransactionCase

REPORT_PATH = Path(__file__).resolve().parents[1] / 'reports' / 'delivery_receipt.xml'


class TestDeliveryReceiptReportFields(TransactionCase):
    """Regression tests for the delivery receipt report on Odoo 16.

    The template rendered ``stock.picking.move_lines``, a field removed
    before Odoo 16 (moves live in ``move_ids`` / ``move_ids_without_package``
    / ``move_line_ids``); base report rendering crashed with an invalid-field
    error. Product moves of a delivery receipt must come from
    ``move_ids_without_package``.
    """

    def test_loaded_template_has_no_removed_move_lines_field(self):
        view = self.env.ref('egy-trade_custom.report_delivery_receipt')
        self.assertNotIn(
            '.move_lines', view.arch_db,
            'stock.picking.move_lines does not exist in Odoo 16',
        )
        self.assertIn('o.move_ids_without_package', view.arch_db)

    def test_source_template_uses_odoo16_move_field(self):
        arch = REPORT_PATH.read_text(encoding='utf-8')
        self.assertNotIn('o.move_lines', arch)
        self.assertIn('o.move_ids_without_package', arch)
