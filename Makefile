APP_NAME := $(shell python metadata.py name)
APP_VERSION := $(shell python metadata.py version)
IMAGE_NAME := demsking/$(APP_NAME)

SSL_PATH := ~/.config/oremi/ssl
SSL_CERT_FILE := $(SSL_PATH)/localhost.pem

TSLITE_FILE := ~/.cache/tensorflow/models/yamnet.tflite

.PHONY: all clean build dist image model publish-image test build/requirements.txt

# Start the development environment using tmuxinator
shell:
	tmuxinator

clean:
	rm -rf dist/ build/ models/*.tflite

$(TSLITE_FILE):
	./scripts/install-model.sh $@

model: $(TSLITE_FILE)

install: model
	pip install poetry
	poetry install

$(SSL_CERT_FILE):
	mkdir -p $(shell dirname $@)
	openssl req -x509 -nodes -new -sha256 -days 3650 -newkey rsa:2048 \
	  -subj "/C=CM/CN=localhost" \
	  -addext "subjectAltName = DNS:discovery" \
	  -keyout $(SSL_PATH)/localhost-key.pem \
	  -out $(SSL_CERT_FILE)

certificates: $(SSL_CERT_FILE)

help:
	poetry run oremi-sds -h

start-wss: model certificates
	poetry run oremi-sds \
	  --verbose \
	  --port 25023 \
	  --model $(TSLITE_FILE) \
	  --cert-file $(SSL_CERT_FILE) \
	  --key-file $(SSL_PATH)/localhost-key.pem

start-ws: model
	poetry run oremi-sds \
	  --verbose \
	  --port 15023 \
	  --model $(TSLITE_FILE)

client-wss: certificates
	python client.py \
	  --port 25023 \
	  --cert-file $(SSL_CERT_FILE)
	  --model $(TSLITE_FILE) \
	  --device-index 8

client-docker: certificates
	python client.py \
	  --port 35023 \
	  --cert-file $(SSL_CERT_FILE) \
	  --device-index 8

client-ws:
	python client.py --port 15023 \
	  --device-index 8

lint:
	pre-commit run --all-files

fix:
	ruff check . --fix

test:
	pytest

coverage:
	pytest --cov=oremi_sds

coverage-html:
	pytest --cov=oremi_sds --cov-report=html

outdated:
	poetry show --outdated

update:
	poetry update
	nix flake update
	pre-commit autoupdate

package:
	rm -rf dist/*
	poetry build --no-cache --format=wheel
	twine check dist/*

pypi: package
	twine upload -r testpypi dist/*

build/requirements.txt: pyproject.toml poetry.lock
	mkdir -p $(shell dirname $@)
	poetry export --only=main --without-hashes -f requirements.txt -o $@

image: build/requirements.txt
	docker build \
	  --progress plain . \
	  --tag $(IMAGE_NAME):$(APP_VERSION) \
	  --build-arg PACKAGE_NAME="$(APP_NAME)" \
	  --build-arg PACKAGE_VERSION="$(APP_VERSION)" \
	  --label "org.opencontainers.image.title=$(APP_NAME)" \
	  --label "org.opencontainers.image.description=$(shell python metadata.py description)" \
	  --label "org.opencontainers.image.version=$(APP_VERSION)" \
	  --label "org.opencontainers.image.revision=$(shell git rev-parse HEAD)" \
	  --label "org.opencontainers.image.authors=$(shell python metadata.py authors)" \
	  --label "org.opencontainers.image.created=$(shell date --rfc-3339=seconds)" \
	  --label "org.opencontainers.image.source=$(shell python metadata.py repository)" \
	  --label "org.opencontainers.image.url=$(shell python metadata.py repository)" \
	  --label "org.opencontainers.image.documentation=$(shell python metadata.py documentation)" \
	  --label "org.opencontainers.image.vendor=Oremi" \
	  --label "org.opencontainers.image.licenses=$(shell python metadata.py license)"
	docker tag $(IMAGE_NAME):$(APP_VERSION) $(IMAGE_NAME):latest

publish: image
	git commit pyproject.toml -m "Release $(APP_VERSION)"
	git tag v$(APP_VERSION)
	docker push $(IMAGE_NAME):$(APP_VERSION)
	docker push $(IMAGE_NAME):latest
	git push --tags origin main
