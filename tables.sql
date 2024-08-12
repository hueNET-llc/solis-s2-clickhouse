-- PLEASE NOTE
-- Buffer tables are what I personally use to batch inserts
-- You may have to modify them to work with your setup

CREATE TABLE solis_s2 (
    inverter_name LowCardinality(String), -- Inverter name
    inverter_temperature_celsius Float32, -- Inverter temperature in Celsius
    inverter_efficiency_percent Float32, -- Inverter DC>AC efficiency in percent
    mppt Array(Nested( -- Array of MPPT inputs
        id UInt8, -- MPPT ID
        voltage Float32, -- MPPT voltage
        amps Float32, -- MPPT current
        watts UInt32 -- MPPT power
    )),
    dc_calculated_watts UInt32, -- DC power calculated by summing MPPT power
    dc_actual_watts UInt32, -- DC power measured by inverter
    dc_busbar_voltage Float32, -- DC busbar voltage
    dc_half_busbar_voltage Float32, -- DC half busbar voltage
    ground_voltage Float32, -- Ground voltage
    ac_reactive_var UInt32, -- AC reactive power
    ac_apparent_va UInt32, -- AC apparent power
    ac_calculated_watts UInt32, -- AC calculated power
    ac_actual_watts UInt32, -- AC actual power
    ac_phases Array(Nested(
        id LowCardinality(String), -- Phase ID (A, B, C)
        voltage Float32, -- Phase voltage
        amps Float32, -- Phase current
        watts UInt32 -- Phase power
    )),
    ac_frequency_hz Float32, -- AC frequency
    daily_yield_kwh Float32, -- Daily yield in kWh
    monthly_yield_kwh UInt32, -- Monthly yield in kWh
    annual_yield_kwh UInt64, -- Annual yield in kWh
    total_yield_kwh UInt64, -- Total yield in kWh
    timestamp DateTime DEFAULT now()
) ENGINE = MergeTree() PARTITION BY toYYYYMM(timestamp) ORDER BY (inverter_name, timestamp) PRIMARY KEY (inverter_name, timestamp);

CREATE TABLE solis_s2_buffer (
    inverter_name LowCardinality(String), -- Inverter name
    inverter_temperature_celsius Float32, -- Inverter temperature in Celsius
    inverter_efficiency_percent Float32, -- Inverter DC>AC efficiency in percent
    mppt Array(Nested( -- Array of MPPT inputs
        id UInt8, -- MPPT ID
        voltage Float32, -- MPPT voltage
        amps Float32, -- MPPT current
        watts UInt32 -- MPPT power
    )),
    mppt_calculated_watts UInt32, -- DC power calculated by summing MPPT power
    mppt_actual_watts UInt32, -- DC power measured by inverter
    dc_busbar_voltage Float32, -- DC busbar voltage
    dc_half_busbar_voltage Float32, -- DC half busbar voltage
    ground_voltage Float32, -- Ground voltage
    ac_reactive_var UInt32, -- AC reactive power
    ac_apparent_va UInt32, -- AC apparent power
    ac_calculated_watts UInt32, -- AC calculated power
    ac_actual_watts UInt32, -- AC actual power
    ac_phase Array(Nested(
        id LowCardinality(String), -- Phase ID (A, B, C)
        voltage Float32, -- Phase voltage
        amps Float32, -- Phase current
        watts UInt32 -- Phase power
    )),
    ac_frequency Float32, -- AC frequency
    daily_yield_kwh Float32, -- Daily yield in kWh
    monthly_yield_kwh UInt32, -- Monthly yield in kWh
    annual_yield_kwh UInt64, -- Annual yield in kWh
    total_yield_kwh UInt64, -- Total yield in kWh
    timestamp DateTime DEFAULT now()
) ENGINE = Buffer(homelab, solis_s2, 1, 10, 10, 10, 100, 10000, 10000);
