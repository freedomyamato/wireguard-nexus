#!/usr/bin/env bash
# New, dedicated Debian/Ubuntu node only. Review before running as root.
set -euo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run as root on your dedicated VPN server.'; exit 1; }
[[ $# -eq 1 && $1 =~ ^[A-Za-z0-9][A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo 'Usage: sudo bash deploy/bootstrap.sh vpn.example.com'; exit 1; }
[[ ! -e /etc/nexus/node.json && ! -e /etc/wireguard/nexus0.conf ]] || { echo 'Nexus already exists; use the documented upgrade procedure.'; exit 1; }
domain=$1
root_dir=$(cd "$(dirname "$0")/.." && pwd)
apt-get update
apt-get install -y python3 wireguard-tools nftables caddy
egress=$(ip -4 route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++)if($i=="dev"){print $(i+1);exit}}')
[[ $egress =~ ^[A-Za-z0-9_.:-]{1,15}$ ]] || { echo 'Unable to identify egress interface.'; exit 1; }
getent passwd nexus >/dev/null || useradd --system --home /var/lib/nexus --shell /usr/sbin/nologin nexus
install -d -m 0755 /opt/nexus
cp -R "$root_dir/server" /opt/nexus/server
chown -R root:root /opt/nexus/server
chmod -R go-w /opt/nexus/server
install -d -o root -g nexus -m 0750 /etc/nexus
install -d -o nexus -g nexus -m 0700 /var/lib/nexus
install -d -m 0700 /etc/wireguard
wg genkey > /etc/nexus/private.key
wg pubkey < /etc/nexus/private.key > /etc/nexus/public.key
python3 - "$domain" <<'PY'
import json, pathlib, secrets, sys
root=pathlib.Path('/etc/nexus')
public={'public_key':(root/'public.key').read_text().strip(),'endpoint':sys.argv[1]+':51821',
        'dns':['1.1.1.1','1.0.0.1'],'ipv4':'10.77.0.0/24','ipv6':'fd77:77:77::/64'}
(root/'public-node.json').write_text(json.dumps(public))
(root/'node.json').write_text(json.dumps({**public,'port':51821}))
(root/'controller.env').write_text('NEXUS_ADMIN_TOKEN='+secrets.token_urlsafe(48)+'\n')
private=(root/'private.key').read_text().strip()
(root/'nexus0.conf').write_text('[Interface]\nPrivateKey = '+private+'\nListenPort = 51821\nAddress = 10.77.0.1/24, fd77:77:77::1/64\n')
PY
chown root:nexus /etc/nexus/public-node.json
chmod 0640 /etc/nexus/public-node.json
ln -s /etc/nexus/nexus0.conf /etc/wireguard/nexus0.conf
cat > /etc/nexus/firewall.nft <<EOF
table inet nexus {
  chain input {
    type filter hook input priority 0; policy accept;
    iifname "nexus0" drop
  }
  chain forward {
    type filter hook forward priority 0; policy accept;
    iifname "nexus0" oifname "nexus0" drop
    iifname "nexus0" ip daddr { 0.0.0.0/8, 10.0.0.0/8, 100.64.0.0/10, 127.0.0.0/8, 169.254.0.0/16, 172.16.0.0/12, 192.168.0.0/16, 224.0.0.0/4 } drop
    iifname "nexus0" ip6 daddr { ::1/128, fc00::/7, fe80::/10, ff00::/8 } drop
    iifname "nexus0" oifname "$egress" accept
    iifname "nexus0" drop
    oifname "nexus0" ct state established,related accept
    oifname "nexus0" drop
  }
  chain postrouting {
    type nat hook postrouting priority srcnat; policy accept;
    ip saddr 10.77.0.0/24 oifname "$egress" masquerade
    ip6 saddr fd77:77:77::/64 oifname "$egress" masquerade
  }
}
EOF
nft --check -f /etc/nexus/firewall.nft
cat > /etc/sysctl.d/91-nexus.conf <<'EOF'
net.ipv4.ip_forward=1
net.ipv6.conf.all.forwarding=1
EOF
sysctl -p /etc/sysctl.d/91-nexus.conf
for unit in nexus-controller nexus-agent nexus-firewall; do
  install -m 0644 "$root_dir/deploy/$unit.service" "/etc/systemd/system/$unit.service"
done
install -d /etc/systemd/system/wg-quick@nexus0.service.d
cat > /etc/systemd/system/wg-quick@nexus0.service.d/nexus.conf <<'EOF'
[Unit]
Requires=nexus-firewall.service
After=nexus-firewall.service
EOF
cat > /etc/nexus/Caddyfile <<EOF
$domain {
  reverse_proxy 127.0.0.1:8787
}
EOF
# Keep existing Caddy configuration intact. The operator must add this site.
systemctl daemon-reload
systemctl enable --now nexus-firewall wg-quick@nexus0 nexus-agent nexus-controller
printf '\nNode services started. Complete HTTPS setup by importing /etc/nexus/Caddyfile into your Caddy configuration.\n'
printf 'Allow cloud-firewall TCP 80/443 and UDP 51821. Read docs/DEPLOYMENT.md for validation and administrator access.\n'
