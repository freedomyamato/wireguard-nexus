import Foundation
import Security
import WireGuardKit

final class NoRedirects: NSObject, URLSessionTaskDelegate {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) { completionHandler(nil) }
}

enum Enrollment {
    struct Device: Decodable {
        var id: String; var desired: String; var applied: String; var profile: RemoteProfile?
    }
    static func origin(_ value: String) throws -> String {
        guard let url = URLComponents(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              url.scheme == "https", url.host != nil, url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, url.path == "" || url.path == "/",
              var clean = URLComponents(string: value.trimmingCharacters(in: .whitespacesAndNewlines)) else { throw NexusFailure.invalidOrigin }
        clean.path = ""
        guard let result = clean.string else { throw NexusFailure.invalidOrigin }
        return result
    }
    static func begin(server: String, token: String, name: String) throws {
        guard try Vault.load() == nil, (32...128).contains(token.count), !name.isEmpty, name.count <= 64 else {
            throw NexusFailure.invalidProfile
        }
        let pair = PrivateKey()
        var bytes = [UInt8](repeating: 0, count: 32)
        guard SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes) == errSecSuccess else { throw NexusFailure.keychain }
        let credential = Data(bytes).base64EncodedString().replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "")
        let state = EnrollmentState(server: try origin(server), token: token, name: name,
            privateKey: pair.base64Key, publicKey: pair.publicKey.base64Key, deviceSecret: credential)
        try Vault.save(JSONEncoder().encode(state))
    }
    static func request(server: String, path: String, token: String? = nil, body: [String: String]? = nil) async throws -> Device {
        guard let url = URL(string: try origin(server) + path) else { throw NexusFailure.invalidOrigin }
        var request = URLRequest(url: url); request.timeoutInterval = 12
        if let token = token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let body = body {
            request.httpMethod = "POST"; request.httpBody = try JSONEncoder().encode(body)
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        }
        let config = URLSessionConfiguration.ephemeral; config.urlCache = nil
        let session = URLSession(configuration: config, delegate: NoRedirects(), delegateQueue: nil)
        defer { session.finishTasksAndInvalidate() }
        let (data, response) = try await session.data(for: request)
        guard let response = response as? HTTPURLResponse, [200,202].contains(response.statusCode), data.count <= 16384 else {
            throw NexusFailure.server
        }
        return try JSONDecoder().decode(Device.self, from: data)
    }
    static func finish() async throws -> Bool {
        guard let saved = try Vault.load() else { throw NexusFailure.invalidProfile }
        var state = try JSONDecoder().decode(EnrollmentState.self, from: saved)
        if state.id == nil {
            guard let token = state.token else { throw NexusFailure.invalidProfile }
            let device = try await request(server: state.server, path: "/v1/enroll", body: [
                "token": token, "public_key": state.publicKey, "device_secret": state.deviceSecret, "name": state.name])
            state.id = device.id; state.token = nil
            try Vault.save(JSONEncoder().encode(state))
        }
        for attempt in 0..<10 {
            let device = try await request(server: state.server, path: "/v1/devices/\(state.id!)", token: state.deviceSecret)
            guard device.desired == "active" else { throw NexusFailure.revoked }
            if device.applied == "active", let profile = device.profile {
                state.profile = profile; _ = try state.configuration()
                try Vault.save(JSONEncoder().encode(state)); return true
            }
            if attempt < 9 { try await Task.sleep(nanoseconds: 1_500_000_000) }
        }
        return false
    }
}
