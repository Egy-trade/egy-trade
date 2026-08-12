# -*- coding: utf-8 -*-

{
    "name" : "Sale Status Waiting Approve",
    "version" : "16.0.0.2",
    "category" : "Sales",
    'license': 'OPL-1',
    "author": "Azam Mustafa Mohamed",
    "depends" : ['sale_revision_history'],
    "data": [
        'security/security_waiting_approve.xml',
        'views/waiting_approve_status.xml'
    ],
    'qweb': [
    ],
    "auto_install": False,
    "installable": True,
}
