# -*- coding: utf-8 -*-
from odoo.tests import TransactionCase


class TestBatchCreateCurrencyRate(TransactionCase):
    """Regression coverage for batch sale.order creation.

    The create override used to be single-record only: a list input crashed
    with AttributeError (``list.get``) and a missing currency id crashed on
    ``max()`` over an empty rate set. It must now handle batches and fall back
    to the company currency while storing the same rate snapshot.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partners = cls.env['res.partner'].create([
            {'name': 'Currency Batch Partner 1'},
            {'name': 'Currency Batch Partner 2'},
        ])

    def test_batch_create_without_currency_id(self):
        orders = self.env['sale.order'].create([
            {'partner_id': self.partners[0].id},
            {'partner_id': self.partners[1].id},
        ])
        self.assertEqual(len(orders), 2)
        for order in orders:
            self.assertEqual(order.currency_id, self.env.company.currency_id)
            self.assertTrue(order.currency_rate_confirm)

    def test_single_create_with_explicit_currency(self):
        order = self.env['sale.order'].create({
            'partner_id': self.partners[0].id,
            'currency_id': self.env.company.currency_id.id,
        })
        rates = order.currency_id.rate_ids
        expected = rates.filtered(
            lambda l: l.name == max([x.name for x in rates])
        ).inverse_company_rate
        self.assertEqual(float(order.currency_rate_confirm), float(expected))
