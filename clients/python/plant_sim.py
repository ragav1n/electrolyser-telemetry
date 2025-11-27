import json
import math
import random
import ssl
import time
import pathlib
import datetime
import hashlib

import tomli
from paho.mqtt import client as mqtt
from jsonschema import validate

# --- Paths & config ---
ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas" / "electrolyser_packet_v1.json").read_text())
cfg = tomli.loads((pathlib.Path(__file__).with_name("settings_plant.toml")).read_text())
BROKER, CERTS, DEVICE = cfg["broker"], cfg["certs"], cfg["device"]

TOPIC = f'electrolyser/{DEVICE["site_id"]}/{DEVICE["device_id"]}/state'


class ElectrolyserPlantSim:
    """
    Simulates your physical setup:
      - PV → buck → 5-cell electrolyser stack
      - H₂ production + storage tank
      - Basic safety & noisy sensors
    """

    def __init__(self, dt: float = 1.0):
        self.dt = dt

        # --- PV model (simple but consistent with your ranges) ---
        self.G_max = 1000.0   # W/m2
        self.Isc_stc = 5.0    # A at 1000 W/m2
        self.Voc_stc = 40.0   # V
        self.T_ref = 25.0     # C
        self.pv_eff = 0.8     # overall derating

        # --- Electrolyser stack ---
        self.N = 5            # cells
        self.U_rev = 1.23     # V per cell
        self.R_ohm = 0.4      # ohm per cell-equivalent

        # --- Hydrogen tank model ---
        self.F = 96485.0      # C/mol
        self.eta_F = 0.95
        self.R = 8.314        # J/mol/K
        self.tank_volume_m3 = 0.02  # 20 L tank
        self.tank_temp_K = 298.0    # ~25°C
        self.n_h2 = 0.0             # mol

        # --- Control & safety limits ---
        self.I_ref = 1.8            # A (setpoint in CC region)
        self.V_cell_max = 2.2       # V, over-voltage limit
        self.P_tank_max_bar = 20.0  # bar, relief valve setpoint

        self.seq = 0

    # ---------- Subsystem models ----------

    def irradiance_profile(self, t_s: float) -> float:
        """
        Simple "day" profile: sinusoid over 24 h, 0..1000 W/m2.
        You can later replace this with real weather data.
        """
        day = 24.0 * 3600.0
        phase = (t_s % day) / day  # 0..1
        # 0 at night, 1 at peak
        g = math.sin(math.pi * phase * 2.0)
        g = max(0.0, g)
        return g * self.G_max

    def step(self, t_s: float) -> dict:
        # --- 1) Solar PV ---
        G = self.irradiance_profile(t_s)
        T = 25.0  # constant for now

        Isc = self.Isc_stc * (G / self.G_max)       # linear with irradiance
        Voc = self.Voc_stc * (1 - 0.004 * (T - self.T_ref))

        # --- 2) Buck converter current control (simplified) ---
        I_guess = self.I_ref
        V_stack_guess = self.N * (self.U_rev + self.R_ohm * I_guess)
        P_req = V_stack_guess * I_guess                   # power needed
        P_avail = Voc * Isc * self.pv_eff                 # power available

        if P_avail <= 0.0:
            I_stack = 0.0
        elif P_avail >= P_req:
            I_stack = self.I_ref                          # CC mode
        else:
            # solar-limited: reduce current to what PV can supply
            I_stack = max(0.0, P_avail / max(V_stack_guess, 1e-3))

        # --- 3) Electrolyser stack V-I characteristic ---
        V_stack = self.N * (self.U_rev + self.R_ohm * I_stack)

        # --- 4) Water flow sensor (with noise) ---
        base_water_flow = 1.2  # L/min nominal
        water_flow = base_water_flow + random.uniform(-0.2, 0.2)

        # --- 5) Cell voltages with noise ---
        cell_voltage_nom = V_stack / self.N if self.N > 0 else 0.0
        cell_voltages = [
            cell_voltage_nom + random.uniform(-0.05, 0.05)
            for _ in range(self.N)
        ]

        status = "OPERATIONAL"

        # --- 6) Safety logic: over-voltage ---
        if any(v > self.V_cell_max for v in cell_voltages):
            status = "TRIP_OVERVOLT"
            I_stack = 0.0
            V_stack = self.N * self.U_rev
            cell_voltage_nom = V_stack / self.N
            cell_voltages = [
                cell_voltage_nom + random.uniform(-0.02, 0.02)
                for _ in range(self.N)
            ]

        # --- 7) Safety logic: low water cut-off ---
        if water_flow < 0.5:
            status = "TRIP_LOW_WATER"
            I_stack = 0.0
            V_stack = self.N * self.U_rev

        # --- 8) Hydrogen production (Faraday’s law) ---
        n_dot = self.eta_F * self.N * I_stack / (2.0 * self.F)  # mol/s
        self.n_h2 += n_dot * self.dt

        # Tank pressure via ideal gas
        P_Pa = self.n_h2 * self.R * self.tank_temp_K / self.tank_volume_m3
        P_bar = P_Pa / 1e5

        # --- 9) Safety: over-pressure relief valve ---
        if P_bar > self.P_tank_max_bar:
            status = "RELIEF_VALVE_OPEN"
            self.n_h2 *= 0.9  # vent some gas
            P_Pa = self.n_h2 * self.R * self.tank_temp_K / self.tank_volume_m3
            P_bar = P_Pa / 1e5

        # Flow rate in L/min for telemetry
        h2_flow_mol_s = n_dot
        mol_to_L = 22.414   # L/mol at STP
        h2_flow_L_min = h2_flow_mol_s * mol_to_L * 60.0

        # Noisy physical sensors
        tank_pressure = P_bar + random.uniform(-0.1, 0.1)
        temperature = 45.0 + random.uniform(-1.0, 1.0)

        # --- 10) Telemetry packet ---
        self.seq += 1

        packet = {
            "device_id": DEVICE["device_id"],
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "status": status,
            "electrical": {
                "total_voltage": round(V_stack, 3),
                "stack_current": round(I_stack, 3),
                "cell_voltages": [round(v, 3) for v in cell_voltages]
            },
            "physical": {
                "h2_flow_rate": round(h2_flow_L_min, 4),
                "tank_pressure": round(tank_pressure, 3),
                "water_flow": round(water_flow, 3),
                "temperature": round(temperature, 2)
            },
            "security": {
                "sequence_id": self.seq,
                "hash": ""
            }
        }

        # Validate shape
        validate(packet, SCHEMA)

        # --- 11) Hash over canonical JSON (without hash field) ---
        packet_no_hash = json.loads(json.dumps(packet))     # deep copy
        packet_no_hash["security"]["hash"] = None
        canonical = json.dumps(
            packet_no_hash,
            sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")
        digest = hashlib.sha256(canonical).hexdigest()
        packet["security"]["hash"] = digest

        return packet


def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Connected:", reason_code)


def main() -> None:
    sim = ElectrolyserPlantSim(dt=1.0)

    client = mqtt.Client(client_id=DEVICE["client_cn"], protocol=mqtt.MQTTv5)
    client.tls_set(
        ca_certs=(ROOT / CERTS["ca"]).as_posix(),
        certfile=(ROOT / CERTS["cert"]).as_posix(),
        keyfile=(ROOT / CERTS["key"]).as_posix(),
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    client.tls_insecure_set(False)
    client.on_connect = on_connect
    client.connect(BROKER["host"], BROKER["port"], keepalive=30)

    client.loop_start()
    t_s = 0.0
    try:
        while True:
            packet = sim.step(t_s)
            payload = json.dumps(packet).encode("utf-8")
            r = client.publish(TOPIC, payload, qos=1)
            r.wait_for_publish()
            print(
                f"plant seq={packet['security']['sequence_id']} "
                f"status={packet['status']} rc={r.rc}"
            )
            t_s += sim.dt
            time.sleep(sim.dt)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
