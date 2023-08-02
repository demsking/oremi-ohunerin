#!/bin/sh

set +e

MODEL_FILENAME=/var/oremi-sds/lite-model-yamnet.tflite

if [ ! -e "$MODEL_FILENAME" ]; then
  curl \
		-L 'https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite' \
		-o $MODEL_FILENAME
fi

oremi-sds \
    --host :: \
    --port 5023 \
    --threshold $THRESHOLD \
    --num-threads $NUM_THREADS \
    --model $MODEL_FILENAME
