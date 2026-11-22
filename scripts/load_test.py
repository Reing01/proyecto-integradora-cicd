"""Medición breve de lectura autenticada, no certificación de capacidad."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import math
import time
import release


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--env', choices=['staging', 'production'], default='staging')
    parser.add_argument('--requests', type=int, default=200)
    parser.add_argument('--concurrency', type=int, default=10)
    args = parser.parse_args()
    if not 1 <= args.requests <= 10000 or not 1 <= args.concurrency <= 50:
        parser.error('requests debe estar entre 1 y 10000; concurrency entre 1 y 50')
    config = release.read_env(release.initialize(args.env))
    base = 'http://127.0.0.1:' + config['APP_PORT']

    def read(index):
        start = time.perf_counter()
        try:
            status = release.http(base, '/api/products', config['API_TOKEN'])[0]
        except OSError:
            status = 599
        return status, time.perf_counter() - start

    start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        results = list(pool.map(read, range(args.requests)))
    elapsed = time.perf_counter() - start
    latencies = sorted(duration for _, duration in results)
    print(json.dumps({'environment': args.env, 'requests': args.requests, 'concurrency': args.concurrency,
        'successful': sum(status == 200 for status, _ in results),
        'server_errors': sum(status >= 500 for status, _ in results),
        'p95_ms': round(latencies[math.ceil(len(latencies) * .95) - 1] * 1000, 2),
        'throughput_rps': round(args.requests / elapsed, 2),
        'duration_seconds': round(elapsed, 2)}, indent=2))
    if any(status != 200 for status, _ in results):
        raise SystemExit(1)


if __name__ == '__main__':
    main()
