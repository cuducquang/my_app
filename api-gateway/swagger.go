package main

// getSwaggerUIHTML returns the Swagger UI HTML page
func getSwaggerUIHTML() string {
	return `<!DOCTYPE html>
<html>
<head>
    <title>API Documentation - MLOps Platform</title>
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui.css" />
    <style>
        html { box-sizing: border-box; overflow: -moz-scrollbars-vertical; overflow-y: scroll; }
        *, *:before, *:after { box-sizing: inherit; }
        body { margin:0; background: #fafafa; }
    </style>
</head>
<body>
    <div id="swagger-ui"></div>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-bundle.js"></script>
    <script src="https://unpkg.com/swagger-ui-dist@5.9.0/swagger-ui-standalone-preset.js"></script>
    <script>
        window.onload = function() {
            fetch('/api-docs/aggregate')
                .then(res => res.json())
                .then(data => {
                    const urls = data.services
                        .filter(s => s.spec || s.url)
                        .map((s, idx) => ({
                            url: s.url || '/openapi.json',
                            name: s.name || 'Service ' + (idx + 1)
                        }));
                    if (urls.length === 0) {
                        urls.push({ url: '/openapi.json', name: 'API Gateway' });
                    }
                    window.ui = SwaggerUIBundle({
                        urls: urls,
                        dom_id: '#swagger-ui',
                        deepLinking: true,
                        presets: [
                            SwaggerUIBundle.presets.apis,
                            SwaggerUIStandalonePreset
                        ],
                        plugins: [
                            SwaggerUIBundle.plugins.DownloadUrl
                        ],
                        layout: "StandaloneLayout"
                    });
                })
                .catch(err => {
                    console.error('Failed to load specs:', err);
                    window.ui = SwaggerUIBundle({
                        url: '/openapi.json',
                        dom_id: '#swagger-ui',
                        deepLinking: true,
                        presets: [
                            SwaggerUIBundle.presets.apis,
                            SwaggerUIStandalonePreset
                        ],
                        layout: "StandaloneLayout"
                    });
                });
        };
    </script>
</body>
</html>`
}
