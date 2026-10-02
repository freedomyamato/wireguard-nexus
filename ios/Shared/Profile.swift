import Foundation
import WireGuardKit

struct RemoteProfile: Codable {
    var addresses: [String]
    var server_public_key: String
    var endpoint: String
    var dns: [String]
    var allowed_ips: [String]
    var keepalive: UInt16
}

struct EnrollmentState: Codable {
    var server: String
    var token: String?
    var name: String
    var privateKey: String
    var publicKey: String
    var deviceSecret: String
    var id: String?
    var profile: RemoteProfile?

    func configuration() throws -> TunnelConfiguration {
        guard let remote = profile, let privateKey = PrivateKey(base64Key: privateKey),
              let publicKey = PublicKey(base64Key: remote.server_public_key),
              let endpoint = Endpoint(from: remote.endpoint),
              Set(remote.allowed_ips) == Set(["0.0.0.0/0", "::/0"]),
              remote.addresses.count == 2, !remote.dns.isEmpty, remote.dns.count <= 8 else {
            throw NexusFailure.invalidProfile
        }
        var interface = InterfaceConfiguration(privateKey: privateKey)
        for address in remote.addresses {
            guard let parsed = IPAddressRange(from: address) else { throw NexusFailure.invalidProfile }
            interface.addresses.append(parsed)
        }
        for address in remote.dns {
            guard let parsed = DNSServer(from: address) else { throw NexusFailure.invalidProfile }
            interface.dns.append(parsed)
        }
        var peer = PeerConfiguration(publicKey: publicKey)
        peer.endpoint = endpoint; peer.persistentKeepAlive = 25
        peer.allowedIPs = [IPAddressRange(from: "0.0.0.0/0")!, IPAddressRange(from: "::/0")!]
        return TunnelConfiguration(name: "Nexus", interface: interface, peers: [peer])
    }
}
