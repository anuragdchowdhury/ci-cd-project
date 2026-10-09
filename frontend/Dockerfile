FROM node:25-alpine@sha256:bdf2cca6fe3dabd014ea60163eca3f0f7015fbd5c7ee1b0e9ccb4ced6eb02ef4 AS build
WORKDIR /build
COPY package.json package-lock.json ./
RUN npm ci
COPY index.html ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM nginxinc/nginx-unprivileged:stable-alpine@sha256:ed04ec1ff34502c339ee5c3ae3f855442398edc1d05591e2b98981dcbbd20b1e
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
