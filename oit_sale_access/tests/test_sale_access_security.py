# -*- coding: utf-8 -*-

from odoo.exceptions import AccessError
from odoo.tests import TransactionCase


class TestSaleOrderAccessBoundary(TransactionCase):
    """Regression tests for the oit_sale_access ACL / record-rule boundary.

    The two ir.model.access rows of this module grant read-only access to
    sale.order and sale.order.line and must apply only to members of the
    group_sale_order_limit_access_for_designer_and_technical_sales_offices
    group, whose record rules then restrict reads to assigned records.

    Both test users are isolated on purpose: they hold no sales group, so any
    model access they have must come from this module's group-bound ACLs.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.limit_group = cls.env.ref(
            'oit_sale_access.'
            'group_sale_order_limit_access_for_designer_and_technical_sales_offices'
        )
        cls.limited_user = cls.env['res.users'].create({
            'name': 'Limit Group User',
            'login': 'acl_limit_group_user',
            'groups_id': [(6, 0, [
                cls.env.ref('base.group_user').id,
                cls.limit_group.id,
            ])],
        })
        cls.outsider_user = cls.env['res.users'].create({
            'name': 'No Sale Access User',
            'login': 'acl_no_sale_access_user',
            'groups_id': [(6, 0, [cls.env.ref('base.group_user').id])],
        })
        cls.partner = cls.env['res.partner'].create({
            'name': 'ACL Boundary Partner',
        })
        cls.product = cls.env['product.product'].create({
            'name': 'ACL Boundary Product',
        })
        cls.own_order = cls._create_order(cls.limited_user)
        cls.outsider_order = cls._create_order(cls.outsider_user)
        cls.other_order = cls._create_order(cls.env.ref('base.user_admin'))

    @classmethod
    def _create_order(cls, salesperson):
        return cls.env['sale.order'].create({
            'partner_id': cls.partner.id,
            'user_id': salesperson.id,
            'order_line': [(0, 0, {
                'product_id': cls.product.id,
                'product_uom_qty': 1.0,
            })],
        })

    def _applicable_acls(self, user, model_name):
        """Every ACL Odoo would evaluate for ``user`` on ``model_name``."""
        return self.env['ir.model.access'].sudo().search([
            ('model_id.model', '=', model_name),
        ]).filtered(
            lambda acl: not acl.group_id or acl.group_id in user.groups_id
        )

    def test_module_acls_are_bound_to_limit_group_and_read_only(self):
        for xmlid in (
            'oit_sale_access.sale_order_id',
            'oit_sale_access.sale_order_line_id',
        ):
            acl = self.env.ref(xmlid)
            self.assertEqual(
                acl.group_id,
                self.limit_group,
                '%s must be bound to %s' % (xmlid, self.limit_group.name),
            )
            self.assertEqual(
                (acl.perm_read, acl.perm_write, acl.perm_create, acl.perm_unlink),
                (True, False, False, False),
                '%s must stay read-only' % xmlid,
            )

    def test_limited_user_model_access_comes_only_from_limit_group(self):
        for model_name in ('sale.order', 'sale.order.line'):
            applicable = self._applicable_acls(self.limited_user, model_name)
            self.assertTrue(
                applicable,
                'isolated user should get sale access from the limit group ACLs',
            )
            self.assertEqual(
                applicable.mapped('group_id'),
                self.limit_group,
                'no other ACL than the limit-group one may apply to %s'
                % model_name,
            )

    def test_outsider_has_no_applicable_sale_acl(self):
        for model_name in ('sale.order', 'sale.order.line'):
            self.assertFalse(
                self._applicable_acls(self.outsider_user, model_name),
                'a non-member of the limit group must not inherit any '
                'sale.order/sale.order.line ACL',
            )

    def test_limited_user_reads_assigned_order_and_lines(self):
        order_values = self.own_order.with_user(
            self.limited_user
        ).read(['name'])
        self.assertEqual(len(order_values), 1)
        self.assertEqual(order_values[0]['id'], self.own_order.id)
        self.assertTrue(
            self.own_order.order_line.with_user(self.limited_user).read(['id'])
        )

    def test_limited_user_cannot_read_unrelated_order_and_lines(self):
        with self.assertRaises(AccessError):
            self.other_order.with_user(self.limited_user).read(['name'])
        with self.assertRaises(AccessError):
            self.other_order.order_line.with_user(
                self.limited_user
            ).read(['id'])

    def test_outsider_cannot_read_even_own_assigned_order(self):
        with self.assertRaises(AccessError):
            self.outsider_order.with_user(self.outsider_user).read(['name'])

    def test_limited_user_cannot_write_assigned_records(self):
        with self.assertRaises(AccessError):
            self.own_order.with_user(self.limited_user).write({
                'client_order_ref': 'acl-test-write',
            })
        own_line = self.own_order.order_line
        with self.assertRaises(AccessError):
            own_line.with_user(self.limited_user).write({'product_uom_qty': 2.0})

    def test_limited_user_cannot_unlink_assigned_records(self):
        with self.assertRaises(AccessError):
            self.own_order.with_user(self.limited_user).unlink()
        with self.assertRaises(AccessError):
            self.own_order.order_line.with_user(self.limited_user).unlink()

    def test_limited_user_cannot_create_orders_or_lines(self):
        Order = self.env['sale.order'].with_user(self.limited_user)
        with self.assertRaises(AccessError):
            Order.create({'partner_id': self.partner.id})
        OrderLine = self.env['sale.order.line'].with_user(self.limited_user)
        with self.assertRaises(AccessError):
            OrderLine.create({
                'order_id': self.own_order.id,
                'product_id': self.product.id,
            })
