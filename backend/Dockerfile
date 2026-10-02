# Release images will also have their base image digests recorded/pinned in Phase 2.
FROM maven:3.9.12-eclipse-temurin-21 AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre-alpine AS agent
ARG AI_AGENT_VERSION=3.7.9
RUN wget -q -O /agent.jar "https://github.com/microsoft/ApplicationInsights-Java/releases/download/${AI_AGENT_VERSION}/applicationinsights-agent-${AI_AGENT_VERSION}.jar"

FROM eclipse-temurin:21-jre-alpine
RUN apk add --no-cache ca-certificates && addgroup -S -g 10001 app && adduser -S -D -H -u 10001 -G app app
WORKDIR /app
COPY --from=build /build/target/notekeeper.jar /app/notekeeper.jar
COPY --from=agent /agent.jar /app/applicationinsights-agent.jar
COPY telemetry/applicationinsights.json /app/applicationinsights.json
COPY --chmod=0555 entrypoint.sh /app/entrypoint.sh
ENV APPLICATIONINSIGHTS_CONFIGURATION_FILE=/app/applicationinsights.json
ENV JAVA_TOOL_OPTIONS="-XX:MaxRAMPercentage=65 -XX:+ExitOnOutOfMemoryError -Djava.io.tmpdir=/tmp"
ARG VCS_REF=local
LABEL org.opencontainers.image.revision=$VCS_REF
USER 10001:10001
EXPOSE 8080 9090
ENTRYPOINT ["/app/entrypoint.sh"]
