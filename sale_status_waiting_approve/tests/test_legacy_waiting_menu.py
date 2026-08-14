# -*- coding: utf-8 -*-

from odoo.tests.common import TransactionCase


class TestLegacyWaitingMenu(TransactionCase):
    def test_disabled_menu_is_valid_on_fresh_install(self):
        """The retired menu must load as an inactive, named record."""
        menu = self.env.ref(
            'sale_status_waiting_approve.menu_sale_order_waiting_approve'
        )
        self.assertTrue(menu.name)
        self.assertFalse(menu.active)
