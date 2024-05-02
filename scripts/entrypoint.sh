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

MODEL_FILENAME=/var/oremi/models/yamnet.tflite
CURRENT_DIR=$(dirname $0)

$CURRENT_DIR/install-model.sh $MODEL_FILENAME || exit 1

PYTHONPATH=/oremi:$PYTHONPATH python -m \
  ohunerin \
    --host 0.0.0.0 \
    --port 5023 \
    --threshold $THRESHOLD \
    --config /oremi/config.json \
    --model $MODEL_FILENAME \
    $@ \
  &

# Check if SERVICE_URI variable is explicitly defined
if [ -n "$SERVICE_URI" ]; then
  if [ -z "$MACHINE_ID" ]; then
    export MACHINE_ID=$(cat /proc/sys/kernel/random/uuid)
  fi

  oremi-discovery \
    --mqtt-host $MQTT_HOST \
    --mqtt-port $MQTT_PORT \
    --client-id "$CLIENT_ID/$MACHINE_ID" \
    --discovery-channel "$DISCOVERY_CHANNEL" \
    --service-name "$SERVICE_NAME" \
    --service-version $SERVICE_VERSION \
    --service-uri $SERVICE_URI \
  &
fi

# Wait for all background processes to finish
wait
