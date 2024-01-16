# -*- coding: utf-8 -*-

'''
Create Date:2017��9��1��

Author     :Administrator
'''
import datetime
import dateutil
import logging
import os
import time
import pdb
import logging
import odoo.tools
_logger = logging.getLogger(__name__)

from pytz import timezone

import odoo
from odoo import api, fields, models, tools, _
from odoo.exceptions import MissingError, UserError, ValidationError


class ClearDataModel(models.Model):
    _name='clear.data.model'
    
    name=fields.Char(string="Model group")
    internal_model_list=fields.Char(string='Always clear',descripton="Model in this list do not need installed. style like this:[string,string,...]")
    model_clear_ids=fields.Many2many("ir.model",'clear_data_ir_model_rel','group_id','model_id',domain=[('model','not in',['clear.data.model'])])
    auto_clear_ir_sequence=fields.Boolean(string="Auto clear ir sequence",defualt=True)
    sequence = fields.Integer(string="", default=0, required=False, )
    date = fields.Date(string="Date To", default=lambda self: fields.Datetime.now(), required=False, )
    date_from = fields.Date(string="Date Form", required=False, )


    def action_do_clear(self):
        self.ensure_one()
        self._do_clear_internal_model()
        self._do_clear_model_relation()
        
        if self.auto_clear_ir_sequence:
            self._do_clear_ir_sequence()
        return True
    
    
    def _do_clear_model_relation(self):
        
        self.ensure_one()
        
        for model_id in self.model_clear_ids:            
            if model_id:
               self._do_clear_by_model_name(model_id.model)
        
    def _do_clear_internal_model(self):
        
        self.ensure_one()
        
        if not self.internal_model_list:
            return True
        
        model_list=[]
        
        try:
            model_list=eval(self.internal_model_list)
            if type(model_list)!=list:
                raise UserError('Always clear model list format is incorrect!')
        except:
            raise UserError('Always clear model list format is incorrect!')
        
        if all(model_list):
            
            for model_name in model_list:
                self._do_clear_by_model_name(model_name)
                
        return True
    
    
    def _do_clear_by_model_name(self,model_name):
        self.ensure_one()
        model_obj=self.env.get(model_name,None)
        if model_obj==None or not odoo.tools.table_exists(self._cr, model_obj._table):
            return
                
        sql="delete from %s" % model_obj._table
        if self.date and self.date_from:
            sql += " where create_date <= '%s' and create_date >= '%s'" % (str(self.date),str(self.date_from))
        elif self.date:
            sql += " where create_date <= '%s' " % str(self.date)
        elif self.date_from:
            sql += " where create_date >= '%s' " % str(self.date_from)
        self._cr.execute(sql)
    
    def _do_clear_ir_sequence(self):
        cr=self._cr
        
        #清除不标准
        cr.execute("update ir_sequence set number_next=1")
        cr.execute("update ir_sequence_date_range set number_next=1")
        #清除标准
        seq_list=self.env['ir.sequence'].search([('implementation','=','standard')])
        if seq_list:
            for seq in seq_list:
                cr.execute("ALTER SEQUENCE ir_sequence_%03d RESTART WITH 1"%seq.id)