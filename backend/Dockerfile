FROM maven:3.9.12-eclipse-temurin-21@sha256:c3c9d3ac4ce8431a3995c0318b8d390f448e693dd4fabc16e9b68d2e1f3d7b46 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:25-jre-alpine@sha256:3c0a9084927a221ccd1d007fcaf614465672c0af37aaa834c5184483afe56d61 AS agent
ARG AI_AGENT_VERSION=3.7.9
ARG AI_AGENT_SHA256=4ab7a442bf9defc7475d026c6b49042793ebb010c391a1db91ae07da0c04d848
RUN wget -q -O /agent.jar "https://github.com/microsoft/ApplicationInsights-Java/releases/download/${AI_AGENT_VERSION}/applicationinsights-agent-${AI_AGENT_VERSION}.jar" \
    && echo "${AI_AGENT_SHA256}  /agent.jar" | sha256sum -c -

FROM eclipse-temurin:25-jre-alpine@sha256:3c0a9084927a221ccd1d007fcaf614465672c0af37aaa834c5184483afe56d61
RUN apk add --no-cache ca-certificates && addgroup -S -g 10001 app && adduser -S -D -H -u 10001 -G app app
WORKDIR /app
COPY --from=build /build/target/notekeeper.jar /app/notekeeper.jar
COPY --from=agent /agent.jar /app/applicationinsights-agent.jar
COPY telemetry/applicationinsights.json /app/applicationinsights.json
COPY --chmod=0555 entrypoint.sh /app/entrypoint.sh
ENV APPLICATIONINSIGHTS_CONFIGURATION_FILE=/app/applicationinsights.json
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp"
ARG VCS_REF=local
ARG SOURCE_REPOSITORY=https://github.com/anuragdchowdhury/ci-cd-project
LABEL org.opencontainers.image.revision=$VCS_REF
LABEL org.opencontainers.image.source=$SOURCE_REPOSITORY
USER 10001:10001
EXPOSE 8080 9090
ENTRYPOINT ["/app/entrypoint.sh"]
