# -*- coding: utf-8 -*-
from odoo import fields
from odoo.tests import TransactionCase


class TestSaleOrderCreateBatching(TransactionCase):
    """Regression coverage for the batched sale.order create-path helpers.

    The follower-user compute and the SO-line name propagation used to issue
    one search per order / per line; they now use one search for the whole
    recordset. These tests pin the resulting stored values so the batching
    cannot silently change semantics.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.admin_user = cls.env.ref('base.user_admin')
        cls.partner = cls.env['res.partner'].create({'name': 'Batching Partner'})

    def _create_orders(self, count=2):
        return self.env['sale.order'].create([
            {'partner_id': self.partner.id} for _ in range(count)
        ])

    def test_batch_create_stores_follower_users_per_order(self):
        orders = self._create_orders(2)
        self.assertEqual(len(orders), 2)

        admin_partner = self.admin_user.partner_id
        for order in orders:
            order.message_subscribe(partner_ids=[admin_partner.id])

        self.env['sale.order'].invalidate_model(['follower_user_ids'])
        for order in orders:
            self.assertIn(self.admin_user, order.follower_user_ids)

        extra_user = self.env['res.users'].create({
            'name': 'Extra Batching Follower',
            'login': 'egy_batch_extra_follower',
        })
        orders[0].message_subscribe(partner_ids=[extra_user.partner_id.id])
        self.env['sale.order'].invalidate_model(['follower_user_ids'])
        self.assertIn(extra_user, orders[0].follower_user_ids)
        self.assertNotIn(extra_user, orders[1].follower_user_ids)

    def _count_queries(self, func):
        """Run func and return the number of executed SQL queries."""
        counter = []
        original_execute = self.env.cr.execute

        def counted(*args, **kwargs):
            counter.append(1)
            return original_execute(*args, **kwargs)

        self.env.cr.execute = counted
        try:
            func()
            self.env.flush_all()
        finally:
            self.env.cr.execute = original_execute
        return len(counter)

    def test_batch_creation_uses_fewer_queries_than_sequential(self):
        """The batched helpers must save per-record searches.

        Creating N orders in ONE create() call groups the follower-user
        resolution into a single res.users search, so it must execute fewer
        queries than N separate creates measured identically.
        """
        partners = self.env['res.partner'].create([
            {'name': 'Query Batch Partner %s' % i} for i in range(6)
        ])
        self.env.flush_all()
        self.env.invalidate_all()

        def sequential():
            for i in range(3):
                self.env['sale.order'].create({'partner_id': partners[i].id})

        def batched():
            self.env['sale.order'].create([
                {'partner_id': partner.id} for partner in partners[3:6]
            ])

        sequential_count = self._count_queries(sequential)
        self.env.invalidate_all()
        batched_count = self._count_queries(batched)
        self.assertLess(
            batched_count, sequential_count,
            'batch creation (%s queries) must beat sequential creation '
            '(%s queries): the follower-user compute must not run one '
            'res.users search per order' % (batched_count, sequential_count),
        )

    def test_line_name_propagates_to_linked_purchase_lines(self):
        order = self._create_orders(1)
        line_note = self.env['sale.order.line'].create({
            'order_id': order.id,
            'display_type': 'line_note',
            'name': 'ORIGINAL NOTE',
        })
        purchase_order = self.env['purchase.order'].create({
            'partner_id': self.partner.id,
        })
        purchase_line = self.env['purchase.order.line'].create({
            'order_id': purchase_order.id,
            'name': 'ORIGINAL NOTE',
            'product_qty': 1.0,
            'product_uom': self.env.ref('uom.product_uom_unit').id,
            'price_unit': 1.0,
            'date_planned': purchase_order.date_order or fields.Datetime.now(),
            'sale_line_id': line_note.id,
        })

        line_note.write({'name': 'RENAMED NOTE'})
        self.assertEqual(purchase_line.name, 'RENAMED NOTE')
