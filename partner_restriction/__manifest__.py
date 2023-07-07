{
    'name': 'Partner Restriction',
    'author': "OIT SOLUTIONS",
    'company': 'OIT SOLUTIONS',
    'website': 'https://oit-solution.com',
    'version': '13.0.0.1.0',
    'category': '',
    'license': 'AGPL-3',
    'sequence': 1,
    'depends': ['base','sale','crm'],
    'images': ['static/description/icon.png'],
    'data': [
        'security/rules.xml',
        'views/res_users.xml',
        'views/views.xml',
        'views/res_partner.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
    'uninstall_hook': "restore_access_rules",
}

