FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginx:1.30.5-alpine@sha256:0985e772fb9f729e6fa0980da05fca5d9c468e870eed43071545afa9d2e27d94
COPY nginx.conf /etc/nginx/nginx.conf
COPY --chown=nginx:nginx docker-entrypoint.sh /usr/local/bin/pitomo-web-entrypoint
COPY --from=build --chown=nginx:nginx /app/dist /usr/share/nginx/html
USER 101:101
EXPOSE 8080
ENTRYPOINT ["/bin/sh", "/usr/local/bin/pitomo-web-entrypoint"]
CMD ["nginx", "-g", "daemon off;"]
