{{- define "notekeeper.db-env" -}}
- name: SPRING_PROFILES_ACTIVE
  value: azure
- name: DB_URL
  value: {{ printf "jdbc:postgresql://%s:5432/%s" (required "postgresFqdn is required" .Values.postgresFqdn) (required "database is required" .Values.database) | quote }}
- name: APP_ENVIRONMENT
  value: dev
{{- end -}}
{{- define "notekeeper.security" -}}
allowPrivilegeEscalation: false
readOnlyRootFilesystem: true
capabilities:
  drop: [ALL]
{{- end -}}
