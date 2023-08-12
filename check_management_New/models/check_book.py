# -*- coding: utf-8 -*-
##############################################################################

import datetime

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError, AccessError, UserError
class check_book_line(models.Model):
    _name = 'check.book.line'
    name = fields.Char(string="Number", required=True, )
    book_id = fields.Many2one(comodel_name="check.book", string="", required=False, )
    check_id = fields.Many2one(comodel_name="check.payment.transaction", string="Check", required=False, )
    reserved = fields.Boolean(string="Reserved", compute="compute_reserved" )

    @api.depends('name','book_id')
    def compute_reserved(self):
        for rec in self:
            checks = self.env['check.payment.transaction'].sudo().search([('book_serial','=',rec.id),('state','!=','cancelled')])
            if checks:
                rec.reserved = True
            else:
                rec.reserved = False

class check_book(models.Model):
    _name = 'check.book'

    book_num = fields.Integer(string="check book Number", required=False, )
    name = fields.Char(string="Name", required=False,compute="_compute_check_book_name",store=True )
    first_check_num = fields.Integer(string="First check Number", required=False, )
    next_check_num = fields.Integer(string="Next check Number",compute="_compute_next_check_num", required=False, )
    last_check_num = fields.Integer(string="Last check Number", required=False, )
    active = fields.Boolean(string="Active", default=True )
    bank_id = fields.Many2one("res.bank", string="Bank")

    serial_ids = fields.One2many(comodel_name="check.book.line", inverse_name="book_id", string="All Serials", compute="compute_serials",store=True  )

    @api.depends('first_check_num','last_check_num')
    def compute_serials(self):

        if self.first_check_num and self.last_check_num:
            first = int(self.first_check_num)
            last = int(self.last_check_num) +1
            lst=[]
            for n in range(first,last):
                print("n === > ",n)
                lst.append({
                    'name': str(n),
                    })
            self.serial_ids = [(5, 0)] + [(0, 0, value) for value in lst]
        else:self.serial_ids=False

    @api.depends('serial_ids')
    def _compute_next_check_num(self):
        serials = self.serial_ids.filtered(lambda l: not l.reserved)
        print('serials ==> ',serials)
        if serials:
            num = serials[0].name
            self.next_check_num = int(num)
        else:self.next_check_num= False



    @api.depends('book_num','bank_id')
    def _compute_check_book_name(self):
        for rec in self:
            name =''
            if rec.bank_id:
                name = rec.bank_id.name
            if rec.book_num:
                name += str(rec.book_num)
            rec.name=name

    def toggle_active(self):
        for rec in self:
            rec.active = not rec.active




