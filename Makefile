APP_NAME := $(shell python metadata.py name)
APP_VERSION := $(shell python metadata.py version)
IMAGE_NAME := demsking/$(APP_NAME)

SSL_PATH := ~/.config/oremi/ssl
SSL_CERT_FILE := $(SSL_PATH)/localhost.pem

TSLITE_FILE := ~/.cache/tensorflow/models/yamnet.tflite

.PHONY: all clean build dist image model publish-image test build/requirements.txt

# Start the development environment using tmuxinator
env:
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

start-wss: model certificates
	poetry run oremi-sds \
	  --verbose \
	  --port 25023 \
	  --model $(TSLITE_FILE) \
	  --cert-file $(SSL_CERT_FILE) \
	  --key-file $(SSL_PATH)/localhost-key.pem \
	  --mqtt-host test.mosquitto.org

start-ws: model
	poetry run oremi-sds \
	  --verbose \
	  --port 15023 \
	  --model $(TSLITE_FILE) \
	  --mqtt-host test.mosquitto.org

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

publish-package: package
	twine upload -r testpypi dist/*

build/requirements.txt:
	mkdir -p $(shell dirname $@)
	poetry export --only=main --without-hashes -f requirements.txt -o $@

image: build/requirements.txt
	docker build \
	  --progress plain . -t $(IMAGE_NAME):$(APP_VERSION) \
	  --build-arg PACKAGE_NAME="$(APP_NAME)" \
	  --build-arg CREATED_DATE="$(shell date --rfc-3339=seconds)" \
	  --build-arg MAINTAINER="$(shell python metadata.py authors)" \
	  --build-arg DESCRIPTION="$(shell python metadata.py description)" \
	  --build-arg VERSION="$(APP_VERSION)" \
	  --build-arg REVISION="$(shell git rev-parse HEAD)" \
	  --build-arg SOURCE_URL="$(shell python metadata.py repository)" \
	  --build-arg VENDOR="Oremi" \
	  --build-arg LICENSE="$(shell python metadata.py license)"
	docker tag $(IMAGE_NAME):$(APP_VERSION) $(IMAGE_NAME):latest

publish-image: image
	git commit pyproject.toml -m "Release $(APP_VERSION)"
	git tag v$(APP_VERSION)
	docker push $(IMAGE_NAME):$(APP_VERSION)
	docker push $(IMAGE_NAME):latest
	git push --tags origin main
