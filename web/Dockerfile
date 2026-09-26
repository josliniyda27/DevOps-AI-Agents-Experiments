# The website: build the frontend to static files, then serve them with Caddy, which also proxies /api to the API,
# asks for a password, and gets an HTTPS certificate automatically when SITE_ADDRESS is a domain name.
FROM node:22-slim AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# proxy.ts (login + API secret) is for Node hosting such as Vercel; a static export has no server, and Caddy does that job here.
RUN rm -f proxy.ts
ENV STATIC_EXPORT=1 NEXT_TELEMETRY_DISABLED=1
RUN npm run build            # writes the static site to ./out

FROM caddy:2-alpine
COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /web/out /srv
