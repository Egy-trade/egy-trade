# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging
import pytz
import threading
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from psycopg2 import sql

from odoo import api, fields, models, tools
from odoo.addons.iap.tools import iap_tools
from odoo.addons.mail.tools import mail_validation
from odoo.addons.phone_validation.tools import phone_validation
from odoo.exceptions import UserError, AccessError
from odoo.osv import expression
from odoo.tools.translate import _
from odoo.tools import date_utils, email_re, email_split, is_html_empty, groupby
from odoo.tools.misc import get_lang


class ResPartner(models.Model):
    _inherit = 'res.partner'
    owner_user = fields.Many2one(
        string="Owner",
        comodel_name="res.users",
    )
    allowed_users_ids = fields.Many2many(
        'res.users',
        'rel_allowed_users_ids',
        string="Allowed Users",
    )
    check_allow = fields.Boolean(
        'check',
        default=False,
        compute='compute_check_allow'
    )
    check_user = fields.Boolean(
        'check',
        default=False,
        compute='compute_check_user'
    )

    def compute_check_user(self):
        for rec in self:
            if rec.owner_user == rec.env.user:
                rec.check_user = True
            else:
                rec.check_user = False

    def compute_check_allow(self):
        for rec in self:
            if rec.env.user.has_group('partner_restriction.group_owner_restrict'):
                rec.check_allow = True
            else:
                rec.check_allow = False

