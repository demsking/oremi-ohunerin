SRC_FILES := $(wildcard *.json *.toml oremi-sds/*.py)

.PHONY: all clean build-images publish-images test

# Start the development environment using tmuxinator
env:
	tmuxinator

clean:
	rm -rf dist/ models/*.tflite

models/lite-model_yamnet_classification_tflite_1.tflite:
	mkdir -p models/
	curl \
		-L 'https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite' \
		-o $@

install: models/lite-model_yamnet_classification_tflite_1.tflite
	poetry install

start: models/lite-model_yamnet_classification_tflite_1.tflite
	python -m oremi-sds --verbose --model $<

client:
	python client.py

lint:
	pre-commit run --all-files

fix:
	ruff check . --fix

test:
	pytest

update-snapshots:
	pytest --snapshot-update

coverage:
	pytest --cov=oremi

coverage-html:
	pytest --cov=oremi --cov-report=html

outdated:
	poetry show --outdated

update:
	poetry update
	pre-commit autoupdate

dist: $(SRC_FILES)
	rm -rf dist/
	poetry build
	twine check dist/*

publish: dist
	twine upload -r testpypi dist/*
