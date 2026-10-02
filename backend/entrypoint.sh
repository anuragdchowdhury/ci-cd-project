#!/bin/sh
set -eu
if [ -n "${APPLICATIONINSIGHTS_CONNECTION_STRING:-}" ]; then
  exec java -javaagent:/app/applicationinsights-agent.jar -jar /app/notekeeper.jar "$@"
fi
exec java -jar /app/notekeeper.jar "$@"
