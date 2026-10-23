#!/bin/bash
# sshd runs with -f /config/sshd/sshd_config; /etc/ssh/sshd_config is only the template.
for cfg in /config/sshd/sshd_config /etc/ssh/sshd_config; do
    [ -f "$cfg" ] || continue
    # Enable TCP forwarding for SSH tunnel tests. The image ships "AllowTcpForwarding no",
    # and the openssh-server-ssh-tunnel mod is downloaded at startup, so it silently
    # does nothing when lscr.io can't be reached.
    sed -i 's/^AllowTcpForwarding no/AllowTcpForwarding yes/' "$cfg"
    grep -q '^AllowTcpForwarding yes' "$cfg" || echo "AllowTcpForwarding yes" >> "$cfg"
    # Increase MaxStartups and MaxSessions for testing
    grep -q '^MaxStartups 100:30:200' "$cfg" || echo "MaxStartups 100:30:200" >> "$cfg"
    grep -q '^MaxSessions 100' "$cfg" || echo "MaxSessions 100" >> "$cfg"
done
# Reload sshd to pick up the changes if it is already running
pkill -HUP sshd 2>/dev/null || true
