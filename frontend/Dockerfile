FROM node:24-alpine@sha256:ebfe2f90462722a7a4de65e91990e97fe0d401c70e0e762c5b53302f905ec1c1 AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:15c994d10d6d78658721c3bcafff14cb281fba2a4bdf9d5ba92c416a472516e3
# Patch PCRE2 in the reviewed Nginx base; Alpine verifies repository signatures.
USER 0
ARG PCRE2_VERSION=10.49-r0
RUN apk add --no-cache --upgrade "pcre2=${PCRE2_VERSION}"
USER 101:101

COPY nginx.conf /etc/nginx/nginx.conf
COPY --from=build /build/dist /usr/share/nginx/html
ARG VCS_REF=local
ARG SOURCE_REPOSITORY=https://github.com/anuragdchowdhury/ci-cd-project
LABEL org.opencontainers.image.revision=$VCS_REF
LABEL org.opencontainers.image.source=$SOURCE_REPOSITORY
USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx", "-g", "daemon off;"]
