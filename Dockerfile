# --- build ---
FROM golang:1.27.2 AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /app/server .

# --- image ---
FROM debian:bookworm-slim
RUN apt-get update \
 && apt-get install -y --no-install-recommends swi-prolog-nox \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /app/server /app/server
COPY src/ /app/src/
# sin esto debian corre en locale C y swipl lee hechos.pl como ascii:
# la ñ y los acentos se vuelven U+FFFD (los "cuadritos" en la interfaz)
ENV LANG=C.UTF-8 \
    LC_ALL=C.UTF-8
ENV PORT=8080
EXPOSE 8080
CMD ["/app/server"]
