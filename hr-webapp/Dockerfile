# Feste Node-Version: reproduzierbare Builds, Test-Abhängigkeiten (jsdom) brauchen >= 22.22.2.
FROM node:22.23.3-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
# Schlägt ein Test fehl, bricht der Build ab – das Deployment läuft dann nicht weiter.
RUN npm test
RUN npm run build

FROM nginx:1.27-alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
