FROM golang:1.22-alpine AS build

WORKDIR /src

COPY go.mod ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags="-s -w" -o /out/api-gateway .

FROM gcr.io/distroless/static:nonroot

WORKDIR /
COPY --from=build /out/api-gateway /api-gateway

EXPOSE 8080
USER nonroot:nonroot

ENTRYPOINT ["/api-gateway"]


