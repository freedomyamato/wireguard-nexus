# Deploy the private beta

This is a source development package, not a compiled or publicly available VPN.
Use an invited beta on a dedicated Debian/Ubuntu VPS. Do not install over an
existing managed gateway. The bootstrap creates a separate `nexus0` interface;
it does not adopt the original installer's `wg0` or existing peers.

## 1. Prepare the operator's server

You need a public server with administrative access, a domain pointing to its
public IP, and a cloud firewall allowing TCP 80/443 and UDP 51821. Confirm your
provider supports WireGuard/UDP and outbound traffic. You pay its hosting and
bandwidth costs; this package does not provision paid infrastructure.

Transfer this directory privately to the server. Review `deploy/bootstrap.sh`,
then run from the extracted package:

```bash
sudo bash deploy/bootstrap.sh vpn.example.com
```

This installs OS packages, creates a non-login `nexus` service account, generates
the node's WireGuard key, enables forwarding, and starts the controller, agent
and dedicated firewall table. It does not overwrite Caddy's existing sites.

Add this line to `/etc/caddy/Caddyfile`, outside an existing site block:

```caddyfile
import /etc/nexus/Caddyfile
```

Then validate and reload:

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
sudo systemctl status nexus-controller nexus-agent wg-quick@nexus0
```

Your domain must resolve and certificate issuance must succeed. Existing host
firewalls may need rules permitting TCP 80/443, UDP 51821 and forwarding. An
accept rule in Nexus's table cannot override another table's drop rule. Validate
your existing rules deliberately; never flush the host firewall.

For IPv6 internet access the provider must supply working IPv6 routing. On
providers using router advertisements, forwarding may require `accept_ra=2` on
the egress interface; check the provider's instructions. This package sends both
default routes into the VPN, so absent server IPv6 connectivity should fail
closed for IPv6 while IPv4 may remain usable. This needs phone testing.

## 2. Confirm control-plane/node synchronization

Open `https://vpn.example.com/health`. Expect:

```json
{"controller":"up","node_synced_recently":true}
```

This proves the controller recently applied its desired peer list and checked
the node public key. It does not prove outbound internet access or phone handshakes.

If false, inspect service status and permissions. The controller uses the local
Unix socket `/run/nexus/agent.sock`. It has no root shell or direct access to
the node private key. Reconciliation repeats every five seconds after failures.

## 3. Get the administrator token

On your trusted server terminal:

```bash
sudo cat /etc/nexus/controller.env
```

Copy only the value after `NEXUS_ADMIN_TOKEN=` into the HTTPS administration
page. This is a powerful secret. Do not paste it into chat, commit it, or share
it with phone users. The dashboard retains it only in page memory. Use Clear
token when finished. Passkey authentication is not included in this beta.

## 4. Invite and enroll a phone

1. Click Create invitation in the administration page.
2. Privately send the HTTPS server origin and invitation token to the intended tester.
3. On Nexus Android/iPhone, accept the data notice, enter those values and a
   device name, and tap Enroll this phone.
4. The phone generates its private key locally. Only its public key, name,
   invitation and independent device-management credential leave the phone.
5. The controller allocates an IPv4 and IPv6 address. The agent adds the public
   key to the real Linux interface and acknowledges persistence.
6. The phone waits for applied state. If delayed, tap Finish pending enrollment.
7. Tap Connect and accept the OS VPN permission prompt.

Do not distribute the administration token to users. Invitations expire in ten
minutes and redeem for one device. Repeating the identical request with the
same locally saved public key/credential is allowed while the invitation is
valid, so a lost HTTP response does not create a second device.

## 5. Verify the tunnel before inviting more people

- Check a real handshake with `sudo wg show nexus0` and exchange traffic.
- Verify the phone's public IPv4/IPv6, DNS resolver, Wi-Fi/mobile handover and sleep behavior.
- Test a denied VPN-consent prompt and a server whose UDP port is blocked.
- Revoke the device on the administration page. Verify `desired=revoked`, then
  `applied=revoked`, and confirm the peer is removed from `wg show nexus0`.
- Confirm the revoked phone cannot pass packets. The local interface may still
  appear active; local tunnel state does not prove server acceptance.
- Reboot the server and verify the persisted peer list, firewall and controller.

Nexus's firewall isolates peers from one another and denies direct traffic to
private/link-local destination ranges and the VPN host. This beta offers internet
egress only. It does not provide LAN access or per-device policies.

## Upgrade and recovery

The bootstrap intentionally refuses an existing Nexus installation. For a code
upgrade, back up `/var/lib/nexus` and `/etc/nexus` using an encrypted backup
destination, stop the controller/agent, replace only `/opt/nexus/server` from a
reviewed package, and restart the services. This version has one SQLite schema;
there is no automated schema migration tool.

The database stores public keys, device metadata and hashed invitation/device
credentials. `/etc/nexus/private.key` and the WireGuard config are root-only
plaintext files, matching normal WireGuard operation. Use host disk encryption
and encrypted backups if needed. Do not claim every server secret is encrypted
at rest. Audit events are append-only through this API, not cryptographically
immutable against a server administrator.

A failed live update attempts to restore the previous kernel and persistent
configuration. Recovery after a process crash relies on the persisted config
and the controller's repeated reconciliation, not a distributed transaction.
Never interpret pending revocation as confirmed access removal.
