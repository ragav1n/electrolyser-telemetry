# Electrolyser Telemetry System

## Overview
A comprehensive digital twin and telemetry solution for monitoring Green Hydrogen Electrolyser plants. This system simulates the operation of multiple electrolysers powered by renewable energy (PV), captures high-frequency sensor data, and provides real-time visualization and analytics.

## Architecture
![System Architecture](Electrolyser_sys_arch.png)

The system follows a robust IoT architecture:
1.  **Sensor Simulation**: Python-based digital twins (`plant_sim.py`) simulate the physics of the electrolyser stack, including:
    -   PV Irradiance & Power generation.
    -   Buck Converter logic (Voltage/Current regulation).
    -   Electrochemical reaction (Faraday's Law).
    -   Gas processing (H2/O2 flow, Tank pressure).
    -   Safety logic (Over-voltage, Over-pressure trips).
2.  **Message Broker**: **Mosquitto** (MQTT) serves as the central nervous system, handling data ingestion from sensors.
    -   **Security**: Enforced Mutual TLS (mTLS) for all clients.
    -   **Authorization**: ACL-based topic restrictions.
3.  **Telemetry Agent**: **Telegraf** subscribes to MQTT topics, parses JSON payloads, and writes metrics to the database.
4.  **Time-Series Database**: **InfluxDB** stores high-resolution sensor data.
5.  **Visualization**: **Grafana** provides interactive dashboards for monitoring plant performance.

## Implemented Components

### 1. Digital Twin Simulation
-   **Multi-Electrolyser Support**: Simulates two distinct units (EL1, EL2) and a shared plant environment.
-   **Physics-Based Modeling**: Realistic correlation between Irradiance -> Current -> Voltage -> Temperature -> Gas Flow -> Pressure.
-   **Noise & Randomness**: Simulates real-world sensor noise, efficiency variations, and environmental fluctuations.
-   **Security**: Each sensor uses a unique X.509 client certificate for authentication.

### 2. Secure Telemetry Pipeline
-   **mTLS Everywhere**: All connections (Sensors -> Broker, Telegraf -> Broker) are encrypted and authenticated using a custom PKI.
-   **Topic Structure**: Hierarchical topics for organized data flow:
    -   `electrolyser/plant-A/EL1/cell/1/voltage`
    -   `electrolyser/plant-A/EL1/stack/current`
    -   `electrolyser/plant-A/irradiance/1`
-   **Certificate Rotation**: Automated script (`scripts/pki/rotate-cert.sh`) to rotate client certificates.
    -   Rotate single: `./scripts/pki/rotate-cert.sh <CN>`
    -   Rotate all: `./scripts/pki/rotate-cert.sh all`
    -   *Note*: Old certificates are backed up to a timestamped directory (e.g., `backup_YYYYMMDD_HHMMSS`) within the client folder and are gitignored.

### 3. Observability Stack
-   **Dockerized Deployment**: The entire stack (Mosquitto, InfluxDB, Telegraf, Grafana) runs in Docker containers.
-   **Automated Provisioning**:
    -   Grafana dashboards are automatically provisioned from JSON.
    -   InfluxDB buckets and tokens are configured on startup.
-   **Dashboards**:
    -   **Electrolyser Comparative**: Real-time comparison of EL1 vs EL2 performance, including efficiency, yield, and safety metrics.

## Key Features
-   **Real-time Monitoring**: Sub-second latency from sensor to dashboard.
-   **Historical Analysis**: Long-term data retention in InfluxDB.
-   **Scalable Design**: Decoupled architecture allows adding more sensors or plants easily.
-   **Enterprise Security**: Industry-standard TLS 1.2+ and Certificate-based identity.


