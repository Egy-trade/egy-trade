# -*- coding: ut
{
    'name': "Letter Of Guarantee",
    'sequence': 1,

    'summary': """
    Manage and Track Letter Guarantee   
    """,

    'description': """
        This module allows you to create Letter Guarantee Request, approve Request and tracking Requests 
        
    """,
    'category': 'Accounting',
    'version': '0.1',

    # any module necessary for this one to work correctly
    'depends': ['base', 'portal','account', 'mail','sale','hr','account_accountant','project', 'Letter_Guarantee'],

    # always loaded
    'data': [
        'security/security.xml',
        'security/ir.model.access.csv',
        'data/data.xml',
        'wizard/lg_wizard.xml',
        'wizard/lg_report.xml',
        'reports/lg_report.xml',
        'views/final_letter_guarantee.xml',
        'views/initial_letter_guarantee.xml',
        'views/final_request_views.xml',
        'views/initial_request_views.xml',
        'views/bank_facilities.xml',
        'views/account_journal.xml',
    ],
    # only loaded in demonstration mode
    'demo': [
    ],
}