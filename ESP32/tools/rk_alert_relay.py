"""Forward existing RK alarm JPEGs without entering the video processing path."""
import argparse
import hashlib
import json
import logging
from pathlib import Path
import time

from gateway_client import Gateway, configured_token


def send(gateway, source, directory):
    record = json.loads(source.read_text(encoding="utf-8"))
    identifier = record["id"]
    image = directory / Path(record.get("image", identifier + ".jpg")).name
    metadata = dict(event_id=identifier, camera=str(record["camera"]),
                    reason=record["reason"], event_time=record["timestamp"],
                    confidence=record.get("confidence"))
    gateway.alert(metadata, image)
    received = gateway.request("GET", "/v1/alerts/" + identifier + "/image")
    digest = hashlib.sha256(image.read_bytes()).hexdigest()
    if hashlib.sha256(received).hexdigest() != digest:
        raise RuntimeError("uploaded JPEG checksum mismatch")
    return dict(event_id=identifier, camera=metadata["camera"], bytes=len(received),
                sha256=digest, verified=True)


def save(path, state):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(state), encoding="utf-8")
    temp.replace(path)


def catalog(directory):
    path = directory / "index.tsv"
    return [line.split()[0].split(".")[0] for line in path.read_text().splitlines() if line.split()] if path.exists() else []


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--url", default="http://192.168.50.1")
    parser.add_argument("--bootstrap", type=int, default=8)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    gateway = Gateway(args.url, configured_token(), timeout=15)
    args.state.parent.mkdir(parents=True, exist_ok=True)
    if args.state.exists():
        state = json.loads(args.state.read_text())
    else:
        known = [p.stem for p in args.directory.glob("*.json")]
        recent = []
        for identifier in catalog(args.directory):
            try:
                record = json.loads((args.directory / (identifier + ".json")).read_text())
                if (args.directory / Path(record["image"]).name).stat().st_size:
                    recent.append(identifier)
            except (OSError, ValueError, KeyError):
                continue
        state = dict(known=known, pending=recent[:args.bootstrap], done=[])
        save(args.state, state)
    known = set(state["known"])
    scan_at = 0
    retry_at = {}
    while True:
        try:
            # Atomic catalog updates make the frequent poll cheap. Reconcile all
            # metadata each minute to recover from a skipped catalog generation.
            ids = catalog(args.directory)
            if time.monotonic() >= scan_at:
                ids += [p.stem for p in args.directory.glob("*.json")]
                scan_at = time.monotonic() + 60
            for identifier in ids:
                if identifier not in known:
                    known.add(identifier)
                    state["known"].append(identifier)
                    state["pending"].append(identifier)
                    save(args.state, state)
            for identifier in list(state["pending"]):
                if time.monotonic() < retry_at.get(identifier, 0):
                    continue
                source = args.directory / (identifier + ".json")
                try:
                    result = send(gateway, source, args.directory)
                except (OSError, ValueError, KeyError, RuntimeError) as error:
                    logging.warning("alarm %s remains queued: %s", identifier, error)
                    if args.once:
                        raise
                    retry_at[identifier] = time.monotonic() + 30
                    continue
                state["done"].append(identifier)
                state["pending"].remove(identifier)
                save(args.state, state)
                logging.info("alarm delivered %s", json.dumps(result, ensure_ascii=False))
                time.sleep(.25)
            if args.once:
                return
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            logging.warning("alarm relay retry: %s", error)
            if args.once:
                raise
            time.sleep(8)
        time.sleep(2)


if __name__ == "__main__":
    main()
