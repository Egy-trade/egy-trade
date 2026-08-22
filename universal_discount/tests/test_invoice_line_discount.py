# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestInvoiceLineDiscountPreserved(TransactionCase):
    """Regression tests for account.move.line.discount writability.

    universal_discount used to redefine ``discount`` as a plain non-stored
    computed field (from discount_1/discount_2 only), so any explicitly
    provided discount was silently discarded at creation: upstream
    TestAccountJournalDashboard.test_customer_invoice_dashboard received
    $77.50 instead of $68.42 because its 10% line discount vanished.
    """

    def _create_invoice_line(self, **line_vals):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'invoice_date': '2019-01-21',
            'invoice_line_ids': [(0, 0, dict({
                'name': 'discount regression line',
                'tax_ids': [],
            }, **line_vals))],
        })
        return move.invoice_line_ids.filtered(
            lambda l: l.display_type == 'product')

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create(
            {'name': 'Discount Regression Partner'})

    def test_explicit_discount_survives_creation(self):
        """The exact upstream dashboard-test amounts."""
        line = self._create_invoice_line(
            quantity=40.0,
            price_unit=2.27,
            discount=10.0,
        )
        self.assertAlmostEqual(line.discount, 10.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 81.72, places=6)
        self.assertAlmostEqual(line.move_id.amount_untaxed, 81.72, places=6)

    def test_zero_discount_stays_zero(self):
        line = self._create_invoice_line(quantity=1.0, price_unit=13.3)
        self.assertAlmostEqual(line.discount, 0.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 13.3, places=6)

    def test_universal_discount_fields_still_drive_discount(self):
        """The module's own feature must keep working."""
        line = self._create_invoice_line(quantity=1.0, price_unit=100.0)
        line.discount_1 = 20.0
        self.env['account.move.line'].invalidate_model(['discount'])
        self.assertAlmostEqual(line.discount, 20.0, places=6)
        self.assertAlmostEqual(line.price_subtotal, 80.0, places=6)
