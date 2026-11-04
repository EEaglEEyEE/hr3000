#!/usr/bin/env bash
# Einmalig als root auf einem frischen Ubuntu-24.04-Server ausführen:
#   bash bootstrap_server.sh
# Installiert Docker (Ubuntu-Pakete), aktiviert Firewall (nur 22/80/443),
# automatische Sicherheitsupdates und erzeugt einen Read-only-Deploy-Key
# für das private GitHub-Repo.
set -euo pipefail

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git ufw fail2ban unattended-upgrades
systemctl enable --now docker fail2ban

# SSH nur per Key (Scanner probieren permanent Passwörter). "00-" damit es vor
# cloud-init-Drop-ins greift (sshd: erste gesetzte Option gewinnt).
cat > /etc/ssh/sshd_config.d/00-hardening.conf <<'SSHEOF'
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
SSHEOF
sshd -t && systemctl reload ssh

ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable

if [ ! -f /root/.ssh/hr3000_deploy ]; then
  mkdir -p /root/.ssh && chmod 700 /root/.ssh
  ssh-keygen -t ed25519 -N "" -C "hr3000-deploy@$(hostname)" -f /root/.ssh/hr3000_deploy
  printf 'Host github.com\n  IdentityFile /root/.ssh/hr3000_deploy\n  IdentitiesOnly yes\n' >> /root/.ssh/config
  chmod 600 /root/.ssh/config
fi

echo
echo "Fertig. Diesen öffentlichen Schlüssel als READ-ONLY Deploy-Key im GitHub-Repo hinterlegen:"
cat /root/.ssh/hr3000_deploy.pub
echo
echo "Danach: git clone git@github.com:<owner>/HR3000.git /opt/hr3000 && cd /opt/hr3000 && bash scripts/deploy.sh"
