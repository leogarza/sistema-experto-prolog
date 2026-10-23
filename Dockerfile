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
ENV PORT=8080
EXPOSE 8080
CMD ["/app/server"]
