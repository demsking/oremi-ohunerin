# Copyright 2026 Sébastien Demanou. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Event-loop responsiveness and throughput benchmark for the Ohunerin server.

Simulates concurrent WebSocket sessions streaming raw PCM at the rate produced
by ``client.py`` and measures pipeline throughput plus event-loop scheduling
lag. A lag spike means the event loop was blocked, typically by synchronous
inference.

Prerequisite: ``models/yamnet.tflite`` (see ``scripts/install-model.sh``).

Usage (from the repository root)::

  .venv/bin/python benchmarks/bench_server.py --connections 4 --windows 6
  .venv/bin/python benchmarks/bench_server.py --threads 20 --json
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine
from ohunerin.models.sound import SoundsConfig
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.server import Server

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = BASE_DIR / "models" / "yamnet.tflite"
DEFAULT_CONFIG = BASE_DIR / "config.json"
WINDOW_BYTES = 15600


class MockRequest:
  """Minimal stand-in for websockets.http11.Request."""

  def __init__(self, path: str) -> None:
    self.path = path
    self.headers = {"User-Agent": "bench"}


class MockConnection:
  """Minimal async-iterable WebSocket replacement: no sockets, no network I/O."""

  def __init__(self, chunks: list[bytes]) -> None:
    self.request = MockRequest("/ws")
    self.remote_address = ("127.0.0.1", 0)
    self._chunks = chunks
    self._index = 0
    self.sent = 0
    self.closed_code: int | None = None
    self.closed_reason: str | None = None

  @property
  def close_code(self) -> int | None:
    return self.closed_code

  @property
  def close_reason(self) -> str | None:
    return self.closed_reason

  def __aiter__(self):
    return self

  async def __anext__(self) -> bytes:
    if self._index >= len(self._chunks):
      raise StopAsyncIteration

    chunk = self._chunks[self._index]
    self._index += 1
    return chunk

  async def send(self, message: object) -> None:
    self.sent += 1

  async def close(self, code: int, reason: str = "") -> None:
    self.closed_code = code


async def sample_loop_lag(stop: asyncio.Event, interval: float, lags: list[float]) -> None:
  """Record how late a 1 ms timer fires; a large lag means the loop was blocked."""
  loop = asyncio.get_running_loop()

  while not stop.is_set():
    started = loop.time()
    await asyncio.sleep(interval)
    lags.append(loop.time() - started - interval)


async def legacy_inline_loop(connection: MockConnection, consumer: DetectorConsumer) -> None:
  """Reproduce the pre-optimization sound loop: inference inline on the loop."""
  async for chunk in connection:
    sound, score = consumer.process_raw(chunk)  # type: ignore[union-attr]

    if sound:
      await connection.send(json.dumps({"type": "sound", "sound": sound, "score": score}))


def summarize(samples: list[float]) -> dict[str, float]:
  """Summarize a list of second-based durations in milliseconds."""
  ordered = sorted(samples)
  index = min(len(ordered) - 1, int(len(ordered) * 0.95))

  return {
    "n": len(ordered),
    "median_ms": round(statistics.median(ordered) * 1e3, 4),
    "p95_ms": round(ordered[index] * 1e3, 4),
    "max_ms": round(ordered[-1] * 1e3, 4),
  }


async def run(args: argparse.Namespace) -> dict[str, object]:
  """Run ``args.connections`` simulated sessions and return a report."""
  if not args.model.is_file():
    raise SystemExit(f"model file not found: {args.model} (run ./scripts/install-model.sh)")

  raw = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
  wakewords_config = WakewordsConfig.model_validate(raw.get("wakewords", []))
  sounds_config = SoundsConfig.model_validate(raw.get("sounds", {}))
  server = Server(
    wakewords_config=wakewords_config,
    sounds_config=sounds_config,
    threshold=args.threshold,
    model=args.model,
  )

  rng = np.random.default_rng(args.seed)
  chunk = rng.integers(-32768, 32767, size=args.chunk_bytes // 2, dtype=np.int16).tobytes()
  chunks_per_window = -(-WINDOW_BYTES // args.chunk_bytes)
  chunk_count = args.windows * chunks_per_window

  connections = [MockConnection([chunk] * chunk_count) for _ in range(args.connections)]

  if args.threads > 0:
    engine = DetectorEngine(args.model, score_threshold=args.threshold, num_threads=args.threads)
    consumers = [DetectorConsumer(engine) for _ in connections]
  else:
    # Exercise the real server path: one shared engine configured with
    # recommended_num_threads() and one consumer per connection.
    consumers = [server.get_detector_consumer() for _ in connections]  # type: ignore[union-attr]

  lags: list[float] = []
  stop = asyncio.Event()
  ticker = asyncio.create_task(sample_loop_lag(stop, 0.001, lags))

  if args.legacy_inline:
    run_one = legacy_inline_loop
  else:
    async def run_one(connection, consumer):  # type: ignore[misc]
      await server._handle_audio_data(connection, None, consumer)  # type: ignore[arg-type]

  started = time.perf_counter()
  await asyncio.gather(*(run_one(connection, consumer) for connection, consumer in zip(connections, consumers)))
  elapsed = time.perf_counter() - started

  stop.set()
  await ticker

  windows_requested = args.connections * args.windows
  detections = sum(connection.sent for connection in connections)

  return {
    "connections": args.connections,
    "legacy_inline": args.legacy_inline,
    "threads": args.threads or server.http_handler.detector_threads,
    "windows_requested": windows_requested,
    "detections": detections,
    "elapsed_s": round(elapsed, 4),
    "windows_per_second": round(windows_requested / elapsed, 2),
    "loop_lag": summarize(lags),
  }


def main() -> None:
  parser = argparse.ArgumentParser(description="Ohunerin server throughput and event-loop lag benchmark.")
  parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path to yamnet.tflite.")
  parser.add_argument("--connections", type=int, default=4, help="Concurrent simulated sessions.")
  parser.add_argument("--windows", type=int, default=6, help="Detection windows per session.")
  parser.add_argument(
    "--threads",
    type=int,
    default=0,
    help="TFLite interpreter thread count; 0 uses the server recommended default.",
  )
  parser.add_argument("--chunk-bytes", type=int, default=8000, help="Client chunk size in bytes.")
  parser.add_argument("--threshold", type=float, default=0.1, help="Detection score threshold.")
  parser.add_argument("--seed", type=int, default=0, help="PRNG seed for the synthetic audio.")
  parser.add_argument(
    "--legacy-inline",
    action="store_true",
    help="Reproduce the pre-optimization loop that runs inference on the event loop.",
  )
  parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
  args = parser.parse_args()

  report = asyncio.run(run(args))

  if args.json:
    print(json.dumps(report, indent=2))
    return

  lag = report["loop_lag"]  # type: ignore[assignment]
  print(
    f"connections={report['connections']} threads={report['threads']} "
    f"windows={report['windows_requested']} detections={report['detections']}"
  )
  print(
    f"elapsed={report['elapsed_s']}s  throughput={report['windows_per_second']} windows/s"
  )
  print(
    f"event-loop lag: median={lag['median_ms']}ms p95={lag['p95_ms']}ms max={lag['max_ms']}ms"
  )


if __name__ == "__main__":
  sys.exit(main())
