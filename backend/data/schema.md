# Data model — Beverage Manufacturing Plant (star schema)

All source CSVs in `SupposedDataset/` were open-source tables from **different domains**
stitched together with synthetic `canonical_*` keys. `RELATIONSHIPS.md` itself states these
keys make files *joinable* but do **not** represent one real process. We therefore replace them
with one **coherent beverage-plant** dataset where every key has a single, consistent meaning.

## Conventions
- Encoding **UTF-8**, delimiter `,`
- Dates `DD-MM-YYYY`, timestamps `DD-MM-YYYY HH:MM:SS`
- List columns use `;` (e.g. `M01;M02`)
- Reproducible: generated with a fixed seed
- **Fact tables have >= 500 rows.** Dimension tables use their natural cardinality
  (a plant has 3 shifts and 5 machines — padding them to 500 would corrupt the model).

## Keys (single meaning everywhere)
| Key | Space | Meaning |
|---|---|---|
| `product_id` | PRD001..PRD040 | Finished beverage SKU |
| `machine_id` | M01..M05 | Production machine |
| `operation_id` | OP10..OP60 | Routing step |
| `worker_id` | W001..W100 | Operator |
| `shift_id` | S1..S3 | Work shift |
| `material_id` | MAT001..MAT006 | Raw/packaging material |
| `order_id` | ORD0001..ORD0500 | Customer production order |
| `supplier_id` | SUP01..SUP04 | Material supplier |

## Dimensions
- **dim_product** (40): product_id, product_name, flavor, size_ml, pack_type, base_material_id, min_batch_minutes, standard_unit_price
- **dim_machine** (5): machine_id, machine_name, line, capable_operations, nominal_rate_units_per_hr, hourly_energy_kwh, reliability_index
- **dim_operation** (6): operation_id, operation_name, required_skill, min_workers, preferred_workers, eligible_machine_ids, sequence, standard_minutes
- **dim_worker** (100): worker_id, worker_name, primary_skill, secondary_skill, preferred_shift_id, max_weekly_hours, max_overtime_hours, hourly_cost_inr, experience_years, machine_qualifications, employment_status
- **dim_shift** (3): shift_id, shift_name, start_time, end_time, capacity_hours, required_workers
- **dim_material** (6): material_id, material_name, unit_of_measure, unit_cost, supplier_id, supplier_lead_time_days, reorder_point, current_stock, safety_stock
- **dim_downtime_factor** (12): factor_id, factor_name, category, is_operator_error

## Facts (>= 500 rows)
- **fact_orders** (500): order_id, product_id, order_quantity, release_date, due_date, priority, customer_region, status
- **fact_job_operations** (3000 = 500 orders x 6 ops): job_id, order_id, product_id, operation_id, sequence, machine_id, material_id, worker_id, shift_id, batch_quantity, processing_hours, scheduled_start, scheduled_end, actual_start, actual_end, downtime_minutes, downtime_factor_id, energy_kwh, job_status *(On-Time/Delayed/Failed — ML delay target)*
- **fact_machine_sensor** (600): event_id, reading_time, machine_id, hydraulic_pressure_bar, coolant_pressure_bar, air_pressure_bar, coolant_temp_c, hydraulic_oil_temp_c, spindle_bearing_temp_c, spindle_vibration_um, tool_vibration_um, spindle_speed_rpm, voltage_v, torque_nm, cutting_force_kn, machine_status, downtime_flag *(ML downtime target)*
- **fact_demand** (600 = 10 SKUs x 60 days): demand_date, product_id, warehouse_id, region, units_sold, inventory_level, reorder_point, order_quantity, unit_cost, unit_price, promotion_flag, stockout_flag, material_id *(units_sold = ML demand target)*
- **fact_production_history** (500): production_id, production_date, product_id, machine_id, shift_id, units_produced, defects, production_time_hours, material_cost_per_unit, labour_cost_per_hour, energy_kwh, operator_count, maintenance_hours, downtime_hours, scrap_rate, rework_hours, quality_checks_failed, avg_temp_c, avg_humidity_pct, status
- **fact_plan_vs_actual** (500): plan_id, production_date, product_id, machine_id, plan_quantity, actual_quantity, plan_energy_kwh, actual_energy_kwh, plan_time_hours, actual_time_hours, quantity_variance_pct, status
- **fact_worker_shift_availability** (700 = 100 workers x 7 days): worker_id, availability_date, shift_id, available, availability_status, available_hours, overtime_available, unavailability_reason, primary_machine_id

## Routing (eligible machines per operation — gives the optimizer choices)
| Operation | Skill | Eligible machines |
|---|---|---|
| OP10 Mixing | Mixing | M01;M02 |
| OP20 Blending | Blending | M01;M02 |
| OP30 Carbonation | Carbonation | M02;M03 |
| OP40 Filling | Filling | M03;M04 |
| OP50 Labeling | Labeling | M04;M05 |
| OP60 Packaging | Packaging | M05;M01 |
