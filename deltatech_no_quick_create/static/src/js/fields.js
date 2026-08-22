odoo.define("deltatech_no_quick_create.fields", function (require) {
    "use strict";
    // Disabled during UAT stabilization.
    //
    // This file previously contained a GLOBAL patch on the core relational
    // fields: a FieldMany2One.include() whose init forced the quick_create
    // node option to a falsy value (and set its no_quick_create counterpart)
    // for every instance, removing the standard "Create ..." (name_create)
    // entry from every relational field of every backend view and breaking
    // core WebSuite relational-field coverage. No view in this repository
    // declares that option per-view, so the blanket patch was not scoped
    // behavior; the module is now non-installable.
    //
    // This stub is kept only so the asset path registered in __manifest__.py
    // stays valid for databases where the module is still installed: after
    // the next asset regeneration those databases load this no-op instead of
    // the global mutation. It deliberately contains no executable forcing
    // pattern, so the containment validator scans it like any other asset.
});
