import Foundation

enum AppDefaults {
    static let defaultBaseURL = "https://workoutbot-ybbz.onrender.com"

    enum Key {
        static let baseURL = "settings.baseURL"
        static let userID = "settings.userID"
        static let appToken = "settings.appToken"
    }
}

struct AppConfiguration: Equatable, Hashable {
    var baseURL: String
    var userIDText: String
    var appToken: String

    var userID: Int? {
        Int(userIDText.trimmingCharacters(in: .whitespacesAndNewlines))
    }

    var normalizedBaseURL: String {
        baseURL.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var trimmedToken: String {
        appToken.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    var isValid: Bool {
        !normalizedBaseURL.isEmpty && userID != nil
    }
}

