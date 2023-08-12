# -*- coding: utf-8 -*-
##############################################################################
#
#    Odoo, Archer Solutions
#    Copyright (C) 2019 dev:Osama Ibrahim Team.
#
##############################################################################
{
    'name': "Letter Guarantee",
    'sequence': 1,

    'summary': """
    Manage and Track Letter Guarantee   
    """,

    'description': """
        This module allows you to create Letter Guarantee Request, approve Request and tracking Requests 
        
    """,

    'author': "Osama Ibrahim Team",
    'website': "https://www.linkedin.com/in/osama-ibrahim-mcts-58b1374b/",
    'category': 'Accounting',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'portal','account', 'mail','sale'],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'wizard/lg_wizard.xml',
        'views/views.xml',
        'views/automated_messages.xml',
        'views/lg_survey.xml',
        'views/request_lg.xml',
        'views/request_views.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
        # 'demo/demo.xml',
    ],
}