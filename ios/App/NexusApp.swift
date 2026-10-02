import SwiftUI

@main struct NexusApp: App {
    var body: some Scene { WindowGroup { NexusView() } }
}

struct NexusView: View {
    @AppStorage("noticeAccepted") private var accepted = false
    @StateObject private var tunnel = TunnelManager()
    @State private var server = ""
    @State private var token = ""
    @State private var name = "My iPhone"
    @State private var confirmForget = false
    var body: some View {
        NavigationView {
            Form {
                if !accepted {
                    Section("Before using Nexus") {
                        Text("Nexus routes traffic through your selected server. Its operator can see connection metadata and unencrypted traffic. Local VPN keys remain in this phone's Keychain. Enrollment sends your device name and public key to your server, which stores them with enrollment and revocation times. Nexus includes no advertising or analytics SDK. This beta does not guarantee a kill switch. Choose a server operator you trust.")
                        Button("Accept and continue") { accepted = true }
                    }
                } else {
                    Section("Connection") {
                        Text(tunnel.message)
                        Button(tunnel.connected ? "Disconnect" : "Connect") {
                            if tunnel.connected { tunnel.disconnect() }
                            else { tunnel.run { try await tunnel.connect() } }
                        }.disabled(tunnel.busy)
                    }
                    Section("Enrollment") {
                        TextField("https://vpn.example.com", text: $server).textInputAutocapitalization(.never).autocorrectionDisabled().keyboardType(.URL)
                        SecureField("Invitation token", text: $token)
                        TextField("Device name", text: $name)
                        Button("Enroll this phone") {
                            tunnel.run {
                                try Enrollment.begin(server: server, token: token, name: name)
                                token = ""
                                tunnel.message = try await Enrollment.finish() ? "Enrolled. Ready to connect." : "Node update pending. Finish enrollment shortly."
                            }
                        }.disabled(tunnel.busy || tunnel.connected)
                        Button("Finish pending enrollment") {
                            tunnel.run { tunnel.message = try await Enrollment.finish() ? "Ready to connect." : "Node update pending." }
                        }.disabled(tunnel.busy || tunnel.connected)
                        Button("Forget local keys", role: .destructive) { confirmForget = true }
                            .disabled(tunnel.busy || tunnel.connected)
                    }
                    Section { Text("Private beta · one server · no automatic region switching or subscription billing.") }
                }
            }.navigationTitle("WireGuard Nexus")
        }.confirmationDialog("Delete local keys? Revoke the device on the server separately.", isPresented: $confirmForget) {
            Button("Delete local keys", role: .destructive) { tunnel.run { try await tunnel.forget() } }
        }
    }
}
