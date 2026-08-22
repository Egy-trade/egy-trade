# -*- coding: utf-8 -*-
from types import SimpleNamespace

from odoo.tests import TransactionCase


class TestRunBuyWithoutPositiveQuantities(TransactionCase):
    """Regression test for stock.rule._run_buy batch safety.

    When every procurement quantity of a domain group is non-positive (MTO
    cancel / reset-to-quotation flows), no RFQ may be created and the line
    grouping must degrade to "no candidates". The override used to keep a
    plain Python list in ``po``, crashing with
    AttributeError: 'list' object has no attribute 'order_line'.
    """

    def _procurement(self, product, uom, qty):
        Procurement = self.env['procurement.group'].Procurement
        return Procurement(
            product_id=product,
            product_qty=qty,
            product_uom=uom,
            location_id=self.env['stock.warehouse'].search([], limit=1).lot_stock_id,
            name='runbuy-regression',
            origin='runbuy-regression',
            company_id=self.env.company,
            values={
                'date_planned': '2026-01-01 12:00:00',
                'warehouse_id': self.env['stock.warehouse'].search([], limit=1),
            },
        )

    def test_only_nonpositive_quantities_creates_nothing(self):
        partner = self.env['res.partner'].create({'name': 'RunBuy Vendor'})
        product = self.env['product.product'].create({
            'name': 'RunBuy Storable',
            'type': 'product',
            'seller_ids': [(0, 0, {
                'partner_id': partner.id,
                'min_qty': 0.0,
                'price': 5.0,
            })],
        })

        def make_domain(*args, **kwargs):
            return ('custom-runbuy-test-domain',)

        rule = SimpleNamespace(
            propagate_cancel=False,
            _make_po_get_domain=make_domain,
        )
        procurements = [
            (self._procurement(product, product.uom_id, qty), rule)
            for qty in (-3.0, -1.0)
        ]

        self.env['stock.rule']._run_buy(procurements)

        self.assertFalse(
            self.env['purchase.order'].search(
                [('origin', '=', 'runbuy-regression')]),
            'no RFQ may be created when every quantity is non-positive',
        )
