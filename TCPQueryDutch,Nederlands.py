import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Omvormer: SE10K-RWB48BFN4
# Batterij: Home Battery 48V - 5 modules
# Alleen-lezenopvragingen!
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
# MODBUS-FUNCTIES
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

    # Ongeldige SunSpec/Modbus-kommagetallen filteren
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# OMVORMER
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATTERIJ
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Uit",
    1: "Stand-by",
    2: "Initialiseren",
    3: "Opladen",
    4: "Ontladen",
    5: "Fout",
    6: "Lading behouden",
    7: "Inactief",
    10: "Energieb besparingsmodus"
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
# METER - VOORLOPIG ALLEEN RUWE GEGEVENS
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# UITVOER
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Niet beschikbaar")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Batterijstatus:                Niet beschikbaar")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Onbekende status ({status})"
        )
        print(f"Batterijstatus:                {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Omvormer:", INVERTER_IP)
    print("Batterij: SolarEdge Home Battery 48V")
    print("Opvraaginterval:", CHECK_INTERVAL, "Sekunden")
    print("Alleen-lezen Modbus-opvragingen")
    print("\nDruk op CTRL + C om af te sluiten")

    if not client.connect():
        print("FOUT: Verbinding met de omvormer mislukt!")
        return

    print("\nVerbinding geslaagd!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- OMVORMER ---")

            display_value(
                "AC-vermogen omvormer:",
                inverter_power,
                "W"
            )

            print("\n--- BATTERIJ ---")

            display_value(
                "Energieniveau batterij:",
                battery["soe"],
                "%"
            )

            display_value(
                "Batterijvermogen:",
                battery["power"],
                "W"
            )

            display_value(
                "Batterijtemperatuur:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- TECHNISCHE GEGEVENS BATTERIJ ---")

            display_value(
                "Nominale capaciteit:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Max. laadvermogen:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Max. ontlaadvermogen:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- ENERGIEMETER ---")

            if meter is not None:
                print("Ruwe gegevens registers 40206-40210:")
                print(meter)
                print("Interpretatie nog niet bevestigd.")
            else:
                print("Geen gegevens ontvangen van de energiemeter.")

            print("\nVolgende opvraging over", CHECK_INTERVAL, "seconden.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nMonitoring wordt gestopt.")
            break

        except Exception as error:
            print("\nFout:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nModbus-verbinding gesloten.")
