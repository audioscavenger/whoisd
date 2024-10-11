FROM python:3-alpine
LABEL maintainer="AudioscavengeR <dev@derewonko.com>"

RUN adduser -h /app -g app -D app

WORKDIR /app

COPY requirements.txt /app

RUN apk add --no-cache bash postgresql-libs \
  && apk add --no-cache --virtual .builddeps build-base postgresql-dev \
  && pip install -r requirements.txt \
  && apk del --no-cache .builddeps

# exclusions in .dockerignore
COPY . /app
RUN chown -R app:app /app
USER app

RUN mkdir -p downloads

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["--help"]
