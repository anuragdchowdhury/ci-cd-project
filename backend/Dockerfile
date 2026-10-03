FROM maven:3-eclipse-temurin-24@sha256:a137a467ec89b5713d0be817b55bdba6b4d6ef16e3d05565a79bc08d8e775a1c AS build
WORKDIR /build
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp -DskipTests package

FROM eclipse-temurin:21-jre-alpine@sha256:51ab5e3302e7141ce665ca3ea85e8b5cd648eafbc3c0c90dd79d6537684e4555 AS agent
ARG AI_AGENT_VERSION=3.7.9
ARG AI_AGENT_SHA256=4ab7a442bf9defc7475d026c6b49042793ebb010c391a1db91ae07da0c04d848
RUN wget -q -O /agent.jar "https://github.com/microsoft/ApplicationInsights-Java/releases/download/${AI_AGENT_VERSION}/applicationinsights-agent-${AI_AGENT_VERSION}.jar" \
    && echo "${AI_AGENT_SHA256}  /agent.jar" | sha256sum -c -

FROM eclipse-temurin:21-jre-alpine@sha256:51ab5e3302e7141ce665ca3ea85e8b5cd648eafbc3c0c90dd79d6537684e4555
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
