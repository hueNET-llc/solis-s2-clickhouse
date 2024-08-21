import aiochclient
import aiohttp
import asyncio
import colorlog
import datetime
import json
import logging
import os
import signal
import socket
import sys
import uvloop
uvloop.install()

from concurrent.futures import ThreadPoolExecutor
from umodbus.client import tcp as umodbus_tcp

log = logging.getLogger('Solis')


class SolisS2:
    def __init__(self, loop):
        # Setup logging
        self._setup_logging()
        # Load environment variables
        self._load_env_vars()

        # Get the event loop
        self.loop: asyncio.BaseEventLoop = loop

        self.targets: list[dict[str, int | str | bool]] = []

        # Queue of data waiting to be inserted into ClickHouse
        self.clickhouse_queue: asyncio.Queue = asyncio.Queue(maxsize=self.clickhouse_queue_limit)

        # Event used to stop the loop
        self.stop_event: asyncio.Event = asyncio.Event()

    def _setup_logging(self):
        """
            Sets up logging colors and formatting
        """
        # Create a new handler with colors and formatting
        shandler = logging.StreamHandler(stream=sys.stdout)
        shandler.setFormatter(colorlog.LevelFormatter(
            fmt={
                'DEBUG': '{log_color}{asctime} [{levelname}] {message}',
                'INFO': '{log_color}{asctime} [{levelname}] {message}',
                'WARNING': '{log_color}{asctime} [{levelname}] {message}',
                'ERROR': '{log_color}{asctime} [{levelname}] {message}',
                'CRITICAL': '{log_color}{asctime} [{levelname}] {message}',
            },
            log_colors={
                'DEBUG': 'blue',
                'INFO': 'white',
                'WARNING': 'yellow',
                'ERROR': 'red',
                'CRITICAL': 'bg_red',
            },
            style='{',
            datefmt='%H:%M:%S'
        ))
        # Add the new handler
        logging.getLogger('Solis').addHandler(shandler)
        log.debug('Finished setting up logging')

    def _load_targets(self):
        # Open and read the targets file
        with open('targets.json', 'r') as file:
            try:
                targets = json.loads(file.read())
            except Exception as e:
                log.error(f'Failed to read targets.json: "{e}"')
                exit(1)

        # Parse targets
        for target in targets:
            try:
                if (port := target.get('port', 161)):
                    try:
                        port = int(port)
                    except ValueError:
                        log.error(f'Invalid port "{port}" for target "{target["name"]}"')
                        continue

                if (mb_slave_id := target.get('mb_slave_id', 1)):
                    try:
                        mb_slave_id = int(mb_slave_id)
                    except ValueError:
                        log.error(f'Invalid mb_slave_id "{mb_slave_id}" for target "{target["name"]}"')
                        continue

                if (interval := target.get('interval', self.fetch_interval)):
                    try:
                        interval = int(interval)
                    except ValueError:
                        log.error(f'Invalid interval "{interval}" for target "{target["name"]}"')
                        continue

                if (timeout := target.get('timeout', self.fetch_timeout)):
                    try:
                        timeout = int(timeout)
                    except ValueError:
                        log.error(f'Invalid timeout "{timeout}" for target "{target["name"]}"')
                        continue

                self.targets.append({
                    'name': target['name'], # Inverter name
                    'ip': target['ip'], # Logging stick IP
                    'port': port, # Logging stick Modbus port
                    'mb_slave_id': mb_slave_id, # Modbus slave ID
                    'interval': interval, # Modbus Fetch interval
                    'timeout': timeout, # Modbus fetch timeout
                })
                log.debug(f'Parsed target "{target["name"]}" at IP "{target["ip"]}"')
            except KeyError as e:
                log.error(f'Missing required key "{e.args[0]}" for target "{target["name"]}"')
            except Exception:
                log.exception(f'Failed to parse target {target}')

    def _load_env_vars(self):
        """
            Loads environment variables
        """
        # Max number of inserts waiting to be inserted at once
        try:
            self.clickhouse_queue_limit = int(os.environ.get('CLICKHOUSE_QUEUE_LIMIT', 50))
        except ValueError:
            log.exception('Invalid CLICKHOUSE_QUEUE_LIMIT passed, must be a number')
            exit(1)

        # Default global SNMP fetch interval
        try:
            self.fetch_interval = int(os.environ.get('FETCH_INTERVAL', 30))
        except ValueError:
            log.exception('Invalid FETCH_INTERVAL passed, must be a number')
            exit(1)

        # Default global Modbus fetch timeout
        try:
            self.fetch_timeout = int(os.environ.get('FETCH_TIMEOUT', 15))
        except ValueError:
            log.exception('Invalid FETCH_TIMEOUT passed, must be a number')
            exit(1)

        # Log level to use
        # 10/debug  20/info  30/warning  40/error
        try:
            log_level = os.environ.get('LOG_LEVEL', 'INFO').upper()
            if log_level not in ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'):
                raise ValueError
        except ValueError:
            log.critical('Invalid LOG_LEVEL, must be a valid log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)')
            exit(1)

        # Set the log level
        log.setLevel({'DEBUG': logging.DEBUG, 'INFO': logging.INFO, 'WARNING': logging.WARNING, 'ERROR': logging.ERROR, 'CRITICAL': logging.CRITICAL}[log_level])

        # ClickHouse info
        try:
            self.clickhouse_url = os.environ['CLICKHOUSE_URL']
            self.clickhouse_user = os.environ['CLICKHOUSE_USERNAME']
            self.clickhouse_pass = os.environ['CLICKHOUSE_PASSWORD']
            self.clickhouse_db = os.environ['CLICKHOUSE_DATABASE']
        except KeyError as e:
            log.error(f'Missing required environment variable "{e.args[0]}"')
            exit(1)
        self.clickhouse_table = os.environ.get('CLICKHOUSE_TABLE', 'solis_s2')

    async def insert_to_clickhouse(self):
        """
            Gets data from the data queue and inserts it into ClickHouse
        """
        while True:
            # Get and check data from the queue
            if not (data := await self.clickhouse_queue.get()):
                continue

            # Keep trying until the insert succeeds
            while True:
                try:
                    # Insert the data into ClickHouse
                    log.debug(f'Inserting ClickHouse data: {data}')
                    await self.clickhouse.execute(

                        f"""
                        INSERT INTO {self.clickhouse_table} (
                            inverter_name, inverter_temperature_celsius, inverter_efficiency_percent,
                            mppt, dc_calculated_watts, dc_actual_watts, dc_busbar_voltage,
                            dc_half_busbar_voltage, ground_voltage, ac_reactive_var, ac_apparent_va,
                            ac_calculated_watts, ac_actual_watts, ac_phases, ac_frequency_hz,
                            daily_yield_kwh, monthly_yield_kwh, annual_yield_kwh, total_yield_kwh,
                            timestamp
                        ) VALUES
                        """,
                        data
                    )
                    log.debug(f'ClickHouse insert success for timestamp {data[-1]}')
                    # Insert succeeded, break the loop and move on
                    break
                except Exception as e:
                    log.error(f'ClickHouse insert failed for timestamp {data[-1]}: "{e}"')
                    # Wait before retrying so we don't spam retries
                    await asyncio.sleep(2)

    async def fetch_inverter(self, inverter:dict[str, int | str | bool]) -> None:
        log.info(f'Starting fetch for "{inverter["name"]}" ({inverter["ip"]})')
        while True:
            # {3000: 178, 3001: 24, 3002: 53, 3003: 0, 3004: 3, 3005: 0, 3006: 20, 3007: 0, 3008: 27, 3009: 0, 3010: 49087, 3011: 0, 3012: 301, 3013: 0, 3014: 1281, 3015: 491, 3016: 91, 3017: 0, 3018: 6703, 3019: 0, 3020: 10444, 3021: 0, 3022: 932, 3023: 1, 3024: 940, 3025: 1, 3026: 881, 3027: 1, 3028: 7, 3029: 1, 3030: 0, 3031: 1820, 3032: 3636, 3033: 0, 3034: 0, 3035: 0, 3036: 2422, 3037: 0, 3038: 0, 3039: 22, 3040: 0, 3041: 7, 3042: 291, 3043: 5999, 3044: 3, 3045: 0, 3046: 0, 3047: 0, 3048: 0, 3049: 0}
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(inverter['timeout'])
            registers = {}
            try:
                # Connect to the socket in the executor
                log.debug(f'Opening socket to "{inverter["name"]}" ({inverter["ip"]})')
                await self.loop.run_in_executor(None, sock.connect, (inverter['ip'], inverter['port']))

                # Fetch registers 3000-3043
                # The send address must be offset from the actual register ID by -1
                message = umodbus_tcp.read_input_registers(slave_id=inverter['mb_slave_id'], starting_address=2999, quantity=44)
                # Send the message and receive the response
                log.debug(f'Fetching registers 3000-3049 from "{inverter["name"]}" ({inverter["ip"]})')
                try:
                    async with asyncio.timeout(inverter['timeout']):
                        response = await self.loop.run_in_executor(None, lambda: umodbus_tcp.send_message(message, sock))

                        for register_id in range(44):
                            registers[3000 + register_id] = response[register_id]

                        # Fetch registers 3050-3059
                        # The send address must be offset from the actual register ID by -1
                        message = umodbus_tcp.read_input_registers(slave_id=inverter['mb_slave_id'], starting_address=3049, quantity=10)
                        # Send the message and receive the response
                        log.debug(f'Fetching registers 3050-3059 from "{inverter["name"]}" ({inverter["ip"]})')
                        response = await self.loop.run_in_executor(None, lambda: umodbus_tcp.send_message(message, sock))

                        for register_id in range(10):
                            registers[3050 + register_id] = response[register_id]

                        log.debug(f'Got register data from "{inverter["name"]}" ({inverter["ip"]}): {registers}')
                except asyncio.TimeoutError:
                    raise asyncio.TimeoutError("Timed out waiting for response")
            except Exception as e:
                log.error(f'Failed to fetch "{inverter["name"]}" ({inverter["ip"]}): {type(e).__name__}: {e}')
                # Retry after the configured delay
                await asyncio.sleep(inverter['interval'])
                continue
            finally:
                 # Try to close the socket
                try:
                    await self.loop.run_in_executor(None, sock.close)
                    log.debug(f'Closed socket to "{inverter["name"]}" ({inverter["ip"]})')
                except Exception as e:
                    log.error(f'Failed to close socket to "{inverter["name"]}" ({inverter["ip"]}): {type(e).__name__}: {e}')

            try:
                # Parse MPPT inputs
                mppt_inputs = []
                # Calculated MPPT DC watts
                mppt_calculated_watts = 0.0

                # MPPT inputs with <10VDC input are probably not connected
                # MPPT 1
                if registers[3022] > 100:
                    watts = (registers[3022] / 10) * (registers[3023] / 10)
                    mppt_inputs.append([(
                        1, # MPPT ID
                        registers[3022] / 10, # MPPT 1 Voltage (0.1 V)
                        registers[3023] / 10, # MPPT 1 Current (0.1 A)
                        watts # MPPT 1 Power (1 W)
                    )])
                    mppt_calculated_watts += watts

                # MPPT 2
                if registers[3024] > 100:
                    watts = (registers[3024] / 10) * (registers[3025] / 10)
                    mppt_inputs.append([(
                        2, # MPPT ID
                        registers[3024] / 10, # MPPT 2 Voltage (0.1 V)
                        registers[3025] / 10, # MPPT 2 Current (0.1 A)
                        watts # MPPT 2 Power (1 W)
                    )])
                    mppt_calculated_watts += watts

                # MPPT 3
                if registers[3026] > 100:
                    watts = (registers[3026] / 10) * (registers[3027] / 10)
                    mppt_inputs.append([(
                        3, # MPPT ID
                        registers[3026] / 10, # MPPT 3 Voltage (0.1 V)
                        registers[3027] / 10, # MPPT 3 Current (0.1 A)
                        watts # MPPT 3 Power (1 W)
                    )])
                    mppt_calculated_watts += watts

                # MPPT 4
                if registers[3028] > 100:
                    watts = (registers[3028] / 10) * (registers[3029] / 10)
                    mppt_inputs.append([(
                        4, # MPPT ID
                        registers[3028] / 10, # MPPT 4 Voltage (0.1 V)
                        registers[3029] / 10, # MPPT 4 Current (0.1 A)
                        watts # MPPT 4 Power (1 W)
                    )])
                    mppt_calculated_watts += watts

                ac_phases = []
                ac_calculated_power = 0

                # AC Phase A
                if registers[3034] > 1:
                    watts = int((registers[3034] / 10) * (registers[3037] / 10))
                    ac_phases.append([(
                        'A', # Phase ID
                        registers[3034] / 10, # AC Phase A Voltage (0.1 V)
                        registers[3037] / 10, # AC Phase A Current (0.1 A)
                        watts # AC Phase A Power (1 W)
                    )])
                    ac_calculated_power += watts

                # AC Phase B
                if registers[3035] > 1:
                    watts = int((registers[3035] / 10) * (registers[3038] / 10))
                    ac_phases.append([(
                        'B', # Phase ID
                        registers[3035] / 10, # AC Phase B Voltage (0.1 V)
                        registers[3038] / 10, # AC Phase B Current (0.1 A)
                        watts # AC Phase B Power (1 W)
                    )])
                    ac_calculated_power += watts

                # AC Phase C
                if registers[3036] > 1:
                    watts = int((registers[3036] / 10) * (registers[3039] / 10))
                    ac_phases.append([(
                        'C', # Phase ID
                        registers[3036] / 10, # AC Phase C Voltage (0.1 V)
                        registers[3039] / 10, # AC Phase C Current (0.1 A)
                        watts # AC Phase C Power (1 W)
                    )])
                    ac_calculated_power += watts

                ac_actual_power = (registers[3005] << 16) + registers[3006]
                dc_actual_power = (registers[3007] << 16) + registers[3008]

                data = [
                    inverter['name'], # Inverter name
                    registers[3042] / 10, # Inverter temperature
                    min(100.0, (ac_actual_power / dc_actual_power) * 100.0), # Inverter DC>AC efficiency
                    mppt_inputs, # MPPT inputs
                    mppt_calculated_watts, # Calculated MPPT DC watts
                    dc_actual_power, # DC Actual Power (1 W)
                    registers[3032] / 10, # DC Busbar Voltage (0.1 V)
                    registers[3033] / 10, # DC half-busbar voltage (0.1 V)
                    registers[3031] / 10, # Ground Voltage (0.1 V)
                    (registers[3056] << 16) + registers[3057], # AC Reactive Power (1 Var)
                    (registers[3058] << 16) + registers[3059], # AC Apparent Power (1 VA)
                    ac_calculated_power, # AC Calculated Power (1 W)
                    ac_actual_power, # AC Actual Power (1 W)
                    ac_phases, # AC Phases
                    registers[3043] / 100, # AC Frequency (0.01 Hz)
                    registers[3015] / 10, # Daily yield (kWh)
                    (registers[3011] << 16) + registers[3012], # Monthly yield (kWh)
                    (registers[3017] << 16) + registers[3018], # Annual yield (kWh)
                    (registers[3009] << 16) + registers[3010], # Total yield (kWh)
                    datetime.datetime.now(tz=datetime.timezone.utc).timestamp() # Current UTC timestamp
                ]
                # Insert the data into the ClickHouse queue
                self.clickhouse_queue.put_nowait(data)
            # Handle full queue
            except asyncio.QueueFull:
                log.error(f'Failed to parse data from "{inverter["name"]}" ({inverter["ip"]}): ClickHouse queue is full')
            except Exception as e:
                log.exception(f'Failed to parse data from "{inverter["name"]}" ({inverter["ip"]}): {e}')
            finally:
                # Wait the configured interval before fetching again
                await asyncio.sleep(inverter['interval'])

    async def run(self):
        """
            Setup and run the exporter
        """
        # Load the targets from targets.json
        self._load_targets()
        if not self.targets:
            log.error('No valid targets found in targets.json')
            exit(1)

        # Create a ClientSession that doesn't verify SSL certificates
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(ssl=False)
        )
        # Create the ClickHouse client
        self.clickhouse = aiochclient.ChClient(
            self.session,
            url=self.clickhouse_url,
            user=self.clickhouse_user,
            password=self.clickhouse_pass,
            database=self.clickhouse_db,
            json=json
        )
        log.debug(f'Using ClickHouse table: "{self.clickhouse_table}" Database: "{self.clickhouse_db}" URL: "{self.clickhouse_url}"')

        # Run the queue inserter as a task
        asyncio.create_task(self.insert_to_clickhouse())

        for inverter in self.targets:
            # Run the fetcher as a task
            log.debug(f'Creating task for target {inverter}')
            asyncio.create_task(self.fetch_inverter(inverter))

        # Run forever or until we get SIGTERM'd
        await self.stop_event.wait()

        log.info('Exiting...')
        # Close the ClientSession
        await self.session.close()
        # Close the ClickHouse client
        await self.clickhouse.close()


loop = asyncio.new_event_loop()
# Create a new thread pool and set it as the default executor
loop.set_default_executor(ThreadPoolExecutor())
# Create an instance of the exporter
solis = SolisS2(loop)

def sigterm_handler(_signo, _stack_frame):
    """
        Handle SIGTERM
    """
    # Set the event to stop the exporter loop
    solis.stop_event.set()

# Register the SIGTERM handler
signal.signal(signal.SIGTERM, sigterm_handler)

try:
    # Run the loop
    loop.run_until_complete(solis.run())
except KeyboardInterrupt:
    # Set the stop event
    solis.stop_event.set()
