import json, os, ssl, time, tomli, pathlib, datetime, random
from paho.mqtt import client as mqtt
from jsonschema import validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "schemas" / "telemetry_v1.json").read_text())

cfg = tomli.loads((pathlib.Path(__file__).with_name("settings.example.toml")).read_text())
BROKER = cfg["broker"]
IDENT = cfg["identity"]
CERTS = cfg["certs"]
PUB = cfg["publish"]

topic = f'electrolyser/{IDENT["site_id"]}/{IDENT["stack_id"]}/{IDENT["sensor_id"]}/telemetry'

def make_payload(seq:int):
    value = round(random.uniform(99.6, 99.99), 3)  # h2 purity %
    payload = {
        "ts": datetime.datetime.utcnow().replace(tzinfo=datetime.timezone.utc).isoformat(),
        "site_id": IDENT["site_id"],
        "stack_id": IDENT["stack_id"],
        "sensor_id": IDENT["sensor_id"],
        "metrics": {"value": value, "unit": "%"},
        "quality": {"qos": PUB["qos"], "status": "OK", "seq": seq},
        "meta": {"firmware": "sim-0.1.0", "simulated": True}
    }
    validate(payload, SCHEMA)
    return json.dumps(payload).encode("utf-8")

def on_connect(client, userdata, flags, reason_code, properties=None):
    print("Connected:", reason_code)

def main():
    client = mqtt.Client(client_id=IDENT["client_cn"], protocol=mqtt.MQTTv5)
    client.tls_set(
        ca_certs=CERTS["ca"],
        certfile=CERTS["cert"],
        keyfile=CERTS["key"],
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    client.tls_insecure_set(False)
    client.on_connect = on_connect
    client.connect(BROKER["host"], BROKER["port"], keepalive=30)

    seq = 0
    client.loop_start()
    try:
        while True:
            payload = make_payload(seq)
            r = client.publish(topic, payload, qos=PUB["qos"], retain=False)
            r.wait_for_publish()
            print(f"pub seq={seq} rc={r.rc}")
            seq += 1
            time.sleep(PUB["interval_seconds"])
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()

