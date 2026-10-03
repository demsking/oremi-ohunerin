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
"""Micro-benchmarks for the Ohunerin sound-detection pipeline.

Measures every stage of the per-window path (PCM -> ndarray -> TensorAudio ->
TFLite -> label) plus the per-chunk cost of ``DetectorConsumer.process_raw``.

Prerequisite: ``models/yamnet.tflite`` (see ``scripts/install-model.sh``).

Usage (from the repository root)::

  .venv/bin/python benchmarks/bench_pipeline.py
  .venv/bin/python benchmarks/bench_pipeline.py --threads 20 --json
  .venv/bin/python benchmarks/bench_pipeline.py --chunk-bytes 8000
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from ohunerin.audio.processing import to_ndarray
from ohunerin.engines.detector import DetectorConsumer
from ohunerin.engines.detector import DetectorEngine

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = BASE_DIR / "models" / "yamnet.tflite"


def percentiles(samples: list[float]) -> dict[str, float]:
  """Return min/median/p95/max for a list of second-based durations in milliseconds."""
  ordered = sorted(samples)
  index = min(len(ordered) - 1, int(len(ordered) * 0.95))

  return {
    "n": len(ordered),
    "min_ms": round(ordered[0] * 1e3, 4),
    "median_ms": round(statistics.median(ordered) * 1e3, 4),
    "p95_ms": round(ordered[index] * 1e3, 4),
    "max_ms": round(ordered[-1] * 1e3, 4),
  }


def measure(fn, repeat: int, warmup: int) -> dict[str, float]:
  """Time ``fn`` after ``warmup`` calls and summarize the ``repeat`` samples."""
  for _ in range(warmup):
    fn()

  samples: list[float] = []

  for _ in range(repeat):
    started = time.perf_counter()
    fn()
    samples.append(time.perf_counter() - started)

  return percentiles(samples)


def run(args: argparse.Namespace) -> dict[str, object]:
  """Execute every stage benchmark and return a JSON-serializable report."""
  if not args.model.is_file():
    raise SystemExit(f"model file not found: {args.model} (run ./scripts/install-model.sh)")

  rng = np.random.default_rng(args.seed)
  window_bytes = 15600
  pcm = rng.integers(-32768, 32767, size=window_bytes // 2, dtype=np.int16)
  window = pcm.tobytes()
  chunk = rng.integers(-32768, 32767, size=args.chunk_bytes // 2, dtype=np.int16).tobytes()

  report: dict[str, object] = {
    "threads": args.threads,
    "repeat": args.repeat,
    "chunk_bytes": len(chunk),
    "window_bytes": window_bytes,
  }

  engine = DetectorEngine(args.model, score_threshold=0.1, num_threads=args.threads)
  report["required_input_buffer_size"] = engine.classifier.required_input_buffer_size

  audio_format = engine.classifier.required_audio_format
  report["required_audio_format"] = {
    "sample_rate": audio_format.sample_rate,
    "channels": audio_format.channels,
  }

  warm_array = to_ndarray(window, 1)
  engine.tensor_audio.load_from_array(warm_array)

  stages: dict[str, dict[str, float]] = {}
  stages["to_ndarray"] = measure(lambda: to_ndarray(window, 1), args.repeat, 10)
  stages["load_from_array"] = measure(lambda: engine.tensor_audio.load_from_array(warm_array), args.repeat, 10)
  stages["classify"] = measure(lambda: engine.classifier.classify(engine.tensor_audio), args.repeat, 3)

  if hasattr(engine, "classify_window"):
    stages["classify_window"] = measure(lambda: engine.classify_window(warm_array), args.repeat, 3)
  else:
    def legacy_window():
      engine.tensor_audio.load_from_array(warm_array)
      return engine.classifier.classify(engine.tensor_audio)

    stages["classify_window"] = measure(legacy_window, args.repeat, 3)

  consumer = DetectorConsumer(engine)

  def buffered_chunk():
    consumer.process_raw(chunk)
    consumer.reset_buffer()

  stages["process_raw_buffering"] = measure(buffered_chunk, max(args.repeat, 200), 10)

  def full_window():
    consumer.reset_buffer()
    return consumer.process_raw(window)

  stages["process_raw_window"] = measure(full_window, args.repeat, 3)
  report["stages"] = stages
  report["engine_create"] = measure(
    lambda: DetectorEngine(args.model, score_threshold=0.1, num_threads=args.threads),
    5,
    1,
  )

  return report


def main() -> None:
  parser = argparse.ArgumentParser(description="Ohunerin sound-detection pipeline micro-benchmarks.")
  parser.add_argument("--model", type=Path, default=DEFAULT_MODEL, help="Path to yamnet.tflite.")
  parser.add_argument("--threads", type=int, default=4, help="TFLite interpreter thread count.")
  parser.add_argument("--repeat", type=int, default=30, help="Timed repetitions per stage.")
  parser.add_argument("--chunk-bytes", type=int, default=8000, help="Simulated client chunk size in bytes.")
  parser.add_argument("--seed", type=int, default=0, help="PRNG seed for the synthetic audio.")
  parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
  args = parser.parse_args()

  report = run(args)

  if args.json:
    print(json.dumps(report, indent=2))
    return

  print(f"model={args.model} threads={args.threads} repeat={args.repeat} chunk={args.chunk_bytes}B")
  print(f"required_input_buffer_size={report['required_input_buffer_size']}")

  for name, stats in report["stages"].items():  # type: ignore[union-attr]
    print(f"{name:28s} median={stats['median_ms']:10.4f}ms  p95={stats['p95_ms']:10.4f}ms")

  create = report["engine_create"]  # type: ignore[assignment]
  print(f"{'engine_create':28s} median={create['median_ms']:10.4f}ms  p95={create['p95_ms']:10.4f}ms")


if __name__ == "__main__":
  sys.exit(main())
