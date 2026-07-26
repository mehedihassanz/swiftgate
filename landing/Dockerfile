FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine

# Railway injects PORT — nginx must listen on it
ENV PORT=80

COPY --from=build /app/dist /usr/share/nginx/html

# Create nginx server config that listens on $PORT (envsubst at startup)
RUN echo 'server { listen ${PORT}; root /usr/share/nginx/html; index index.html; location / { try_files $uri $uri/ /index.html; } }' \
    > /etc/nginx/templates/default.conf.template

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
