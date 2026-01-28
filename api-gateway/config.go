package main

import (
	"fmt"
	"net"
	"os"
	"strings"
	"time"
)

// Config holds application configuration
type Config struct {
	Port            string
	EurekaServerURL string
	AppName         string
	InstanceID      string
	PreferIP        bool

	// Flask discovery
	FlaskAppName  string
	FlaskBaseURL  string // fallback if Eureka has no instances
	RequestTimout time.Duration
}

func getenv(key, def string) string {
	v := strings.TrimSpace(os.Getenv(key))
	if v == "" {
		return def
	}
	return v
}

func localIP() string {
	// Prefer POD_IP from k8s downward API, then HOSTNAME, then auto-detect
	if podIP := strings.TrimSpace(os.Getenv("POD_IP")); podIP != "" {
		return podIP
	}
	if hostname := strings.TrimSpace(os.Getenv("HOSTNAME")); hostname != "" {
		// In k8s, HOSTNAME is often the pod name, but try to resolve it
		if ip := net.ParseIP(hostname); ip != nil {
			return ip.String()
		}
	}
	// Best-effort: pick first non-loopback IPv4.
	ifaces, err := net.Interfaces()
	if err != nil {
		return "127.0.0.1"
	}
	for _, iface := range ifaces {
		if iface.Flags&net.FlagUp == 0 || iface.Flags&net.FlagLoopback != 0 {
			continue
		}
		addrs, _ := iface.Addrs()
		for _, a := range addrs {
			var ip net.IP
			switch v := a.(type) {
			case *net.IPNet:
				ip = v.IP
			case *net.IPAddr:
				ip = v.IP
			}
			if ip == nil {
				continue
			}
			ip = ip.To4()
			if ip == nil {
				continue
			}
			return ip.String()
		}
	}
	return "127.0.0.1"
}

func mustParseDuration(s string, def time.Duration) time.Duration {
	s = strings.TrimSpace(s)
	if s == "" {
		return def
	}
	d, err := time.ParseDuration(s)
	if err != nil {
		return def
	}
	return d
}

func loadConfig() Config {
	port := getenv("PORT", "8080")
	appName := getenv("APP_NAME", "API-GATEWAY")
	ip := localIP()
	instanceID := getenv("INSTANCE_ID", fmt.Sprintf("%s:%s:%s", strings.ToLower(appName), ip, port))

	return Config{
		Port:            port,
		EurekaServerURL: strings.TrimRight(getenv("EUREKA_SERVER_URL", "http://localhost:8761/eureka"), "/"),
		AppName:         appName,
		InstanceID:      instanceID,
		PreferIP:        strings.ToLower(getenv("PREFER_IP", "true")) == "true",
		FlaskAppName:    getenv("FLASK_APP_NAME", "FLASK-SERVICE"),
		FlaskBaseURL:    strings.TrimRight(getenv("FLASK_BASE_URL", ""), "/"),
		RequestTimout:   mustParseDuration(getenv("REQUEST_TIMEOUT", "10s"), 10*time.Second),
	}
}
