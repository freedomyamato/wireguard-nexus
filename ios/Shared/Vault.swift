import Foundation
import Security

enum NexusFailure: Error { case invalidProfile, keychain, server, revoked, invalidOrigin }

enum Vault {
    private static var group: String { Bundle.main.object(forInfoDictionaryKey: "NexusKeychainGroup") as! String }
    private static var query: [String: Any] {
        [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: "Nexus",
         kSecAttrAccount as String: "enrollment", kSecAttrAccessGroup as String: group]
    }
    static func load() throws -> Data? {
        var request = query; request[kSecReturnData as String] = true
        request[kSecMatchLimit as String] = kSecMatchLimitOne
        var output: CFTypeRef?
        let status = SecItemCopyMatching(request as CFDictionary, &output)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = output as? Data else { throw NexusFailure.keychain }
        return data
    }
    static func save(_ data: Data) throws {
        let attributes: [String: Any] = [kSecValueData as String: data]
        var status = SecItemUpdate(query as CFDictionary, attributes as CFDictionary)
        if status == errSecItemNotFound {
            var request = query; request[kSecValueData as String] = data
            request[kSecAttrAccessible as String] = kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly
            status = SecItemAdd(request as CFDictionary, nil)
        }
        guard status == errSecSuccess else { throw NexusFailure.keychain }
    }
    static func reference() throws -> Data {
        var request = query; request[kSecReturnPersistentRef as String] = true
        var output: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &output) == errSecSuccess,
              let data = output as? Data else { throw NexusFailure.keychain }
        return data
    }
    static func load(reference: Data) throws -> Data {
        let request: [String: Any] = [kSecValuePersistentRef as String: reference,
                                     kSecReturnData as String: true]
        var output: CFTypeRef?
        guard SecItemCopyMatching(request as CFDictionary, &output) == errSecSuccess,
              let data = output as? Data else { throw NexusFailure.keychain }
        return data
    }
    static func clear() throws {
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else { throw NexusFailure.keychain }
    }
}
