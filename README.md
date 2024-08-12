# [solis-s2-clickhouse](https://github.com/hueNET-llc/solis-s2-clickhouse)
[![GitHub Workflow Status](https://img.shields.io/github/actions/workflow/status/huenet-llc/solis-s2-clickhouse/master.yml?branch=master)](https://github.com/hueNET-llc/solis-s2-clickhouse/actions/workflows/master.yml)
[![Docker Image Version (latest by date)](https://img.shields.io/docker/v/rafaelwastaken/solis-s2-clickhouse)](https://hub.docker.com/r/rafaelwastaken/solis-s2-clickhouse)

A Solis S2-WL-ST exporter for ClickHouse using native Modbus TCP

Configuration is done via environment variables and targets.json

## Compatibility ##
⚠️ This exporter has only been tested with the following equipment:

    Data Logger: Solis 4-pin S2-WL-ST (Ethernet, firmware v1001019)
    Inverter: 1-phase, 3-MPPT Solis-1P7.6K-4G-US

It should support up to 3-phase, 4-MPPT inverters as long as they utilize the same register IDs

## Environment Variables ##
|  Name  | Description | Type | Default | Example |
| ------ | ----------- | ---- | ------- | ------- |
| FETCH_INTERVAL | Default Modbus fetch interval in seconds | int | 30 | 30 |
| FETCH_TIMEOUT| Default Modbus fetch timeout in seconds | int | 60 | 60 |
| LOG_LEVEL | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | str | INFO | INFO |
| CLICKHOUSE_URL | ClickHouse URL | str | N/A | https://10.0.0.1:8123 |
| CLICKHOUSE_USERNAME | ClickHouse login username | str | N/A | exporter |
| CLICKHOUSE_PASSWORD | ClickHouse login password | str | N/A | hunter2 |
| CLICKHOUSE_DATABASE | ClickHouse database name | str | N/A | metrics |
| CLICKHOUSE_TABLE | ClickHouse table name | str | solis_s2 | solar |
| CLICKHOUSE_QUEUE_LIMIT | Max number of data waiting to be inserted to ClickHouse (minimum 25) | int | 1000 | 25000 |

## targets.json ##

Used to configure logging stick targets. Example config in `targets.example.json`

```
[
    {
        name: Inverter name (string),
        ip: Logging stick IP (string),
        port: Logging stick Modbus TCP port (int, optional, default: "502"),
        mb_slave_id: Inverter Modbus slave ID (int, optional, default: "1"),
        interval: Modbus fetch interval in seconds (int, optional, default: "30")
        timeout: Modbus timeout duration in seconds (int, optional, default: "60"),
    }
]
```