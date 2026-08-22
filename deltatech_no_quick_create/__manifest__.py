# ©  2008-2021 Deltatech
# See README.rst file on addons root folder for license details


{
    "name": "No quick_create",
    "summary": "disable quick_create",
    "version": "16.0.1.0.0",
    "author": "Terrabit, Dorin Hongu",
    "website": "https://www.terrabit.ro",
    "category": "Tools",
    "depends": ["base", "web"],
    "license": "LGPL-3",
    # Disabled for UAT stabilization: this module injected a GLOBAL
    # FieldMany2One.include() patch that forced quick_create=false onto every
    # relational field of every view, removing standard create/name_create
    # flows repo-wide (upstream WebSuite relational-field coverage depends on
    # them). No business view in this repository declares a targeted
    # no_quick_create option, so there is no scoped intent to preserve.
    "installable": False,
    "auto_install": False,
    "data": [],
    "images": ["static/description/main_screenshot.png"],
    "development_status": "Beta",
    "maintainers": ["dhongu"],
    "assets": {
        "web.assets_backend": [
            "deltatech_no_quick_create/static/src/js/fields.js",
        ]
    },
}
