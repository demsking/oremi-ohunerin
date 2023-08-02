import datetime
from typing import Callable, Coroutine, Literal, TypedDict

from tflite_support.task import audio, core, processor

from .audio import to_ndarray
from .trace import Trace
from .wakeword import WakewordEngine


class DetectedSound(TypedDict):
  type: Literal['sound']
  sound: str
  score: float
  time: str


class Detector:
  def __init__(self, model: str, *, score_threshold: float = 0.1, num_threads: int = -1, logger: Trace):
    if (score_threshold < 0) or (score_threshold > 1.0):
      raise ValueError('Score threshold must be between (inclusive) 0 and 1.')

    self._logger = logger

    # Initialize the audio classification model.
    base_options = core.BaseOptions(
      file_name = model,
      use_coral = False,
      num_threads = num_threads,
    )

    classification_options = processor.ClassificationOptions(
      max_results = 1,
      score_threshold = score_threshold,
      category_name_allowlist = [
        'Shout',  # Cri
        'Bellows',  # Sonner
        'Children shouting',  # Cris d'enfants
        'Laughter',  # Rire
        'Baby laughter',  # Rire de bébé
        'Crying, sobbing',  # Pleurer, sangloter
        'Baby cry, infant cry',  # Cri de bébé, pleurs d'enfant
        'Whistling',  # Siffler
        'Wheeze',  # Wheeze
        'Snoring',  # Ronfler
        'Cough',  # Tousser
        'Sneeze',  # Éternuer
        'Burping',  # Roter
        'Hiccup',  # Hoqueter
      ],
    )

    self._logger.info(f'Allowlist: {", ".join(classification_options.category_name_allowlist)}')

    options = audio.AudioClassifierOptions(
      base_options = base_options,
      classification_options = classification_options,
    )

    self.classifier = audio.AudioClassifier.create_from_options(options)
    self.tensor_audio = self.classifier.create_input_tensor_audio()


class Consumer:
  def __init__(
    self,
    detector: Detector,
    *,
    logger: Trace,
    num_channels: int,
    wakeword_engine: WakewordEngine,
    on_sound_detect: Callable[[DetectedSound], Coroutine],
  ) -> None:
    self._logger = logger
    self._detector = detector
    self._wakeword_engine = wakeword_engine
    self._on_sound_detect = on_sound_detect
    self._num_channels = num_channels

    # Initialize the audio classification buffer.
    self._buffer = bytearray(15600)
    self._buffer_index = 0

  def _reset_buffer(self):
    self._buffer_index = 0

  async def _handle_input_data(self, data: bytes):
    for byte in data:
      self._buffer[self._buffer_index] = byte
      self._buffer_index += 1
      if self._buffer_index == len(self._buffer):
        await self.classify_audio(bytes(self._buffer))
        self._reset_buffer()

  async def classify_audio(self, chunk: bytes):
    audio_array = to_ndarray(chunk, self._num_channels)
    self._detector.tensor_audio.load_from_array(audio_array)
    result = self._detector.classifier.classify(self._detector.tensor_audio)

    if len(result.classifications) > 0 and len(result.classifications[0].categories) > 0:
      time = datetime.datetime.now().isoformat()
      sound = result.classifications[0].categories[0]

      self._logger.info(f'Sound {sound.category_name} detected with score {sound.score:.2f}')
      await self._on_sound_detect({
        'type': 'sound',
        'sound': sound.category_name.lower(),
        'score': sound.score,
        'time': time,
      })

  def start_utt(self) -> None:
    self._wakeword_engine.start_utt()

  def end_utt(self) -> None:
    self._wakeword_engine.end_utt()

  async def process_raw(self, chunk: bytes):
    is_wakeword = self._wakeword_engine.process_raw(chunk)

    if is_wakeword:
      await self._on_sound_detect({
        'type': 'sound',
        'sound': 'wakeword',
        'score': 1.0,
        'time': datetime.datetime.now().isoformat(),
      })

      self._reset_buffer()
    else:
      await self._handle_input_data(chunk)
