# -*- coding: utf-8 -*-

from datetime import timedelta

from lxml import etree

from odoo import fields
from odoo.exceptions import UserError, ValidationError
from odoo.tests.common import SavepointCase

from ..models.sale_order_offer_dates import _OFFER_DATE_INTERNAL_TOKEN


class TestOfferExpiry(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref("base.res_partner_1")
        cls.company = cls.env.company
        cls.original_default_days = cls.company.quotation_expiry_days_default
        cls.company.quotation_expiry_days_default = 30

    @classmethod
    def tearDownClass(cls):
        cls.company.quotation_expiry_days_default = cls.original_default_days
        super().tearDownClass()

    def _order(self, **values):
        defaults = {"partner_id": self.partner.id}
        defaults.update(values)
        return self.env["sale.order"].create(defaults)

    def test_order_column_default_is_schema_safe(self):
        field = self.env["sale.order"]._fields["offer_expiry_days"]
        self.assertEqual(field.default(self.env["sale.order"]), 30)

    def test_default_get_uses_company_setting_and_preserves_context_default(self):
        self.company.quotation_expiry_days_default = 14
        defaults = self.env["sale.order"].default_get(["offer_expiry_days"])
        self.assertEqual(defaults["offer_expiry_days"], 14)
        context_defaults = (
            self.env["sale.order"].with_context(default_offer_expiry_days=9)
            .default_get(["offer_expiry_days"])
        )
        self.assertEqual(context_defaults["offer_expiry_days"], 9)

    def test_create_uses_company_default_and_timezone_business_date(self):
        self.company.quotation_expiry_days_default = 14
        order = self.env["sale.order"].with_context(
            tz="Pacific/Kiritimati"
        ).create({"partner_id": self.partner.id})
        expected_offer_date = fields.Date.context_today(order)

        self.assertEqual(order.offer_expiry_days, 14)
        self.assertEqual(order.offer_date, expected_offer_date)
        displayed_date_order = fields.Date.to_date(
            fields.Datetime.context_timestamp(order, order.date_order)
        )
        self.assertEqual(displayed_date_order, expected_offer_date)
        self.assertEqual(
            order.validity_date,
            expected_offer_date + timedelta(days=14),
        )

    def test_draft_save_refreshes_offer_date_and_expiration(self):
        order = self._order(offer_expiry_days=10)
        old_offer_date = fields.Date.context_today(order) - timedelta(days=5)
        order.with_context(
            _offer_date_internal_token=_OFFER_DATE_INTERNAL_TOKEN
        ).write({
            "offer_date": old_offer_date,
            "validity_date": old_offer_date + timedelta(days=1),
        })

        order.write({"note": "Explicit draft save"})
        expected_offer_date = fields.Date.context_today(order)
        self.assertEqual(order.offer_date, expected_offer_date)
        self.assertEqual(fields.Date.to_date(order.date_order), expected_offer_date)
        self.assertEqual(
            order.validity_date,
            expected_offer_date + timedelta(days=10),
        )

    def test_per_quotation_days_recomputes_expiration_on_save(self):
        order = self._order(offer_expiry_days=5)
        order.write({"offer_expiry_days": 21})

        self.assertEqual(order.offer_expiry_days, 21)
        self.assertEqual(
            order.validity_date,
            order.offer_date + timedelta(days=21),
        )

    def test_zero_days_expires_on_offer_date(self):
        order = self._order(offer_expiry_days=0)
        self.assertEqual(order.validity_date, order.offer_date)

    def test_negative_days_are_rejected(self):
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self._order(offer_expiry_days=-1)
        with self.assertRaises(ValidationError):
            with self.env.cr.savepoint():
                self.company.quotation_expiry_days_default = -1

    def test_sent_quotation_dates_are_immutable(self):
        order = self._order(offer_expiry_days=7)
        original = (
            order.offer_date,
            order.offer_expiry_days,
            order.date_order,
            order.validity_date,
        )
        order.write({"state": "sent"})

        with self.assertRaises(UserError):
            order.write({"offer_expiry_days": 10})
        with self.assertRaises(UserError):
            order.write({
                "offer_date": order.offer_date + timedelta(days=1),
            })
        self.assertEqual(
            (
                order.offer_date,
                order.offer_expiry_days,
                order.date_order,
                order.validity_date,
            ),
            original,
        )

    def test_archived_draft_dates_are_immutable(self):
        order = self._order()
        if "active" not in order._fields:
            self.skipTest("Revision history module is not installed.")
        order.write({"active": False})
        with self.assertRaises(UserError):
            order.with_context(active_test=False).write({
                "offer_expiry_days": 15,
            })

    def test_draft_copy_gets_fresh_dates_and_preserves_days(self):
        source = self._order(offer_expiry_days=8)
        old_offer_date = fields.Date.context_today(source) - timedelta(days=7)
        source.with_context(
            _offer_date_internal_token=_OFFER_DATE_INTERNAL_TOKEN
        ).write({
            "offer_date": old_offer_date,
            "validity_date": old_offer_date + timedelta(days=1),
        })

        copied = source.copy()
        expected_offer_date = fields.Date.context_today(copied)
        self.assertEqual(copied.offer_expiry_days, 8)
        self.assertEqual(copied.offer_date, expected_offer_date)
        self.assertEqual(
            copied.validity_date,
            expected_offer_date + timedelta(days=8),
        )

    def test_offer_fields_are_visible_and_system_managed(self):
        view = self.env.ref(
            "sale_order_product_pricing.sale_order_offer_expiry_form"
        )
        root = etree.fromstring(view.arch_db.encode())
        self.assertEqual(
            root.xpath("//field[@name='offer_date']/@readonly"),
            ["1"],
        )
        self.assertEqual(
            root.xpath("//field[@name='offer_expiry_days']/@string"),
            ["Days of Expiry"],
        )
        self.assertEqual(
            root.xpath(
                "//field[@name='validity_date']/"
                "attribute[@name='string']/text()"
            ),
            ["Expiration Date"],
        )
        self.assertEqual(
            root.xpath(
                "//field[@name='validity_date']/"
                "attribute[@name='readonly']/text()"
            ),
            ["1"],
        )
