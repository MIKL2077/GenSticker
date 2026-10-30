#!/bin/sh
set -eu
# Keep the six-hour collector, but put the owner's human-review policy last in
# the ingest environment. No provider credentials or other services are edited.
install -d -m 0755 /etc/systemd/system/gensticker-ingest.service.d
umask 077
cat > /etc/gensticker-human-review.env <<'EOF'
GENSTICKER_MINIMAX_ENABLED=0
EOF
cat > /etc/systemd/system/gensticker-ingest.service.d/90-human-template-review.conf <<'EOF'
[Service]
EnvironmentFile=/etc/gensticker-human-review.env
EOF
chmod 0644 /etc/systemd/system/gensticker-ingest.service.d/90-human-template-review.conf
systemctl daemon-reload
