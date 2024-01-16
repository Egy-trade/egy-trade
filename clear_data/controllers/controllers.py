# -*- coding: utf-8 -*-
from odoo import http

# class ClearData(http.Controller):
#     @http.route('/clear_data/clear_data/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/clear_data/clear_data/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('clear_data.listing', {
#             'root': '/clear_data/clear_data',
#             'objects': http.request.env['clear_data.clear_data'].search([]),
#         })

#     @http.route('/clear_data/clear_data/objects/<model("clear_data.clear_data"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('clear_data.object', {
#             'object': obj
#         })