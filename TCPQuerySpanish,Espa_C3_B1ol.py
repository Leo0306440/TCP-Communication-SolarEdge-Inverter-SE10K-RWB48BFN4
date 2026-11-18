import time
import inspect
import math
import struct
from datetime import datetime
from pymodbus.client import ModbusTcpClient

# ============================================================
# SOLAREDGE LIVE MONITORING V4
# Inversor: SE10K-RWB48BFN4
# Batería: Home Battery 48V - 5 módulos
# ¡Consultas de solo lectura!
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
# FUNCIONES MODBUS
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

    # Filtrar valores de coma flotante SunSpec/Modbus no válidos
    if not math.isfinite(value) or abs(value) > 1e30:
        return None

    return value


def read_uint32(address):

    regs = read_registers(address, 2)

    if regs is None:
        return None

    return (regs[1] << 16) | regs[0]


# ------------------------------------------------------------
# INVERSOR
# ------------------------------------------------------------

def get_inverter_power():

    regs = read_registers(40083, 2)

    if regs is None:
        return None

    power = signed16(regs[0])
    sf = signed16(regs[1])

    return power * (10 ** sf)


# ------------------------------------------------------------
# BATERÍA
# ------------------------------------------------------------

STATUS_NAMES = {
    0: "Apagada",
    1: "En espera",
    2: "Inicializando",
    3: "Cargando",
    4: "Descargando",
    5: "Error",
    6: "Carga mantenida",
    7: "Inactiva",
    10: "Modo de ahorro de energía"
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
# CONTADOR - POR AHORA, SOLO DATOS SIN PROCESAR
# ------------------------------------------------------------

def get_meter_raw():

    return read_registers(40206, 5)


# ------------------------------------------------------------
# SALIDA
# ------------------------------------------------------------

def display_value(label, value, unit=""):

    if value is None:
        print(f"{label:<30} No disponible")
    else:
        print(f"{label:<30} {value:.2f} {unit}")


def display_status(status):

    if status is None:
        print("Estado de la batería:          No disponible")
    else:
        name = STATUS_NAMES.get(
            status,
            f"Estado desconocido ({status})"
        )
        print(f"Estado de la batería:          {name}")


def monitor():

    print("\n" * 2)
    print("=" * 65)
    print(" SOLAREDGE LIVE MONITORING V4")
    print("=" * 65)
    print("Inversor:", INVERTER_IP)
    print("Batería: SolarEdge Home Battery 48V")
    print("Intervalo de consulta:", CHECK_INTERVAL, "Sekunden")
    print("Consultas Modbus de solo lectura")
    print("\nPulsa CTRL + C para salir")

    if not client.connect():
        print("ERROR: ¡No se pudo conectar con el inversor!")
        return

    print("\n¡Conexión correcta!")

    while True:

        try:

            inverter_power = get_inverter_power()
            battery = get_battery_data()
            meter = get_meter_raw()

            print("\n")
            print("=" * 65)
            print(" ZEIT:", datetime.now().strftime("%d.%m.%Y %H:%M:%S"))
            print("=" * 65)

            print("\n--- INVERSOR ---")

            display_value(
                "Potencia CA del inversor:",
                inverter_power,
                "W"
            )

            print("\n--- BATERÍA ---")

            display_value(
                "Estado de energía de la batería:",
                battery["soe"],
                "%"
            )

            display_value(
                "Potencia de la batería:",
                battery["power"],
                "W"
            )

            display_value(
                "Temperatura de la batería:",
                battery["temperature"],
                "°C"
            )

            display_status(battery["status"])

            print("\n--- DATOS TÉCNICOS DE LA BATERÍA ---")

            display_value(
                "Capacidad nominal:",
                battery["capacity"],
                "Wh"
            )

            display_value(
                "Potencia máx. de carga:",
                battery["charge_limit"],
                "W"
            )

            display_value(
                "Potencia máx. de descarga:",
                battery["discharge_limit"],
                "W"
            )

            print("\n--- CONTADOR DE ENERGÍA ---")

            if meter is not None:
                print("Datos sin procesar de los registros 40206-40210:")
                print(meter)
                print("La interpretación aún no está confirmada.")
            else:
                print("No se han recibido datos del contador de energía.")

            print("\nSiguiente consulta en", CHECK_INTERVAL, "segundos.")

            time.sleep(CHECK_INTERVAL)

        except KeyboardInterrupt:
            print("\nSe está deteniendo la monitorización.")
            break

        except Exception as error:
            print("\nError:", repr(error))
            time.sleep(CHECK_INTERVAL)


try:
    monitor()

finally:
    client.close()
    print("\nConexión Modbus cerrada.")
