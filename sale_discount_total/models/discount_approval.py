# -*- coding: utf-8 -*-
#############################################################################
#
#    Cybrosys Technologies Pvt. Ltd.
#
#    Copyright (C) 2022-TODAY Cybrosys Technologies(<https://www.cybrosys.com>).
#    Author: Faslu Rahman(odoo@cybrosys.com)
#
#    You can modify it under the terms of the GNU AFFERO
#    GENERAL PUBLIC LICENSE (AGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU AFFERO GENERAL PUBLIC LICENSE (AGPL v3) for more details.
#
#    You should have received a copy of the GNU AFFERO GENERAL PUBLIC LICENSE
#    (AGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

from odoo import _, fields, models
from odoo.exceptions import UserError


class sale_discount(models.Model):
    _inherit = 'sale.order'

    def action_confirm(self):
        """Keep standard Odoo confirmation; quotation approvals are separate evidence."""
        return super().action_confirm()

    def action_approve(self):
        raise UserError(_(
            'The legacy discount approval action is retired. Use the standard '
            'confirmation flow after completing quotation approvals.'
        ))


class Company(models.Model):
    _inherit = 'res.company'

    # Retained temporarily for forward-compatible databases.  The legacy
    # double-validation settings are no longer read by any confirmation path.
    so_double_validation = fields.Selection([
        ('one_step', 'Confirm sale orders in one step'),
        ('two_step', 'Get 2 levels of approvals to confirm a sale order')
    ], string="Levels of Approvals", default='one_step',
        help="Provide a double validation mechanism for sales discount")

    so_double_validation_limit = fields.Float(string="Percentage of Discount that requires double validation'",
                                  help="Minimum discount percentage for which a double validation is required")
