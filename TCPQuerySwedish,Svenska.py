import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Växelriktare: SE10K-RWB48BFN4
# Batteri: Home Battery 48V - 5 moduler
# Endast läsförfrågningar!
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
# MODBUS-FUNKTIONER
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

    # Filtrera bort ogiltiga flyttalsvärden från SunSpec/Modbus
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# VÄXELRIKTARE
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATTERI
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Av",
    1: "Viloläge",
    2: "Initierar",
    3: "Laddar",
    4: "Laddar ur",
    5: "Fel",
    6: "Laddning bibehålls",
    7: "Inaktiv",
    10: "Energisparläge"
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
# MÄTARE - ENDAST RÅDATA FÖR NÄRVARANDE
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# UTDATA
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Inte tillgänglig")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Batteristatus:                 Inte tillgänglig")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Okänd status ({status})"
        )
        print(f"Batteristatus:                 {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Växelriktare:", INVERTER_IP)
    print("Batteri: SolarEdge Home Battery 48V")
    print("Avläsningsintervall:", CHECK_INTERVAL, "Sekunden")
    print("Modbus-förfrågningar, endast läsning")
    print("\nTryck på CTRL + C för att avsluta")

    if not client.connect():
        print("FEL: Det gick inte att ansluta till växelriktaren!")
        return

    print("\nAnslutningen lyckades!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- VÄXELRIKTARE ---")

            display_value(
                "Växelriktarens AC-effekt:",
                inverter_power,
                "W"
            )

            print("\n--- BATTERI ---")

            display_value(
                "Batteriets energinivå:",
                battery["soe"],
                "%"
            )

            display_value(
                "Batterieffekt:",
                battery["power"],
                "W"
            )

            display_value(
                "Batteritemperatur:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- BATTERIETS TEKNISKA DATA ---")

            display_value(
                "Nominell kapacitet:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Max. laddeffekt:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Max. urladdningseffekt:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- ENERGIMÄTARE ---")

            if meter is not None:
                print("Rådata från registren 40206-40210:")
                print(meter)
                print("Tolkningen är ännu inte bekräftad.")
            else:
                print("Inga data har tagits emot från energimätaren.")

            print("\nNästa avläsning om", CHECK_INTERVAL, "sekunder.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nÖvervakningen avslutas.")
            break

        except Exception as error:
            print("\nFel:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nModbus-anslutningen är stängd.")
