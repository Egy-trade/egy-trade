# -*- coding: utf-8 -*-
import re
from pathlib import Path

from unittest.mock import patch

from odoo import fields
from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from odoo.addons.check_management_New.models.check_payment_transaction import (
    CheckPaymentTransaction,
)

MODULE_DIR = Path(__file__).resolve().parents[1]


class TestCheckResetFailClosed(TransactionCase):
    """Regression tests for the fail-closed reset policy of check payment transactions."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.partner = cls.env['res.partner'].create({'name': 'Fail Closed Partner'})
        cls.check_counter = 0

    def _unique_number(self):
        self.check_counter += 1
        return 'FC-%s-%04d' % (fields.Date.today().isoformat().replace('-', ''), self.check_counter)

    def _create_check(self, **vals):
        state = vals.pop('state', None)
        check_vals = {
            'partner_id': self.partner.id,
            'amount': 100.0,
            'check_number': self._unique_number(),
        }
        check_vals.update(vals)
        check = self.env['check.payment.transaction'].create(check_vals)
        if state:
            check.write({'state': state})
            self.env['check.payment.transaction'].flush_recordset(['state'])
            self.env['check.payment.transaction'].invalidate_model(['state'])
        return check

    def _create_linked_move(self, check, journal_state=False):
        sequence = self._unique_number().replace('-', '')
        journal = self.env['account.journal'].create({
            'name': 'General %s' % sequence,
            'code': 'G%s' % sequence[-4:],
            'type': 'general',
        })
        debit_account = self.env['account.account'].create({
            'name': 'Debit %s' % sequence,
            'code': 'FD%s' % sequence[-5:],
            'account_type': 'asset_current',
        })
        credit_account = self.env['account.account'].create({
            'name': 'Credit %s' % sequence,
            'code': 'FM%s' % sequence[-5:],
            'account_type': 'asset_current',
        })
        move_vals = {
            'move_type': 'entry',
            'journal_id': journal.id,
            'date': fields.Date.today(),
            'ref': 'fail closed fixture %s' % sequence,
            'check_id': check.id,
            'line_ids': [
                (0, 0, {
                    'name': 'debit line',
                    'account_id': debit_account.id,
                    'debit': 100.0,
                    'credit': 0.0,
                }),
                (0, 0, {
                    'name': 'credit line',
                    'account_id': credit_account.id,
                    'debit': 0.0,
                    'credit': 100.0,
                }),
            ],
        }
        if journal_state:
            move_vals['journal_state'] = journal_state
        return self.env['account.move'].create(move_vals)

    def _persisted_move_snapshot(self, move):
        self.env['account.move'].flush_recordset(['state'])
        self.env['account.move.line'].flush_recordset(['debit', 'credit', 'account_id'])
        self.env['account.move'].invalidate_model(['state'])
        self.env['account.move.line'].invalidate_model(['debit', 'credit', 'account_id'])
        return {
            'exists': bool(move.exists()),
            'state': move.state,
            'lines': sorted(
                (line.id, line.debit, line.credit, line.account_id.id)
                for line in move.line_ids
            ),
        }

    def _persisted_check_state(self, check):
        self.env['check.payment.transaction'].flush_recordset(['state'])
        self.env['check.payment.transaction'].invalidate_model(['state'])
        return check.state

    def test_reset_draft_raises_and_preserves_everything(self):
        check = self._create_check(state='received')
        move = self._create_linked_move(check)
        move_before = self._persisted_move_snapshot(move)
        check_before = self._persisted_check_state(check)

        with self.assertRaises(UserError):
            check.reset_draft()

        self.assertEqual(
            self._persisted_check_state(check),
            check_before,
            "reset_draft must not change the check state",
        )
        self.assertEqual(
            self._persisted_move_snapshot(move),
            move_before,
            "reset_draft must not change the linked move state or its lines",
        )

    def test_reset_before_add_raises_on_matching_move_and_preserves_it(self):
        check = self._create_check(state='received')
        move = self._create_linked_move(check, journal_state='received')
        before = self._persisted_move_snapshot(move)
        check_before = self._persisted_check_state(check)

        with self.assertRaises(UserError):
            check.reset_before_add('received')

        after = self._persisted_move_snapshot(move)
        self.assertEqual(after, before, "matching move must stay untouched")
        self.assertTrue(after['exists'], "matching move must not be deleted")
        self.assertEqual(self._persisted_check_state(check), check_before)

    def test_invalid_source_states_never_invoke_guard_or_mutate_entries(self):
        cases = [
            ('action_receive', 'received'),
            ('action_deposit', 'draft'),
            ('action_fund_credited', 'received'),
            ('action_issue', 'issued'),
            ('action_fund_debited', 'deposited'),
        ]
        for action_name, invalid_state in cases:
            with self.subTest(action=action_name, state=invalid_state):
                check = self._create_check(state=invalid_state)
                move = self._create_linked_move(check)
                before = self._persisted_move_snapshot(move)

                with patch.object(CheckPaymentTransaction, 'reset_before_add') as guard:
                    with self.assertRaises(UserError):
                        getattr(check, action_name)()

                guard.assert_not_called()
                self.assertEqual(
                    self._persisted_move_snapshot(move),
                    before,
                    "%s from an invalid source state must not mutate linked entries" % action_name,
                )

    def test_valid_transition_without_matching_entry_reaches_create_move(self):
        check = self._create_check(state='draft')
        self.assertFalse(
            self.env['account.move'].search([('check_id', '=', check.id)]),
            "fixture must start without any linked entry",
        )
        with patch.object(CheckPaymentTransaction, 'create_move_rec') as creator:
            check.action_receive()
        creator.assert_called_once()
        self.assertEqual(self._persisted_check_state(check), 'received')

    def test_valid_issue_transition_without_matching_entry_reaches_create_move(self):
        check = self._create_check(state='draft')
        self.assertFalse(
            self.env['account.move'].search([('check_id', '=', check.id)]),
            "fixture must start without any linked entry",
        )
        with patch.object(CheckPaymentTransaction, 'create_move') as creator:
            check.action_issue()
        creator.assert_called_once()
        self.assertEqual(self._persisted_check_state(check), 'issued')

    def test_reset_before_add_allows_transitions_when_no_entry_matches(self):
        check = self._create_check(state='draft')
        other_stage_move = self._create_linked_move(check, journal_state='deposited')
        before = self._persisted_move_snapshot(other_stage_move)
        try:
            check.reset_before_add('posted')
        except UserError:
            self.fail("guard must pass when no entry matches the requested stage")
        self.assertEqual(
            self._persisted_move_snapshot(other_stage_move),
            before,
            "guard must leave entries of other stages untouched",
        )

    def test_module_source_has_no_delete_from_account_move_line_pattern(self):
        pattern = re.compile(r'delete\s+from\s+account_move_line', re.IGNORECASE)
        offenders = [
            str(path)
            for path in MODULE_DIR.rglob('*')
            if path.suffix in ('.py', '.xml')
            and pattern.search(path.read_text(encoding='utf-8', errors='ignore'))
        ]
        self.assertEqual(offenders, [], "no executable or commented SQL deletion may remain")

    def test_reset_draft_button_absent_from_every_form_view(self):
        views = self.env['ir.ui.view'].search([
            ('model', '=', 'check.payment.transaction'),
            ('type', '=', 'form'),
        ])
        self.assertTrue(views, "expected form views for check.payment.transaction")
        for view in views:
            with self.subTest(view=view.xml_id or view.name):
                self.assertNotIn('reset_draft', view.arch)

    def test_known_statusbar_forms_have_no_reset_draft_button(self):
        for xml_id in (
            'check_management_New.check_payment_form_statusbar_customer',
            'check_management_New.check_payment_form_statusbar_vendor',
        ):
            with self.subTest(view=xml_id):
                view = self.env.ref(xml_id)
                self.assertNotIn('reset_draft', view.arch)
