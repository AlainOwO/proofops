ARG POSTGRES_BASE=postgres:17-alpine@sha256:b0f9560a2de083e2cc7382e75f808c7381a32852a7ec49117deedb300e552b24
FROM ${POSTGRES_BASE}
# Keep the official entrypoint's root-owned volume initialization. Replace only
# its `exec gosu postgres` invocation with the equivalent su-exec UID/GID switch,
# and remove the stale Go binary entirely from the final filesystem.
RUN apk upgrade --no-cache \
    && apk add --no-cache su-exec \
    && rm /usr/local/bin/gosu \
    && sed -i 's/exec gosu postgres /exec su-exec postgres /' /usr/local/bin/docker-entrypoint.sh
