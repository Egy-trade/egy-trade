"""Seed trustworthy pricing baselines for lines created before origin tracking.

Historical source cannot be reconstructed safely from the old duplicate grid,
so the migration preserves the visible selling price and marks it conservatively
as Odoo Price List until a new confirmed Product Pricing Apply establishes a
different origin.
"""


def migrate(cr, version):
    del version
    cr.execute("""
        WITH baselined AS (
            UPDATE sale_order_line AS line
               SET price_origin = 'pricelist',
                   price_reference = line.price_unit,
                   price_currency_id = sale.currency_id,
                   pricing_reprice_pending = FALSE,
                   pricing_warning = CASE
                       WHEN COALESCE(line.purchase_price_estimate, 0.0) = 0.0
                       THEN 'No purchasing cost: Product Pricing is ineligible; Odoo Price List is used.'
                       ELSE NULL
                   END
              FROM sale_order AS sale
             WHERE sale.id = line.order_id
               AND line.display_type IS NULL
               AND NOT COALESCE(line.is_downpayment, FALSE)
               AND line.price_currency_id IS NULL
         RETURNING line.order_id
        )
        INSERT INTO sale_order_pricing_audit (
            order_id,
            company_id,
            old_origin,
            new_origin,
            old_currency_id,
            new_currency_id,
            reason,
            user_id,
            event_date,
            create_uid,
            create_date,
            write_uid,
            write_date
        )
        SELECT DISTINCT
            sale.id,
            sale.company_id,
            NULL,
            'pricelist',
            sale.currency_id,
            sale.currency_id,
            'Upgrade baseline: existing selling prices were preserved and conservatively classified as Odoo Price List because the historical source could not be proven.',
            root_user.res_id,
            NOW(),
            root_user.res_id,
            NOW(),
            root_user.res_id,
            NOW()
          FROM baselined
          JOIN sale_order AS sale ON sale.id = baselined.order_id
          CROSS JOIN LATERAL (
              SELECT res_id
                FROM ir_model_data
               WHERE module = 'base' AND name = 'user_root'
               LIMIT 1
          ) AS root_user
    """)
