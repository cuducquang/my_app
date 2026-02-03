FROM node:20-alpine

WORKDIR /app

COPY package.json package-lock.json* ./
RUN npm install --omit=dev

COPY server.js ./

EXPOSE 8000

ENV PORT=8000
ENV CHROME_MCP_ARGS="--headless=true --isolated=true"

CMD ["npm", "start"]

