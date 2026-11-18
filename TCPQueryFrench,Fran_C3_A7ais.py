import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Onduleur : SE10K-RWB48BFN4
# Batterie : Home Battery 48V - 5 modules
# Requêtes en lecture seule !
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
# FONCTIONS MODBUS
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

    # Filtrer les valeurs à virgule flottante SunSpec/Modbus invalides
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# ONDULEUR
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
    0: "Arrêt",
    1: "Veille",
    2: "Initialisation",
    3: "En charge",
    4: "Décharge",
    5: "Erreur",
    6: "Charge maintenue",
    7: "Inactif",
    10: "Mode économie d’énergie"
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
# COMPTEUR - DONNÉES BRUTES UNIQUEMENT POUR LE MOMENT
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# SORTIE
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} Non disponible")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("État de la batterie :          Non disponible")
    else:
        name = STATUS_NAMES.get(
            status,
            f"État inconnu ({status})"
        )
        print(f"État de la batterie :          {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Onduleur :", INVERTER_IP)
    print("Batterie : SolarEdge Home Battery 48V")
    print("Intervalle d’interrogation :", CHECK_INTERVAL, "Sekunden")
    print("Requêtes Modbus en lecture seule")
    print("\nAppuyez sur CTRL + C pour quitter")

    if not client.connect():
        print("ERREUR : impossible de se connecter à l’onduleur !")
        return

    print("\nConnexion réussie !")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- ONDULEUR ---")

            display_value(
                "Puissance CA de l’onduleur :",
                inverter_power,
                "W"
            )

            print("\n--- BATTERIE ---")

            display_value(
                "État énergétique de la batterie :",
                battery["soe"],
                "%"
            )

            display_value(
                "Puissance de la batterie :",
                battery["power"],
                "W"
            )

            display_value(
                "Température de la batterie :",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- DONNÉES TECHNIQUES DE LA BATTERIE ---")

            display_value(
                "Capacité nominale :",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Puissance de charge max. :",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Puissance de décharge max. :",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- COMPTEUR D’ÉNERGIE ---")

            if meter is not None:
                print("Données brutes des registres 40206-40210 :")
                print(meter)
                print("Interprétation pas encore confirmée.")
            else:
                print("Aucune donnée reçue du compteur d’énergie.")

            print("\nProchaine interrogation dans", CHECK_INTERVAL, "secondes.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nArrêt de la surveillance.")
            break

        except Exception as error:
            print("\nErreur :", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nConnexion Modbus fermée.")
