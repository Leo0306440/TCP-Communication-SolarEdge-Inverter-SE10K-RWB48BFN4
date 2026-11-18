import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Wechselrichter: SE10K-RWB48BFN4
# Batterie: Home Battery 48V - 5 modules
# Nur lesende Abfragen!
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
# MODBUS-FUNKTIONEN
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

    # Ungueltige SunSpec-/Modbus-Floatwerte herausfiltern
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# WECHSELRICHTER
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATTERIE
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Aus",
    1: "Standby",
    2: "Initialisierung",
    3: "Laden",
    4: "Entladen",
    5: "Fehler",
    6: "Ladung erhalten",
    7: "Leerlauf",
    10: "Energiesparmodus"
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
# ZAEHLER - VORERST NUR ROHDATEN
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# AUSGABE
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Nicht verfuegbar")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Batteriestatus:               Nicht verfuegbar")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Unbekannter Status ({status})"
        )
        print(f"Batteriestatus:               {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Wechselrichter:", INVERTER_IP)
    print("Batterie: SolarEdge Home Battery 48V")
    print("Abfrageintervall:", CHECK_INTERVAL, "Sekunden")
    print("Nur lesende Modbus-Abfragen")
    print("\nBeenden mit STRG + C")

    if not client.connect():
        print("FEHLER: Verbindung zum Wechselrichter fehlgeschlagen!")
        return

    print("\nVerbindung erfolgreich!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- WECHSELRICHTER ---")

            display_value(
                "AC-Leistung Wechselrichter:",
                inverter_power,
                "W"
            )

            print("\n--- BATTERIE ---")

            display_value(
                "Batterie-Ladezustand:",
                battery["soe"],
                "%"
            )

            display_value(
                "Batterieleistung:",
                battery["power"],
                "W"
            )

            display_value(
                "Batterietemperatur:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- BATTERIE TECHNISCHE DATEN ---")

            display_value(
                "Nennkapazitaet:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Max. Ladeleistung:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Max. Entladeleistung:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- ENERGIEZAEHLER ---")

            if meter is not None:
                print("Rohdaten Register 40206-40210:")
                print(meter)
                print("Interpretation noch nicht bestaetigt.")
            else:
                print("Keine Daten vom Energiezaehler.")

            print("\nNaechste Abfrage in", CHECK_INTERVAL, "Sekunden.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nMonitoring wird beendet.")
            break

        except Exception as error:
            print("\nFehler:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nModbus-Verbindung geschlossen.")
