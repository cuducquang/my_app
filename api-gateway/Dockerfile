FROM golang:1.24-alpine AS build

WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/api-gateway ./cmd/api-gateway

FROM alpine:latest

WORKDIR /
COPY --from=build /out/api-gateway /api-gateway

RUN apk --no-cache add curl

EXPOSE 8080

ENTRYPOINT ["/api-gateway"]


