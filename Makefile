APP_VERSION := $(shell python oremi-sds/version.py)
SRC_FILES := $(wildcard *.json *.toml *.lock oremi-sds/*.py models/*/*)
TSLITE_FILE := ~/.cache/tensorflow/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite

.PHONY: all clean build image prepare publish-image test

# Start the development environment using tmuxinator
env:
	tmuxinator

clean:
	rm -rf dist/ models/*.tflite

$(TSLITE_FILE):
	mkdir -p $(shell dirname $@)
	curl \
	  -L 'https://storage.googleapis.com/download.tensorflow.org/models/tflite/task_library/audio_classification/rpi/lite-model_yamnet_classification_tflite_1.tflite' \
	  -o $@

prepare: $(TSLITE_FILE)
	mkdir -p dist

install: prepare
	poetry install

build: dist/oremi-sds

start: $(TSLITE_FILE)
	python -m oremi-sds --verbose --host 0.0.0.0 --model $<

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
	nix flake update
	pre-commit autoupdate

dist: $(SRC_FILES)
	rm -rf dist/*
	poetry build
	twine check dist/*

publish: dist
	twine upload dist/*

build/oremi-sds-base.tar.gz: base.nix
	nix-build --out-link $@ $<
	docker load < $@

build/oremi-sds-image.tar.gz: image.nix
	nix-build --out-link $@ $<
	docker load < $@

# image: publish
image:
	docker build . --progress plain --build-arg VERSION=$(APP_VERSION) -t demsking/oremi-sds:$(APP_VERSION)

# image: build/oremi-sds-image.tar.gz
# 	docker build . --progress plain --build-arg VERSION=$(APP_VERSION) -t demsking/oremi-sds:$(APP_VERSION)
# 	docker build . --build-arg VERSION=$(APP_VERSION) -t demsking/oremi-sds:latest

publish-image: image
	docker publish demsking/oremi-sds:$(APP_VERSION)
	docker publish demsking/oremi-sds:latest
