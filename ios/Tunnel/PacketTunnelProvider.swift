import Foundation
import NetworkExtension
import WireGuardKit

final class PacketTunnelProvider: NEPacketTunnelProvider {
    private lazy var adapter = WireGuardAdapter(with: self) { _, _ in
        // Do not emit runtime configurations, key material or endpoint details into logs.
    }
    override func startTunnel(options: [String: NSObject]?, completionHandler: @escaping (Error?) -> Void) {
        do {
            guard let config = protocolConfiguration as? NETunnelProviderProtocol,
                  let reference = config.passwordReference else { throw NexusFailure.invalidProfile }
            let state = try JSONDecoder().decode(EnrollmentState.self, from: Vault.load(reference: reference))
            adapter.start(tunnelConfiguration: try state.configuration()) { error in
                completionHandler(error == nil ? nil : NexusFailure.server)
            }
        } catch { completionHandler(NexusFailure.invalidProfile) }
    }
    override func stopTunnel(with reason: NEProviderStopReason, completionHandler: @escaping () -> Void) {
        adapter.stop { _ in completionHandler() }
    }
}
