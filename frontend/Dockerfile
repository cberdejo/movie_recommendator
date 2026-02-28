# Build stage
FROM node:22-alpine AS builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci

COPY frontend/ .

# Backend URLs: browser uses these (from host). Override with build-args in production.
ARG VITE_API_BASE=http://localhost:8000/api/v1
ARG VITE_WS_URL=ws://localhost:8000/api/v1/ws/movies
ENV VITE_API_BASE=$VITE_API_BASE
ENV VITE_WS_URL=$VITE_WS_URL

RUN npm run build

# Runtime: serve static files with nginx
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html
COPY frontend/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
