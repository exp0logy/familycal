#!/bin/sh
# Generate a self-signed TLS cert at container start if none is present.
# Runs via nginx:alpine's /docker-entrypoint.d/ mechanism (before nginx starts).
#
# Set TLS_HOSTNAME (e.g. 192-168-1-50.sslip.io) so the cert's CN/SAN matches the
# URL you load — this is the host Google's OAuth redirect comes back to. Optionally
# set TLS_IP to add the LAN IP as a SAN. Mount a real cert at
# /etc/nginx/certs/{cert,key}.pem to override generation.
set -e

CERT_DIR=/etc/nginx/certs
mkdir -p "$CERT_DIR"

if [ -f "$CERT_DIR/cert.pem" ] && [ -f "$CERT_DIR/key.pem" ]; then
    echo "[tls] Using existing cert in $CERT_DIR"
    exit 0
fi

HOST="${TLS_HOSTNAME:-localhost}"
SAN="DNS:${HOST}"
if [ -n "${TLS_IP:-}" ]; then
    SAN="${SAN},IP:${TLS_IP}"
fi

echo "[tls] Generating self-signed cert  CN=${HOST}  SAN=${SAN}  (10y)"
openssl req -x509 -newkey rsa:2048 -nodes -days 3650 \
    -keyout "$CERT_DIR/key.pem" \
    -out "$CERT_DIR/cert.pem" \
    -subj "/CN=${HOST}" \
    -addext "subjectAltName=${SAN}" 2>/dev/null

echo "[tls] Done."
