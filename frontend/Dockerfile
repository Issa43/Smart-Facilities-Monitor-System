FROM node:22-alpine AS build

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --fetch-timeout=600000 --fetch-retry-mintimeout=20000 --fetch-retry-maxtimeout=120000
COPY . .
ARG VITE_API_BASE_URL=/api/v1
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL
# Browser-side URL for the detector MJPEG feed, so it names the host
# rather than the 'detector' container. Vite inlines it at build time.
ARG VITE_CAMERA_STREAM_URL=http://localhost:8090/stream
ENV VITE_CAMERA_STREAM_URL=$VITE_CAMERA_STREAM_URL
# Each detector runs in its own container on its own port, so the dashboard
# needs one URL per model.
ARG VITE_INTRUSION_STREAM_URL=http://localhost:8091/stream
ENV VITE_INTRUSION_STREAM_URL=$VITE_INTRUSION_STREAM_URL
ARG VITE_ANPR_STREAM_URL=http://localhost:8092/stream
ENV VITE_ANPR_STREAM_URL=$VITE_ANPR_STREAM_URL
RUN npm run build

FROM nginx:1.27-alpine
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD wget -q -O /dev/null http://127.0.0.1:8080/healthz || exit 1

