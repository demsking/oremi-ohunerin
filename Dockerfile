FROM alpine:3.17

ARG VERSION

LABEL Author="Sébastien Demanou <demsking@gmail.com>"
LABEL Repository="https://gitlab.com/demsking/oremi-sds"

ENV THRESHOLD=0.2
ENV NUM_THREADS=-1

RUN apk add --no-cache --upgrade python3 py3-pip \
  && pip3 install --upgrade pip \
  && rm -rf /var/cache/apk/*

RUN addgroup -S oremi \
  && adduser -S oremi -u 1000 -G oremi \
  && mkdir /var/oremi-sds \
  && chown -R oremi:oremi /var/oremi-sds

RUN pip install --index-url https://test.pypi.org/simple Oremi-SDS==$VERSION

COPY image/entrypoint.sh /var/oremi-sds/entrypoint.sh

USER oremi

EXPOSE 5023

ENTRYPOINT ["/var/oremi/entrypoint.sh"]
