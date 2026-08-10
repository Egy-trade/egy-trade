"""Reconcile historical quotation price origins without changing prices.

The previous 16.0.2.0.0 upgrade preserved every selling price but classified
every legacy baseline as Odoo Pricelist because no evidence field existed.
This migration certifies only controlled or formula-proven origins and marks
every other historical source unverified.
"""


def migrate(cr, version):
    del version

    # Trust a historical label only when a line-specific pricing audit proves
    # Product Pricing and Manual Price values created by 16.0.2.0.0 are
    # controlled system transitions. The earlier blanket legacy conversion used
    # only the Pricelist label, so it is intentionally not trusted here.
    cr.execute("""
        UPDATE sale_order_line
           SET price_origin_verified = TRUE,
               price_origin_evidence = CASE price_origin
                   WHEN 'product_pricing' THEN 'product_pricing_apply'
                   WHEN 'edited' THEN 'manual_edit'
               END
         WHERE price_origin IN ('product_pricing', 'edited')
           AND NOT COALESCE(price_origin_verified, FALSE)
    """)
    # the same controlled transition. The previous blanket migration audit used
    # line_id NULL and therefore cannot certify an individual line.
    cr.execute("""
        UPDATE sale_order_line AS line
           SET price_origin_verified = TRUE,
               price_origin_evidence = CASE line.price_origin
                   WHEN 'product_pricing' THEN 'product_pricing_apply'
                   WHEN 'edited' THEN 'manual_edit'
                   WHEN 'pricelist' THEN 'new_pricelist'
               END
         WHERE line.price_origin IN ('product_pricing', 'edited', 'pricelist')
           AND NOT COALESCE(line.price_origin_verified, FALSE)
           AND EXISTS (
               SELECT 1
                 FROM sale_order_pricing_audit AS audit
                WHERE audit.line_id = line.id
                  AND audit.new_origin = line.price_origin
           )
    """)

    # Capture formula-proven candidates before updating so the audit retains
    # the previous conservative origin.
    cr.execute("""
        CREATE TEMP TABLE legacy_formula_origin_candidates ON COMMIT DROP AS
        SELECT line.id,
               line.order_id,
               line.product_id,
               line.price_unit,
               line.price_origin AS old_origin,
               sale.company_id,
               sale.currency_id
          FROM sale_order_line AS line
          JOIN sale_order AS sale ON sale.id = line.order_id
          LEFT JOIN res_currency AS currency ON currency.id = sale.currency_id
         WHERE line.display_type IS NULL
           AND NOT COALESCE(line.is_downpayment, FALSE)
           AND NOT COALESCE(line.price_origin_verified, FALSE)
           AND COALESCE(sale.product_pricing, FALSE)
           AND COALESCE(line.purchase_price_estimate, 0.0) > 0.0
           AND COALESCE(line.factor, 0.0) > 0.0
           AND COALESCE(line.line_factor, 0.0) > 0.0
           AND COALESCE(line.currency_rate_estimate, 0.0) > 0.0
           AND ABS(
               line.price_unit - (
                   line.purchase_price_estimate
                   * line.factor
                   * line.line_factor
                   * line.currency_rate_estimate
               )
           ) <= GREATEST(COALESCE(currency.rounding, 0.01), 0.000001)
           AND ABS(
               COALESCE(line.price_reference, line.price_unit) - line.price_unit
           ) <= GREATEST(COALESCE(currency.rounding, 0.01), 0.000001)
    """)

    cr.execute("""
        UPDATE sale_order_line AS line
           SET price_origin = 'product_pricing',
               price_origin_verified = TRUE,
               price_origin_evidence = 'legacy_formula',
               pricing_warning = NULL
          FROM legacy_formula_origin_candidates AS candidate
         WHERE candidate.id = line.id
    """)

    cr.execute("""
        INSERT INTO sale_order_pricing_audit (
            order_id, line_id, product_id, company_id,
            old_price, new_price, old_currency_id, new_currency_id,
            old_origin, new_origin, reason, user_id, event_date,
            create_uid, create_date, write_uid, write_date
        )
        SELECT candidate.order_id, candidate.id, candidate.product_id,
               candidate.company_id, candidate.price_unit, candidate.price_unit,
               candidate.currency_id, candidate.currency_id,
               candidate.old_origin, 'product_pricing',
               'Upgrade evidence: stored purchase estimate, factors, currency rate, reference, and selling price match the Product Pricing formula within currency rounding.',
               root_user.res_id, NOW(), root_user.res_id, NOW(),
               root_user.res_id, NOW()
          FROM legacy_formula_origin_candidates AS candidate
          CROSS JOIN LATERAL (
              SELECT res_id
                FROM ir_model_data
               WHERE module = 'base' AND name = 'user_root'
               LIMIT 1
          ) AS root_user
    """)

    # Preserve every remaining price but stop claiming its source was the
    # Odoo Pricelist. A manager may later certify it with recorded evidence.
    cr.execute("""
        CREATE TEMP TABLE legacy_unverified_origin_candidates ON COMMIT DROP AS
        SELECT line.id,
               line.order_id,
               line.product_id,
               line.price_unit,
               line.price_origin AS old_origin,
               sale.company_id,
               sale.currency_id
          FROM sale_order_line AS line
          JOIN sale_order AS sale ON sale.id = line.order_id
         WHERE line.display_type IS NULL
           AND NOT COALESCE(line.is_downpayment, FALSE)
           AND NOT COALESCE(line.price_origin_verified, FALSE)
    """)

    cr.execute("""
        UPDATE sale_order_line AS line
           SET price_origin = 'historical_unverified',
               price_origin_verified = FALSE,
               price_origin_evidence = 'legacy_unverified',
               pricing_warning = 'Historical price source is unverified; a Pricing Manager must review it before controlled repricing.'
          FROM legacy_unverified_origin_candidates AS candidate
         WHERE candidate.id = line.id
    """)

    cr.execute("""
        INSERT INTO sale_order_pricing_audit (
            order_id, line_id, product_id, company_id,
            old_price, new_price, old_currency_id, new_currency_id,
            old_origin, new_origin, reason, user_id, event_date,
            create_uid, create_date, write_uid, write_date
        )
        SELECT candidate.order_id, candidate.id, candidate.product_id,
               candidate.company_id, candidate.price_unit, candidate.price_unit,
               candidate.currency_id, candidate.currency_id,
               candidate.old_origin, 'historical_unverified',
               'Upgrade evidence: the historical unit-price source could not be proven; the selling price was preserved unchanged for manager review.',
               root_user.res_id, NOW(), root_user.res_id, NOW(),
               root_user.res_id, NOW()
          FROM legacy_unverified_origin_candidates AS candidate
          CROSS JOIN LATERAL (
              SELECT res_id
                FROM ir_model_data
               WHERE module = 'base' AND name = 'user_root'
               LIMIT 1
          ) AS root_user
    """)
