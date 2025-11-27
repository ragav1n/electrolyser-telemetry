import ssl
import json
import time
import random
import argparse
import pathlib
from paho.mqtt import client as mqtt

ROOT = pathlib.Path(__file__).resolve().parents[2]

def generate_value(sensor):
    if sensor == "voltage":
        return round(9.8 + random.uniform(-0.1, 0.1), 3)
    if sensor == "current":
        return round(1.8 + random.uniform(-0.05, 0.05), 3)
    if sensor == "gas_flow":
        return round(0.40 + random.uniform(-0.05, 0.05), 4)
    if sensor == "temperature":
        return round(45.0 + random.uniform(-1.5, 1.5), 2)
    if sensor == "pressure":
        return round(12.0 + random.uniform(-0.3, 0.3), 2)
    return 0.0

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sensor", required=True)
    parser.add_argument("--cn", required=True)
    args = parser.parse_args()

    topic = f"electrolyser/sensors/{args.sensor}"
    
    # Certificate paths
    ca = ROOT / "certs/ca/ca.crt"
    cert = ROOT / f"certs/clients/{args.cn}/client.crt"
    key = ROOT / f"certs/clients/{args.cn}/client.key"

    client = mqtt.Client(client_id=args.cn, protocol=mqtt.MQTTv5)

    client.tls_set(
        ca_certs=str(ca),
        certfile=str(cert),
        keyfile=str(key),
        tls_version=ssl.PROTOCOL_TLS_CLIENT
    )

    client.tls_insecure_set(False)
    client.connect("127.0.0.1", 8883, 60)
    client.loop_start()

    seq = 0
    while True:
        value = generate_value(args.sensor)
        payload = {
            "sensor": args.sensor,
            "timestamp": time.time(),
            "value": value,
            "sequence_id": seq
        }
        client.publish(topic, json.dumps(payload), qos=1)
        print(f"{args.sensor} → {value}")
        seq += 1
        time.sleep(1)

if __name__ == "__main__":
    main()
