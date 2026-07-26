FROM node:20-slim AS build
WORKDIR /app
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ .
RUN npm run build

FROM nginx:alpine

# Default: proxy to backend service (Railway sets BACKEND_URL via env)
ENV BACKEND_URL=http://backend.railway.internal:8000
ENV PORT=80

COPY --from=build /app/dist /usr/share/nginx/html
COPY web/nginx.conf /etc/nginx/templates/default.conf.template

# Railway nginx template — uses $BACKEND_URL for proxy_pass
# nginx:alpine image supports envsubst on files in /etc/nginx/templates/
EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
