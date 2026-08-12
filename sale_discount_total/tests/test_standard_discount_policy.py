# -*- coding: utf-8 -*-

from lxml import etree

from odoo.exceptions import AccessError, ValidationError
from odoo.tests.common import SavepointCase


class TestStandardDiscountPolicy(SavepointCase):
    def test_personal_cap_survives_dynamic_access_rights_view_regeneration(self):
        self.env["res.groups"]._update_user_groups_view()
        view = self.env["res.users"].fields_view_get(
            view_id=self.env.ref("base.view_users_form").id,
            view_type="form",
        )
        root = etree.fromstring(view["arch"].encode())
        self.assertEqual(
            len(root.xpath("//page[@name='access_rights']//field[@name='standard_discount_cap']")),
            1,
        )

    def test_company_limits_never_exceed_thirty_percent(self):
        with self.assertRaises(ValidationError):
            self.env.company.write({"standard_discount_maximum": 30.01})
        with self.assertRaises(ValidationError):
            self.env.company.write({"standard_discount_default_cap": -0.01})

    def test_non_manager_cannot_change_personal_cap(self):
        user = self.env["res.users"].create({
            "name": "Discount Cap User",
            "login": "discount.cap.user@example.test",
            "groups_id": [(6, 0, [self.env.ref("base.group_user").id])],
        })
        with self.assertRaises(AccessError):
            user.with_user(user).write({"standard_discount_cap": 5.0})
