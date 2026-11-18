import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Inverter: SE10K-RWB48BFN4
# Battery: Home Battery 48V - 5 modules
# Read-only queries!
# ============================================================

INVERTER_IP = "192.168.1.245"
MODBUS_PORT = 1502
SLAVE_ID = 1

BATTERY_BASE = 0xE100

CHECK_INTERVAL = 5
TIMEOUT = 3

client = ModbusTcpClient(
    INVERTER_IP,
    port=MODBUS_PORT,
    timeout=TIMEOUT,
    retries=0
)

# ------------------------------------------------------------
# MODBUS FUNCTIONS
# ------------------------------------------------------------

def read_registers(address, count):

    params = inspect.signature(
        client.read_holding_registers
    ).parameters

    kwargs = {
        "address": address,
        "count": count
    }

    if "device_id" in params:
        kwargs["device_id"] = SLAVE_ID
    elif "slave" in params:
        kwargs["slave"] = SLAVE_ID
    else:
        kwargs["unit"] = SLAVE_ID

    try:
        result = client.read_holding_registers(**kwargs)

        if result.isError():
            return None

        return result.registers

    except Exception:
        return None


def signed16(value):
    return value - 65536 if value >= 32768 else value


def read_float(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    raw = struct.pack(">HH", regs[1], regs[0])
    value = struct.unpack(">f", raw)[0]

    # Filter out invalid SunSpec/Modbus floating-point values
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# INVERTER
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATTERY
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Off",
    1: "Standby",
    2: "Initializing",
    3: "Charging",
    4: "Discharging",
    5: "Error",
    6: "Charge maintained",
    7: "Idle",
    10: "Energy-saving mode"
}


def get_battery_data():

    return {
        "capacity": read_float(BATTERY_BASE + 0x42),
        "charge_limit": read_float(BATTERY_BASE + 0x44),
        "discharge_limit": read_float(BATTERY_BASE + 0x46),
        "temperature": read_float(BATTERY_BASE + 0x6C),
        "power": read_float(BATTERY_BASE + 0x74),
        "soe": read_float(BATTERY_BASE + 0x84),
        "status": read_uint32(BATTERY_BASE + 0x86)
    }


# ------------------------------------------------------------
# METER - RAW DATA ONLY FOR NOW
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# OUTPUT
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Not available")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Battery status:               Not available")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Unknown status ({status})"
        )
        print(f"Battery status:               {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Inverter:", INVERTER_IP)
    print("Battery: SolarEdge Home Battery 48V")
    print("Polling interval:", CHECK_INTERVAL, "Sekunden")
    print("Read-only Modbus queries")
    print("\nPress CTRL + C to exit")

    if not client.connect():
        print("ERROR: Failed to connect to the inverter!")
        return

    print("\nConnection successful!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- INVERTER ---")

            display_value(
                "Inverter AC power:",
                inverter_power,
                "W"
            )

            print("\n--- BATTERY ---")

            display_value(
                "Battery state of energy:",
                battery["soe"],
                "%"
            )

            display_value(
                "Battery power:",
                battery["power"],
                "W"
            )

            display_value(
                "Battery temperature:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- BATTERY TECHNICAL DATA ---")

            display_value(
                "Nominal capacity:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Max. charging power:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Max. discharging power:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- ENERGY METER ---")

            if meter is not None:
                print("Raw data registers 40206-40210:")
                print(meter)
                print("Interpretation not yet confirmed.")
            else:
                print("No data received from the energy meter.")

            print("\nNext poll in", CHECK_INTERVAL, "seconds.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nMonitoring is stopping.")
            break

        except Exception as error:
            print("\nError:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nModbus connection closed.")
