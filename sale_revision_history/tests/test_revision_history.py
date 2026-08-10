# -*- coding: utf-8 -*-

from odoo import fields
from odoo.exceptions import AccessError, UserError
from odoo.tests.common import SavepointCase

from odoo.addons.sale_order_product_pricing.models.sale_order import (
    _PRICING_INTERNAL_TOKEN,
)

from ..models.sale_order import _REVISION_INTERNAL_TOKEN


class RevisionHistoryCase(SavepointCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env.ref("base.res_partner_1")
        cls.product = cls.env["product.product"].create({
            "name": "Revision history test product",
            "sale_ok": True,
            "purchase_ok": True,
            "list_price": 100.0,
            "standard_price": 40.0,
        })
        internal = cls.env.ref("base.group_user")
        salesman = cls.env.ref("sales_team.group_sale_salesman")
        specialist = cls.env.ref(
            "sale_order_product_pricing.quotation_specialist_group"
        )
        manager = cls.env.ref("sales_team.group_sale_manager")

        def make_user(name, login, groups):
            return cls.env["res.users"].create({
                "name": name,
                "login": login,
                "groups_id": [(6, 0, [group.id for group in groups])],
            })

        # Deliberately no Product Pricing or Quotation Specialist group: an
        # ordinary assigned Salesperson must still be able to make a revision.
        cls.owner = make_user(
            "Revision Owner", "revision.owner@example.test", [internal, salesman]
        )
        cls.quotation_specialist = make_user(
            "Revision Specialist", "revision.specialist@example.test",
            [internal, specialist],
        )
        cls.other_salesperson = make_user(
            "Unassigned Salesperson", "revision.other@example.test",
            [internal, salesman],
        )
        cls.sales_manager = make_user(
            "Revision Manager", "revision.manager@example.test",
            [internal, manager],
        )

    def _sent_order(self):
        order = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "user_id": self.owner.id,
            "quotation_specialist_id": self.quotation_specialist.id,
            "product_pricing": True,
            "global_factor": 1.35,
        })
        line = self.env["sale.order.line"].create({
            "order_id": order.id,
            "product_id": self.product.id,
            "name": self.product.display_name,
            "product_uom_qty": 2.0,
            "price_unit": 145.0,
            "purchase_price_estimate": 55.0,
        })
        line.with_context(
            _pricing_internal_token=_PRICING_INTERNAL_TOKEN,
        ).write({
            "price_unit": 145.0,
            "price_reference": 140.0,
            "price_origin": "edited",
            "price_currency_id": order.currency_id.id,
            "purchase_price_estimate": 55.0,
            "factor": 1.35,
            "line_factor": 1.10,
        })
        order.write({"state": "sent"})
        return order

    @staticmethod
    def _revision_from_action(env, action):
        return env["sale.order"].browse(action["res_id"])

    def test_01_owner_creates_exact_distinct_draft_without_mutating_source(self):
        source = self._sent_order()
        source_name = source.name
        source_line = source.order_line
        source_line_values = {
            field_name: source_line[field_name]
            for field_name in (
                "product_id", "product_uom_qty", "price_unit",
                "price_reference", "price_origin", "price_currency_id",
                "purchase_price_estimate", "factor", "line_factor",
            )
        }

        action = source.with_user(self.owner).action_view_revision_wizard(
            "  Customer requested a value-engineering alternative.  "
        )
        revision = self._revision_from_action(self.env, action)
        revision_line = revision.order_line

        self.assertNotEqual(revision, source)
        self.assertEqual(source.name, source_name)
        self.assertEqual(source.state, "sent")
        self.assertEqual(source.order_line, source_line)
        self.assertFalse(source.active)
        self.assertEqual(source.current_revision_id, revision)
        self.assertEqual(source.revision_reason, "Customer requested a value-engineering alternative.")
        self.assertEqual(source.revision_author_id, self.owner)
        self.assertTrue(source.revision_date)

        self.assertEqual(revision.state, "draft")
        self.assertTrue(revision.active)
        self.assertFalse(revision.current_revision_id)
        self.assertEqual(revision.revision_number, 1)
        self.assertEqual(revision.unrevisioned_name, source_name)
        self.assertEqual(revision.name, "%s-01" % source_name)
        for field_name, expected in source_line_values.items():
            self.assertEqual(revision_line[field_name], expected, field_name)
        self.assertFalse(revision.pricing_audit_log_ids)

    def test_02_assigned_specialist_and_manager_are_authorized(self):
        specialist_source = self._sent_order()
        specialist_action = specialist_source.with_user(
            self.quotation_specialist
        ).action_view_revision_wizard("Specialist correction")
        self.assertEqual(
            self._revision_from_action(self.env, specialist_action).state, "draft"
        )

        manager_source = self._sent_order()
        manager_action = manager_source.with_user(
            self.sales_manager
        ).action_view_revision_wizard("Manager correction")
        self.assertEqual(
            self._revision_from_action(self.env, manager_action).state, "draft"
        )

    def test_03_unassigned_salesperson_is_denied(self):
        source = self._sent_order()
        with self.assertRaises(AccessError):
            source.with_user(self.other_salesperson).action_view_revision_wizard(
                "Unauthorized revision"
            )
        self.assertTrue(source.active)
        self.assertEqual(source.state, "sent")

    def test_04_revision_family_is_relinked_and_newest_is_current(self):
        original = self._sent_order()
        first = self._revision_from_action(
            self.env,
            original.with_user(self.owner).action_view_revision_wizard("First change"),
        )
        first.write({"state": "sent"})
        second = self._revision_from_action(
            self.env,
            first.with_user(self.owner).action_view_revision_wizard("Second change"),
        )

        history = second.with_context(active_test=False).old_revision_ids
        self.assertEqual(set(history.ids), {original.id, first.id})
        self.assertEqual(original.current_revision_id, second)
        self.assertEqual(first.current_revision_id, second)
        self.assertEqual(first.revision_reason, "Second change")
        self.assertEqual(second.revision_number, 2)
        self.assertEqual(second.name, "%s-02" % original.name)
        self.assertTrue(all(not item.active for item in history))

        action = second.action_open_revision_history()
        self.assertEqual(set(action["domain"][0][2]), set((history | second).ids))
        self.assertEqual(action["domain"][1], ("revision_reason", "!=", False))
        self.assertEqual(
            action["search_view_id"][0],
            self.env.ref(
                "sale_revision_history.sale_order_revision_history_search"
            ).id,
        )
        self.assertFalse(action["context"]["active_test"])
        self.assertEqual(action["context"]["search_default_has_revision_comment"], 1)

    def test_05_legacy_snapshot_direction_is_reused_without_reversal(self):
        current = self._sent_order()
        internal_context = {
            "_revision_internal_token": _REVISION_INTERNAL_TOKEN,
            "_pricing_internal_token": _PRICING_INTERNAL_TOKEN,
        }
        legacy_snapshot = current.sudo().with_context(**internal_context).copy({
            "name": current.name,
            # Legacy storage is modelled in two steps so the modern sent-line
            # guard is not bypassed merely to build the fixture.
            "state": "draft",
            "active": False,
            "current_revision_id": current.id,
            "revision_number": 0,
            "unrevisioned_name": current.unrevisioned_name,
            "revision_reason": "Legacy first revision",
            "revision_date": fields.Datetime.now(),
            "revision_author_id": self.owner.id,
        })
        legacy_snapshot.sudo().with_context(**internal_context).write({
            "state": "cancel",
        })
        current.sudo().with_context(**internal_context).write({
            "revision_number": 1,
        })

        newest = self._revision_from_action(
            self.env,
            current.with_user(self.owner).action_view_revision_wizard(
                "First revision after upgrade"
            ),
        )

        self.assertEqual(legacy_snapshot.current_revision_id, newest)
        self.assertIn(legacy_snapshot, newest.with_context(active_test=False).old_revision_ids)
        self.assertFalse(legacy_snapshot.active)
        self.assertEqual(legacy_snapshot.revision_reason, "Legacy first revision")

    def test_06_only_sent_active_current_tip_and_nonblank_comment_are_accepted(self):
        sent = self._sent_order()
        with self.assertRaises(UserError):
            sent.action_view_revision_wizard("   ")

        for state in ("draft", "sale", "cancel"):
            order = self._sent_order()
            order.sudo().write({"state": state})
            with self.assertRaises(UserError):
                order.action_view_revision_wizard("Wrong state")

        old = self._sent_order()
        self._revision_from_action(
            self.env, old.action_view_revision_wizard("Superseded")
        )
        with self.assertRaises(UserError):
            old.with_context(active_test=False).action_view_revision_wizard("Again")

    def test_07_public_context_copy_and_writes_cannot_forge_revision_metadata(self):
        source = self._sent_order()
        with self.assertRaises(UserError):
            source.with_context(
                sale_revision_history=True, reason="Forged legacy context"
            ).copy()
        self.assertTrue(source.active)
        self.assertFalse(source.current_revision_id)
        self.assertFalse(source.revision_reason)

        with self.assertRaises(AccessError):
            source.write({"revision_reason": "Forged"})
        with self.assertRaises(AccessError):
            source.with_context(_revision_internal_token=True).write({
                "revision_number": 99,
            })

        created = self.env["sale.order"].create({
            "partner_id": self.partner.id,
            "revision_number": 99,
            "revision_reason": "Injected",
            "unrevisioned_name": "INJECTED",
        })
        self.assertEqual(created.revision_number, 0)
        self.assertFalse(created.revision_reason)
        self.assertNotEqual(created.unrevisioned_name, "INJECTED")

    def test_08_revision_history_cannot_be_archived_or_restored_manually(self):
        source = self._sent_order()
        revision = self._revision_from_action(
            self.env,
            source.action_view_revision_wizard("Protected history"),
        )
        with self.assertRaises(AccessError):
            source.with_context(active_test=False).write({"active": True})
        with self.assertRaises(AccessError):
            revision.write({"active": False})

    def test_09_revision_draft_can_preview_and_apply_product_pricing(self):
        source = self._sent_order()
        revision = self._revision_from_action(
            self.env,
            source.with_user(self.owner).action_view_revision_wizard(
                "Reprice the revised commercial alternative"
            ),
        )

        revision_line = revision.order_line
        copied_price = revision_line.price_unit
        revision.action_preview_product_pricing()
        revision.with_context(
            pricing_apply_confirmed=True,
        ).action_apply_product_pricing()

        self.assertEqual(revision.state, "draft")
        self.assertEqual(revision_line.price_origin, "edited")
        self.assertEqual(revision_line.price_unit, copied_price)

        # Preview/Apply only reprices after an authorized pricing input changes
        # on the draft successor; it never silently rewrites the exact copy.
        revision_line.write({"product_uom_qty": 3.0})
        self.assertTrue(revision_line.pricing_reprice_pending)
        revision.action_preview_product_pricing()
        revision.with_context(
            pricing_apply_confirmed=True,
        ).action_apply_product_pricing()
        self.assertEqual(revision_line.price_origin, "product_pricing")
        self.assertTrue(revision.pricing_audit_log_ids)

    def test_10_history_views_are_readonly_filtered_and_newest_first(self):
        tree_arch = self.env.ref(
            "sale_revision_history.sale_order_revision_history_tree"
        ).arch_db
        search_arch = self.env.ref(
            "sale_revision_history.sale_order_revision_history_search"
        ).arch_db
        form_arch = self.env.ref("sale_revision_history.sale_order_view_form").arch_db
        self.assertIn(
            'default_order="revision_number desc, revision_date desc, id desc"',
            tree_arch,
        )
        self.assertIn('name="has_revision_comment"', search_arch)
        self.assertIn('name="my_revision_comments"', search_arch)
        self.assertIn("'group_by': 'unrevisioned_name'", search_arch)
        self.assertIn("'group_by': 'revision_author_id'", search_arch)
        self.assertIn("'group_by': 'revision_date:day'", search_arch)
        self.assertIn("'group_by': 'revision_number'", search_arch)
        self.assertIn("button[@name='action_cancel'])[1]", form_arch)
        self.assertNotIn("action_quotations_with_onboarding", form_arch)
