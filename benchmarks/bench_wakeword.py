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
"""Wake-word (PocketSphinx) benchmarks.

Measures decoder construction cost and resident memory, plus the per-chunk cost
of ``WakewordEngine.process_raw`` on silence and on noise. The CMU Sphinx models
are tracked in the repository, so no download is required.

Usage (from the repository root)::

  .venv/bin/python benchmarks/bench_wakeword.py
  .venv/bin/python benchmarks/bench_wakeword.py --language en --json
"""
import argparse
import json
import statistics
import sys
import time
from pathlib import Path

import numpy as np

from ohunerin.engines.wakeword import WakewordEngine
from ohunerin.engines.wakeword import WakewordPool
from ohunerin.models.wakeword import DictionaryEntry
from ohunerin.models.wakeword import WakewordsConfig
from ohunerin.models.wakeword import WakewordSetting
from ohunerin.server.http import LANGUAGE_MODEL_PATHS

BASE_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = BASE_DIR / "models"
DEFAULT_CONFIG = BASE_DIR / "config.json"


def rss_mb() -> float:
  """Return the current resident set size in MiB (Linux); 0.0 elsewhere."""
  try:
    with open("/proc/self/status", encoding="utf-8") as file:
      for line in file:
        if line.startswith("VmRSS:"):
          return int(line.split()[1]) / 1024.0
  except OSError:  # pragma: no cover - non-Linux platforms
    return 0.0

  return 0.0


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


def build_setting(language: str, raw_config: dict) -> WakewordSetting:
  """Resolve the acoustic model, dictionary and keyphrases for ``language``."""
  model_rel, dict_rel = LANGUAGE_MODEL_PATHS.get(
    language,
    (f"wakeword-{language}/acoustic-model", f"wakeword-{language}/pronounciation-dictionary.dict"),
  )
  config = WakewordsConfig.model_validate(raw_config.get("wakewords", []))
  entries = [entry for entry in config.wakewords if entry.language == language]

  return WakewordSetting(
    model=str(MODELS_DIR / model_rel),
    dictionary=str(MODELS_DIR / dict_rel),
    wakewords=[DictionaryEntry(word=entry.word, phones=entry.phones) for entry in entries],
    discriminants=[discriminant for entry in entries for discriminant in entry.discriminants],
  )


def run(args: argparse.Namespace) -> dict[str, object]:
  """Run every wake-word benchmark and return a JSON-serializable report."""
  raw_config = json.loads(DEFAULT_CONFIG.read_text(encoding="utf-8"))
  setting = build_setting(args.language, raw_config)

  before = rss_mb()
  started = time.perf_counter()
  engine = WakewordEngine(setting)
  create_s = time.perf_counter() - started
  created_mb = rss_mb() - before

  silence = b"\x00" * args.chunk_bytes
  rng = np.random.default_rng(args.seed)
  noise = rng.integers(-32768, 32767, size=args.chunk_bytes // 2, dtype=np.int16).tobytes()

  engine.start_utt()
  silence_stats = measure(lambda: engine.process_raw(silence), max(args.repeat, 200), 10)
  noise_stats = measure(lambda: engine.process_raw(noise), args.repeat, 10)
  engine.end_utt()

  # One connection / utterance lifecycle: reinitialize the feature extractor and
  # open+close an utterance. This is the per-session cost added to keep a reused
  # decoder from drifting (see WakewordEngine._begin_utterance).
  def utterance_cycle() -> None:
    engine.start_utt()
    engine.end_utt()

  cycle_stats = measure(utterance_cycle, max(args.repeat * 5, 100), 5)

  pool_before = rss_mb()
  pool = WakewordPool(setting, size=args.pool_size)
  pool_started = time.perf_counter()
  leased = [pool.acquire(timeout=0) for _ in range(args.pool_size)]
  pool_create_s = time.perf_counter() - pool_started
  pool_rss_mb = rss_mb() - pool_before

  for checked_out in leased:
    pool.release(checked_out)

  def lease_cycle() -> None:
    checked_out = pool.acquire(timeout=0)
    pool.release(checked_out)

  lease_stats = measure(lease_cycle, args.repeat, 5)

  return {
    "language": args.language,
    "chunk_bytes": args.chunk_bytes,
    "engine_create_ms": round(create_s * 1e3, 4),
    "engine_rss_mb": round(created_mb, 2),
    "process_raw_silence": silence_stats,
    "process_raw_noise": noise_stats,
    "utterance_cycle_ms": round(cycle_stats["median_ms"], 4),
    "pool_size": args.pool_size,
    "pool_create_ms": round(pool_create_s * 1e3, 4),
    "pool_rss_mb": round(pool_rss_mb, 2),
    "pool_lease": lease_stats,
  }


def main() -> None:
  parser = argparse.ArgumentParser(description="Ohunerin wake-word benchmarks.")
  parser.add_argument("--language", default="fr", help="Wake-word language to benchmark.")
  parser.add_argument("--repeat", type=int, default=30, help="Timed repetitions for the noise stage.")
  parser.add_argument("--chunk-bytes", type=int, default=8000, help="Simulated client chunk size in bytes.")
  parser.add_argument("--seed", type=int, default=0, help="PRNG seed for the synthetic noise.")
  parser.add_argument("--pool-size", type=int, default=4, help="Number of per-connection decoders to pool.")
  parser.add_argument("--json", action="store_true", help="Emit the report as JSON.")
  args = parser.parse_args()

  report = run(args)

  if args.json:
    print(json.dumps(report, indent=2))
    return

  print(f"language={report['language']} chunk={report['chunk_bytes']}B")
  print(f"engine_create={report['engine_create_ms']}ms  engine_rss={report['engine_rss_mb']}MB")
  print(f"pool_size={report['pool_size']}  pool_create={report['pool_create_ms']}ms  pool_rss={report['pool_rss_mb']}MB")
  print(f"utterance_cycle={report['utterance_cycle_ms']}ms (median)")

  for stage in ("process_raw_silence", "process_raw_noise"):
    stats = report[stage]  # type: ignore[assignment]
    print(f"{stage:22s} median={stats['median_ms']:8.4f}ms  p95={stats['p95_ms']:8.4f}ms")

  lease = report["pool_lease"]  # type: ignore[assignment]
  print(f"{'pool_lease':22s} median={lease['median_ms']:8.4f}ms  p95={lease['p95_ms']:8.4f}ms")


if __name__ == "__main__":
  sys.exit(main())
