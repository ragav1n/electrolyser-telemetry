
# Electrolyser Telemetry System 

## Prototype for Secure, End-to-End Telemetry in Renewable-Powered Hydrogen Electrolysers

---

### 📘 Overview

**Electrolyser-Telemetry** is a fully modular, open-source prototype for secure, real-time telemetry in a green hydrogen electrolyser farm.  
It simulates **100+ IoT sensors** measuring critical process and renewable parameters such as:

- Solar irradiance 
- Wind speed 
- Stack temperature  
- Electrolyte conductivity 
- Pressure & flow rates 
- H₂ purity, O₂ crossover, dew point, current, and voltage 

Each simulated device publishes **encrypted JSON payloads via MQTT over TLS 1.3 with mutual authentication (mTLS)**, ensuring **end-to-end confidentiality and integrity** from edge to cloud.

---

### 🧩 Architecture

```
+---------------------+      +-------------------+      +------------------+      +----------------+
|  Simulated Sensors  | ---> |  MQTT Broker (mTLS)| --> | Telegraf Collector | --> | InfluxDB v2.7  |
| (ESP32/Python Paho) |      |  Dockerized Mosquitto |  | (MQTT → JSON → DB) |      |  Time-series DB |
+---------------------+      +-------------------+      +------------------+      +--------+-------+
                                                                                          |
                                                                                          v
                                                                                   +--------------+
                                                                                   | Grafana 11.2 |
                                                                                   |   Dashboards |
                                                                                   +--------------+
```

#### Key Security Components

| Component | Mechanism |
|---------|-----------|
| **Transport** | TLS 1.3 + mTLS — both client and broker authenticate using X.509 certs |
| **Access Control** | Mosquitto ACLs — per-client topic restrictions (publish/read) |
| **Confidentiality** | AES-256 (optional) — payload-level symmetric encryption layer |
| **Reliability** | QoS 1 — guarantees at-least-once delivery |
| **Certificate Rotation** | `rotate-certs.sh` — automated re-issuance of expiring certs |
| **Validation** | JSON Schema v2020-12 — enforces telemetry format consistency |

---

### Directory Structure

```
electrolyser-telemetry/
├── docker-compose.yml          # Mosquitto + InfluxDB + Telegraf + Grafana stack
├── Makefile                    # one-touch automation for certs & services
├── certs/                      # CA, broker, and client certificates (gitignored)
├── mosquitto/
│   ├── conf/mosquitto.conf     # TLS 1.3, mTLS, ACLs
│   ├── conf/aclfile
│   └── data/
├── scripts/pki/                # CA/broker/client/rotation shell scripts
├── clients/python/             # Sensor simulators (H₂ purity, solar irradiance, etc.)
├── schemas/telemetry_v1.json   # JSON schema for telemetry validation
├── telegraf/telegraf.conf      # MQTT → Influx pipeline
├── grafana/                    # Provisioned datasources & dashboards
└── tests/                      # Pytest schema validation
```

---

### Quick Start

#### 1️⃣ Prerequisites
- Docker + Docker Compose
- Python 3.10+
- OpenSSL (for PKI scripts)

#### 2️⃣ Clone and Setup

```bash
git clone https://github.com/<yourusername>/electrolyser-telemetry.git
cd electrolyser-telemetry
cp .env.example .env      # or define your own credentials
```

#### 3️⃣ Generate Certificates

```bash
make ca
make broker
make client CN=sensor-h2_purity-03
make client CN=sensor-solar_irradiance-03
make client CN=telegraf-subscriber
```

Update ACLs:

```bash
cat >> mosquitto/conf/aclfile <<'EOF'
user sensor-h2_purity-03
topic write electrolyser/rvce-plant-A/stack-03/h2_purity/telemetry
user sensor-solar_irradiance-03
topic write electrolyser/rvce-plant-A/stack-03/solar_irradiance/telemetry
user telegraf-subscriber
topic read electrolyser/#
EOF
chmod 700 mosquitto/conf/aclfile
```

#### 4️⃣ Launch Secure Stack

```bash
make up
docker compose up -d influxdb telegraf grafana
```

**Services**  
- **Mosquitto (mTLS):** `mqtts://localhost:8883`  
- **InfluxDB:** `http://localhost:8086`  
- **Grafana:** `http://localhost:3000` (admin/admin)

#### 5️⃣ Run Sensor Simulators

```bash
make sim                            # H₂ purity
python clients/python/publisher_solar.py  # Solar irradiance
```

**Example JSON Payload:**

```json
{
  "ts": "2025-11-12T19:12:36.254Z",
  "site_id": "rvce-plant-A",
  "stack_id": "stack-03",
  "sensor_id": "h2_purity",
  "metrics": {"value": 99.92, "unit": "%"},
  "quality": {"qos": 1, "status": "OK", "seq": 12},
  "meta": {"firmware": "sim-0.1.0", "simulated": true}
}
```

#### 6️⃣ View Live Dashboards

1. Visit [http://localhost:3000](http://localhost:3000)  
2. Login → InfluxDB datasource is **pre-provisioned**  
3. Open dashboard: **“Electrolyser Telemetry”**

**You’ll see:**  
- Real-time H₂ purity (%)  
- Solar irradiance (W/m²)  
- Derived H₂ yield proxy vs irradiance  

---

### Testing

Run JSON schema validation:

```bash
make test
```

---

### Security Model

| Layer | Mechanism | Description |
|------|-----------|-----------|
| **Transport** | TLS 1.3 + mTLS | Both client and broker authenticate using X.509 certs |
| **Access Control** | Mosquitto ACLs | Per-client topic restrictions (publish/read) |
| **Confidentiality** | AES-256 (optional) | Payload-level symmetric encryption layer |
| **Reliability** | QoS 1 | Guarantees at-least-once delivery |
| **Certificate Rotation** | `rotate-certs.sh` | Automated re-issuance of expiring certs |
| **Validation** | JSON Schema v2020-12 | Enforces telemetry format consistency |

---

### Grafana Dashboards

| Panel | Description |
|------|-------------|
| **H₂ Purity (%)** | From `sensor-h2_purity-03` |
| **Solar Irradiance (W/m²)** | From `sensor-solar_irradiance-03` |
| **H₂ Yield Proxy vs Irradiance** | Demonstrates renewable–hydrogen correlation |

> Dashboards **auto-refresh every 5s** for near-real-time insight.

---

### Developer Notes

- PKI is **self-contained and idempotent**.  
  Re-run with `FORCE=1 make ca` only when you **intentionally rotate the CA**.
- ACLs are **explicit** for auditability; patterns can be scripted.
- Telemetry schema supports **future extension** (v2 planned with AES envelope).
- `Makefile` targets handle local testing: `sim`, `test`, `up`, `down`.

---

### Future Enhancements

- Fault-injection test harness (`pytest`, `locust`, `fault_injector.py`)
- Automated certificate renewal (rotation without downtime)
- AES-GCM payload encryption and integrity tag validation
- Integration with **AWS IoT Core / Greengrass bridge**
- Predictive analytics for yield optimization


