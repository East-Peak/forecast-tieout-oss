FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci --production=false
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app

COPY engine/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/ ./engine/
COPY schema/ ./schema/

COPY --from=frontend-build /app/frontend/dist ./frontend/dist

RUN apt-get update && apt-get install -y --no-install-recommends nginx cron && rm -rf /var/lib/apt/lists/*

COPY docker/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8080
CMD ["/entrypoint.sh"]
