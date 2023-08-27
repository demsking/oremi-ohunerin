#!/bin/bash

# Copyright 2023 Sébastien Demanou. All Rights Reserved.
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

set +e

APP_NAME="oremi-sds"
MODEL_DIR="$1"  # Models directory passed as argument
MODEL_NAME="yamnet.tflite"
MODEL_PATH="$MODEL_DIR/$MODEL_NAME"
MODEL_URL="https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite"

log_info() {
  echo -e "\e[32m$(date +'%Y-%m-%d %H:%M:%S') \e[37m- \e[34m$APP_NAME \e[37m- \e[90mINFO \e[37m- $1\e[0m"
}

log_error() {
  echo -e "\e[32m$(date +'%Y-%m-%d %H:%M:%S') \e[37m- \e[34m$APP_NAME \e[37m- \e[31mERROR \e[37m- $1\e[0m" >&2
  exit 1
}

install_model() {
  if [ ! -f "$MODEL_PATH" ]; then
    log_info "Downloading and installing model $MODEL_URL..."
    mkdir -p "$MODEL_DIR"
    if curl -sL "$MODEL_URL" -o "$MODEL_PATH"; then
      log_info "Model $MODEL_PATH installed successfully."
    else
      log_error "Failed to download and install $MODEL_URL"
    fi
  else
    log_info "Model $MODEL_PATH already installed. Skipping..."
  fi
}

# Check if MODEL_DIR argument is provided
if [ -z "$MODEL_DIR" ]; then
  log_error "MODEL_DIR argument not provided."
fi

# Call the install function
install_model
