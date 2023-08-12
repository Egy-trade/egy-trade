# -*- coding: utf-8 -*-
from odoo import http

# class Lg(http.Controller):
#     @http.route('/lg/lg/', auth='public')
#     def index(self, **kw):
#         return "Hello, world"

#     @http.route('/lg/lg/objects/', auth='public')
#     def list(self, **kw):
#         return http.request.render('lg.listing', {
#             'root': '/lg/lg',
#             'objects': http.request.env['lg.lg'].search([]),
#         })

#     @http.route('/lg/lg/objects/<model("lg.lg"):obj>/', auth='public')
#     def object(self, obj, **kw):
#         return http.request.render('lg.object', {
#             'object': obj
#         })