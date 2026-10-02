import Foundation
import Combine
import NetworkExtension

@MainActor final class TunnelManager: ObservableObject {
    @Published var message = "Enroll this phone with your Nexus server."
    @Published var busy = false
    @Published var connected = false
    private var manager: NETunnelProviderManager?
    private var observer: NSObjectProtocol?

    init() {
        observer = NotificationCenter.default.addObserver(forName: .NEVPNStatusDidChange, object: nil, queue: .main) { [weak self] _ in
            Task { @MainActor [weak self] in self?.refresh() }
        }
        Task { try? await load(); refresh() }
    }
    private func load() async throws {
        let managers = try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<[NETunnelProviderManager], Error>) in
            NETunnelProviderManager.loadAllFromPreferences { managers, error in
                if let error = error { continuation.resume(throwing: error) }
                else { continuation.resume(returning: managers ?? []) }
            }
        }
        let bundle = Bundle.main.bundleIdentifier! + ".tunnel"
        manager = managers.first { ($0.protocolConfiguration as? NETunnelProviderProtocol)?.providerBundleIdentifier == bundle }
    }
    func refresh() {
        connected = manager?.connection.status == .connected
        switch manager?.connection.status {
        case .connected: message = "Tunnel active. Verify server reachability, public IP and DNS."
        case .connecting: message = "Connecting…"
        case .disconnecting: message = "Disconnecting…"
        case .disconnected: message = "Disconnected"
        default: break
        }
    }
    func run(_ operation: @escaping () async throws -> Void) {
        guard !busy else { return }; busy = true
        Task {
            defer { busy = false }
            do { try await operation() }
            catch { message = "Operation failed. Check server, invitation, provisioning or VPN settings." }
        }
    }
    func connect() async throws {
        guard let saved = try Vault.load() else { throw NexusFailure.invalidProfile }
        let state = try JSONDecoder().decode(EnrollmentState.self, from: saved)
        _ = try state.configuration()
        try await load()
        let manager = self.manager ?? NETunnelProviderManager()
        let config = NETunnelProviderProtocol()
        config.providerBundleIdentifier = Bundle.main.bundleIdentifier! + ".tunnel"
        config.serverAddress = state.profile!.endpoint
        config.passwordReference = try Vault.reference()
        manager.protocolConfiguration = config; manager.localizedDescription = "WireGuard Nexus"; manager.isEnabled = true
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            manager.saveToPreferences { error in if let error = error { c.resume(throwing: error) } else { c.resume() } }
        }
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            manager.loadFromPreferences { error in if let error = error { c.resume(throwing: error) } else { c.resume() } }
        }
        self.manager = manager
        guard let session = manager.connection as? NETunnelProviderSession else { throw NexusFailure.invalidProfile }
        try session.startTunnel(); refresh()
    }
    func disconnect() { manager?.connection.stopVPNTunnel() }
    func forget() async throws {
        try await load()
        guard manager?.connection.status != .connected, manager?.connection.status != .connecting else {
            throw NexusFailure.invalidProfile
        }
        if let manager = manager {
            try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
                manager.removeFromPreferences { error in if let error = error { c.resume(throwing: error) } else { c.resume() } }
            }
        }
        try Vault.clear(); manager = nil; message = "Local keys deleted. Revoke this device on the server separately."
    }
}
