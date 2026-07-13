-- Recalculate manual remaining stock by:
-- inbound_quantity - all manual warehouse quantities.
-- Run this once only after confirming old remaining_stock values can be replaced.

UPDATE customs_inventory_list
SET remaining_stock =
        COALESCE(inbound_quantity, 0)
        - COALESCE(czech_warehouse_qty, 0)
        - COALESCE(uk_warehouse_qty, 0)
        - COALESCE(us_warehouse_qty, 0)
        - COALESCE(de_warehouse_qty, 0)
        - COALESCE(fba_de_qty, 0)
        - COALESCE(fba_uk_qty, 0)
        - COALESCE(fba_us_qty, 0)
        - COALESCE(fba_fr_qty, 0),
    auto_czech_warehouse_qty = COALESCE(czech_warehouse_qty, 0),
    auto_uk_warehouse_qty = COALESCE(uk_warehouse_qty, 0),
    auto_us_warehouse_qty = COALESCE(us_warehouse_qty, 0),
    auto_de_warehouse_qty = COALESCE(de_warehouse_qty, 0),
    auto_fba_de_qty = COALESCE(fba_de_qty, 0),
    auto_fba_uk_qty = COALESCE(fba_uk_qty, 0),
    auto_fba_us_qty = COALESCE(fba_us_qty, 0),
    auto_fba_fr_qty = COALESCE(fba_fr_qty, 0),
    auto_remaining_stock =
        COALESCE(inbound_quantity, 0)
        - COALESCE(czech_warehouse_qty, 0)
        - COALESCE(uk_warehouse_qty, 0)
        - COALESCE(us_warehouse_qty, 0)
        - COALESCE(de_warehouse_qty, 0)
        - COALESCE(fba_de_qty, 0)
        - COALESCE(fba_uk_qty, 0)
        - COALESCE(fba_us_qty, 0)
        - COALESCE(fba_fr_qty, 0);
