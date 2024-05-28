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
	poetry install
	git apply sounddevice.py.patch

$(SSL_CERT_FILE):
	mkdir -p $(shell dirname $@)
	openssl req -x509 -nodes -new -sha256 -days 3650 -newkey rsa:2048 \
	  -subj "/C=CM/CN=localhost" \
	  -addext "subjectAltName = DNS:discovery" \
	  -keyout $(SSL_PATH)/localhost-key.pem \
	  -out $(SSL_CERT_FILE)

certificates: $(SSL_CERT_FILE)

help:
	poetry run oremi-ohunerin -h

start-wss: model certificates
	LOG_LEVEL=debug \
	poetry run oremi-ohunerin \
	  --port 25023 \
	  --model $(TSLITE_FILE) \
	  --cert-file $(SSL_CERT_FILE) \
	  --key-file $(SSL_PATH)/localhost-key.pem

start-ws: model
	LOG_LEVEL=debug \
	poetry run oremi-ohunerin \
	  --port 15023 \
	  --model $(TSLITE_FILE)

client-wss: certificates
	python client.py \
	  --port 25023 \
	  --cert-file $(SSL_CERT_FILE)
	  --model $(TSLITE_FILE)

client-docker: certificates
	python client.py \
	  --port 35023 \
	  --cert-file $(SSL_CERT_FILE)

client-ws:
	python client.py --port 15023

lint:
	pre-commit run --all-files

fix:
	ruff check . --fix

test:
	pytest

coverage:
	pytest --cov=ohunerin

coverage-html:
	pytest --cov=ohunerin --cov-report=html

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

#
## Packaging
build/requirements.txt: pyproject.toml poetry.lock
	mkdir -p build/
	poetry export --only=main --without-hashes -f requirements.txt -o $@

build/context:
	docker buildx create --name $(APP_NAME) --bootstrap
	mkdir -p build/
	touch $@

image: build/requirements.txt build/context
	docker buildx use $(APP_NAME)
	docker buildx build . \
	  --platform linux/amd64 \
	  --push \
	  --progress plain \
	  --tag $(IMAGE_NAME):$(APP_VERSION) \
	  --tag $(IMAGE_NAME):latest \
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

# 	git commit pyproject.toml -m "Release $(APP_VERSION)"
publish: image
	git tag v$(APP_VERSION)
	git push --tags origin main
