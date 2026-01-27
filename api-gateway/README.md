## api-gateway (Go)

### Env

- **PORT**: port của gateway (default `8080`)
- **EUREKA_SERVER_URL**: Eureka base URL (default `http://localhost:8761/eureka`)
- **APP_NAME**: tên app đăng ký Eureka (default `API-GATEWAY`)
- **INSTANCE_ID**: instanceId (default auto)
- **FLASK_APP_NAME**: tên app của Flask trong Eureka (default `FLASK-SERVICE`)
- **FLASK_BASE_URL**: fallback URL nếu Flask chưa đăng ký Eureka (vd `http://localhost:5000` hoặc trong k8s `http://flask-service`)
- **REQUEST_TIMEOUT**: (default `10s`)

### Run local

```bash
cd api-gateway
go run .
```

### Endpoints

- `GET /health`
- `GET /flask` → proxy sang Flask `GET /`
- `POST /flask/test-infrastructure` → proxy sang Flask `POST /test-infrastructure`


